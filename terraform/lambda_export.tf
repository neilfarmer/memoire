# ── Export Lambda ─────────────────────────────────────────────────────────────

resource "aws_iam_role" "export" {
  name               = "${local.name_prefix}-export"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "export_basic" {
  role       = aws_iam_role.export.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "export" {
  function_name    = "${local.name_prefix}-export"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.export.arn
  filename         = data.archive_file.lambda_export.output_path
  source_code_hash = data.archive_file.lambda_export.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      TASKS_TABLE        = aws_dynamodb_table.tasks.name
      TASK_FOLDERS_TABLE = aws_dynamodb_table.task_folders.name
      JOURNAL_TABLE      = aws_dynamodb_table.journal.name
      NOTES_TABLE        = aws_dynamodb_table.notes.name
      FOLDERS_TABLE      = aws_dynamodb_table.note_folders.name
      HEALTH_TABLE       = aws_dynamodb_table.health.name
      NUTRITION_TABLE    = aws_dynamodb_table.nutrition.name
      GOALS_TABLE        = aws_dynamodb_table.goals.name
      HABITS_TABLE       = aws_dynamodb_table.habits.name
      HABIT_LOGS_TABLE   = aws_dynamodb_table.habit_logs_v2.name
      FRONTEND_BUCKET    = aws_s3_bucket.frontend.id
    }
  }
}

resource "aws_cloudwatch_log_group" "export" {
  name              = "/aws/lambda/${aws_lambda_function.export.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "export_dynamodb" {
  name = "${local.name_prefix}-export-dynamodb"
  role = aws_iam_role.export.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["dynamodb:Query"]
      Resource = [
        aws_dynamodb_table.tasks.arn,
        aws_dynamodb_table.task_folders.arn,
        aws_dynamodb_table.journal.arn,
        aws_dynamodb_table.notes.arn,
        aws_dynamodb_table.note_folders.arn,
        aws_dynamodb_table.health.arn,
        aws_dynamodb_table.nutrition.arn,
        aws_dynamodb_table.goals.arn,
        aws_dynamodb_table.habits.arn,
        aws_dynamodb_table.habit_logs_v2.arn,
      ]
    }]
  })
}

resource "aws_iam_role_policy" "export_s3" {
  name = "${local.name_prefix}-export-s3"
  role = aws_iam_role.export.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = [
          "${aws_s3_bucket.frontend.arn}/note-images/*",
          "${aws_s3_bucket.frontend.arn}/note-attachments/*",
          "${aws_s3_bucket.frontend.arn}/exports/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.frontend.arn}/exports/*"]
      },
    ]
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
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
