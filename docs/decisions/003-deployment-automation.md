# Decision: Deployment Automation & AWS Best Practices

## Status
Accepted (partially implemented — see phased rollout)

## Context

The initial deployment was manual and lacked guardrails: local Terraform state, no spend visibility, no data protection, and Lambda functions that could scale unbounded. As the app moves toward a stable personal production environment, several low-effort, high-value improvements were identified.

## Implemented

### Centralized Terraform locals (`main.tf`)

A single `locals` block holds all tuneable configuration. Previously, values like Lambda timeout, memory, runtime, and log retention were hardcoded independently in each `lambda_*.tf` file. Now they are defined once and referenced everywhere. To change the Python runtime or log retention across all Lambdas, edit one line.

**Current locals:**
- `alert_emails` — list of addresses for budget alerts and future ops notifications
- `budget_thresholds_usd` — monthly spend thresholds in USD that trigger email alerts
- `lambda_timeout`, `lambda_memory_mb`, `lambda_runtime` — defaults applied to all Lambda functions; override per-function as needed
- `lambda_max_concurrency` — reserved concurrency cap applied to all API-facing Lambdas
- `log_retention_days` — CloudWatch log retention for all Lambda log groups
- `note_attachment_ia_days`, `note_attachment_glacier_days` — S3 lifecycle transition thresholds for note attachments

### AWS Budget alerts (`budget.tf`)

One monthly cost budget covering the entire AWS account. A `dynamic notification` block creates one alert per entry in `budget_thresholds_usd`. Alerts are sent directly to `alert_emails` — no SNS required. `limit_amount` is automatically set to the highest threshold.

AWS allows 2 free budgets per account; this uses one.

To add a threshold or recipient, edit the relevant local in `main.tf` and apply.

### DynamoDB Point-in-Time Recovery (`dynamodb.tf`)

`point_in_time_recovery { enabled = true }` added to all 10 tables. Enables continuous backups with a 35-day restore window at per-second granularity. Restore is initiated via the AWS console or CLI and creates a new table from the backup — the original table is unaffected.

Cost: ~$0.20/GB/month of table data. Negligible at personal scale.

This protects against accidental deletion, corrupted writes, and application bugs that destroy data.

### Lambda reserved concurrency (`main.tf`, all `lambda_*.tf`)

`reserved_concurrent_executions = local.lambda_max_concurrency` (currently `5`) applied to all API-facing Lambda functions. The watcher Lambda is hardcoded to `1` since it runs on an EventBridge schedule and never needs parallel invocations.

Without this, a bug causing retries or a sudden traffic spike could consume the account-wide concurrency pool (default 1000), running up cost or starving other functions. For a personal app, 5 concurrent executions per function is more than sufficient for normal use.

To raise the limit for a specific function (e.g. the export Lambda during a large export), override `reserved_concurrent_executions` directly in that function's `.tf` file.

### S3 lifecycle rules for note attachments (`s3_frontend.tf`)

Note images (`note-images/` prefix) and file attachments (`note-attachments/` prefix) are stored in the same S3 bucket as the frontend. They are typically accessed once or twice after upload and then rarely touched. Two lifecycle rules transition them to cheaper storage tiers:

- **Day 90** → `STANDARD_IA` (Infrequent Access): same durability and millisecond retrieval, ~60% cheaper storage cost
- **Day 365** → `GLACIER_IR` (Glacier Instant Retrieval): millisecond restore, ~80% cheaper than standard

Both thresholds are controlled by locals in `main.tf`. The frontend HTML and `config.js` objects are not affected — they have no prefix filter match.

## Not Yet Implemented

### Remote Terraform state (S3 + DynamoDB lock)

The highest-risk gap remaining. Local `tfstate` can be lost, corrupted, or become inconsistent if apply is interrupted. The commented-out backend block in `main.tf` is the starting point.

Bootstrap process:
1. Manually create an S3 bucket and DynamoDB table for state locking (or use a separate Terraform root module)
2. Uncomment and configure the `backend "s3"` block in `main.tf`
3. Run `terraform init -migrate-state` to move local state to S3

Until this is done, the `terraform.tfstate` file must be treated as critical and backed up manually.

### GitHub Actions CI/CD

Currently deploy requires running `make deploy-auto` from a local machine with AWS credentials. A GitHub Actions workflow would:
- Run `terraform plan` on every pull request for review before apply
- Run `terraform apply` + CloudFront invalidation on push to `main`
- Use OIDC for AWS authentication (no long-lived access keys stored in GitHub secrets)

### CloudWatch Alarms

No alerting exists for runtime failures. Useful alarms to add in a `monitoring.tf`:
- Lambda error rate > 0 for any function → SNS → `alert_emails`
- API Gateway 5xx rate > 1%
- Lambda p99 duration > 80% of timeout

### Watcher Lambda dead letter queue (DLQ)

The watcher runs on an EventBridge schedule. Failed invocations are silently dropped. An SQS DLQ would capture them for inspection and replay. API-facing Lambdas do not need this — API Gateway surfaces errors directly to the caller.

## Consequences

- Any change to Lambda runtime, memory, or timeout now requires editing one line in `main.tf` rather than hunting through each `lambda_*.tf` file.
- Budget alerts will fire to both email addresses when monthly spend crosses any configured threshold. First-time recipients must confirm the SNS subscription email from AWS before alerts are delivered (handled automatically by AWS Budgets for direct email subscriptions — no action required).
- PITR adds a small ongoing cost per table. At current data volumes this is effectively zero.
- Reserved concurrency means each Lambda can handle at most `lambda_max_concurrency` simultaneous requests. If this limit is hit, API Gateway returns 429 (throttled). For a single-user personal app this will never happen in practice.
- S3 objects in `STANDARD_IA` incur a minimum 30-day storage charge and a per-GB retrieval fee. Objects transitioned before 30 days of age will still be charged for the full 30 days. At current note attachment volumes this cost is negligible.
