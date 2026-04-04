# ── Home Lambda (cost dashboard + admin stats) ────────────────────────────────

resource "aws_lambda_function" "home" {
  function_name    = "${local.name_prefix}-home"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_home.output_path
  source_code_hash = data.archive_file.lambda_home.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = 30
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      PROJECT_NAME    = var.project_name
      FUNCTION_PREFIX = local.name_prefix
      FRONTEND_BUCKET = aws_s3_bucket.frontend.id
      TASKS_TABLE     = aws_dynamodb_table.tasks.name
      JOURNAL_TABLE   = aws_dynamodb_table.journal.name
      NOTES_TABLE     = aws_dynamodb_table.notes.name
      FOLDERS_TABLE   = aws_dynamodb_table.note_folders.name
      HABITS_TABLE    = aws_dynamodb_table.habits.name
      HEALTH_TABLE    = aws_dynamodb_table.health.name
      NUTRITION_TABLE = aws_dynamodb_table.nutrition.name
      SETTINGS_TABLE  = aws_dynamodb_table.settings.name
      ADMIN_USER_IDS  = var.admin_user_ids
    }
  }
}

resource "aws_cloudwatch_log_group" "home" {
  name              = "/aws/lambda/${aws_lambda_function.home.function_name}"
  retention_in_days = var.log_retention_days
}

# Cost Explorer read-only access
resource "aws_iam_role_policy" "home_cost_explorer" {
  name = "${local.name_prefix}-home-cost-explorer"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ce:GetCostAndUsage"]
        Resource = "*"
      }
    ]
  })
}

# Admin stats permissions: DynamoDB DescribeTable, S3 ListBucket, CloudWatch metrics
resource "aws_iam_role_policy" "home_admin_stats" {
  name = "${local.name_prefix}-home-admin-stats"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["dynamodb:DescribeTable"]
        Resource = [
          aws_dynamodb_table.tasks.arn,
          aws_dynamodb_table.journal.arn,
          aws_dynamodb_table.notes.arn,
          aws_dynamodb_table.note_folders.arn,
          aws_dynamodb_table.habits.arn,
          aws_dynamodb_table.health.arn,
          aws_dynamodb_table.nutrition.arn,
          aws_dynamodb_table.settings.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [aws_s3_bucket.frontend.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:GetMetricStatistics"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_permission" "home_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.home.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "home" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.home.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "home_costs" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /home/costs"
  target             = "integrations/${aws_apigatewayv2_integration.home.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}

resource "aws_apigatewayv2_route" "admin_stats" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /admin/stats"
  target             = "integrations/${aws_apigatewayv2_integration.home.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
