# ── Export Lambda ─────────────────────────────────────────────────────────────

resource "aws_lambda_function" "export" {
  function_name    = "${local.name_prefix}-export"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_export.output_path
  source_code_hash = data.archive_file.lambda_export.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      TASKS_TABLE      = aws_dynamodb_table.tasks.name
      JOURNAL_TABLE    = aws_dynamodb_table.journal.name
      NOTES_TABLE      = aws_dynamodb_table.notes.name
      FOLDERS_TABLE    = aws_dynamodb_table.note_folders.name
      HEALTH_TABLE     = aws_dynamodb_table.health.name
      NUTRITION_TABLE  = aws_dynamodb_table.nutrition.name
      FRONTEND_BUCKET  = aws_s3_bucket.frontend.id
    }
  }
}

resource "aws_cloudwatch_log_group" "export" {
  name              = "/aws/lambda/${aws_lambda_function.export.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "export_dynamodb" {
  name = "${local.name_prefix}-export-dynamodb"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["dynamodb:Query"]
      Resource = [
        aws_dynamodb_table.tasks.arn,
        aws_dynamodb_table.journal.arn,
        aws_dynamodb_table.notes.arn,
        aws_dynamodb_table.note_folders.arn,
        aws_dynamodb_table.health.arn,
        aws_dynamodb_table.nutrition.arn,
      ]
    }]
  })
}

resource "aws_iam_role_policy" "export_s3" {
  name = "${local.name_prefix}-export-s3"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = [
        "${aws_s3_bucket.frontend.arn}/note-images/*",
        "${aws_s3_bucket.frontend.arn}/note-attachments/*",
      ]
    }]
  })
}

resource "aws_lambda_permission" "export_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.export.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + route ──────────────────────────────────────────

resource "aws_apigatewayv2_integration" "export" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.export.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "export" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /export"
  target             = "integrations/${aws_apigatewayv2_integration.export.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}
