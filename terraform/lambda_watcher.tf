# ── Watcher Lambda ────────────────────────────────────────────────────────────
#
# Runs hourly via EventBridge. Scans active tasks and sends ntfy notifications.
#
# No DLQ configured by design: the watcher is a best-effort notification job.
# A missed run (e.g. due to a transient error) causes a delayed notification,
# not data loss. The next hourly invocation will re-evaluate and send any
# outstanding notifications. A DLQ would add cost and operational overhead
# with no meaningful reliability benefit for this use case.

resource "aws_iam_role" "watcher" {
  name               = "${local.name_prefix}-watcher"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "watcher_basic" {
  role       = aws_iam_role.watcher.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "watcher" {
  function_name    = "${local.name_prefix}-watcher"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.watcher.arn
  filename         = data.archive_file.lambda_watcher.output_path
  source_code_hash = data.archive_file.lambda_watcher.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = 300
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = 1

  environment {
    variables = {
      TASKS_TABLE      = aws_dynamodb_table.tasks.name
      SETTINGS_TABLE   = aws_dynamodb_table.settings.name
      HABITS_TABLE     = aws_dynamodb_table.habits.name
      HABIT_LOGS_TABLE = aws_dynamodb_table.habit_logs_v2.name
    }
  }
}

resource "aws_cloudwatch_log_group" "watcher" {
  name              = "/aws/lambda/${aws_lambda_function.watcher.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "watcher_dynamodb" {
  name = "${local.name_prefix}-watcher-dynamodb"
  role = aws_iam_role.watcher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.tasks.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem"]
        Resource = aws_dynamodb_table.settings.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.habits.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem"]
        Resource = aws_dynamodb_table.habit_logs_v2.arn
      },
    ]
  })
}

# ── EventBridge rule — runs every hour ───────────────────────────────────────

resource "aws_cloudwatch_event_rule" "watcher_hourly" {
  name                = "${local.name_prefix}-watcher-hourly"
  description         = "Trigger the watcher Lambda every hour"
  schedule_expression = "rate(1 hour)"
}

resource "aws_cloudwatch_event_target" "watcher" {
  rule      = aws_cloudwatch_event_rule.watcher_hourly.name
  target_id = "watcher-lambda"
  arn       = aws_lambda_function.watcher.arn
}

resource "aws_lambda_permission" "watcher_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.watcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.watcher_hourly.arn
}
