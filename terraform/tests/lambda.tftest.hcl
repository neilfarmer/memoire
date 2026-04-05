# Verify every Lambda function uses the shared runtime variable and every
# CloudWatch log group has a retention period set.
# Adding a new Lambda without wiring up these settings will fail this test.

mock_provider "aws" {}
mock_provider "archive" {}
mock_provider "random" {}
mock_provider "cloudflare" {}

run "all_lambdas_use_runtime_variable" {
  command = plan

  assert {
    condition     = aws_lambda_function.tasks.runtime == var.lambda_runtime
    error_message = "tasks: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.settings.runtime == var.lambda_runtime
    error_message = "settings: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.watcher.runtime == var.lambda_runtime
    error_message = "watcher: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.habits.runtime == var.lambda_runtime
    error_message = "habits: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.journal.runtime == var.lambda_runtime
    error_message = "journal: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.notes.runtime == var.lambda_runtime
    error_message = "notes: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.home.runtime == var.lambda_runtime
    error_message = "home: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.export.runtime == var.lambda_runtime
    error_message = "export: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.health.runtime == var.lambda_runtime
    error_message = "health: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.nutrition.runtime == var.lambda_runtime
    error_message = "nutrition: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.goals.runtime == var.lambda_runtime
    error_message = "goals: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.authorizer.runtime == var.lambda_runtime
    error_message = "authorizer: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.tokens.runtime == var.lambda_runtime
    error_message = "tokens: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.assistant.runtime == var.lambda_runtime
    error_message = "assistant: runtime must use var.lambda_runtime"
  }
  assert {
    condition     = aws_lambda_function.auth.runtime == var.lambda_runtime
    error_message = "auth: runtime must use var.lambda_runtime"
  }
}

run "all_log_groups_have_retention" {
  command = plan

  assert {
    condition     = aws_cloudwatch_log_group.tasks.retention_in_days == var.log_retention_days
    error_message = "tasks log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.settings.retention_in_days == var.log_retention_days
    error_message = "settings log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.watcher.retention_in_days == var.log_retention_days
    error_message = "watcher log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.habits.retention_in_days == var.log_retention_days
    error_message = "habits log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.journal.retention_in_days == var.log_retention_days
    error_message = "journal log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.notes.retention_in_days == var.log_retention_days
    error_message = "notes log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.home.retention_in_days == var.log_retention_days
    error_message = "home log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.export.retention_in_days == var.log_retention_days
    error_message = "export log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.health.retention_in_days == var.log_retention_days
    error_message = "health log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.nutrition.retention_in_days == var.log_retention_days
    error_message = "nutrition log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.goals.retention_in_days == var.log_retention_days
    error_message = "goals log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.authorizer.retention_in_days == var.log_retention_days
    error_message = "authorizer log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.tokens.retention_in_days == var.log_retention_days
    error_message = "tokens log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.assistant.retention_in_days == var.log_retention_days
    error_message = "assistant log group: retention_in_days must use var.log_retention_days"
  }
  assert {
    condition     = aws_cloudwatch_log_group.auth.retention_in_days == var.log_retention_days
    error_message = "auth log group: retention_in_days must use var.log_retention_days"
  }
}
