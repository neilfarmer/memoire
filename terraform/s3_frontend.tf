# ── S3 bucket (private — accessed only via CloudFront) ────────────────────────

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "frontend" {
  bucket        = "${local.name_prefix}-frontend-${random_id.bucket_suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_cors_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  cors_rule {
    allowed_headers = ["Content-Type"]
    allowed_methods = ["PUT"]
    allowed_origins = [local.frontend_origin]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── CloudFront Response Headers Policy (security headers) ────────────────────

resource "aws_cloudfront_response_headers_policy" "security" {
  name = "${local.name_prefix}-security-headers"

  security_headers_config {
    content_security_policy {
      content_security_policy = join("; ", [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
        "style-src 'self' https://fonts.googleapis.com https://cdn.jsdelivr.net 'unsafe-inline'",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        # connect-src uses https: rather than local.api_url to avoid a dependency
        # cycle: api_gateway_api → local.frontend_origin → cloudfront_distribution
        # → response_headers_policy → local.api_url → api_gateway_stage → api_gateway_api.
        # Terraform evaluates both branches of a conditional for graph purposes,
        # so the conditional approach does not break the cycle — omit api_url entirely.
        "connect-src 'self' https:",
        "frame-ancestors 'none'",
      ])
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    content_type_options {
      override = true
    }

    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      override                   = true
    }

    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
  }
}

# ── CloudFront Origin Access Control ─────────────────────────────────────────

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.name_prefix}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ── CloudFront distribution ───────────────────────────────────────────────────

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "${local.name_prefix} frontend"

  # Populated when a custom domain is configured; empty list uses the default CloudFront domain.
  aliases = local.custom_domain_enabled ? [local.frontend_domain] : []

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    allowed_methods              = ["GET", "HEAD"]
    cached_methods               = ["GET", "HEAD"]
    target_origin_id             = "s3-frontend"
    viewer_protocol_policy       = "redirect-to-https"
    compress                     = true
    response_headers_policy_id   = aws_cloudfront_response_headers_policy.security.id

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000
  }

  # openapi.yaml embeds the live API URL — must not be cached
  ordered_cache_behavior {
    path_pattern           = "/openapi.yaml"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # config.js must not be cached — it holds API/Cognito config values
  ordered_cache_behavior {
    path_pattern           = "/config.js"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    # When a custom domain is active, use the ACM certificate issued in dns.tf.
    # When no custom domain is configured, fall back to the default CloudFront certificate.
    cloudfront_default_certificate = local.custom_domain_enabled ? false : true
    acm_certificate_arn            = local.custom_domain_enabled ? one(aws_acm_certificate_validation.main[*].certificate_arn) : null
    ssl_support_method             = local.custom_domain_enabled ? "sni-only" : null
    minimum_protocol_version       = local.custom_domain_enabled ? "TLSv1.2_2021" : null
  }
}

# ── Bucket policy — allow CloudFront OAC to read objects ─────────────────────

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
        }
      }
    }]
  })
}

# ── Note attachment lifecycle ─────────────────────────────────────────────────
#
# Note images and file attachments are accessed infrequently after initial upload.
# Transition them to cheaper storage tiers over time.
# Thresholds are controlled by locals in main.tf.

resource "aws_s3_bucket_lifecycle_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    id     = "note-images-lifecycle"
    status = "Enabled"

    filter {
      prefix = "note-images/"
    }

    transition {
      days          = var.note_attachment_ia_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.note_attachment_glacier_days
      storage_class = "GLACIER_IR"
    }
  }

  rule {
    id     = "note-attachments-lifecycle"
    status = "Enabled"

    filter {
      prefix = "note-attachments/"
    }

    transition {
      days          = var.note_attachment_ia_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.note_attachment_glacier_days
      storage_class = "GLACIER_IR"
    }
  }

  rule {
    id     = "export-cleanup"
    status = "Enabled"

    filter {
      prefix = "exports/"
    }

    expiration {
      days = 1
    }
  }
}

# ── Upload frontend files ─────────────────────────────────────────────────────

# config.js is generated by Terraform with actual resource values injected
resource "aws_s3_object" "config_js" {
  bucket       = aws_s3_bucket.frontend.id
  key          = "config.js"
  content_type = "application/javascript"

  content = <<-JS
    window.MEMOIRE_CONFIG = {
      apiUrl: "${local.api_url}",
      cognitoClientId: "${local.auth_jwt_client_id}",
      cognitoUserPoolId: "${var.auth_provider == "cognito" ? aws_cognito_user_pool.main[0].id : ""}",
      authDomain: "${local.auth_hosted_ui_url}",
      awsRegion: "${var.aws_region}",
    };
  JS
}

resource "aws_s3_object" "index_html" {
  bucket       = aws_s3_bucket.frontend.id
  key          = "index.html"
  source       = "${path.module}/../frontend/index.html"
  content_type = "text/html"
  etag         = filemd5("${path.module}/../frontend/index.html")
}

resource "aws_s3_object" "icon_svg" {
  bucket       = aws_s3_bucket.frontend.id
  key          = "icon.svg"
  source       = "${path.module}/../frontend/icon.svg"
  content_type = "image/svg+xml"
  etag         = filemd5("${path.module}/../frontend/icon.svg")
}

resource "aws_s3_object" "docs_html" {
  bucket       = aws_s3_bucket.frontend.id
  key          = "docs.html"
  source       = "${path.module}/../frontend/docs.html"
  content_type = "text/html"
  etag         = filemd5("${path.module}/../frontend/docs.html")
}

# openapi.yaml is generated from the template so the live API URL is embedded.
# Terraform computes a content hash to force S3 replacement when the spec changes.
resource "aws_s3_object" "openapi_yaml" {
  bucket       = aws_s3_bucket.frontend.id
  key          = "openapi.yaml"
  content      = templatefile("${path.module}/../frontend/openapi.yaml.tpl", { api_url = local.api_url })
  content_type = "application/yaml"
  etag         = md5(templatefile("${path.module}/../frontend/openapi.yaml.tpl", { api_url = local.api_url }))
}
