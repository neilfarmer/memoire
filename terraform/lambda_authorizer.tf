# ── Authorizer Lambda ─────────────────────────────────────────────────────────
#
# Custom REQUEST authorizer that validates both Cognito JWTs and Personal Access
# Tokens (PATs). Replaces the built-in JWT authorizer for all user-facing routes.
#
# JWT validation: pure Python RS256/PKCS1v1.5 using stdlib pow() + hashlib.
# PAT validation: SHA-256 lookup against the tokens DynamoDB GSI.

resource "aws_lambda_function" "authorizer" {
  function_name    = "${local.name_prefix}-authorizer"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_authorizer.output_path
  source_code_hash = data.archive_file.lambda_authorizer.output_base64sha256
  timeout          = 10
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      TOKENS_TABLE = aws_dynamodb_table.tokens.name
      JWKS_URI     = "${local.auth_jwt_issuer_url}/.well-known/jwks.json"
      JWT_ISSUER   = local.auth_jwt_issuer_url
      JWT_AUDIENCE = local.auth_jwt_client_id
    }
  }
}

resource "aws_cloudwatch_log_group" "authorizer" {
  name              = "/aws/lambda/${aws_lambda_function.authorizer.function_name}"
  retention_in_days = var.log_retention_days
}

# Allow API Gateway to invoke the authorizer Lambda
resource "aws_lambda_permission" "authorizer_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# Read access to the tokens GSI so the authorizer can validate PATs
resource "aws_iam_role_policy" "authorizer_dynamodb" {
  name = "${local.name_prefix}-authorizer-dynamodb"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:Query"]
      Resource = ["${aws_dynamodb_table.tokens.arn}/index/token-hash-index"]
    }]
  })
}
