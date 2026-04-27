# ── Fitbit sync Lambda ────────────────────────────────────────────────────────
#
# Runs every 30 minutes via EventBridge. Scans the settings table for
# users with fitbit.enabled=true, refreshes OAuth tokens as needed, and
# pulls today's activity / nutrition / weight / sleep summary into the
# fitbit_data table. Also invoked directly by the fitbit Lambda when the
# user requests an on-demand sync.

resource "aws_iam_role" "fitbit_sync" {
  name               = "${local.name_prefix}-fitbit-sync"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "fitbit_sync_basic" {
  role       = aws_iam_role.fitbit_sync.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "fitbit_sync" {
  function_name    = "${local.name_prefix}-fitbit-sync"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.fitbit_sync.arn
  filename         = data.archive_file.lambda_fitbit_sync.output_path
  source_code_hash = data.archive_file.lambda_fitbit_sync.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = 300
  memory_size      = var.lambda_memory_mb
  # Allow a couple of overlapping invocations: the EventBridge schedule
  # iterates all enabled users, while user "Sync now" + post-food-log async
  # invokes can land mid-flight. A cap of 1 throttles those with
  # TooManyRequestsException; 3 leaves a generous buffer without
  # uncapped concurrency.
  reserved_concurrent_executions = 3

  environment {
    variables = {
      FITBIT_TOKENS_TABLE  = aws_dynamodb_table.fitbit_tokens.name
      FITBIT_DATA_TABLE    = aws_dynamodb_table.fitbit_data.name
      SETTINGS_TABLE       = aws_dynamodb_table.settings.name
      HEALTH_TABLE         = aws_dynamodb_table.health.name
      FITBIT_CLIENT_ID     = var.fitbit_client_id
      FITBIT_CLIENT_SECRET = var.fitbit_client_secret
    }
  }
}

resource "aws_cloudwatch_log_group" "fitbit_sync" {
  name              = "/aws/lambda/${aws_lambda_function.fitbit_sync.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "fitbit_sync_dynamodb" {
  name = "${local.name_prefix}-fitbit-sync-dynamodb"
  role = aws_iam_role.fitbit_sync.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan"]
        Resource = aws_dynamodb_table.settings.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
        ]
        Resource = [
          aws_dynamodb_table.fitbit_tokens.arn,
          aws_dynamodb_table.fitbit_data.arn,
          aws_dynamodb_table.health.arn,
        ]
      },
    ]
  })
}

# ── EventBridge rule — every 30 minutes ───────────────────────────────────────

resource "aws_cloudwatch_event_rule" "fitbit_sync" {
  name                = "${local.name_prefix}-fitbit-sync"
  description         = "Trigger the Fitbit sync Lambda every 30 minutes"
  schedule_expression = "rate(30 minutes)"
}

resource "aws_cloudwatch_event_target" "fitbit_sync" {
  rule      = aws_cloudwatch_event_rule.fitbit_sync.name
  target_id = "fitbit-sync-lambda"
  arn       = aws_lambda_function.fitbit_sync.arn
}

resource "aws_lambda_permission" "fitbit_sync_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fitbit_sync.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.fitbit_sync.arn
}
