# Development Guide

This guide covers the day-to-day development workflow, how to add a new feature, and how to run tests.

---

## Repository layout

```
memoire/
├── frontend/
│   └── index.html              Single-file vanilla JS SPA. No build step.
├── lambda/
│   ├── layer/python/           Shared utilities (db.py, response.py) — Lambda layer
│   ├── assistant/              AI assistant (chat.py, tools.py, memory.py)
│   ├── tasks/                  handler.py, router.py, crud.py
│   ├── habits/                 handler.py, router.py, crud.py
│   ├── goals/                  handler.py, router.py, crud.py
│   ├── journal/                handler.py, router.py, crud.py
│   ├── notes/                  handler.py, router.py, crud.py
│   ├── health/                 handler.py, router.py, crud.py
│   ├── nutrition/              handler.py, router.py, crud.py
│   ├── settings/               handler.py, router.py, crud.py
│   ├── home/                   AWS Cost Explorer data for the home dashboard
│   ├── export/                 Generates ZIP of all user data as Markdown
│   ├── auth/                   Cognito auth helpers
│   ├── authorizer/             JWT authorizer Lambda
│   └── watcher/                EventBridge-triggered Lambda for ntfy notifications
├── terraform/
│   ├── main.tf                 Locals (global config), providers, archive_file sources
│   ├── variables.tf            Input variables
│   ├── outputs.tf              API URL, CloudFront URL, Cognito IDs, etc.
│   ├── dynamodb.tf             All DynamoDB table definitions
│   ├── lambda_*.tf             One file per Lambda (function, log group, IAM, API routes)
│   ├── api_gateway.tf          HTTP API, JWT authorizer, stage
│   ├── cognito.tf              User pool and client
│   └── s3_frontend.tf          S3 bucket, CloudFront, lifecycle rules
├── tests/
│   └── test_api.py             Integration tests against the live API
├── docs/                       Documentation
├── Makefile
└── .env                        Local credentials (gitignored)
```

---

## Make targets

```bash
make deploy       # terraform apply with confirmation prompt
make deploy-auto  # terraform apply -auto-approve + CloudFront cache invalidation
make invalidate   # invalidate CloudFront cache only (no terraform changes)
make test         # run integration tests against the live API
```

**No manual zip step required.** Terraform's `archive_file` data sources build Lambda ZIPs from the source directories automatically on each `apply`.

**Deploy flow:**

```
make deploy-auto
  └── terraform apply -auto-approve
        ├── Rebuilds Lambda ZIPs from lambda/ source dirs
        ├── Uploads index.html, icon.svg to S3
        ├── Regenerates config.js with current API URL + Cognito IDs
        └── Applies any infrastructure changes
  └── scripts/invalidate-cache.sh
        ├── Reads CloudFront ID from Terraform state
        ├── Creates /* invalidation
        └── Polls every 30 seconds until complete (~30–60 seconds)
```

---

## Environment setup

Copy `.env.example` to `.env` and fill in values from `terraform output`:

```bash
export API_URL=               # terraform output -raw api_url
export COGNITO_CLIENT_ID=     # terraform output -raw cognito_client_id
export COGNITO_USER_POOL_ID=  # terraform output -raw cognito_user_pool_id
export AWS_REGION=us-east-1
export TEST_EMAIL=            # your test user email
export TEST_PASSWORD=         # your test user password
```

Create the test user (first time only):

```bash
source .env && python tests/test_api.py --create-user
```

---

## Running tests

```bash
make test
```

Tests run against the live API. They create, read, update, and delete real data in the dev environment. The test user's data is cleaned up at the end of each run.

To run a specific test module:

```bash
source .env && python tests/test_api.py
```

---

## Lambda structure

Each feature Lambda follows the same three-file pattern:

```
handler.py   — Entry point. Extracts user_id from the JWT claims, parses the
               request body, and delegates to the router.
router.py    — Dispatches by HTTP method and path to the right crud function.
crud.py      — DynamoDB CRUD operations. All queries are scoped to user_id.
```

The shared layer (`lambda/layer/python/`) provides two utilities available to all Lambdas:

- `db.py` — DynamoDB helpers: `get_table`, `query_by_user`, `get_item`, `delete_item`
- `response.py` — HTTP response helpers: `ok`, `not_found`, `bad_request`, `server_error`

User ID extraction pattern (copy this in every new handler):

```python
user_id = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
```

API Gateway validates the JWT before the Lambda runs — Lambdas never validate tokens themselves.

---

## Adding a new feature

Follow this checklist. The tasks feature is the reference implementation.

**1. Lambda code**

Create `lambda/{feature}/handler.py`, `router.py`, `crud.py` following the tasks pattern.

**2. DynamoDB table (`terraform/dynamodb.tf`)**

```hcl
resource "aws_dynamodb_table" "my_feature" {
  name         = "${local.name_prefix}-my-feature"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "user_id"
  range_key = "item_id"

  attribute { name = "user_id" type = "S" }
  attribute { name = "item_id" type = "S" }

  point_in_time_recovery { enabled = true }
  tags = local.tags
}
```

**3. Terraform Lambda file (`terraform/lambda_myfeature.tf`)**

Copy `terraform/lambda_tasks.tf` and replace all references to `tasks` with your feature name. This file defines:
- `aws_lambda_function`
- `aws_cloudwatch_log_group`
- `aws_iam_role_policy` (scoped to your table ARN only)
- `aws_lambda_permission`
- `aws_apigatewayv2_integration`
- `aws_apigatewayv2_route` (one per method/path)

**4. `archive_file` source (`terraform/main.tf`)**

```hcl
data "archive_file" "lambda_myfeature" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/myfeature"
  output_path = "${path.module}/../build/myfeature.zip"
  excludes    = ["__pycache__", "*.pyc"]
}
```

**5. Frontend (`frontend/index.html`)**

Add the sidebar link, page section, any modals, and the JS module for your feature. Follow the pattern of the tasks section.

**6. Deploy**

```bash
make deploy-auto
```

---

## Push notifications (ntfy)

Memoire uses [ntfy](https://ntfy.sh) for push notifications. Users configure their ntfy topic URL in Settings.

The watcher Lambda (`lambda/watcher/`) runs on an EventBridge schedule (hourly) and sends notifications for:

- Tasks due within the configured window (1 hour, 1 day, 3 days before due)
- Tasks past their due date (overdue reminders)
- Recurring task reminders
- Habit daily reminders at the user's configured UTC time

Notifications are deduplicated. The watcher tracks what it has already sent to avoid sending the same alert twice in the same window.

To add notifications for a new feature, add a handler in `lambda/watcher/` following the existing task and habit patterns.

---

## Frontend notes

The entire frontend is a single file: `frontend/index.html`. There is no build step, no bundler, and no framework. This is intentional — it keeps the deploy pipeline simple (upload one file to S3) and avoids build tooling as a dependency.

JS is vanilla ES2020+. The app is a client-side SPA with a simple hash-based router.

`config.js` is generated by Terraform at deploy time and injected into the S3 bucket alongside `index.html`. It sets `window.MEMOIRE_CONFIG` with the live API URL and Cognito client IDs. This is how the frontend knows where to talk to without hardcoding anything.

---

## Architecture decision records

| ADR | Decision |
|---|---|
| [001 — No Lambda unit tests](decisions/001-no-lambda-unit-tests.md) | Why integration tests are used instead |
| [002 — AI integration architecture](decisions/002-ai-integration-architecture.md) | How the AI assistant is wired to Bedrock |
| [003 — Deployment automation](decisions/003-deployment-automation.md) | Deploy pipeline choices and gaps |
