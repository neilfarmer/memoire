# ── Nutrition Lambda ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "nutrition" {
  function_name    = "${local.name_prefix}-nutrition"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_nutrition.output_path
  source_code_hash = data.archive_file.lambda_nutrition.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.nutrition.name
    }
  }
}

resource "aws_cloudwatch_log_group" "nutrition" {
  name              = "/aws/lambda/${aws_lambda_function.nutrition.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "nutrition_dynamodb" {
  name = "${local.name_prefix}-nutrition-dynamodb"
  role = aws_iam_role.lambda_exec.id

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
        Resource = aws_dynamodb_table.nutrition.arn
      },
    ]
  })
}

resource "aws_lambda_permission" "nutrition_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.nutrition.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "nutrition" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.nutrition.invoke_arn
  payload_format_version = "2.0"
}

locals {
  nutrition_routes = [
    "GET /nutrition",
    "GET /nutrition/{date}",
    "PUT /nutrition/{date}",
    "DELETE /nutrition/{date}",
  ]
}

resource "aws_apigatewayv2_route" "nutrition" {
  for_each = toset(local.nutrition_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.nutrition.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
