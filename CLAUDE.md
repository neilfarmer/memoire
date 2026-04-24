# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Style

- No emojis in any code, UI, or output.

## Commits

Always use Conventional Commits: `type(scope): description`

Types: `feat`, `fix`, `chore`, `refactor`, `test`, `ci`, `docs`, `build`

Scope is optional but encouraged for larger repos (e.g. `feat(notes)`, `fix(auth)`). Breaking changes append `!` after the type: `feat!: ...`

## Pre-commit checks (MANDATORY)

Before every `git commit` that touches code, Claude MUST run these locally and
confirm they all pass. No exceptions — CI enforces the same gates and a failure
after push wastes a round-trip.

1. `make lint` — ruff + djlint + `terraform fmt -check`.
2. `make test-unit` — pytest with **`--cov-fail-under=80`**. Running
   `pytest --no-cov` is insufficient; it will not catch coverage drops and the
   CI job *will* fail even when every test passes locally.
3. `make security` — bandit + pip-audit, when Python dependencies or imports
   change.
4. `make test-terraform` — when anything under `terraform/` changes.

If any of the above fails, **fix it before committing**. Common failure modes:

- **Coverage drop below 80%**: new assistant tool handlers, watcher branches,
  and `lambda/home/` code are the usual suspects because they are hard to
  exercise indirectly. Add unit tests that call the new handler through
  `tools.handle_tool(...)` (see `tests/unit/test_assistant.py`) rather than
  relying on coverage from other modules.
- **Ruff E702 / E701 / F401**: don't chain statements with `;` or leave unused
  imports. E402 and E701 are globally ignored in `ruff.toml`; everything else
  fails CI.
- **djlint on `frontend/index.html`**: run `make lint` — the file is huge and
  djlint catches unclosed tags and indentation issues that are easy to miss.

If `make test-unit` is impractical in the current environment (e.g. network
sandboxing, missing deps), say so explicitly in the commit message and flag it
to the user rather than committing blind.

## Commands

Use `make` targets for all operations. Do not run raw shell commands directly — propose a new make target and get approval before adding one.

**Available targets:**
```bash
make test              # run all tests (unit + terraform)
make test-unit         # run unit tests with coverage (pytest tests/unit/, 80% minimum)
make test-terraform    # run Terraform tests (plan-only, no remote state)
make coverage          # unit tests with HTML coverage report -> htmlcov/index.html
make lint              # ruff check lambda/ tests/ + djlint frontend/ + terraform fmt -check
make security          # bandit (SAST) + pip-audit (CVE scan)
make deploy            # terraform apply (interactive, sources .env)
make deploy-auto       # terraform apply -auto-approve + CloudFront invalidation
make invalidate        # invalidate CloudFront cache only
make destroy           # terraform destroy
```

**Run a single unit test** (exception to the make-only rule -- `make test-unit` does not support targeting individual tests):
```bash
python -m pytest tests/unit/test_tasks.py -v
python -m pytest tests/unit/test_tasks.py::TestValidateFields::test_valid_status -v
```

**Run integration tests manually** (requires a PAT from the deployed stack):
```bash
TEST_PAT=pat_... python tests/test_api.py
TEST_PAT=pat_... python tests/test_api.py --suite tasks
```

## Architecture

Serverless, multi-tenant personal productivity app (tasks, notes, habits, journal, goals, health, nutrition, finances, bookmarks, feeds, diagrams, favorites, settings).

```
API Gateway (HTTP API, Lambda authorizer)
  +-- Lambda functions (per feature)
  |     +-- DynamoDB (user_id PK + feature_id SK)
  |     +-- S3 (note attachments/images)
  +-- Lambda authorizer (JWT + PAT dual auth)

S3 + CloudFront -> frontend/index.html + config.js (injected at deploy)
Cognito (or external OIDC) -> JWT tokens
EventBridge -> watcher Lambda (hourly scheduled)
Bedrock -> assistant Lambda (AI chat)
```

**Request flow**: Cognito (or OIDC) authenticates -> Lambda authorizer validates JWT or PAT -> Lambda extracts `user_id` from `event["requestContext"]["authorizer"]["lambda"]` -> all DynamoDB ops scoped to that `user_id`.

### Lambda Structure

Each CRUD feature follows this 3-layer pattern:
- `lambda/{feature}/handler.py` -- entry point, extracts auth + body, delegates to router
- `lambda/{feature}/router.py` -- dispatches by HTTP method + path
- `lambda/{feature}/crud.py` -- DynamoDB CRUD with validation

**Shared layer** (`lambda/layer/python/`, available at `/opt/python` in Lambda):
- `auth.py` -- `get_user_id()` extracts user_id from JWT or Lambda authorizer context
- `db.py` -- DynamoDB helpers: `get_table()`, `query_by_user()`, `get_item()`, `delete_item()`
- `response.py` -- HTTP response helpers: `ok()`, `created()`, `error()`, `not_found()`, `forbidden()`, `server_error()` with Decimal->JSON serialization
- `utils.py` -- `now_iso()`, `validate_date()`, `parse_tags()`, `build_update_expression()`
- `links_util.py` -- wiki-link parsing and the `links` table sync/query helpers (`parse_wiki_links`, `sync_links`, `delete_source_links`, `query_outbound`, `query_inbound`); no-op when `LINKS_TABLE` is unset

### Standard CRUD Lambdas

These follow the handler/router/crud pattern:

| Lambda | Tables | Notes |
|--------|--------|-------|
| `tasks` | tasks, task_folders | Includes `folders.py`; auto-creates "Inbox" folder |
| `notes` | notes, note_folders | Complex: `note_crud.py`, `folders.py`, `image_crud.py`, `attachment_crud.py`; S3 for images/attachments |
| `habits` | habits, habit_logs_v2 | habit_logs (v1) is deprecated |
| `journal` | journal | One entry per user per day (entry_date SK) |
| `goals` | goals | |
| `health` | health | Daily metrics (log_date SK) |
| `nutrition` | nutrition | Daily logs (log_date SK) |
| `finances` | debts, income, fixed_expenses | 3 tables; summary calculations, decimal validation |
| `feeds` | feeds, feeds_read | RSS parsing, concurrent article fetching, caching |
| `bookmarks` | bookmarks | Tags/metadata support |
| `diagrams` | diagrams | JSON elements and state |
| `favorites` | favorites | |
| `settings` | settings | No sort key (user_id PK only) |
| `tokens` | tokens | PAT management; rejects PAT-authenticated requests (JWT only) |
| `links` | links | Read-only endpoints (`GET /links`, `GET /backlinks`) for the wiki-link graph. Writers (notes/journal/tasks) keep the table in sync via `lambda/layer/python/links_util.py` during create/update/delete. |

### Special-Purpose Lambdas

These do not follow the standard CRUD pattern:

- `lambda/auth/` -- OAuth2 proxy for Cognito; handles `/auth/callback`, `/auth/refresh`, `/auth/logout`; sets HttpOnly cookies; uses stdlib only (no external packages)
- `lambda/authorizer/` -- Lambda REQUEST authorizer; validates both Cognito JWTs (RS256 pure-Python verification, JWKS caching with 1h TTL) and PATs (SHA-256 hash lookup via DynamoDB GSI); no shared layer
- `lambda/assistant/` -- Bedrock-backed AI assistant; `chat.py` (multi-turn with tool calling, max 6 iterations), `tools.py` (38KB, tool specs for all features), `memory.py` (conversation history + user facts), `analysis.py` (AI profile analysis), `token_auth.py`; reads 10 DynamoDB tables for context; 60s timeout, 256MB memory
- `lambda/watcher/` -- EventBridge-scheduled hourly; ntfy push notifications for tasks/habits with deduplication; Bedrock fact extraction for user profile inference; monolithic `handler.py` (489 lines)
- `lambda/export/` -- Generates ZIP of all user data as Markdown with YAML frontmatter; reads 11 tables + S3 attachments
- `lambda/home/` -- Admin dashboard; `costs.py` (Lambda execution costs from CloudWatch), `stats.py` (system-wide metrics: DynamoDB counts, S3 storage, Bedrock token usage with pricing); gated by `ADMIN_USER_IDS` env var

### Frontend

Vanilla JS SPA (`frontend/index.html`, 451KB). Reads `window.MEMOIRE_CONFIG` from `config.js`, which Terraform generates and uploads to S3 with API URL + Cognito IDs. No build step. Also includes `openapi.yaml.tpl` (templated with live API URL) and `docs.html`.

## DynamoDB Patterns

All tables use on-demand billing and point-in-time recovery (PITR). Terraform tests enforce PITR on every table. All queries scoped by `user_id` partition key.

| Table | PK | SK | GSI |
|-------|----|----|-----|
| tasks | user_id | task_id | -- |
| task_folders | user_id | folder_id | -- |
| notes | user_id | note_id | -- |
| note_folders | user_id | folder_id | -- |
| habits | user_id | habit_id | -- |
| habit_logs | habit_id | log_date | -- (deprecated, replaced by habit_logs_v2) |
| habit_logs_v2 | user_id | log_id | -- (SK format: `{habit_id}#{YYYY-MM-DD}`) |
| journal | user_id | entry_date | -- |
| goals | user_id | goal_id | -- |
| health | user_id | log_date | -- |
| nutrition | user_id | log_date | -- |
| settings | user_id | -- (no SK) | -- |
| tokens | user_id | token_id | **token-hash-index** (KEYS_ONLY, used by authorizer for PAT lookup) |
| assistant_conversations | user_id | msg_id | -- (messages carry `conversation_id`; thread metadata stored as `msg_id = __meta__#<id>`; message TTL configurable via settings.chat_retention_days, default 30d, 0=forever) |
| assistant_memory | user_id | memory_key | -- |
| favorites | user_id | favorite_id | -- |
| feeds | user_id | feed_id | -- |
| feeds_read | user_id | article_url | -- |
| debts | user_id | debt_id | -- |
| income | user_id | income_id | -- |
| fixed_expenses | user_id | expense_id | -- |
| diagrams | user_id | diagram_id | -- |
| bookmarks | user_id | bookmark_id | -- |
| links | user_id | link_key (`{source_type}#{source_id}#{target_type}#{target_id}`) | **reverse-index** (user_id, target_key) — used by `GET /backlinks` |

Utility functions in `lambda/layer/python/db.py`:
- `get_table(name)` -> resource
- `query_by_user(table, user_id)` -> all items for user
- `get_item(table, user_id, sk_name, sk_value)` -> single item
- `delete_item(table, user_id, sk_name, sk_value)`

## Testing Strategy

**Unit tests** (`tests/unit/`, 18 test files): Use `moto` to mock AWS and `freezegun` for time. Coverage minimum: 80% (enforced by `make test-unit`).

`conftest.py` handles module loading: `load_lambda(feature, filename)` registers each Lambda module under a unique `sys.modules` alias (`_lambda_{feature}_{stem}`) to prevent collisions across features with identically-named files (crud.py, router.py, etc.). It also pre-registers shared layer modules (db.py, response.py, utils.py) and sets fake AWS credentials before any boto3 imports.

**Terraform tests** (`terraform/tests/`, 3 files):
- `dynamodb.tftest.hcl` -- validates all tables have PITR enabled
- `lambda.tftest.hcl` -- enforces consistent runtime and log retention
- `security.tftest.hcl` -- S3 encryption, public access blocks, CloudFront OAC + HTTPS, API throttling

**Integration tests** (`tests/test_api.py`): Run manually against the live deployed stack. Pass `TEST_PAT` as an env var (see usage above). These catch IAM permission gaps, schema mismatches, and env var wiring that unit tests cannot.

## CI/CD

GitHub Actions workflows in `.github/workflows/`:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci.yml` | push + PR | Python 3.12 unit tests, 80% coverage, Codecov upload |
| `lint.yml` | push + PR | Code linting (ruff, djlint) |
| `security.yml` | push + PR | Bandit SAST + pip-audit CVE scan |
| `terraform-lint.yml` | push + PR | tflint with provider init |
| `terraform-test.yml` | push + PR | `terraform test` (all 3 test files) |
| `release.yml` | -- | Release automation (release-please) |
| `renovate.yml` | -- | Dependency updates (grouped by category) |

## MCP Server

A standalone MCP (Model Context Protocol) server lives in `mcp/` with its own `pyproject.toml`. Entry point: `memoire-mcp = "memoire_mcp.server:main"`.

- Single file: `mcp/memoire_mcp/server.py` (42KB) using FastMCP
- Exposes tools for all features (tasks, notes, journal, goals, habits, health, nutrition, diagrams, bookmarks, favorites, feeds, finances, settings, assistant, home/admin, export, tokens)
- Authenticates via Personal Access Token (PAT) environment variable
- Configured in Claude Code via `.claude/settings.json`
- Dependencies: `mcp[cli]>=1.0.0`, `httpx>=0.27.0`

## Adding a New Feature

1. Create `lambda/{feature}/handler.py`, `router.py`, `crud.py` matching the tasks pattern
2. Add DynamoDB table(s) in `terraform/dynamodb.tf` (must have PITR enabled -- Terraform tests enforce this)
3. Add Lambda function in `terraform/lambda_{feature}.tf` (Terraform auto-generates the zip via `archive_file` in `main.tf`)
4. Add IAM inline policy in `terraform/iam.tf` scoped to the new table(s)
5. Add API routes in `terraform/api_gateway.tf`
6. Add unit tests in `tests/unit/test_{feature}.py` using `conftest.load_lambda()` pattern
7. Add MCP tools in `mcp/memoire_mcp/server.py` if the feature should be exposed via MCP
8. If the assistant should interact with the feature, add tool specs in `lambda/assistant/tools.py`
9. If the export should include the feature, update `lambda/export/exporter.py`
10. `terraform apply`

## Terraform Layout

All infrastructure in `terraform/`. Key files:

- `main.tf` -- provider, `archive_file` data sources for all Lambda zips, layer definition
- `variables.tf` -- 30+ variables (region, environment, domain, auth provider, Lambda settings, budget thresholds)
- `outputs.tf` -- API URL, Cognito IDs, frontend URL, S3 bucket, CloudFront distribution ID
- `api_gateway.tf` -- HTTP API with CORS, Lambda authorizer, rate throttling (50 req/s, 100 burst)
- `dynamodb.tf` -- all 23 DynamoDB tables
- `iam.tf` -- shared Lambda assume role policy
- `s3_frontend.tf` -- private S3 bucket, CloudFront with OAC, CSP/HSTS headers, lifecycle rules (attachments: 90d->IA, 365d->Glacier; exports: 1d auto-expire), config.js + openapi.yaml injection
- `cognito.tf` -- optional Cognito user pool (conditionally created based on auth provider)
- `lambda_auth.tf` -- OAuth callback/refresh/logout (unauthenticated routes)
- `lambda_authorizer.tf` -- custom JWT + PAT validator
- `lambda_{feature}.tf` -- one file per feature (IAM role + policy + function + log group + DynamoDB perms + API Gateway routes)
- `monitoring.tf` -- SNS alerts, CloudWatch alarms for auth failures (>20 in 5min) and JWT rejections
- `budget.tf` -- AWS Budgets with multi-threshold notifications
- `dns.tf`, `dns_aws.tf`, `dns_cloudflare.tf` -- optional custom domain with ACM cert (supports Route 53 or Cloudflare)

## Environment Variables

Terraform deploy targets (`make deploy`, `make deploy-auto`) source `.env` automatically. See `.env.example`:
- `API_URL` -- from `terraform output api_url`
- `COGNITO_CLIENT_ID`, `COGNITO_USER_POOL_ID` -- from `terraform output`
- `AWS_REGION`

Lambda environment variables are set by Terraform per function. Notable ones:
- All CRUD lambdas: `{FEATURE}_TABLE` (table name injected by Terraform)
- `authorizer`: `TOKENS_TABLE`, `JWKS_URI`, `JWT_ISSUER`, `JWT_AUDIENCE`
- `auth`: `AUTH_DOMAIN`, `COGNITO_CLIENT_ID`
- `assistant`: `ASSISTANT_MODEL_ID`, `AWS_REGION`, plus table names for all features it reads
- `watcher`: table names for tasks, settings, habits, habit_logs, journal, goals, notes, memory; `INFERENCE_MODEL_ID`
- `home`: `FUNCTION_PREFIX`, `ASSISTANT_FUNCTION_NAME`, `ASSISTANT_MODEL_ID`, `ADMIN_USER_IDS`

## Project Configuration

- `pyproject.toml` -- pytest, coverage, bandit, djlint configs
- `ruff.toml` -- ignores E402 (module-level import order, needed for test sys.path manipulation) and E701 (multiple statements on one line)
- `pytest.ini` -- test path `tests/unit`, patterns `test_*.py` / `Test*` / `test_*`
- `requirements-test.txt` -- all dev/test dependencies (pytest, moto, freezegun, bandit, ruff, pip-audit, boto3, etc.)
- `renovate.json` -- weekly dependency updates (Monday before 9am), grouped by category (GitHub Actions, Terraform, Python test, Python runtime)
- `release-please-config.json` + `.release-please-manifest.json` -- automated release management
