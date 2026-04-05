# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Style

- No emojis in any code, UI, or output.

## Commits

Always use Conventional Commits: `type(scope): description`

Types: `feat`, `fix`, `chore`, `refactor`, `test`, `ci`, `docs`, `build`

Scope is optional but encouraged for larger repos (e.g. `feat(notes)`, `fix(auth)`). Breaking changes append `!` after the type: `feat!: ...`

## Commands

Use `make` targets for all operations. Do not run raw shell commands directly — propose a new make target and get approval before adding one.

**Available targets:**
```bash
make test-unit         # run unit tests with coverage (pytest tests/unit/)
make test-terraform    # run Terraform tests
make test-all          # test-unit + test-terraform
make coverage          # unit tests with HTML coverage report → htmlcov/index.html
make lint              # ruff check lambda/ tests/
make security          # bandit (SAST) + pip-audit (CVE scan)
make test              # integration tests against live API (requires TEST_PAT in .env)
make deploy            # terraform apply (interactive)
make deploy-auto       # terraform apply -auto-approve + CloudFront invalidation
make invalidate        # invalidate CloudFront cache only
make destroy           # terraform destroy
```

**Run a single unit test** (exception to the make-only rule — `make test-unit` does not support targeting individual tests):
```bash
python -m pytest tests/unit/test_tasks.py -v
python -m pytest tests/unit/test_tasks.py::TestValidateFields::test_valid_status -v
```

```bash
make lint          # ruff check lambda/ tests/
```

**First-time test user setup:**
```bash
source .env && python tests/test_api.py --create-user
```

## Architecture

Serverless, multi-tenant personal productivity app (tasks, notes, habits).

```
API Gateway (HTTP API, JWT auth)
  └── Lambda functions (per feature)
        └── DynamoDB (user_id PK + feature_id SK)

S3 + CloudFront → frontend/index.html + config.js (injected at deploy)
Cognito → JWT tokens, validated by API Gateway before Lambda invocation
```

**Request flow**: Cognito authenticates → API Gateway validates JWT → Lambda extracts `user_id` from `event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]` → all DynamoDB ops scoped to that `user_id`.

**Lambda structure** (each feature follows this pattern):
- `lambda/{feature}/handler.py` — entry point, extracts auth + body, delegates to router
- `lambda/{feature}/router.py` — dispatches by HTTP method + path
- `lambda/{feature}/crud.py` — DynamoDB CRUD with validation
- `lambda/layer/python/db.py` — shared DynamoDB client helpers (imported via layer)
- `lambda/layer/python/response.py` — shared HTTP response helpers
- `lambda/layer/python/auth.py` — `get_user_id()` extracts user_id from JWT or Lambda authorizer context (supports both Cognito JWT and PAT)

**Special-purpose Lambdas** (do not follow the standard CRUD pattern):
- `lambda/assistant/` — Bedrock-backed AI assistant; chat.py, tools.py, memory.py
- `lambda/watcher/` — EventBridge-scheduled (hourly); ntfy push notifications for tasks/habits with deduplication
- `lambda/export/` — generates a ZIP of all user data as Markdown files
- `lambda/authorizer/` — Lambda JWT authorizer for API Gateway
- `lambda/tokens/` — PAT (Personal Access Token) management

**Frontend**: Vanilla JS SPA (`frontend/index.html`). Reads `window.MEMOIRE_CONFIG` from `config.js`, which Terraform generates and uploads to S3 with API URL + Cognito IDs. No build step.

## DynamoDB Patterns

All tables use `user_id` (String) as partition key and `{feature}_id` (String) as sort key. On-demand billing, PITR enabled. No GSIs — all queries by `user_id`. Utility functions in `lambda/layer/python/db.py`:
- `get_table(name)` → resource
- `query_by_user(table, user_id)` → all items for user
- `get_item(table, user_id, sk_name, sk_value)` → single item
- `delete_item(table, user_id, sk_name, sk_value)`

## Testing Strategy

**Unit tests** (`tests/unit/`): Use `moto` to mock AWS and `freezegun` for time. `conftest.py` loads Lambda modules via a unique sys.modules alias (`_lambda_{feature}_{stem}`) to prevent collisions across features with identically-named files (crud.py, router.py, etc.).

**Integration tests** (`tests/test_api.py`): Run against the live deployed stack. Require `TEST_PAT` in `.env`. These are the primary correctness tests — they catch IAM permission gaps, schema mismatches, and env var wiring that unit tests cannot.

## Adding a New Feature

1. Create `lambda/{feature}/handler.py`, `router.py`, `crud.py` matching tasks pattern
2. Add DynamoDB table in `terraform/dynamodb.tf`
3. Add Lambda function in `terraform/lambda_{feature}.tf` (Terraform auto-generates the zip via `archive_file` in `main.tf`)
4. Add IAM inline policy in `terraform/iam.tf` scoped to the new table
5. Add API routes in `terraform/api_gateway.tf`
6. `terraform apply`

## Environment Variables

Copy `.env.example` → `.env` and fill in:
- `API_URL` — from `terraform output api_url`
- `COGNITO_CLIENT_ID`, `COGNITO_USER_POOL_ID` — from `terraform output`
- `AWS_REGION`
- `TEST_EMAIL`, `TEST_PASSWORD` — for integration tests
- `TEST_PAT` — Personal Access Token for integration test auth
