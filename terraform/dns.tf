# ── Custom domain — shared AWS resources ─────────────────────────────────────
#
# All resources in this file are gated on local.custom_domain_enabled.
# DNS records live in dns_cloudflare.tf or dns_aws.tf depending on domain_provider.
#
# ACM certificates for CloudFront MUST be in us-east-1. The API Gateway custom
# domain also uses this certificate since the default region is us-east-1.
# If you deploy to a different region, add a separate us-east-1 provider alias
# and reference it on the aws_acm_certificate resource.

resource "aws_acm_certificate" "main" {
  count = local.custom_domain_enabled ? 1 : 0

  domain_name               = local.frontend_domain
  subject_alternative_names = [local.api_domain]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Waits for DNS validation records to propagate and ACM to issue the certificate.
# validation_record_fqdns is populated by whichever DNS provider is active.
resource "aws_acm_certificate_validation" "main" {
  count = local.custom_domain_enabled ? 1 : 0

  certificate_arn = aws_acm_certificate.main[0].arn

  validation_record_fqdns = concat(
    [for r in cloudflare_record.acm_validation : r.hostname],
    [for r in aws_route53_record.acm_validation : r.fqdn],
  )
}

# ── API Gateway custom domain ─────────────────────────────────────────────────

resource "aws_apigatewayv2_domain_name" "main" {
  count = local.custom_domain_enabled ? 1 : 0

  domain_name = local.api_domain

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.main[0].certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "main" {
  count = local.custom_domain_enabled ? 1 : 0

  api_id      = aws_apigatewayv2_api.main.id
  domain_name = aws_apigatewayv2_domain_name.main[0].id
  stage       = aws_apigatewayv2_stage.default.id
}
