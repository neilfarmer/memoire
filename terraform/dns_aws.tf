# ── Route 53 DNS records ──────────────────────────────────────────────────────
# Only created when domain_provider = "aws".
#
# The frontend uses an A alias record pointing at the CloudFront distribution.
# The API uses an A alias record pointing at the API Gateway regional domain.
# ACM DNS validation records prove domain ownership so the certificate can be issued.

resource "aws_route53_record" "acm_validation" {
  for_each = local.route53_enabled ? toset([local.frontend_domain, local.api_domain]) : toset([])

  zone_id = var.route53_zone_id
  name = one([
    for dvo in try(aws_acm_certificate.main[0].domain_validation_options, []) :
    dvo.resource_record_name if dvo.domain_name == each.value
  ])
  type = one([
    for dvo in try(aws_acm_certificate.main[0].domain_validation_options, []) :
    dvo.resource_record_type if dvo.domain_name == each.value
  ])
  ttl = 60
  records = [one([
    for dvo in try(aws_acm_certificate.main[0].domain_validation_options, []) :
    dvo.resource_record_value if dvo.domain_name == each.value
  ])]
}

# Frontend A alias → CloudFront distribution
resource "aws_route53_record" "frontend" {
  count = local.route53_enabled ? 1 : 0

  zone_id = var.route53_zone_id
  name    = local.frontend_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

# API A alias → API Gateway regional domain
resource "aws_route53_record" "api" {
  count = local.route53_enabled ? 1 : 0

  zone_id = var.route53_zone_id
  name    = local.api_domain
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.main[0].domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.main[0].domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}
