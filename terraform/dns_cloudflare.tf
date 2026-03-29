# ── Cloudflare DNS records ────────────────────────────────────────────────────
# Only created when domain_provider = "cloudflare".

data "cloudflare_zone" "main" {
  count = local.cloudflare_enabled ? 1 : 0
  name  = var.root_domain
}

locals {
  cloudflare_zone_id = local.cloudflare_enabled ? data.cloudflare_zone.main[0].id : ""
}
#
# All records use proxied = false (DNS-only / gray cloud) so that:
#   - CloudFront handles TLS for the frontend (requires direct CNAME → CF domain)
#   - API Gateway handles TLS for the API (regional endpoint, not Cloudflare-terminated)
#
# The ACM validation records are CNAME records that prove domain ownership to AWS.
# They are permanent and safe to leave in place after issuance.

# Keys are the domain names we already know statically — this lets Terraform plan
# the resource instances without needing domain_validation_options to be resolved.
# The record name/type/value are unknown until the cert exists, which is fine.
resource "cloudflare_record" "acm_validation" {
  for_each = local.cloudflare_enabled ? toset([local.frontend_domain, local.api_domain]) : toset([])

  zone_id = local.cloudflare_zone_id
  name = trimsuffix(one([
    for dvo in try(aws_acm_certificate.main[0].domain_validation_options, []) :
    dvo.resource_record_name if dvo.domain_name == each.value
  ]), ".")
  type = one([
    for dvo in try(aws_acm_certificate.main[0].domain_validation_options, []) :
    dvo.resource_record_type if dvo.domain_name == each.value
  ])
  content = trimsuffix(one([
    for dvo in try(aws_acm_certificate.main[0].domain_validation_options, []) :
    dvo.resource_record_value if dvo.domain_name == each.value
  ]), ".")
  ttl     = 60
  proxied = false
}

# Frontend CNAME → CloudFront distribution domain
resource "cloudflare_record" "frontend" {
  count = local.cloudflare_enabled ? 1 : 0

  zone_id = local.cloudflare_zone_id
  name    = local.frontend_domain
  type    = "CNAME"
  content = aws_cloudfront_distribution.frontend.domain_name
  ttl     = 1
  proxied = false
}

# API CNAME → API Gateway regional domain
resource "cloudflare_record" "api" {
  count = local.cloudflare_enabled ? 1 : 0

  zone_id = local.cloudflare_zone_id
  name    = local.api_domain
  type    = "CNAME"
  content = aws_apigatewayv2_domain_name.main[0].domain_name_configuration[0].target_domain_name
  ttl     = 1
  proxied = false
}
