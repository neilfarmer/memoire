# Configuration Reference

All Memoire configuration is done through Terraform variables passed to the module. This page covers every available variable.

---

## Minimal configuration

Only two variables are required to deploy:

```hcl
module "memoire" {
  source = "github.com/neilfarmer/memoire//terraform?ref=v0.6.0"

  default_user_email    = "you@example.com"
  default_user_password = "ChangeMe123!"
}
```

Everything else has a sensible default.

---

## All variables

### Core

| Variable | Type | Default | Description |
|---|---|---|---|
| `aws_region` | `string` | `"us-east-1"` | AWS region for all resources |
| `project_name` | `string` | `"memoire"` | Prefix applied to all resource names. Must match the `Project` tag in your provider's `default_tags` for the cost widget to work. |
| `environment` | `string` | `"dev"` | Deployment environment label (`dev`, `staging`, `prod`). Appended to resource names. |

### Authentication

| Variable | Type | Default | Description |
|---|---|---|---|
| `auth_provider` | `string` | `"cognito"` | `cognito` — Terraform creates and manages an AWS Cognito user pool. `oidc` — bring your own OIDC provider (Auth0, Okta, etc.). |
| `default_user_email` | `string` | `""` | Email for the first Cognito user created on deploy. Only used when `auth_provider = "cognito"`. Leave empty to skip auto-creation. |
| `default_user_password` | `string` | `""` | Password for the initial Cognito user. Must meet Cognito policy: 8+ characters, uppercase, lowercase, number. Sensitive — do not commit to version control. |
| `auth_oidc_issuer_url` | `string` | `""` | OIDC issuer URL. Required when `auth_provider = "oidc"` (e.g. `https://your-domain.auth0.com/`). |
| `auth_oidc_client_id` | `string` | `""` | JWT audience (client ID) from your OIDC provider. Required when `auth_provider = "oidc"`. |

### Custom Domain

Leave `domain_provider = "none"` (the default) to use the auto-generated CloudFront and API Gateway URLs.

| Variable | Type | Default | Description |
|---|---|---|---|
| `domain_provider` | `string` | `"none"` | DNS provider: `cloudflare`, `aws`, or `none`. |
| `root_domain` | `string` | `""` | Root domain (e.g. `example.com`). Frontend goes to `{project_name}-{environment}.{root_domain}`, API to `api.{project_name}-{environment}.{root_domain}`. |
| `cloudflare_api_token` | `string` | `""` | Cloudflare API token. Required when `domain_provider = "cloudflare"`. Sensitive. |
| `route53_zone_id` | `string` | `""` | Route 53 hosted zone ID. Required when `domain_provider = "aws"`. |

### AI Assistant

| Variable | Type | Default | Description |
|---|---|---|---|
| `assistant_model_id` | `string` | `"us.amazon.nova-lite-v1:0"` | Amazon Bedrock model ID. Switch to `us.amazon.nova-pro-v1:0` for better reasoning. |
| `assistant_system_prompt` | `string` | `""` | Override the default system prompt. Leave empty to use the built-in prompt. |
| `usda_api_key` | `string` | `""` | USDA FoodData Central API key for nutrition lookups. See [AI Assistant — USDA API Key](features-ai-pal.md#usda-fooddata-central-api). |
| `admin_user_ids` | `list(string)` | `[]` | Cognito `sub` (user ID) values that can access the `/admin` dashboard. |

### Alerting

| Variable | Type | Default | Description |
|---|---|---|---|
| `alert_emails` | `list(string)` | `[]` | Email addresses for AWS budget alerts. AWS will send a confirmation email — you must click the link to activate. |
| `budget_thresholds_usd` | `list(number)` | `[10, 20, 30]` | Monthly spend thresholds (USD). An alert fires when actual spend crosses each value. |

### Lambda

| Variable | Type | Default | Description |
|---|---|---|---|
| `lambda_runtime` | `string` | `"python3.12"` | Lambda runtime identifier. |
| `lambda_timeout` | `number` | `10` | Default function timeout in seconds. The watcher Lambda overrides this to `300`. |
| `lambda_memory_mb` | `number` | `128` | Memory per Lambda function in MB. |
| `lambda_max_concurrency` | `number` | `5` | Reserved concurrent executions per API Lambda. Caps runaway cost from bugs or load spikes. Set to `-1` for unreserved. |

### Observability

| Variable | Type | Default | Description |
|---|---|---|---|
| `log_retention_days` | `number` | `14` | CloudWatch log retention for all log groups. |

### Storage Lifecycle

These control when note attachments move to cheaper S3 storage tiers. The frontend files are not affected.

| Variable | Type | Default | Description |
|---|---|---|---|
| `note_attachment_ia_days` | `number` | `90` | Days before note attachments transition from S3 Standard to Infrequent Access. |
| `note_attachment_glacier_days` | `number` | `365` | Days before note attachments transition to Glacier Instant Retrieval. |

---

## Outputs

After `terraform apply`, these outputs are available:

| Output | Description |
|---|---|
| `frontend_url` | URL of the CloudFront distribution (or custom domain if configured) |
| `api_url` | Base URL for the API Gateway |
| `cognito_client_id` | Cognito app client ID (needed for `.env` test setup) |
| `cognito_user_pool_id` | Cognito user pool ID (needed for `.env` test setup) |
| `cloudfront_distribution_id` | CloudFront distribution ID (used by cache invalidation) |

---

## Multiple environments

Deploy `dev` and `prod` from the same module by using different `environment` values. Resource names will be prefixed differently, so they won't conflict:

```hcl
module "memoire_dev" {
  source      = "github.com/neilfarmer/memoire//terraform?ref=v0.6.0"
  environment = "dev"
  ...
}

module "memoire_prod" {
  source      = "github.com/neilfarmer/memoire//terraform?ref=v0.6.0"
  environment = "prod"
  ...
}
```

This is the pattern used in the reference deploy repo.
