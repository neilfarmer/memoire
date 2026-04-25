# ── Links Lambda ──────────────────────────────────────────────────────────────
#
# Read-only endpoints for the wiki-link graph. Writes happen inside the
# source feature Lambdas (notes, journal, tasks) via the shared
# lambda/layer/python/links_util.py helper.

resource "aws_iam_role" "links" {
  name               = "${local.name_prefix}-links"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "links_basic" {
  role       = aws_iam_role.links.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "links" {
  function_name                  = "${local.name_prefix}-links"
  runtime                        = var.lambda_runtime
  handler                        = "handler.lambda_handler"
  role                           = aws_iam_role.links.arn
  filename                       = data.archive_file.lambda_links.output_path
  source_code_hash               = data.archive_file.lambda_links.output_base64sha256
  layers                         = [aws_lambda_layer_version.shared.arn]
  timeout                        = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      LINKS_TABLE = aws_dynamodb_table.links.name
    }
  }
}

resource "aws_cloudwatch_log_group" "links" {
  name              = "/aws/lambda/${aws_lambda_function.links.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "links_dynamodb" {
  name = "${local.name_prefix}-links-dynamodb"
  role = aws_iam_role.links.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:Query",
      ]
      Resource = [
        aws_dynamodb_table.links.arn,
        "${aws_dynamodb_table.links.arn}/index/*",
      ]
    }]
  })
}

resource "aws_lambda_permission" "links_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.links.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "links" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.links.invoke_arn
  payload_format_version = "2.0"
}

locals {
  links_routes = [
    "GET /links",
    "GET /backlinks",
  ]
}

resource "aws_apigatewayv2_route" "links" {
  for_each = toset(local.links_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.links.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
