# ── Health Lambda ─────────────────────────────────────────────────────────────

resource "aws_iam_role" "health" {
  name               = "${local.name_prefix}-health"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "health_basic" {
  role       = aws_iam_role.health.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "health" {
  function_name                  = "${local.name_prefix}-health"
  runtime                        = var.lambda_runtime
  handler                        = "handler.lambda_handler"
  role                           = aws_iam_role.health.arn
  filename                       = data.archive_file.lambda_health.output_path
  source_code_hash               = data.archive_file.lambda_health.output_base64sha256
  layers                         = [aws_lambda_layer_version.shared.arn]
  timeout                        = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.health.name
    }
  }
}

resource "aws_cloudwatch_log_group" "health" {
  name              = "/aws/lambda/${aws_lambda_function.health.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "health_dynamodb" {
  name = "${local.name_prefix}-health-dynamodb"
  role = aws_iam_role.health.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
        ]
        Resource = aws_dynamodb_table.health.arn
      },
    ]
  })
}

resource "aws_lambda_permission" "health_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.health.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "health" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.health.invoke_arn
  payload_format_version = "2.0"
}

locals {
  health_routes = [
    "GET /health",
    "GET /health/summary",
    "GET /health/exercises/recent",
    "GET /health/{date}",
    "PUT /health/{date}",
    "DELETE /health/{date}",
  ]
}

resource "aws_apigatewayv2_route" "health" {
  for_each = toset(local.health_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.health.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
