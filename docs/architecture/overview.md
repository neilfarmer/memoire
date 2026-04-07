# Architecture Overview

Memoire is a serverless, multi-tenant personal productivity app (tasks, notes, habits, journal, diagrams).

## System Diagram

```
Browser (SPA)
  └── CloudFront → S3 (frontend/index.html, config.js)
  └── API Gateway (HTTP API, JWT authorizer)
        └── Lambda functions (per feature)
              └── DynamoDB tables (per feature)
              └── S3 (note-images/, note-attachments/)
  └── Cognito (user pool, hosted UI)
```

## Request Flow

1. User authenticates via Cognito hosted UI — receives a JWT
2. Browser stores JWT and sends it as `Authorization: Bearer <token>` on every API call
3. API Gateway validates the JWT against the Cognito user pool before invoking any Lambda
4. Lambda extracts `user_id` from `event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]`
5. All DynamoDB queries are scoped to that `user_id` — no cross-user data access is possible at the application layer

## Lambda Structure

Each feature follows the same three-file pattern:

```
lambda/{feature}/
  handler.py   — entry point: extracts auth + body, calls router
  router.py    — dispatches by HTTP method + path
  crud.py      — DynamoDB operations

lambda/layer/python/
  db.py        — shared DynamoDB client helpers
  response.py  — shared HTTP response helpers (handles Decimal serialization)
```

## DynamoDB

All tables use `user_id` (String) as partition key and `{feature}_id` (String) as sort key. On-demand billing. No GSIs — all queries are by `user_id`.

## Frontend

Vanilla JS SPA served from S3 via CloudFront. Reads `window.MEMOIRE_CONFIG` from `config.js`, which Terraform generates and uploads with the API URL and Cognito IDs injected.
