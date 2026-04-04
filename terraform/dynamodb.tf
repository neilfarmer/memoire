# ── Tasks table ───────────────────────────────────────────────────────────────
#
# PK: user_id  (String) — Cognito sub claim
# SK: task_id  (String) — UUID generated at creation
#
# Access patterns:
#   List all tasks for a user  → Query PK=user_id
#   Get a single task          → GetItem PK=user_id, SK=task_id
#   Create / update / delete   → PutItem / UpdateItem / DeleteItem

resource "aws_dynamodb_table" "tasks" {
  name         = "${local.name_prefix}-tasks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "task_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "task_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Settings table ────────────────────────────────────────────────────────────
#
# PK: user_id  (String) — one item per user, no sort key
#
# Access patterns:
#   Get settings for a user    → GetItem PK=user_id
#   Create / update settings   → UpdateItem PK=user_id

resource "aws_dynamodb_table" "settings" {
  name         = "${local.name_prefix}-settings"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Habits table ──────────────────────────────────────────────────────────────
#
# PK: user_id   (String) — Cognito sub claim
# SK: habit_id  (String) — UUID generated at creation

resource "aws_dynamodb_table" "habits" {
  name         = "${local.name_prefix}-habits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "habit_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "habit_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Habit logs table (deprecated — kept until data migration is complete) ──────
#
# DO NOT WRITE TO THIS TABLE. All Lambda functions now use habit_logs_v2.
# Remove this resource once migrate_habit_logs.py has been run in production.

resource "aws_dynamodb_table" "habit_logs" {
  name         = "${local.name_prefix}-habit-logs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "habit_id"
  range_key    = "log_date"

  attribute {
    name = "habit_id"
    type = "S"
  }

  attribute {
    name = "log_date"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Habit logs v2 table ────────────────────────────────────────────────────────
#
# PK: user_id  (String) — Cognito sub, enforces per-user isolation
# SK: log_id   (String) — composite "{habit_id}#{log_date}" (YYYY-MM-DD)
#
# Access patterns:
#   Logs for a habit in a date range → Query PK=user_id, SK between
#                                      "{habit_id}#{from}" and "{habit_id}#{to}"
#   Toggle a specific day            → GetItem / PutItem / DeleteItem on
#                                      PK=user_id, SK="{habit_id}#{date}"
#   Delete all logs for a habit      → Query PK=user_id, SK begins_with
#                                      "{habit_id}#", then batch delete

resource "aws_dynamodb_table" "habit_logs_v2" {
  name         = "${local.name_prefix}-habit-logs-v2"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "log_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "log_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Journal table ─────────────────────────────────────────────────────────────
#
# PK: user_id     (String) — Cognito sub claim
# SK: entry_date  (String) — YYYY-MM-DD, one entry per user per day

resource "aws_dynamodb_table" "journal" {
  name         = "${local.name_prefix}-journal"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "entry_date"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "entry_date"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Note folders table ────────────────────────────────────────────────────────
#
# PK: user_id    (String)
# SK: folder_id  (String) — UUID
# Attr: parent_id (String, optional) — enables nesting

resource "aws_dynamodb_table" "note_folders" {
  name         = "${local.name_prefix}-note-folders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "folder_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "folder_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Notes table ────────────────────────────────────────────────────────────────
#
# PK: user_id  (String)
# SK: note_id  (String) — UUID
# Attr: folder_id (String) — parent folder

resource "aws_dynamodb_table" "notes" {
  name         = "${local.name_prefix}-notes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "note_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "note_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Health table ──────────────────────────────────────────────────────────────
#
# PK: user_id   (String) — Cognito sub claim
# SK: log_date  (String) — YYYY-MM-DD, one log per user per day

resource "aws_dynamodb_table" "health" {
  name         = "${local.name_prefix}-health"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "log_date"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "log_date"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Nutrition table ───────────────────────────────────────────────────────────
#
# PK: user_id   (String) — Cognito sub claim
# SK: log_date  (String) — YYYY-MM-DD, one log per user per day

resource "aws_dynamodb_table" "nutrition" {
  name         = "${local.name_prefix}-nutrition"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "log_date"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "log_date"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Goals table ───────────────────────────────────────────────────────────────
#
# PK: user_id  (String) — Cognito sub claim
# SK: goal_id  (String) — UUID generated at creation

resource "aws_dynamodb_table" "goals" {
  name         = "${local.name_prefix}-goals"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "goal_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "goal_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Personal Access Tokens table ─────────────────────────────────────────────
#
# PK: user_id    (String) — Cognito sub claim
# SK: token_id   (String) — UUID generated at creation
#
# GSI token-hash-index:
#   PK: token_hash  — SHA-256 hex digest of the plaintext PAT
#   The Lambda authorizer queries this index to validate incoming PATs.
#   The plaintext token is never stored; only its hash is persisted.

resource "aws_dynamodb_table" "tokens" {
  name         = "${local.name_prefix}-tokens"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "token_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "token_id"
    type = "S"
  }

  attribute {
    name = "token_hash"
    type = "S"
  }

  global_secondary_index {
    name            = "token-hash-index"
    hash_key        = "token_hash"
    projection_type = "KEYS_ONLY"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ── Task folders table ────────────────────────────────────────────────────────
#
# PK: user_id    (String)
# SK: folder_id  (String) — UUID

resource "aws_dynamodb_table" "task_folders" {
  name         = "${local.name_prefix}-task-folders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key     = "folder_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "folder_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}
