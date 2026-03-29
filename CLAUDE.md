# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Use `make` targets for all operations. Do not run raw shell commands directly — propose a new make target and get approval before adding one.

**Available targets:**
```bash
make test          # run integration tests (sources .env automatically)
make deploy        # terraform apply (interactive)
make deploy-auto   # terraform apply -auto-approve + CloudFront invalidation
make invalidate    # invalidate CloudFront cache only
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

**Frontend**: Vanilla JS SPA (`frontend/index.html`). Reads `window.MEMOIRE_CONFIG` from `config.js`, which Terraform generates and uploads to S3 with API URL + Cognito IDs.

## DynamoDB Patterns

All tables use `user_id` (String) as partition key and `{feature}_id` (String) as sort key. On-demand billing. Utility functions in `lambda/layer/python/db.py`:
- `get_table(name)` → resource
- `query_by_user(table, user_id)` → all items for user
- `get_item(table, user_id, sk_name, sk_value)` → single item
- `delete_item(table, user_id, sk_name, sk_value)`

## Adding a New Feature

1. Create `lambda/{feature}/handler.py`, `router.py`, `crud.py` matching tasks pattern
2. Add DynamoDB table in `terraform/dynamodb.tf`
3. Add Lambda function in `terraform/lambda_{feature}.tf`
4. Add IAM inline policy in `terraform/iam.tf` scoped to the new table
5. Add API routes in `terraform/api_gateway.tf`
6. Zip: `cd lambda/{feature} && zip -r ../../build/{feature}.zip .`
7. `terraform apply`

## Environment Variables

Copy `.env.example` → `.env` and fill in:
- `API_URL` — from `terraform output api_url`
- `COGNITO_CLIENT_ID`, `COGNITO_USER_POOL_ID` — from `terraform output`
- `AWS_REGION`
- `TEST_EMAIL`, `TEST_PASSWORD` — for integration tests
