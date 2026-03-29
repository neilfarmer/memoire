# Memoire

Memoire is a personal productivity app — one place for tasks, habits, goals, journal, notes, health, and nutrition. Serverless on AWS.

## Features

### Tasks
Create and track tasks with title, description, status (To Do / In Progress / Done), priority (low / medium / high), and due date. Tasks appear on the home dashboard when due today or in progress. Supports per-task ntfy push notifications: on due, before due (1h / 1d / 3d), and recurring reminders.

A Pomodoro timer is built into the Tasks page. Focus a specific task, and the timer tracks work and break cycles.

### Habits
Define daily habits and mark them done each day. Tracks current streak, best streak, and a 30-day heatmap history per habit. Completion counts appear on the home dashboard. Supports per-habit ntfy reminders at a configured daily time (UTC).

### Goals
Track long-term goals with a title, description, target date, and status (Active / Completed / Abandoned). Filter by status. Active goals appear on the home dashboard. Goals are intentionally simple — no milestones or sub-tasks.

### Journal
One entry per day. Markdown editor with auto-save. Each entry has a mood (Great / Good / Okay / Bad / Terrible) and optional tags. Month calendar view with dots on days that have entries. Streak tracking (current and longest). Full-text search across all entries.

### Notes
Hierarchical folder tree (nesting supported). Full-screen markdown editor with a formatting toolbar and auto-save. Supports image attachments (inline in the note) and file attachments. Search across all notes.

### Exercise Log
Log workouts by day. Each log can have multiple exercises; each exercise has sets with reps and weight, plus a duration. Freeform notes field per log. Month calendar view showing which days have entries.

### Nutrition
Log meals by day. Each log can have multiple meals with name, calories, protein, carbs, and fat. Freeform notes field per log. Daily macro totals calculated automatically. Month calendar view.

### Home Dashboard
Greeting, date, and four widgets: active/in-progress tasks, habit completion for today, journal streak, and active goals. Loads data for all widgets on login.

### Export
Downloads a ZIP of all your data as Markdown files, organized by feature. Journal entries include frontmatter (date, mood, tags). Notes are organized in their folder hierarchy with attachments included.

### Settings
- **Dark mode** — persisted per user
- **Display name** — shown in the home greeting
- **ntfy URL** — endpoint for push notifications; includes a test button
- **Auto-save interval** — controls how frequently the note and journal editors auto-save (30s / 1m / 2m / 5m)

---

## Architecture

```
Browser → CloudFront → S3 (index.html + config.js)
Browser → API Gateway (HTTP API, JWT auth) → Lambda (per feature) → DynamoDB

Cognito      — user accounts and JWT tokens
EventBridge  — triggers watcher Lambda hourly (ntfy notifications)
Cost Explorer — queried from home Lambda for the AWS cost widget
```

**Request flow:** Cognito issues a JWT → API Gateway validates it → Lambda extracts `user_id` from the `sub` claim → all DynamoDB operations are scoped to that `user_id`.

**Frontend:** Single-file vanilla JS SPA (`frontend/index.html`). No build step. Reads `window.MEMOIRE_CONFIG` from `config.js`, which Terraform generates and uploads with the live API URL and Cognito IDs.

**Lambda structure:** Each feature follows handler → router → crud. A shared Lambda layer (`lambda/layer/python/`) provides `db.py` and `response.py` to all functions.

---

## AWS Cost

All figures are **us-east-1** pricing as of mid-2025. Assumes a single AWS account with no other significant workloads sharing the free tier.

### Idle (deployed, zero active users)

| Service | Usage | Cost |
|---|---|---|
| Lambda (watcher) | 720 invocations/month × 128 MB × ~2 s | $0 — within free tier |
| EventBridge | 720 events/month | $0 — within free tier |
| DynamoDB | 10 tables, ~0 requests, <1 MB storage | $0 — within 25 GB free tier |
| CloudFront | No traffic | $0 |
| S3 | <1 MB | $0 |
| Cognito | 0 MAU | $0 |
| CloudWatch Logs | Minimal watcher logs | $0 |
| **Total** | | **~$0/month** |

### Personal use (1 user, ~50 API calls/day)

| Service | Usage | Cost |
|---|---|---|
| Lambda | ~1,500 invocations/month | $0 — within free tier |
| API Gateway HTTP API | 1,500 requests/month | $0.002 |
| DynamoDB on-demand | ~1,500 mixed read/write ops | $0.002 |
| Cost Explorer API | ~30 logins/month × $0.01/call | **$0.30** |
| CloudWatch Logs | ~5 MB/month | $0 |
| CloudFront + S3 | Minimal | $0 |
| **Total** | | **~$0.30/month** |

Cost Explorer is the dominant cost at personal scale. Every home page load triggers one `GetCostAndUsage` API call at $0.01. There is no free tier for this API.

### Active development (frequent deploys + personal use)

| Item | Cost |
|---|---|
| Personal-use costs (above) | ~$0.30 |
| CloudFront invalidations | $0 — first 1,000 paths/month free; `make deploy-auto` creates one `/*` per run |
| Additional CloudWatch Logs | $0 — within free tier |
| **Total** | **~$0.30/month** |

---

## Prerequisites

- AWS account with billing enabled
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6
- Python 3.12 (for running integration tests)
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) configured (`aws configure`)
- Cost Explorer enabled: AWS Billing console → Cost Explorer → Enable
- `Project` cost allocation tag activated: AWS Billing console → Cost allocation tags → activate `Project`. **This is required for the home dashboard cost widget.** Tags can take up to 24 hours to appear after first deploy.

---

## Getting Started

### 1. Create a deployment repo

Create a new directory for your deployment and add a `main.tf`:

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    cloudflare = {
      # Only needed if domain_provider = "cloudflare"
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }

  # Configure your backend here
  # backend "s3" { ... }
}

provider "aws" {
  region = "us-east-1"

  # The Project tag is required — the home dashboard's cost widget queries
  # Cost Explorer filtered by this tag. Without it, costs will show as $0.
  default_tags {
    tags = {
      Project   = "memoire"   # must match var.project_name
      ManagedBy = "terraform"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token   # omit if not using Cloudflare
}

module "memoire" {
  source = "github.com/neilfarmer/memoire//terraform?ref=v0.1.0"

  # Required for initial login
  default_user_email    = "you@example.com"
  default_user_password = "ChangeMe123!"

  # Optional — see full variable reference below
  # domain_provider = "cloudflare"
  # root_domain     = "yourdomain.com"
}

output "frontend_url"  { value = module.memoire.frontend_url }
output "api_url"       { value = module.memoire.api_url }
```

### 2. Deploy

```bash
terraform init
terraform apply
```

### 3. Set up your environment

```bash
cp .env.example .env
```

Fill in `.env` using the values from `terraform output`:

```bash
terraform output api_url               # → API_URL
terraform output cognito_client_id     # → COGNITO_CLIENT_ID
terraform output cognito_user_pool_id  # → COGNITO_USER_POOL_ID
```

Set `TEST_EMAIL` and `TEST_PASSWORD` to match `default_user_email` and `default_user_password`.

### 4. Open the app

```bash
terraform output frontend_url
```

Navigate to that URL and log in with the credentials you configured.

---

## Terraform Variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `aws_region` | `string` | `"us-east-1"` | AWS region to deploy all resources |
| `project_name` | `string` | `"memoire"` | Prefix applied to all resource names. Must match the `Project` tag in your provider's `default_tags`. |
| `environment` | `string` | `"dev"` | Deployment environment (`dev`, `staging`, `prod`) |
| **Auth** | | | |
| `auth_provider` | `string` | `"cognito"` | Authentication provider: `cognito` (deploys AWS Cognito) or `oidc` (bring your own) |
| `auth_oidc_issuer_url` | `string` | `""` | OIDC issuer URL. Required when `auth_provider = "oidc"` (e.g. `https://your-domain.auth0.com/`) |
| `auth_oidc_client_id` | `string` | `""` | JWT audience (client ID) from your OIDC provider. Required when `auth_provider = "oidc"` |
| `default_user_email` | `string` | `""` | Email for the initial Cognito user created on first deploy. Only used when `auth_provider = "cognito"`. Leave empty to skip. |
| `default_user_password` | `string` | `""` | Password for the initial Cognito user. Must meet Cognito policy: 8+ chars, upper, lower, number. Sensitive. |
| **Custom Domain** | | | |
| `domain_provider` | `string` | `"none"` | DNS provider: `cloudflare`, `aws`, or `none` |
| `root_domain` | `string` | `""` | Root domain (e.g. `example.com`). Frontend at `{project}-{env}.{domain}`, API at `api.{project}-{env}.{domain}` |
| `route53_zone_id` | `string` | `""` | Route 53 hosted zone ID. Required when `domain_provider = "aws"` |
| **Alerting** | | | |
| `alert_emails` | `list(string)` | `[]` | Email addresses to receive AWS budget alerts |
| `budget_thresholds_usd` | `list(number)` | `[10, 20, 30]` | Monthly spend thresholds in USD. An alert fires when actual spend exceeds each value. |
| **Lambda** | | | |
| `lambda_runtime` | `string` | `"python3.12"` | Lambda runtime identifier |
| `lambda_timeout` | `number` | `10` | Default function timeout in seconds |
| `lambda_memory_mb` | `number` | `128` | Default function memory in MB |
| `lambda_max_concurrency` | `number` | `5` | Reserved concurrent executions per Lambda. `-1` means unreserved. |
| **Observability** | | | |
| `log_retention_days` | `number` | `14` | CloudWatch log retention period in days |
| **S3 Lifecycle** | | | |
| `note_attachment_ia_days` | `number` | `90` | Days before note attachments transition to S3 Infrequent Access |
| `note_attachment_glacier_days` | `number` | `365` | Days before note attachments transition to S3 Glacier Instant Retrieval |

---

## Development Workflow

```bash
make deploy       # terraform apply with confirmation prompt
make deploy-auto  # terraform apply --auto-approve + CloudFront cache invalidation
make invalidate   # invalidate CloudFront cache only (no terraform changes)
make test         # run integration tests against the live API
```

**Deploy flow:** `make deploy-auto` runs `terraform apply`, which regenerates Lambda ZIPs from source, uploads the frontend, and regenerates `config.js` with live values. It then runs `scripts/invalidate-cache.sh`, which creates a CloudFront `/*` invalidation and polls until complete (~30–60 seconds).

No manual zip step is required. Terraform's `archive_file` data sources build the ZIPs automatically before apply.

---

## Adding a New Feature

1. Create `lambda/{feature}/handler.py`, `router.py`, `crud.py` following the tasks pattern
2. Add the `data "archive_file"` source in `terraform/main.tf`
3. Add a DynamoDB table in `terraform/dynamodb.tf` (include `point_in_time_recovery`)
4. Create `terraform/lambda_{feature}.tf` with Lambda function, CloudWatch log group, IAM policy, API Gateway integration, and routes
5. Add the page, sidebar entry, modal, and JS module to `frontend/index.html`
6. Run `make deploy-auto`

---

## Notifications (ntfy)

Memoire uses [ntfy](https://ntfy.sh) for push notifications. Configure your ntfy topic URL in Settings. The watcher Lambda runs hourly via EventBridge and sends notifications for:

- Tasks due within a configured window (1h / 1d / 3d before due date)
- Tasks past their due date
- Recurring task reminders
- Habit daily reminders at the configured time (UTC)

Notifications are deduplicated — the watcher tracks what has been sent to avoid repeat alerts within the same window.

---

## Infrastructure & Automation

See [`docs/infrastructure.md`](docs/infrastructure.md) for the full infrastructure reference: Terraform layout, global config locals, deploy flow, and known operational gaps.

See [`docs/cost.md`](docs/cost.md) for a full cost breakdown by daily / weekly / monthly / yearly usage across light, personal, and power-user tiers.

See [`docs/decisions/`](docs/decisions/) for architecture decision records:
- [001 — No Lambda unit tests](docs/decisions/001-no-lambda-unit-tests.md)
- [002 — AI integration architecture](docs/decisions/002-ai-integration-architecture.md)
- [003 — Deployment automation & AWS best practices](docs/decisions/003-deployment-automation.md)
