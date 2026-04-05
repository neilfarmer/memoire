# ── Habits Lambda ─────────────────────────────────────────────────────────────

resource "aws_iam_role" "habits" {
  name               = "${local.name_prefix}-habits"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "habits_basic" {
  role       = aws_iam_role.habits.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "habits" {
  function_name                  = "${local.name_prefix}-habits"
  runtime                        = var.lambda_runtime
  handler                        = "handler.lambda_handler"
  role                           = aws_iam_role.habits.arn
  filename                       = data.archive_file.lambda_habits.output_path
  source_code_hash               = data.archive_file.lambda_habits.output_base64sha256
  layers                         = [aws_lambda_layer_version.shared.arn]
  timeout                        = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      HABITS_TABLE     = aws_dynamodb_table.habits.name
      HABIT_LOGS_TABLE = aws_dynamodb_table.habit_logs_v2.name
    }
  }
}

resource "aws_cloudwatch_log_group" "habits" {
  name              = "/aws/lambda/${aws_lambda_function.habits.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "habits_dynamodb" {
  name = "${local.name_prefix}-habits-dynamodb"
  role = aws_iam_role.habits.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
        ]
        Resource = aws_dynamodb_table.habits.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
        ]
        Resource = aws_dynamodb_table.habit_logs_v2.arn
      },
    ]
  })
}

resource "aws_lambda_permission" "habits_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.habits.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "habits" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.habits.invoke_arn
  payload_format_version = "2.0"
}

locals {
  habits_routes = [
    "GET /habits",
    "POST /habits",
    "PUT /habits/{id}",
    "DELETE /habits/{id}",
    "POST /habits/{id}/toggle",
  ]
}

resource "aws_apigatewayv2_route" "habits" {
  for_each = toset(local.habits_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.habits.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
