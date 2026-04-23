# ── Assistant Lambda ──────────────────────────────────────────────────────────

resource "aws_iam_role" "assistant" {
  name               = "${local.name_prefix}-assistant"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "assistant_basic" {
  role       = aws_iam_role.assistant.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "assistant" {
  function_name                  = "${local.name_prefix}-assistant"
  runtime                        = var.lambda_runtime
  handler                        = "handler.lambda_handler"
  role                           = aws_iam_role.assistant.arn
  filename                       = data.archive_file.lambda_assistant.output_path
  source_code_hash               = data.archive_file.lambda_assistant.output_base64sha256
  layers                         = [aws_lambda_layer_version.shared.arn]
  timeout                        = 60
  memory_size                    = 256
  reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      CONVERSATIONS_TABLE     = aws_dynamodb_table.assistant_conversations.name
      MEMORY_TABLE            = aws_dynamodb_table.assistant_memory.name
      EVENTS_TABLE            = aws_dynamodb_table.assistant_events.name
      TASKS_TABLE             = aws_dynamodb_table.tasks.name
      NOTES_TABLE             = aws_dynamodb_table.notes.name
      NOTE_FOLDERS_TABLE      = aws_dynamodb_table.note_folders.name
      HABITS_TABLE            = aws_dynamodb_table.habits.name
      GOALS_TABLE             = aws_dynamodb_table.goals.name
      JOURNAL_TABLE           = aws_dynamodb_table.journal.name
      NUTRITION_TABLE         = aws_dynamodb_table.nutrition.name
      HEALTH_TABLE            = aws_dynamodb_table.health.name
      SETTINGS_TABLE          = aws_dynamodb_table.settings.name
      ASSISTANT_MODEL_ID      = var.assistant_model_id
      ASSISTANT_SYSTEM_PROMPT = var.assistant_system_prompt
      USDA_API_KEY            = var.usda_api_key
    }
  }
}

resource "aws_cloudwatch_log_group" "assistant" {
  name              = "/aws/lambda/${aws_lambda_function.assistant.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "assistant_dynamodb" {
  name = "${local.name_prefix}-assistant-dynamodb"
  role = aws_iam_role.assistant.id

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
        "dynamodb:BatchWriteItem",
      ]
      Resource = [
        aws_dynamodb_table.assistant_conversations.arn,
        aws_dynamodb_table.assistant_memory.arn,
        aws_dynamodb_table.assistant_events.arn,
        aws_dynamodb_table.tasks.arn,
        aws_dynamodb_table.notes.arn,
        aws_dynamodb_table.note_folders.arn,
        aws_dynamodb_table.habits.arn,
        aws_dynamodb_table.goals.arn,
        aws_dynamodb_table.journal.arn,
        aws_dynamodb_table.nutrition.arn,
        aws_dynamodb_table.health.arn,
      ]
      }, {
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
      ]
      Resource = [
        aws_dynamodb_table.settings.arn,
      ]
    }]
  })
}

resource "aws_iam_role_policy" "assistant_bedrock" {
  name = "${local.name_prefix}-assistant-bedrock"
  role = aws_iam_role.assistant.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
      ]
      Resource = [
        "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
        "arn:aws:bedrock:*::foundation-model/amazon.nova-pro-v1:0",
        "arn:aws:bedrock:*::foundation-model/amazon.nova-premier-v1:0",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:${var.aws_region}:*:inference-profile/us.amazon.nova-lite-v1:0",
        "arn:aws:bedrock:${var.aws_region}:*:inference-profile/us.amazon.nova-pro-v1:0",
        "arn:aws:bedrock:${var.aws_region}:*:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
      ]
    }]
  })
}



resource "aws_lambda_permission" "assistant_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.assistant.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway integration + route ──────────────────────────────────────────

resource "aws_apigatewayv2_integration" "assistant" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.assistant.invoke_arn
  payload_format_version = "2.0"
}

locals {
  assistant_routes = [
    "POST /assistant/chat",
    "GET /assistant/history",
    "DELETE /assistant/history",
    "GET /assistant/conversations",
    "POST /assistant/conversations",
    "GET /assistant/conversations/{id}",
    "PATCH /assistant/conversations/{id}",
    "DELETE /assistant/conversations/{id}",
    "GET /assistant/usage",
    "GET /assistant/memory",
    "PUT /assistant/memory",
    "PUT /assistant/memory/facts/{key}",
    "DELETE /assistant/memory/{key}",
    "GET /assistant/profile",
    "PUT /assistant/profile",
    "POST /assistant/profile/analyze",
  ]
}

resource "aws_apigatewayv2_route" "assistant" {
  for_each = toset(local.assistant_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.assistant.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda.id
  authorization_type = "CUSTOM"
}
