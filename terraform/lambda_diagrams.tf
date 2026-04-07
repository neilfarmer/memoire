# ── Diagrams Lambda ────────────────────────────────────────────────────────────

resource "aws_iam_role" "diagrams" {
  name               = "${local.name_prefix}-diagrams"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "diagrams_basic" {
  role       = aws_iam_role.diagrams.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "diagrams" {
  function_name                  = "${local.name_prefix}-diagrams"
  runtime                        = var.lambda_runtime
  handler                        = "handler.lambda_handler"
  role                           = aws_iam_role.diagrams.arn
  filename                       = data.archive_file.lambda_diagrams.output_path
  source_code_hash               = data.archive_file.lambda_diagrams.output_base64sha256
  layers                         = [aws_lambda_layer_version.shared.arn]
  timeout                        = 15
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      DIAGRAMS_TABLE = aws_dynamodb_table.diagrams.name
    }
  }
}

resource "aws_cloudwatch_log_group" "diagrams" {
  name              = "/aws/lambda/${aws_lambda_function.diagrams.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "diagrams_dynamodb" {
  name = "${local.name_prefix}-diagrams-dynamodb"
  role = aws_iam_role.diagrams.id

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
        Resource = aws_dynamodb_table.diagrams.arn
      },
    ]
  })
}

resource "aws_lambda_permission" "diagrams_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.diagrams.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "diagrams" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.diagrams.invoke_arn
  payload_format_version = "2.0"
}

locals {
  diagrams_routes = [
    "GET /diagrams",
    "POST /diagrams",
    "GET /diagrams/{id}",
    "PUT /diagrams/{id}",
    "DELETE /diagrams/{id}",
  ]
}

resource "aws_apigatewayv2_route" "diagrams" {
  for_each = toset(local.diagrams_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.diagrams.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
