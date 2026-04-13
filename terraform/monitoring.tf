# ── SNS topic for security alerts ─────────────────────────────────────────────
#
# Only created when at least one alert email is configured.
#
# KMS encryption is intentionally omitted: the topic publishes only CloudWatch
# alarm state changes (no PII or secrets). A customer-managed KMS key would
# add $1/month and require key rotation management with no meaningful security
# benefit for this payload type.

resource "aws_sns_topic" "alerts" {
  count = length(var.alert_emails) > 0 ? 1 : 0
  name  = "${local.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "alert_emails" {
  count     = length(var.alert_emails)
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_emails[count.index]
}

# ── Auth failure metric filter + alarm ────────────────────────────────────────
#
# Counts log lines from the Lambda authorizer that contain "Auth rejected" or
# "JWT rejected" (emitted at WARNING level).  An alarm fires when the rate
# exceeds 20 failures in 5 minutes — a sign of brute-force or credential
# stuffing.

resource "aws_cloudwatch_log_metric_filter" "auth_failures" {
  name           = "${local.name_prefix}-auth-failures"
  log_group_name = aws_cloudwatch_log_group.authorizer.name
  pattern        = "Auth rejected"

  metric_transformation {
    name      = "AuthFailures"
    namespace = "${local.name_prefix}/Security"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "auth_failure_rate" {
  count               = length(var.alert_emails) > 0 ? 1 : 0
  alarm_name          = "${local.name_prefix}-auth-failure-rate"
  alarm_description   = "More than 20 auth failures in 5 minutes — possible brute-force or credential stuffing."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "AuthFailures"
  namespace           = "${local.name_prefix}/Security"
  period              = 300
  statistic           = "Sum"
  threshold           = 20
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts[0].arn]
  ok_actions    = [aws_sns_topic.alerts[0].arn]
}

# ── JWT rejection metric filter + alarm ───────────────────────────────────────
#
# Tracks JWT-specific failures (expired, wrong issuer, bad signature).
# Separate from auth rejections so we can distinguish token validation errors
# from missing tokens.

resource "aws_cloudwatch_log_metric_filter" "jwt_rejections" {
  name           = "${local.name_prefix}-jwt-rejections"
  log_group_name = aws_cloudwatch_log_group.authorizer.name
  pattern        = "JWT rejected"

  metric_transformation {
    name      = "JwtRejections"
    namespace = "${local.name_prefix}/Security"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "jwt_rejection_rate" {
  count               = length(var.alert_emails) > 0 ? 1 : 0
  alarm_name          = "${local.name_prefix}-jwt-rejection-rate"
  alarm_description   = "More than 20 JWT rejections in 5 minutes — possible token manipulation or expired session abuse."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "JwtRejections"
  namespace           = "${local.name_prefix}/Security"
  period              = 300
  statistic           = "Sum"
  threshold           = 20
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts[0].arn]
  ok_actions    = [aws_sns_topic.alerts[0].arn]
}
