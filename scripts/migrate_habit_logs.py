#!/usr/bin/env python3
"""
Migrate habit_logs → habit_logs_v2.

Old table schema:  PK=habit_id (String), SK=log_date (String)
New table schema:  PK=user_id  (String), SK=log_id  (String, "{habit_id}#{log_date}")

The habits table (PK=user_id, SK=habit_id) is used to look up the user_id
for each habit so that each log can be migrated with the correct owner.

Usage:
    AWS_PROFILE=<profile> python scripts/migrate_habit_logs.py \
        --old-table <name> \
        --new-table <name> \
        --habits-table <name> \
        [--dry-run]

    # Or use terraform output names directly:
    source .env
    OLD=$(AWS_PROFILE=$AWS_PROFILE aws dynamodb list-tables --query \
        "TableNames[?contains(@,'habit-logs')]" --output text | tr '\t' '\n' \
        | grep -v v2 | head -1)
    NEW=$(AWS_PROFILE=$AWS_PROFILE aws dynamodb list-tables --query \
        "TableNames[?contains(@,'habit-logs-v2')]" --output text | head -1)
    HBT=$(AWS_PROFILE=$AWS_PROFILE aws dynamodb list-tables --query \
        "TableNames[?contains(@,'-habits')]" --output text | head -1)
    python scripts/migrate_habit_logs.py \
        --old-table "$OLD" --new-table "$NEW" --habits-table "$HBT"
"""

import argparse
import sys

import boto3
from boto3.dynamodb.conditions import Key


def _scan_all(table):
    resp  = table.scan()
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def _build_habit_user_map(habits_table):
    """Return {habit_id: user_id} for every habit."""
    habits = _scan_all(habits_table)
    return {h["habit_id"]: h["user_id"] for h in habits}


def migrate(old_table_name: str, new_table_name: str, habits_table_name: str, dry_run: bool):
    dynamo = boto3.resource("dynamodb")
    old_table    = dynamo.Table(old_table_name)
    new_table    = dynamo.Table(new_table_name)
    habits_table = dynamo.Table(habits_table_name)

    print(f"Building habit → user_id map from {habits_table_name}...")
    habit_user = _build_habit_user_map(habits_table)
    print(f"  Found {len(habit_user)} habits.")

    print(f"Scanning old table {old_table_name}...")
    old_logs = _scan_all(old_table)
    print(f"  Found {len(old_logs)} log entries.")

    skipped = 0
    migrated = 0

    with new_table.batch_writer() as batch:
        for log in old_logs:
            habit_id = log.get("habit_id")
            log_date = log.get("log_date")

            if not habit_id or not log_date:
                print(f"  SKIP (missing fields): {log}", file=sys.stderr)
                skipped += 1
                continue

            user_id = habit_user.get(habit_id)
            if not user_id:
                print(f"  SKIP (no habit found for habit_id={habit_id}): log_date={log_date}", file=sys.stderr)
                skipped += 1
                continue

            new_item = {
                "user_id": user_id,
                "log_id":  f"{habit_id}#{log_date}",
                "habit_id": habit_id,
            }

            if dry_run:
                print(f"  [DRY RUN] Would write: {new_item}")
            else:
                batch.put_item(Item=new_item)

            migrated += 1

    print(f"\nDone. migrated={migrated}, skipped={skipped}")
    if dry_run:
        print("(dry run — no items were written)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate habit_logs to habit_logs_v2")
    parser.add_argument("--old-table",    required=True, help="Source table name (habit-logs)")
    parser.add_argument("--new-table",    required=True, help="Destination table name (habit-logs-v2)")
    parser.add_argument("--habits-table", required=True, help="Habits table name (for user_id lookup)")
    parser.add_argument("--dry-run",      action="store_true", help="Print what would be written without writing")
    args = parser.parse_args()

    migrate(args.old_table, args.new_table, args.habits_table, args.dry_run)
