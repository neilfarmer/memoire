# Verify every DynamoDB table has point-in-time recovery enabled.
# Adding a new table without PITR will cause this test to fail.

mock_provider "aws" {
  # assume_role_policy requires valid JSON; mock_provider returns a placeholder
  # string by default which fails provider validation. Supply a minimal valid
  # policy so the plan can proceed.
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}
mock_provider "archive" {}
mock_provider "random" {}
mock_provider "cloudflare" {}

run "all_tables_have_pitr_enabled" {
  command = plan

  assert {
    condition     = aws_dynamodb_table.tasks.point_in_time_recovery[0].enabled
    error_message = "tasks: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.settings.point_in_time_recovery[0].enabled
    error_message = "settings: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.habits.point_in_time_recovery[0].enabled
    error_message = "habits: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.habit_logs.point_in_time_recovery[0].enabled
    error_message = "habit_logs: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.habit_logs_v2.point_in_time_recovery[0].enabled
    error_message = "habit_logs_v2: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.journal.point_in_time_recovery[0].enabled
    error_message = "journal: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.note_folders.point_in_time_recovery[0].enabled
    error_message = "note_folders: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.notes.point_in_time_recovery[0].enabled
    error_message = "notes: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.health.point_in_time_recovery[0].enabled
    error_message = "health: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.nutrition.point_in_time_recovery[0].enabled
    error_message = "nutrition: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.goals.point_in_time_recovery[0].enabled
    error_message = "goals: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.tokens.point_in_time_recovery[0].enabled
    error_message = "tokens: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.assistant_conversations.point_in_time_recovery[0].enabled
    error_message = "assistant_conversations: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.assistant_memory.point_in_time_recovery[0].enabled
    error_message = "assistant_memory: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.task_folders.point_in_time_recovery[0].enabled
    error_message = "task_folders: PITR must be enabled"
  }
  assert {
    condition     = aws_dynamodb_table.links.point_in_time_recovery[0].enabled
    error_message = "links: PITR must be enabled"
  }
}
