"""Finances CRUD operations against DynamoDB."""

import math
import os
import uuid
from decimal import Decimal, InvalidOperation

from botocore.exceptions import ClientError
from response import ok, created, no_content, error, not_found
import db
from utils import now_iso, build_update_expression

def _is_conditional_check_failed(exc: ClientError) -> bool:
    return exc.response["Error"]["Code"] == "ConditionalCheckFailedException"

DEBTS_TABLE    = os.environ["DEBTS_TABLE"]
INCOME_TABLE   = os.environ["INCOME_TABLE"]
EXPENSES_TABLE = os.environ["EXPENSES_TABLE"]

VALID_DEBT_TYPES = {
    "auto_loan", "mortgage", "credit_card", "student_loan",
    "personal_loan", "line_of_credit", "other",
}
VALID_FREQUENCIES    = {"monthly", "biweekly", "weekly", "annual"}
VALID_EXPENSE_CATS   = {
    "housing", "utilities", "subscriptions", "insurance",
    "food", "transport", "healthcare", "other",
}

MAX_NAME_LEN  = 200
MAX_NOTES_LEN = 1_000

# Multipliers to normalize any frequency to monthly
MONTHLY_MULTIPLIER = {
    "monthly":   Decimal("1"),
    "biweekly":  Decimal("26") / Decimal("12"),
    "weekly":    Decimal("52") / Decimal("12"),
    "annual":    Decimal("1") / Decimal("12"),
}


def _debts_table():    return db.get_table(DEBTS_TABLE)
def _income_table():   return db.get_table(INCOME_TABLE)
def _expenses_table(): return db.get_table(EXPENSES_TABLE)


def _validate_positive_decimal(value, field_name: str) -> str | None:
    if value is None:
        return f"{field_name} is required"
    try:
        val = Decimal(str(value))
        if val < 0:
            return f"{field_name} must be non-negative"
    except InvalidOperation:
        return f"{field_name} must be a valid number"
    return None


def _validate_amount(value, field_name: str = "amount") -> str | None:
    if value is None:
        return f"{field_name} is required"
    try:
        val = Decimal(str(value))
        if val <= 0:
            return f"{field_name} must be greater than zero"
    except InvalidOperation:
        return f"{field_name} must be a valid number"
    return None


def _to_dec(value) -> Decimal:
    return Decimal(str(value))


def _compute_debt_fields(balance: Decimal, apr: Decimal, monthly_payment: Decimal) -> dict:
    """Compute annual_interest, payoff_months, total_interest_remaining."""
    annual_interest = str(round(balance * apr / Decimal("100"), 2))

    if monthly_payment <= 0:
        return {"annual_interest": annual_interest, "payoff_months": None, "total_interest_remaining": None}

    r = apr / Decimal("1200")  # monthly rate

    if r == 0:
        months = math.ceil(float(balance / monthly_payment))
        return {
            "annual_interest": annual_interest,
            "payoff_months": months,
            "total_interest_remaining": "0",
        }

    rP = r * balance
    if monthly_payment <= rP:
        # Payment doesn't cover interest — will never pay off
        return {"annual_interest": annual_interest, "payoff_months": None, "total_interest_remaining": None}

    months_exact = -math.log(1 - float(rP / monthly_payment)) / math.log(1 + float(r))
    months = math.ceil(months_exact)
    total_paid = float(monthly_payment) * months
    total_interest = max(0.0, total_paid - float(balance))

    return {
        "annual_interest":          annual_interest,
        "payoff_months":            months,
        "total_interest_remaining": str(round(Decimal(str(total_interest)), 2)),
    }


def _compute_total_fields(original_balance: Decimal, apr: Decimal, monthly_payment: Decimal) -> dict:
    """Compute total_months from the original loan amount (for progress bar)."""
    result = _compute_debt_fields(original_balance, apr, monthly_payment)
    return {"total_months": result["payoff_months"]}


def _to_monthly(amount: Decimal, frequency: str) -> Decimal:
    return amount * MONTHLY_MULTIPLIER[frequency]


# ── Debts ─────────────────────────────────────────────────────────────────────

def list_debts(user_id: str) -> dict:
    items = db.query_by_user(_debts_table(), user_id)
    for item in items:
        balance  = _to_dec(item["balance"])
        apr      = _to_dec(item["apr"])
        payment  = _to_dec(item["monthly_payment"])
        orig_bal = _to_dec(item.get("original_balance") or item["balance"])
        item.update(_compute_debt_fields(balance, apr, payment))
        item.update(_compute_total_fields(orig_bal, apr, payment))
    items.sort(key=lambda d: d.get("name", ""))
    return ok(items)


def create_debt(user_id: str, body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")
    if len(name) > MAX_NAME_LEN:
        return error(f"name exceeds maximum length of {MAX_NAME_LEN}")

    debt_type = body.get("type", "other")
    if debt_type not in VALID_DEBT_TYPES:
        return error(f"type must be one of: {', '.join(sorted(VALID_DEBT_TYPES))}")

    err = _validate_amount(body.get("balance"), "balance")
    if err:
        return error(err)

    err = _validate_positive_decimal(body.get("apr"), "apr")
    if err:
        return error(err)

    err = _validate_amount(body.get("monthly_payment"), "monthly_payment")
    if err:
        return error(err)

    notes = (body.get("notes") or "").strip()
    if len(notes) > MAX_NOTES_LEN:
        return error(f"notes exceeds maximum length of {MAX_NOTES_LEN}")

    balance         = _to_dec(body["balance"])
    apr             = _to_dec(body["apr"])
    monthly_payment = _to_dec(body["monthly_payment"])

    raw_orig = body.get("original_balance")
    original_balance = _to_dec(raw_orig) if raw_orig not in (None, "") else balance
    if original_balance < balance:
        original_balance = balance

    now = now_iso()
    item = {
        "user_id":          user_id,
        "debt_id":          str(uuid.uuid4()),
        "name":             name,
        "type":             debt_type,
        "balance":          str(balance),
        "original_balance": str(original_balance),
        "apr":              str(apr),
        "monthly_payment":  str(monthly_payment),
        "notes":            notes or None,
        "created_at":       now,
        "updated_at":       now,
    }
    item = {k: v for k, v in item.items() if v is not None}
    _debts_table().put_item(Item=item)

    item.update(_compute_debt_fields(balance, apr, monthly_payment))
    item.update(_compute_total_fields(original_balance, apr, monthly_payment))
    return created(item)


def update_debt(user_id: str, debt_id: str, body: dict) -> dict:
    updatable = {"name", "type", "balance", "original_balance", "apr", "monthly_payment", "notes"}
    fields = {k: v for k, v in body.items() if k in updatable}
    if not fields:
        return error("No valid fields provided for update")

    if "name" in fields:
        fields["name"] = fields["name"].strip()
        if not fields["name"]:
            return error("name cannot be empty")
        if len(fields["name"]) > MAX_NAME_LEN:
            return error(f"name exceeds maximum length of {MAX_NAME_LEN}")

    if "type" in fields and fields["type"] not in VALID_DEBT_TYPES:
        return error(f"type must be one of: {', '.join(sorted(VALID_DEBT_TYPES))}")

    for field in ("balance", "original_balance", "monthly_payment"):
        if field in fields:
            err = _validate_amount(fields[field], field)
            if err:
                return error(err)
            fields[field] = str(_to_dec(fields[field]))

    if "apr" in fields:
        err = _validate_positive_decimal(fields["apr"], "apr")
        if err:
            return error(err)
        fields["apr"] = str(_to_dec(fields["apr"]))

    if "notes" in fields:
        fields["notes"] = (fields["notes"] or "").strip()
        if len(fields["notes"]) > MAX_NOTES_LEN:
            return error(f"notes exceeds maximum length of {MAX_NOTES_LEN}")

    fields["updated_at"] = now_iso()
    update_expr, names, values = build_update_expression(fields)

    try:
        result = _debts_table().update_item(
            Key={"user_id": user_id, "debt_id": debt_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(debt_id)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if not _is_conditional_check_failed(e):
            raise
        return not_found("Debt")

    item = result["Attributes"]
    balance  = _to_dec(item["balance"])
    apr      = _to_dec(item["apr"])
    payment  = _to_dec(item["monthly_payment"])
    orig_bal = _to_dec(item.get("original_balance") or item["balance"])
    item.update(_compute_debt_fields(balance, apr, payment))
    item.update(_compute_total_fields(orig_bal, apr, payment))
    return ok(item)


def delete_debt(user_id: str, debt_id: str) -> dict:
    try:
        _debts_table().delete_item(
            Key={"user_id": user_id, "debt_id": debt_id},
            ConditionExpression="attribute_exists(debt_id)",
        )
    except ClientError as e:
        if not _is_conditional_check_failed(e):
            raise
        return not_found("Debt")
    return no_content()


# ── Income ────────────────────────────────────────────────────────────────────

def list_income(user_id: str) -> dict:
    items = db.query_by_user(_income_table(), user_id)
    for item in items:
        item["monthly_amount"] = str(_to_monthly(_to_dec(item["amount"]), item["frequency"]))
    items.sort(key=lambda i: i.get("name", ""))
    return ok(items)


def create_income(user_id: str, body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")
    if len(name) > MAX_NAME_LEN:
        return error(f"name exceeds maximum length of {MAX_NAME_LEN}")

    err = _validate_amount(body.get("amount"), "amount")
    if err:
        return error(err)

    frequency = body.get("frequency", "monthly")
    if frequency not in VALID_FREQUENCIES:
        return error(f"frequency must be one of: {', '.join(sorted(VALID_FREQUENCIES))}")

    notes = (body.get("notes") or "").strip()
    if len(notes) > MAX_NOTES_LEN:
        return error(f"notes exceeds maximum length of {MAX_NOTES_LEN}")

    amount = _to_dec(body["amount"])
    now = now_iso()
    item = {
        "user_id":   user_id,
        "income_id": str(uuid.uuid4()),
        "name":      name,
        "amount":    str(amount),
        "frequency": frequency,
        "notes":     notes or None,
        "created_at": now,
        "updated_at": now,
    }
    item = {k: v for k, v in item.items() if v is not None}
    _income_table().put_item(Item=item)
    item["monthly_amount"] = str(_to_monthly(amount, frequency))
    return created(item)


def update_income(user_id: str, income_id: str, body: dict) -> dict:
    updatable = {"name", "amount", "frequency", "notes"}
    fields = {k: v for k, v in body.items() if k in updatable}
    if not fields:
        return error("No valid fields provided for update")

    if "name" in fields:
        fields["name"] = fields["name"].strip()
        if not fields["name"]:
            return error("name cannot be empty")
        if len(fields["name"]) > MAX_NAME_LEN:
            return error(f"name exceeds maximum length of {MAX_NAME_LEN}")

    if "amount" in fields:
        err = _validate_amount(fields["amount"], "amount")
        if err:
            return error(err)
        fields["amount"] = str(_to_dec(fields["amount"]))

    if "frequency" in fields and fields["frequency"] not in VALID_FREQUENCIES:
        return error(f"frequency must be one of: {', '.join(sorted(VALID_FREQUENCIES))}")

    if "notes" in fields:
        fields["notes"] = (fields["notes"] or "").strip()
        if len(fields["notes"]) > MAX_NOTES_LEN:
            return error(f"notes exceeds maximum length of {MAX_NOTES_LEN}")

    fields["updated_at"] = now_iso()
    update_expr, names, values = build_update_expression(fields)

    try:
        result = _income_table().update_item(
            Key={"user_id": user_id, "income_id": income_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(income_id)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if not _is_conditional_check_failed(e):
            raise
        return not_found("Income source")

    item = result["Attributes"]
    item["monthly_amount"] = str(_to_monthly(_to_dec(item["amount"]), item["frequency"]))
    return ok(item)


def delete_income(user_id: str, income_id: str) -> dict:
    try:
        _income_table().delete_item(
            Key={"user_id": user_id, "income_id": income_id},
            ConditionExpression="attribute_exists(income_id)",
        )
    except ClientError as e:
        if not _is_conditional_check_failed(e):
            raise
        return not_found("Income source")
    return no_content()


# ── Fixed expenses ─────────────────────────────────────────────────────────────

def list_expenses(user_id: str) -> dict:
    items = db.query_by_user(_expenses_table(), user_id)
    for item in items:
        item["monthly_amount"] = str(_to_monthly(_to_dec(item["amount"]), item["frequency"]))
    items.sort(key=lambda e: (e.get("category", ""), e.get("name", "")))
    return ok(items)


def _validate_due_day(value) -> tuple[int | None, str | None]:
    """Return (day, error_message). day is None if value is absent."""
    if value is None or value == "":
        return None, None
    try:
        day = int(value)
    except (ValueError, TypeError):
        return None, "due_day must be an integer between 1 and 31"
    if not 1 <= day <= 31:
        return None, "due_day must be between 1 and 31"
    return day, None


def create_expense(user_id: str, body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")
    if len(name) > MAX_NAME_LEN:
        return error(f"name exceeds maximum length of {MAX_NAME_LEN}")

    err = _validate_amount(body.get("amount"), "amount")
    if err:
        return error(err)

    frequency = body.get("frequency", "monthly")
    if frequency not in VALID_FREQUENCIES:
        return error(f"frequency must be one of: {', '.join(sorted(VALID_FREQUENCIES))}")

    category = body.get("category", "other")
    if category not in VALID_EXPENSE_CATS:
        return error(f"category must be one of: {', '.join(sorted(VALID_EXPENSE_CATS))}")

    due_day, err = _validate_due_day(body.get("due_day"))
    if err:
        return error(err)

    notes = (body.get("notes") or "").strip()
    if len(notes) > MAX_NOTES_LEN:
        return error(f"notes exceeds maximum length of {MAX_NOTES_LEN}")

    amount = _to_dec(body["amount"])
    now = now_iso()
    item = {
        "user_id":    user_id,
        "expense_id": str(uuid.uuid4()),
        "name":       name,
        "amount":     str(amount),
        "frequency":  frequency,
        "category":   category,
        "due_day":    due_day,
        "notes":      notes or None,
        "created_at": now,
        "updated_at": now,
    }
    item = {k: v for k, v in item.items() if v is not None}
    _expenses_table().put_item(Item=item)
    item["monthly_amount"] = str(_to_monthly(amount, frequency))
    return created(item)


def update_expense(user_id: str, expense_id: str, body: dict) -> dict:
    updatable = {"name", "amount", "frequency", "category", "due_day", "notes"}
    fields = {k: v for k, v in body.items() if k in updatable}
    if not fields:
        return error("No valid fields provided for update")

    if "name" in fields:
        fields["name"] = fields["name"].strip()
        if not fields["name"]:
            return error("name cannot be empty")
        if len(fields["name"]) > MAX_NAME_LEN:
            return error(f"name exceeds maximum length of {MAX_NAME_LEN}")

    if "amount" in fields:
        err = _validate_amount(fields["amount"], "amount")
        if err:
            return error(err)
        fields["amount"] = str(_to_dec(fields["amount"]))

    if "frequency" in fields and fields["frequency"] not in VALID_FREQUENCIES:
        return error(f"frequency must be one of: {', '.join(sorted(VALID_FREQUENCIES))}")

    if "category" in fields and fields["category"] not in VALID_EXPENSE_CATS:
        return error(f"category must be one of: {', '.join(sorted(VALID_EXPENSE_CATS))}")

    remove_due_day = False
    if "due_day" in fields:
        due_day, err = _validate_due_day(fields["due_day"])
        if err:
            return error(err)
        if due_day is None:
            fields.pop("due_day")
            remove_due_day = True
        else:
            fields["due_day"] = due_day

    if "notes" in fields:
        fields["notes"] = (fields["notes"] or "").strip()
        if len(fields["notes"]) > MAX_NOTES_LEN:
            return error(f"notes exceeds maximum length of {MAX_NOTES_LEN}")

    fields["updated_at"] = now_iso()
    update_expr, names, values = build_update_expression(fields)

    if remove_due_day:
        names["#due_day"] = "due_day"
        update_expr += " REMOVE #due_day"

    try:
        result = _expenses_table().update_item(
            Key={"user_id": user_id, "expense_id": expense_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(expense_id)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if not _is_conditional_check_failed(e):
            raise
        return not_found("Expense")

    item = result["Attributes"]
    item["monthly_amount"] = str(_to_monthly(_to_dec(item["amount"]), item["frequency"]))
    return ok(item)


def delete_expense(user_id: str, expense_id: str) -> dict:
    try:
        _expenses_table().delete_item(
            Key={"user_id": user_id, "expense_id": expense_id},
            ConditionExpression="attribute_exists(expense_id)",
        )
    except ClientError as e:
        if not _is_conditional_check_failed(e):
            raise
        return not_found("Expense")
    return no_content()


# ── Summary ───────────────────────────────────────────────────────────────────

def get_summary(user_id: str) -> dict:
    debts    = db.query_by_user(_debts_table(),    user_id)
    incomes  = db.query_by_user(_income_table(),   user_id)
    expenses = db.query_by_user(_expenses_table(), user_id)

    total_monthly_income   = Decimal("0")
    total_monthly_expenses = Decimal("0")
    total_monthly_debt_payments = Decimal("0")
    total_debt_balance     = Decimal("0")
    total_annual_interest  = Decimal("0")

    debts_out = []
    for d in debts:
        balance         = _to_dec(d["balance"])
        apr             = _to_dec(d["apr"])
        monthly_payment = _to_dec(d["monthly_payment"])
        orig_bal        = _to_dec(d.get("original_balance") or d["balance"])
        computed        = _compute_debt_fields(balance, apr, monthly_payment)
        total_debt_balance          += balance
        total_monthly_debt_payments += monthly_payment
        total_annual_interest       += _to_dec(computed["annual_interest"])
        debts_out.append({**d, **computed, **_compute_total_fields(orig_bal, apr, monthly_payment)})

    for i in incomes:
        total_monthly_income += _to_monthly(_to_dec(i["amount"]), i["frequency"])

    for e in expenses:
        total_monthly_expenses += _to_monthly(_to_dec(e["amount"]), e["frequency"])

    total_monthly_outflow   = total_monthly_expenses + total_monthly_debt_payments
    net_monthly_cash_flow   = total_monthly_income - total_monthly_outflow

    return ok({
        "total_monthly_income":        str(round(total_monthly_income,        2)),
        "total_monthly_expenses":      str(round(total_monthly_expenses,      2)),
        "total_monthly_debt_payments": str(round(total_monthly_debt_payments, 2)),
        "total_monthly_outflow":       str(round(total_monthly_outflow,       2)),
        "net_monthly_cash_flow":       str(round(net_monthly_cash_flow,       2)),
        "total_debt_balance":          str(round(total_debt_balance,          2)),
        "total_annual_interest":       str(round(total_annual_interest,       2)),
        "debts":    debts_out,
        "income":   [{**i, "monthly_amount": str(_to_monthly(_to_dec(i["amount"]), i["frequency"]))} for i in incomes],
        "expenses": [{**e, "monthly_amount": str(_to_monthly(_to_dec(e["amount"]), e["frequency"]))} for e in expenses],
    })
