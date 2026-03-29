# Decision: No unit tests for Lambda functions

## Status
Accepted

## Context

The project has integration tests (`tests/test_api.py`) that run against the live deployed API. The question was whether to also add unit tests for the individual Lambda functions.

## Decision

No unit tests for Lambda CRUD code. Integration tests only.

## Reasoning

**The Lambda code is too thin to unit test usefully.** Each feature Lambda follows the same three-file pattern: handler extracts auth, router dispatches, crud does one DynamoDB operation. There is almost no business logic to isolate — the code *is* the DynamoDB interaction.

**Mocking DynamoDB introduces false confidence.** A mocked `put_item` call will accept any schema silently. The mock passes while the real deployment can fail due to wrong key names, missing table env vars, or IAM permission gaps. This is exactly the kind of divergence that goes undetected until production.

**Integration tests catch what actually matters.** IAM permissions, environment variable wiring, API Gateway route matching, DynamoDB key structure, and response serialization are all exercised by hitting the real stack. Two of the five test failures found during the initial run (`BatchWriteItem` permission missing, `Decimal` serialized as string) would not have been caught by unit tests with mocked DynamoDB.

**Where unit tests would add value:** The `watcher` Lambda has real logic — notification window checks, deduplication, ntfy payload construction — that runs on an hourly EventBridge schedule and is hard to exercise via integration tests. If that logic grows more complex, unit tests there would be appropriate.

## Consequences

- Faster CI (no mock setup, no fixture maintenance)
- Test failures point to real bugs in real infrastructure
- Tests require a live deployed stack and valid Cognito credentials to run
- The watcher Lambda's notification logic remains untested beyond manual observation
