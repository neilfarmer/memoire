# Infrastructure & Automation Reference

This document describes the infrastructure layout, deployment automation, and operational configuration for Memoire. For architecture decisions and their rationale, see `docs/decisions/`.

---

## Repository Layout

```
memoire/
├── frontend/
│   └── index.html          — entire SPA (vanilla JS, single file)
├── lambda/
│   ├── layer/python/       — shared utilities (db.py, response.py) deployed as a Lambda layer
│   ├── tasks/              — handler.py, router.py, crud.py
│   ├── habits/             — handler.py, router.py, crud.py
│   ├── goals/              — handler.py, router.py, crud.py
│   ├── journal/            — handler.py, router.py, crud.py
│   ├── notes/              — handler.py, router.py, crud.py
│   ├── health/             — handler.py, router.py, crud.py
│   ├── nutrition/          — handler.py, router.py, crud.py
│   ├── settings/           — handler.py, router.py, crud.py
│   ├── home/               — Lambda for AWS cost data (Cost Explorer API)
│   ├── export/             — generates ZIP of all user data
│   └── watcher/            — EventBridge-scheduled Lambda for ntfy notifications
├── terraform/
│   ├── main.tf             — locals (global config), providers, archive_file sources
│   ├── variables.tf        — input variables with defaults
│   ├── outputs.tf          — API URL, CloudFront URL, Cognito IDs, etc.
│   ├── dynamodb.tf         — all DynamoDB table definitions
│   ├── lambda_*.tf         — one file per Lambda (function, log group, IAM, API routes)
│   ├── lambda_layer.tf     — shared Python layer
│   ├── api_gateway.tf      — HTTP API, JWT authorizer, stage
│   ├── cognito.tf          — user pool, client, domain
│   ├── iam.tf              — shared Lambda execution role + basic execution policy
│   ├── s3_frontend.tf      — S3 bucket, CloudFront distribution, OAC, lifecycle rules
│   ├── budget.tf           — monthly cost budget with email alerts
│   └── terraform.tfstate   — local state (see note below)
├── scripts/
│   └── invalidate-cache.sh — CloudFront cache invalidation with polling
├── tests/
│   └── test_api.py         — integration tests against the live API
├── docs/
│   ├── decisions/          — architecture decision records
│   └── infrastructure.md   — this file
├── build/                  — generated Lambda ZIPs (gitignored)
├── Makefile
├── CLAUDE.md
└── .env                    — local credentials (gitignored)
```

---

## Terraform Structure

### Global Config (`main.tf` locals)

All tuneable values are centralised in the `locals` block in `main.tf`. Edit here, then `terraform apply` — no need to hunt through individual resource files.

| Local | Default | Purpose |
|---|---|---|
| `alert_emails` | two addresses | Budget alert recipients |
| `budget_thresholds_usd` | `[10, 20, 30]` | Monthly spend amounts that trigger alerts |
| `lambda_runtime` | `"python3.12"` | Runtime for all Lambda functions |
| `lambda_timeout` | `10` | Seconds; watcher overrides to `300` |
| `lambda_memory_mb` | `128` | Memory for all Lambda functions |
| `lambda_max_concurrency` | `5` | Reserved concurrency cap per API Lambda |
| `log_retention_days` | `14` | CloudWatch log retention for all log groups |
| `note_attachment_ia_days` | `90` | Days before note files → S3 Infrequent Access |
| `note_attachment_glacier_days` | `365` | Days before note files → Glacier Instant Retrieval |

### Lambda Files Pattern

Each feature follows the same Terraform structure in `lambda_{feature}.tf`:

```
aws_lambda_function           — function definition, env vars, layer reference
aws_cloudwatch_log_group      — log group with retention
aws_iam_role_policy           — inline policy scoped to that feature's DynamoDB table(s)
aws_lambda_permission         — allows API Gateway to invoke the function
aws_apigatewayv2_integration  — AWS_PROXY integration
aws_apigatewayv2_route        — one route per HTTP method/path, all JWT-authed
```

Lambda ZIPs are generated automatically by `data "archive_file"` sources in `main.tf` — no manual zip step required before `terraform apply`.

### DynamoDB Tables

All tables use `PAY_PER_REQUEST` billing and have Point-in-Time Recovery (PITR) enabled (35-day continuous restore window).

| Table | PK | SK |
|---|---|---|
| `memoire-dev-tasks` | `user_id` | `task_id` |
| `memoire-dev-settings` | `user_id` | — |
| `memoire-dev-habits` | `user_id` | `habit_id` |
| `memoire-dev-habit-logs` | `habit_id` | `log_date` |
| `memoire-dev-journal` | `user_id` | `entry_date` |
| `memoire-dev-note-folders` | `user_id` | `folder_id` |
| `memoire-dev-notes` | `user_id` | `note_id` |
| `memoire-dev-health` | `user_id` | `log_date` |
| `memoire-dev-nutrition` | `user_id` | `log_date` |
| `memoire-dev-goals` | `user_id` | `goal_id` |

All data is scoped to `user_id` (the Cognito `sub` claim). API Gateway validates the JWT before Lambda runs — Lambdas never validate tokens themselves.

### S3 Bucket

One bucket (`memoire-dev-frontend`) serves three purposes:

1. **Frontend** — `index.html`, `icon.svg`, `config.js` (generated by Terraform with live values)
2. **Note images** — `note-images/{user_id}/{uuid}.{ext}`
3. **Note attachments** — `note-attachments/{user_id}/{uuid}/{filename}`

Lifecycle rules transition note files to cheaper storage tiers (thresholds in `main.tf` locals). The frontend objects have no matching prefix and are not affected.

CloudFront serves the bucket via Origin Access Control (OAC). The bucket has no public access.

### Budget Alerts (`budget.tf`)

One `aws_budgets_budget` covering the whole AWS account. Notifications fire when actual monthly spend exceeds each value in `budget_thresholds_usd`. Alerts go to all addresses in `alert_emails` via direct email (no SNS subscription step required).

AWS gives 2 free budgets per account.

---

## Deployment Automation

### Makefile Targets

```bash
make deploy       # terraform apply (interactive — shows plan, prompts for confirmation)
make deploy-auto  # terraform apply -auto-approve, then invalidates CloudFront cache
make invalidate   # invalidate CloudFront cache only (no terraform apply)
make test         # run integration tests against the live API (sources .env automatically)
```

### CloudFront Invalidation (`scripts/invalidate-cache.sh`)

Called automatically by `make deploy-auto`. Pulls the CloudFront distribution ID from Terraform state (no hardcoded IDs), creates a `/*` invalidation, and polls every 30 seconds until the invalidation completes. Exits non-zero on failure.

### Deploy Flow (end-to-end)

```
make deploy-auto
  └── terraform apply -auto-approve
        ├── Regenerates build/*.zip from lambda/ source dirs (archive_file)
        ├── Uploads index.html and icon.svg to S3
        ├── Regenerates config.js with current API URL + Cognito IDs
        └── Applies any infrastructure changes (tables, functions, routes, etc.)
  └── scripts/invalidate-cache.sh
        ├── Reads CloudFront ID from terraform state
        ├── Creates /* invalidation
        └── Polls until complete (~30–60 seconds)
```

### Environment File (`.env`)

Required for running tests. Not used by Terraform.

```bash
export API_URL=               # from: terraform output api_url
export COGNITO_CLIENT_ID=     # from: terraform output cognito_client_id
export COGNITO_USER_POOL_ID=  # from: terraform output cognito_user_pool_id
export AWS_REGION=us-east-1
export TEST_EMAIL=            # Cognito user for tests
export TEST_PASSWORD=         # Cognito user password
```

---

## Known Gaps

### Remote Terraform State

State is currently stored locally in `terraform/terraform.tfstate`. The `backend "s3"` block in `main.tf` is commented out. Until remote state is enabled, this file must be treated as critical — losing it means Terraform can no longer manage existing resources.

**To migrate:**
1. Create an S3 bucket and DynamoDB table for state locking (manually or via a bootstrap module)
2. Uncomment and configure the `backend "s3"` block in `main.tf`
3. Run `terraform init -migrate-state`

### No CI/CD Pipeline

Deployments require running `make deploy-auto` from a local machine with AWS credentials. A GitHub Actions workflow with OIDC authentication would remove this dependency. See `docs/decisions/003-deployment-automation.md`.

### No CloudWatch Alarms

There is no alerting for Lambda errors, API Gateway 5xx responses, or latency spikes. A `monitoring.tf` with `aws_cloudwatch_metric_alarm` resources wired to an SNS topic using `alert_emails` is the natural next step.

### Watcher Has No Dead Letter Queue

The watcher Lambda runs on an EventBridge schedule. Failed invocations are silently dropped. An SQS DLQ would capture them for inspection and replay.
