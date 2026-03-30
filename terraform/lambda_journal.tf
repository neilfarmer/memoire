# ── Journal Lambda ────────────────────────────────────────────────────────────

resource "aws_lambda_function" "journal" {
  function_name    = "${local.name_prefix}-journal"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_journal.output_path
  source_code_hash = data.archive_file.lambda_journal.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.journal.name
    }
  }
}

resource "aws_cloudwatch_log_group" "journal" {
  name              = "/aws/lambda/${aws_lambda_function.journal.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "journal_dynamodb" {
  name = "${local.name_prefix}-journal-dynamodb"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
      ]
      Resource = aws_dynamodb_table.journal.arn
    }]
  })
}

resource "aws_lambda_permission" "journal_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.journal.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "journal" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.journal.invoke_arn
  payload_format_version = "2.0"
}

locals {
  journal_routes = [
    "GET /journal",
    "GET /journal/{date}",
    "PUT /journal/{date}",
    "DELETE /journal/{date}",
  ]
}

resource "aws_apigatewayv2_route" "journal" {
  for_each = toset(local.journal_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.journal.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
