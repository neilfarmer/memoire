# ── Tokens Lambda (Personal Access Token management) ──────────────────────────
#
# CRUD endpoints for creating and revoking PATs.
# Routes are protected by the Cognito JWT authorizer only —
# PATs cannot be used to create or revoke other PATs.

resource "aws_lambda_function" "tokens" {
  function_name    = "${local.name_prefix}-tokens"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_tokens.output_path
  source_code_hash = data.archive_file.lambda_tokens.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.tokens.name
    }
  }
}

resource "aws_cloudwatch_log_group" "tokens" {
  name              = "/aws/lambda/${aws_lambda_function.tokens.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "tokens_dynamodb" {
  name = "${local.name_prefix}-tokens-dynamodb"
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
      ]
      Resource = [aws_dynamodb_table.tokens.arn]
    }]
  })
}

resource "aws_lambda_permission" "tokens_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.tokens.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "tokens" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.tokens.invoke_arn
  payload_format_version = "2.0"
}

locals {
  tokens_routes = [
    "GET /tokens",
    "POST /tokens",
    "DELETE /tokens/{id}",
  ]
}

# Token management routes require Cognito JWT auth only.
# PATs cannot be used to manage other PATs.
resource "aws_apigatewayv2_route" "tokens" {
  for_each = toset(local.tokens_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.tokens.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
  authorization_type = "JWT"
}
