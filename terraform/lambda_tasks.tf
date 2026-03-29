# ── Tasks Lambda ─────────────────────────────────────────────────────────────

resource "aws_lambda_function" "tasks" {
  function_name    = "${local.name_prefix}-tasks"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_tasks.output_path
  source_code_hash = data.archive_file.lambda_tasks.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.tasks.name
    }
  }
}

resource "aws_cloudwatch_log_group" "tasks" {
  name              = "/aws/lambda/${aws_lambda_function.tasks.function_name}"
  retention_in_days = var.log_retention_days
}

# DynamoDB permissions scoped to the tasks table only
resource "aws_iam_role_policy" "tasks_dynamodb" {
  name = "${local.name_prefix}-tasks-dynamodb"
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
      Resource = aws_dynamodb_table.tasks.arn
    }]
  })
}

# Allow API Gateway to invoke this Lambda
resource "aws_lambda_permission" "tasks_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.tasks.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "tasks" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.tasks.invoke_arn
  payload_format_version = "2.0"
}

locals {
  tasks_routes = [
    "GET /tasks",
    "POST /tasks",
    "GET /tasks/{id}",
    "PUT /tasks/{id}",
    "DELETE /tasks/{id}",
  ]
}

resource "aws_apigatewayv2_route" "tasks" {
  for_each = toset(local.tasks_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.tasks.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
  authorization_type = "JWT"
}
