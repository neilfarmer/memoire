"""Budget CRUD operations against DynamoDB."""

import os
import re
import uuid
from decimal import Decimal, InvalidOperation

import boto3
from response import ok, created, no_content, error, not_found
import db
from utils import now_iso, build_update_expression

_dynamodb_client = boto3.client("dynamodb")

TRANSACTIONS_TABLE = os.environ["TABLE_NAME"]
BUDGETS_TABLE      = os.environ["BUDGETS_TABLE"]
SORT_KEY_TXN       = "transaction_id"
SORT_KEY_BDG       = "budget_id"

VALID_TYPES = {"income", "expense", "debt_payment"}

MAX_CATEGORY_LEN    = 100
MAX_DESCRIPTION_LEN = 1_000


def _txn_table():
    return db.get_table(TRANSACTIONS_TABLE)


def _bdg_table():
    return db.get_table(BUDGETS_TABLE)


def _validate_amount(value, field_name: str = "amount") -> str | None:
    """Return error string if value is not a positive decimal, else None."""
    if value is None:
        return f"{field_name} is required"
    try:
        val = Decimal(str(value))
        if val <= 0:
            return f"{field_name} must be greater than zero"
    except InvalidOperation:
        return f"{field_name} must be a valid number"
    return None


def _validate_month(month: str) -> str | None:
    if not month or not re.match(r"^\d{4}-\d{2}$", month):
        return "month must be YYYY-MM"
    return None


def _validate_date(date: str) -> str | None:
    if not date or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return "date must be YYYY-MM-DD"
    return None


# ── Transactions ──────────────────────────────────────────────────────────────

def list_transactions(user_id: str, query_params: dict) -> dict:
    items = db.query_by_user(_txn_table(), user_id)
    month    = query_params.get("month")
    category = query_params.get("category")
    if month:
        items = [t for t in items if t.get("date", "").startswith(month)]
    if category:
        items = [t for t in items if t.get("category", "").lower() == category.lower()]
    items.sort(key=lambda t: t.get("date", ""), reverse=True)
    return ok(items)


def create_transaction(user_id: str, body: dict) -> dict:
    err = _validate_amount(body.get("amount"))
    if err:
        return error(err)

    txn_type = body.get("type", "expense")
    if txn_type not in VALID_TYPES:
        return error(f"type must be one of: {', '.join(sorted(VALID_TYPES))}")

    category = (body.get("category") or "").strip()
    if not category:
        return error("category is required")
    if len(category) > MAX_CATEGORY_LEN:
        return error(f"category exceeds maximum length of {MAX_CATEGORY_LEN}")

    err = _validate_date(body.get("date"))
    if err:
        return error(err)

    description = (body.get("description") or "").strip()
    if len(description) > MAX_DESCRIPTION_LEN:
        return error(f"description exceeds maximum length of {MAX_DESCRIPTION_LEN}")

    interest_rate = body.get("interest_rate")
    if interest_rate is not None:
        err = _validate_amount(interest_rate, "interest_rate")
        if err:
            # interest_rate of 0 is valid (no interest)
            try:
                ir = Decimal(str(interest_rate))
                if ir < 0:
                    return error("interest_rate must be non-negative")
            except InvalidOperation:
                return error("interest_rate must be a valid number")

    now = now_iso()
    txn = {
        "user_id":        user_id,
        "transaction_id": str(uuid.uuid4()),
        "amount":         str(Decimal(str(body["amount"]))),
        "type":           txn_type,
        "category":       category,
        "description":    description,
        "date":           body["date"],
        "interest_rate":  str(Decimal(str(interest_rate))) if interest_rate is not None else None,
        "created_at":     now,
        "updated_at":     now,
    }
    txn = {k: v for k, v in txn.items() if v is not None}
    _txn_table().put_item(Item=txn)
    return created(txn)


def get_transaction(user_id: str, transaction_id: str) -> dict:
    txn = db.get_item(_txn_table(), user_id, SORT_KEY_TXN, transaction_id)
    if not txn:
        return not_found("Transaction")
    return ok(txn)


def update_transaction(user_id: str, transaction_id: str, body: dict) -> dict:
    updatable = {"amount", "type", "category", "description", "date", "interest_rate"}
    fields = {k: v for k, v in body.items() if k in updatable}
    if not fields:
        return error("No valid fields provided for update")

    if "amount" in fields:
        err = _validate_amount(fields["amount"])
        if err:
            return error(err)
        fields["amount"] = str(Decimal(str(fields["amount"])))

    if "type" in fields and fields["type"] not in VALID_TYPES:
        return error(f"type must be one of: {', '.join(sorted(VALID_TYPES))}")

    if "category" in fields:
        fields["category"] = fields["category"].strip()
        if not fields["category"]:
            return error("category cannot be empty")
        if len(fields["category"]) > MAX_CATEGORY_LEN:
            return error(f"category exceeds maximum length of {MAX_CATEGORY_LEN}")

    if "date" in fields:
        err = _validate_date(fields["date"])
        if err:
            return error(err)

    if "description" in fields and len(fields["description"]) > MAX_DESCRIPTION_LEN:
        return error(f"description exceeds maximum length of {MAX_DESCRIPTION_LEN}")

    if "interest_rate" in fields:
        ir = fields["interest_rate"]
        if ir is not None:
            try:
                ir_val = Decimal(str(ir))
                if ir_val < 0:
                    return error("interest_rate must be non-negative")
                fields["interest_rate"] = str(ir_val)
            except InvalidOperation:
                return error("interest_rate must be a valid number")

    fields["updated_at"] = now_iso()
    update_expr, names, values = build_update_expression(fields)

    try:
        result = _txn_table().update_item(
            Key={"user_id": user_id, SORT_KEY_TXN: transaction_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(transaction_id)",
            ReturnValues="ALL_NEW",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Transaction")

    return ok(result["Attributes"])


def delete_transaction(user_id: str, transaction_id: str) -> dict:
    try:
        _txn_table().delete_item(
            Key={"user_id": user_id, SORT_KEY_TXN: transaction_id},
            ConditionExpression="attribute_exists(transaction_id)",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Transaction")
    return no_content()


# ── Budgets ───────────────────────────────────────────────────────────────────

def list_budgets(user_id: str, query_params: dict) -> dict:
    items = db.query_by_user(_bdg_table(), user_id)
    month = query_params.get("month")
    if month:
        items = [b for b in items if b.get("month") == month]
    return ok(items)


def create_budget(user_id: str, body: dict) -> dict:
    category = (body.get("category") or "").strip()
    if not category:
        return error("category is required")
    if len(category) > MAX_CATEGORY_LEN:
        return error(f"category exceeds maximum length of {MAX_CATEGORY_LEN}")

    err = _validate_amount(body.get("limit"), "limit")
    if err:
        return error(err)

    month = (body.get("month") or "").strip()
    err = _validate_month(month)
    if err:
        return error(err)

    now = now_iso()
    budget = {
        "user_id":    user_id,
        "budget_id":  str(uuid.uuid4()),
        "category":   category,
        "limit":      str(Decimal(str(body["limit"]))),
        "month":      month,
        "created_at": now,
        "updated_at": now,
    }
    _bdg_table().put_item(Item=budget)
    return created(budget)


def update_budget(user_id: str, budget_id: str, body: dict) -> dict:
    updatable = {"category", "limit", "month"}
    fields = {k: v for k, v in body.items() if k in updatable}
    if not fields:
        return error("No valid fields provided for update")

    if "category" in fields:
        fields["category"] = fields["category"].strip()
        if not fields["category"]:
            return error("category cannot be empty")
        if len(fields["category"]) > MAX_CATEGORY_LEN:
            return error(f"category exceeds maximum length of {MAX_CATEGORY_LEN}")

    if "limit" in fields:
        err = _validate_amount(fields["limit"], "limit")
        if err:
            return error(err)
        fields["limit"] = str(Decimal(str(fields["limit"])))

    if "month" in fields:
        err = _validate_month(fields["month"])
        if err:
            return error(err)

    fields["updated_at"] = now_iso()
    update_expr, names, values = build_update_expression(fields)

    try:
        result = _bdg_table().update_item(
            Key={"user_id": user_id, SORT_KEY_BDG: budget_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(budget_id)",
            ReturnValues="ALL_NEW",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Budget")

    return ok(result["Attributes"])


def delete_budget(user_id: str, budget_id: str) -> dict:
    try:
        _bdg_table().delete_item(
            Key={"user_id": user_id, SORT_KEY_BDG: budget_id},
            ConditionExpression="attribute_exists(budget_id)",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Budget")
    return no_content()


# ── Summary ───────────────────────────────────────────────────────────────────

def get_summary(user_id: str, query_params: dict) -> dict:
    month = (query_params.get("month") or "").strip()
    err = _validate_month(month)
    if err:
        return error(err)

    all_txns = db.query_by_user(_txn_table(), user_id)
    txns = [t for t in all_txns if t.get("date", "").startswith(month)]

    all_budgets = db.query_by_user(_bdg_table(), user_id)
    budgets = [b for b in all_budgets if b.get("month") == month]

    total_income  = Decimal("0")
    total_expense = Decimal("0")
    category_spend: dict[str, Decimal] = {}

    for t in txns:
        amt = Decimal(t.get("amount", "0"))
        if t.get("type") == "income":
            total_income += amt
        else:
            total_expense += amt
            cat = t.get("category", "Uncategorized")
            category_spend[cat] = category_spend.get(cat, Decimal("0")) + amt

    net = total_income - total_expense

    budget_by_category = {b["category"]: b for b in budgets}
    all_categories = sorted(set(list(category_spend.keys()) + list(budget_by_category.keys())))

    category_breakdown = []
    for cat in all_categories:
        spent = category_spend.get(cat, Decimal("0"))
        entry: dict = {"category": cat, "spent": str(spent)}
        budget_item = budget_by_category.get(cat)
        if budget_item:
            entry["budget_id"] = budget_item["budget_id"]
            entry["limit"]     = budget_item["limit"]
        category_breakdown.append(entry)

    return ok({
        "month":              month,
        "total_income":       str(total_income),
        "total_expense":      str(total_expense),
        "net":                str(net),
        "category_breakdown": category_breakdown,
        "transaction_count":  len(txns),
    })
