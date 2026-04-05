# Getting Started

This guide walks you through deploying Memoire from scratch to a working URL.

---

## Prerequisites

Before you begin, you need:

- **AWS account** with billing enabled
- **[Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6**
- **AWS CLI** installed and configured (`aws configure`) with credentials for your account
- **Cost Explorer enabled** — open the AWS Billing console, go to Cost Explorer, and click Enable. This is required for the home dashboard cost widget. Tags can take up to 24 hours to appear after first deploy.
- **`Project` cost allocation tag activated** — AWS Billing console → Cost allocation tags → activate `Project`

Optional:
- **Python 3.12** — only needed if you want to run integration tests
- **A custom domain** — Cloudflare or Route 53 DNS supported (see [Configuration](configuration.md))

---

## Step 1 — Create a deployment repo

Create a new directory and add a `main.tf`. This repo holds your deployment config and Terraform state — keep it separate from the Memoire source code.

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

  # Recommended: configure a remote backend here once you have an S3 bucket
  # backend "s3" { ... }
}

provider "aws" {
  region = "us-east-1"

  # The Project tag is required — the home dashboard's cost widget filters
  # Cost Explorer by this tag. Without it, costs will show as $0.
  default_tags {
    tags = {
      Project   = "memoire"
      ManagedBy = "terraform"
    }
  }
}

module "memoire" {
  source = "github.com/neilfarmer/memoire//terraform?ref=v0.6.0"

  # Credentials for the first user created on deploy
  default_user_email    = "you@example.com"
  default_user_password = "ChangeMe123!"
}

output "frontend_url" { value = module.memoire.frontend_url }
output "api_url"       { value = module.memoire.api_url }
```

> **Password requirements:** 8+ characters, including uppercase, lowercase, and a number (enforced by Cognito).

---

## Step 2 — Deploy

```bash
terraform init
terraform apply
```

Terraform will show you the plan — around 60–70 resources on first deploy. Review it, type `yes`, and wait a few minutes for everything to provision.

When it completes, you'll see output like:

```
frontend_url = "https://memoire-dev.edenforge.io"
api_url      = "https://api.memoire-dev.edenforge.io"
```

---

## Step 3 — Open the app

Navigate to the `frontend_url` output and log in with the email and password you set in `main.tf`.

That's it. You're in.

---

## Step 4 (optional) — Set up a local environment for tests

If you want to run the integration tests, create a `.env` file in the Memoire source repo:

```bash
cp .env.example .env
```

Fill in the values using Terraform outputs:

```bash
export API_URL=$(terraform output -raw api_url)
export COGNITO_CLIENT_ID=$(terraform output -raw cognito_client_id)
export COGNITO_USER_POOL_ID=$(terraform output -raw cognito_user_pool_id)
export AWS_REGION=us-east-1
export TEST_EMAIL=you@example.com      # same as default_user_email
export TEST_PASSWORD=ChangeMe123!      # same as default_user_password
```

Create the test user (first time only):

```bash
source .env && python tests/test_api.py --create-user
```

Run the tests:

```bash
make test
```

---

## Custom domain (optional)

Set `domain_provider` and `root_domain` in your module block. Memoire will create DNS records automatically.

**Cloudflare:**
```hcl
module "memoire" {
  source = "github.com/neilfarmer/memoire//terraform?ref=v0.6.0"
  ...
  domain_provider       = "cloudflare"
  root_domain           = "yourdomain.com"
  cloudflare_api_token  = var.cloudflare_api_token
}
```

**Route 53:**
```hcl
module "memoire" {
  source = "github.com/neilfarmer/memoire//terraform?ref=v0.6.0"
  ...
  domain_provider  = "aws"
  root_domain      = "yourdomain.com"
  route53_zone_id  = "Z1234567890ABC"
}
```

The frontend will be at `{project_name}-{environment}.{root_domain}` and the API at `api.{project_name}-{environment}.{root_domain}`.

---

## AI Assistant (optional)

Memoire includes an AI assistant (Pip) powered by Amazon Bedrock. To enable it, your AWS account needs access to Amazon Nova Lite and/or Nova Pro models.

Request access in the [Bedrock console](https://console.aws.amazon.com/bedrock/) under Model access. Nova Lite and Nova Pro are typically approved immediately.

No additional Terraform configuration is required — Bedrock access is handled via the Lambda's IAM role.

For USDA nutrition lookup (used when logging meals), see [AI Assistant — USDA API Key](features-ai-pal.md#usda-fooddata-central-api).

---

## Troubleshooting

**The cost widget shows $0**
Cost allocation tags take up to 24 hours to activate after first deploy. The `Project` tag must also be activated in the AWS Billing console under Cost allocation tags.

**Login fails immediately after deploy**
The Cognito user is created with a temporary password that requires a reset on first login. If the app doesn't prompt for a new password, try logging in and changing the password manually via the AWS Cognito console.

**CloudFront serves old content after a deploy**
Run `make invalidate` to force a cache purge, or wait up to 5 minutes for the TTL to expire.

**Terraform state is local**
By default, state is stored in `terraform.tfstate` in your deployment repo. Back this file up or migrate to an S3 backend before running in production — losing it means Terraform can no longer manage your existing resources. See [Infrastructure](infrastructure.md#remote-terraform-state) for migration steps.
