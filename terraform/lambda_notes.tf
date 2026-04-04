# ── Notes Lambda ─────────────────────────────────────────────────────────────

resource "aws_iam_role" "notes" {
  name               = "${local.name_prefix}-notes"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "notes_basic" {
  role       = aws_iam_role.notes.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "notes" {
  function_name    = "${local.name_prefix}-notes"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.notes.arn
  filename         = data.archive_file.lambda_notes.output_path
  source_code_hash = data.archive_file.lambda_notes.output_base64sha256
  layers           = [aws_lambda_layer_version.shared.arn]
  timeout          = var.lambda_timeout
  memory_size                    = var.lambda_memory_mb
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      FOLDERS_TABLE  = aws_dynamodb_table.note_folders.name
      NOTES_TABLE    = aws_dynamodb_table.notes.name
      FRONTEND_BUCKET = aws_s3_bucket.frontend.id
      CLOUDFRONT_URL  = "https://${aws_cloudfront_distribution.frontend.domain_name}"
    }
  }
}

resource "aws_cloudwatch_log_group" "notes" {
  name              = "/aws/lambda/${aws_lambda_function.notes.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "notes_dynamodb" {
  name = "${local.name_prefix}-notes-dynamodb"
  role = aws_iam_role.notes.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:BatchWriteItem",
        ]
        Resource = aws_dynamodb_table.note_folders.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchWriteItem",
        ]
        Resource = aws_dynamodb_table.notes.arn
      },
    ]
  })
}

resource "aws_iam_role_policy" "notes_s3" {
  name = "${local.name_prefix}-notes-s3"
  role = aws_iam_role.notes.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = [
          "${aws_s3_bucket.frontend.arn}/note-images/*",
          "${aws_s3_bucket.frontend.arn}/note-attachments/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.frontend.arn}/note-images/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.frontend.arn}/note-attachments/*"
      },
    ]
  })
}

resource "aws_lambda_permission" "notes_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notes.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + routes ─────────────────────────────────────────

resource "aws_apigatewayv2_integration" "notes" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.notes.invoke_arn
  payload_format_version = "2.0"
}

locals {
  notes_routes = [
    "GET /notes/folders",
    "POST /notes/folders",
    "PUT /notes/folders/{id}",
    "DELETE /notes/folders/{id}",
    "POST /notes/images",
    "GET /notes/images",
    "POST /notes/{id}/attachments",
    "GET /notes/{id}/attachments/{att_id}",
    "DELETE /notes/{id}/attachments/{att_id}",
    "GET /notes",
    "GET /notes/{id}",
    "POST /notes",
    "PUT /notes/{id}",
    "DELETE /notes/{id}",
  ]
}

resource "aws_apigatewayv2_route" "notes" {
  for_each = toset(local.notes_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.notes.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
