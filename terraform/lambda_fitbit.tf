# ── Fitbit Lambda ─────────────────────────────────────────────────────────────
#
# Handles OAuth2 connect/callback/disconnect plus the read endpoint that
# returns today's cached Fitbit data. Data is fetched and stored by the
# separate fitbit_sync Lambda on a 30-minute schedule.

resource "aws_iam_role" "fitbit" {
  name               = "${local.name_prefix}-fitbit"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "fitbit_basic" {
  role       = aws_iam_role.fitbit.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "fitbit" {
  function_name    = "${local.name_prefix}-fitbit"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.fitbit.arn
  filename         = data.archive_file.lambda_fitbit.output_path
  source_code_hash = data.archive_file.lambda_fitbit.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  # 60s — `log_food` invokes the sync Lambda asynchronously now, but other
  # routes (search, status, today) make outbound Fitbit API calls (each up
  # to 10s) and need headroom. Stay under API Gateway's 29s read timeout
  # for synchronous routes; longer ops should fire-and-forget instead.
  timeout                        = 60
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      FITBIT_TOKENS_TABLE  = aws_dynamodb_table.fitbit_tokens.name
      FITBIT_DATA_TABLE    = aws_dynamodb_table.fitbit_data.name
      FITBIT_SYNC_FUNCTION = aws_lambda_function.fitbit_sync.function_name
      FITBIT_CLIENT_ID     = var.fitbit_client_id
      FITBIT_CLIENT_SECRET = var.fitbit_client_secret
    }
  }
}

resource "aws_cloudwatch_log_group" "fitbit" {
  name              = "/aws/lambda/${aws_lambda_function.fitbit.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "fitbit_dynamodb" {
  name = "${local.name_prefix}-fitbit-dynamodb"
  role = aws_iam_role.fitbit.id

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
        Resource = [
          aws_dynamodb_table.fitbit_tokens.arn,
          aws_dynamodb_table.fitbit_data.arn,
        ]
      },
    ]
  })
}

resource "aws_iam_role_policy" "fitbit_invoke_sync" {
  name = "${local.name_prefix}-fitbit-invoke-sync"
  role = aws_iam_role.fitbit.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.fitbit_sync.arn
    }]
  })
}

resource "aws_lambda_permission" "fitbit_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fitbit.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "fitbit" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fitbit.invoke_arn
  payload_format_version = "2.0"
}

locals {
  fitbit_routes = [
    "GET /fitbit/today",
    "GET /fitbit/status",
    "GET /fitbit/auth/start",
    "POST /fitbit/auth/callback",
    "POST /fitbit/disconnect",
    "POST /fitbit/sync",
    "POST /fitbit/food",
    "GET /fitbit/food/search",
    "GET /fitbit/history",
  ]
}

resource "aws_apigatewayv2_route" "fitbit" {
  for_each = toset(local.fitbit_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.fitbit.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
