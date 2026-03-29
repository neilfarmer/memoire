# ── Monthly cost budget ───────────────────────────────────────────────────────
#
# One budget covering the entire AWS account. A notification fires when actual
# spend exceeds each threshold in var.budget_thresholds_usd. Alerts go to
# every address in var.alert_emails.
#
# AWS allows 2 free budgets per account; additional budgets cost $0.02/day each.

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(max(var.budget_thresholds_usd...))
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = var.budget_thresholds_usd
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "ABSOLUTE_VALUE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.alert_emails
    }
  }
}
