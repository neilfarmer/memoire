# ── Finances Lambda ───────────────────────────────────────────────────────────

resource "aws_iam_role" "finances" {
  name               = "${local.name_prefix}-finances"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "finances_basic" {
  role       = aws_iam_role.finances.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "finances" {
  function_name                  = "${local.name_prefix}-finances"
  runtime                        = var.lambda_runtime
  handler                        = "handler.lambda_handler"
  role                           = aws_iam_role.finances.arn
  filename                       = data.archive_file.lambda_finances.output_path
  source_code_hash               = data.archive_file.lambda_finances.output_base64sha256
  layers                         = [aws_lambda_layer_version.shared.arn]
  timeout                        = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      DEBTS_TABLE    = aws_dynamodb_table.debts.name
      INCOME_TABLE   = aws_dynamodb_table.income.name
      EXPENSES_TABLE = aws_dynamodb_table.fixed_expenses.name
    }
  }
}

resource "aws_cloudwatch_log_group" "finances" {
  name              = "/aws/lambda/${aws_lambda_function.finances.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "finances_dynamodb" {
  name = "${local.name_prefix}-finances-dynamodb"
  role = aws_iam_role.finances.id

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
      Resource = [
        aws_dynamodb_table.debts.arn,
        aws_dynamodb_table.income.arn,
        aws_dynamodb_table.fixed_expenses.arn,
      ]
    }]
  })
}

resource "aws_lambda_permission" "finances_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.finances.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "finances" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.finances.invoke_arn
  payload_format_version = "2.0"
}

locals {
  finances_routes = [
    "GET /debts",
    "POST /debts",
    "PUT /debts/{id}",
    "DELETE /debts/{id}",
    "GET /income",
    "POST /income",
    "PUT /income/{id}",
    "DELETE /income/{id}",
    "GET /fixed-expenses",
    "POST /fixed-expenses",
    "PUT /fixed-expenses/{id}",
    "DELETE /fixed-expenses/{id}",
    "GET /finances/summary",
  ]
}

resource "aws_apigatewayv2_route" "finances" {
  for_each = toset(local.finances_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.finances.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
