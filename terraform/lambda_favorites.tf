# ── Favorites Lambda ──────────────────────────────────────────────────────────

resource "aws_iam_role" "favorites" {
  name               = "${local.name_prefix}-favorites"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "favorites_basic" {
  role       = aws_iam_role.favorites.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "favorites" {
  function_name                  = "${local.name_prefix}-favorites"
  runtime                        = var.lambda_runtime
  handler                        = "handler.lambda_handler"
  role                           = aws_iam_role.favorites.arn
  filename                       = data.archive_file.lambda_favorites.output_path
  source_code_hash               = data.archive_file.lambda_favorites.output_base64sha256
  layers                         = [aws_lambda_layer_version.shared.arn]
  timeout                        = 15
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      FAVORITES_TABLE = aws_dynamodb_table.favorites.name
    }
  }
}

resource "aws_cloudwatch_log_group" "favorites" {
  name              = "/aws/lambda/${aws_lambda_function.favorites.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "favorites_dynamodb" {
  name = "${local.name_prefix}-favorites-dynamodb"
  role = aws_iam_role.favorites.id

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
          "dynamodb:UpdateItem",
        ]
        Resource = aws_dynamodb_table.favorites.arn
      },
    ]
  })
}

resource "aws_lambda_permission" "favorites_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.favorites.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "favorites" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.favorites.invoke_arn
  payload_format_version = "2.0"
}

locals {
  favorites_routes = [
    "GET /favorites",
    "POST /favorites",
    "DELETE /favorites/{id}",
    "PATCH /favorites/{id}",
  ]
}

resource "aws_apigatewayv2_route" "favorites" {
  for_each = toset(local.favorites_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.favorites.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
