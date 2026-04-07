# ── Feeds Lambda ──────────────────────────────────────────────────────────────

resource "aws_iam_role" "feeds" {
  name               = "${local.name_prefix}-feeds"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "feeds_basic" {
  role       = aws_iam_role.feeds.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "feeds" {
  function_name                  = "${local.name_prefix}-feeds"
  runtime                        = var.lambda_runtime
  handler                        = "handler.lambda_handler"
  role                           = aws_iam_role.feeds.arn
  filename                       = data.archive_file.lambda_feeds.output_path
  source_code_hash               = data.archive_file.lambda_feeds.output_base64sha256
  layers                         = [aws_lambda_layer_version.shared.arn]
  timeout                        = 30
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      FEEDS_TABLE      = aws_dynamodb_table.feeds.name
      FEEDS_READ_TABLE = aws_dynamodb_table.feeds_read.name
    }
  }
}

resource "aws_cloudwatch_log_group" "feeds" {
  name              = "/aws/lambda/${aws_lambda_function.feeds.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "feeds_dynamodb" {
  name = "${local.name_prefix}-feeds-dynamodb"
  role = aws_iam_role.feeds.id

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
        Resource = aws_dynamodb_table.feeds.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:Query",
        ]
        Resource = aws_dynamodb_table.feeds_read.arn
      },
    ]
  })
}

resource "aws_lambda_permission" "feeds_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.feeds.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "feeds" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.feeds.invoke_arn
  payload_format_version = "2.0"
}

locals {
  feeds_routes = [
    "GET /feeds",
    "POST /feeds",
    "DELETE /feeds/{id}",
    "GET /feeds/articles",
    "GET /feeds/article-text",
    "GET /feeds/read",
    "POST /feeds/read",
  ]
}

resource "aws_apigatewayv2_route" "feeds" {
  for_each = toset(local.feeds_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.feeds.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
