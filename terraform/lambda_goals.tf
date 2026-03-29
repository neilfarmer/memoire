# ── Goals Lambda ──────────────────────────────────────────────────────────────

resource "aws_lambda_function" "goals" {
  function_name    = "${local.name_prefix}-goals"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_goals.output_path
  source_code_hash = data.archive_file.lambda_goals.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.goals.name
    }
  }
}

resource "aws_cloudwatch_log_group" "goals" {
  name              = "/aws/lambda/${aws_lambda_function.goals.function_name}"
  retention_in_days = var.log_retention_days
}

# DynamoDB permissions scoped to the goals table only
resource "aws_iam_role_policy" "goals_dynamodb" {
  name = "${local.name_prefix}-goals-dynamodb"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
      ]
      Resource = aws_dynamodb_table.goals.arn
    }]
  })
}

# Allow API Gateway to invoke this Lambda
resource "aws_lambda_permission" "goals_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.goals.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "goals" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.goals.invoke_arn
  payload_format_version = "2.0"
}

locals {
  goals_routes = [
    "GET /goals",
    "POST /goals",
    "GET /goals/{id}",
    "PUT /goals/{id}",
    "DELETE /goals/{id}",
  ]
}

resource "aws_apigatewayv2_route" "goals" {
  for_each = toset(local.goals_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.goals.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
  authorization_type = "JWT"
}
