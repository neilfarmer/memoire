"""Unit tests for lambda/budget/crud.py."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars before module load ───────────────────────────────────────────────
os.environ["TABLE_NAME"]    = "test-transactions"
os.environ["BUDGETS_TABLE"] = "test-budgets"

crud = load_lambda("budget", "crud.py")

TXN_TABLE    = "test-transactions"
BUDGET_TABLE = "test-budgets"


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TXN_TABLE,    "user_id", "transaction_id")
        make_table(ddb, BUDGET_TABLE, "user_id", "budget_id")
        yield


# ── _validate_amount ──────────────────────────────────────────────────────────

class TestValidateAmount:
    def test_none_returns_error(self):
        assert crud._validate_amount(None) is not None

    def test_zero_rejected(self):
        assert crud._validate_amount("0") is not None

    def test_negative_rejected(self):
        assert crud._validate_amount("-5") is not None

    def test_non_numeric_rejected(self):
        assert crud._validate_amount("abc") is not None

    def test_valid_integer(self):
        assert crud._validate_amount("100") is None

    def test_valid_decimal(self):
        assert crud._validate_amount("99.99") is None


# ── _validate_month ───────────────────────────────────────────────────────────

class TestValidateMonth:
    def test_valid_month(self):
        assert crud._validate_month("2025-03") is None

    def test_invalid_format(self):
        assert crud._validate_month("2025-3") is not None

    def test_empty_string(self):
        assert crud._validate_month("") is not None

    def test_wrong_separator(self):
        assert crud._validate_month("2025/03") is not None


# ── create_transaction ────────────────────────────────────────────────────────

class TestCreateTransaction:
    def test_requires_amount(self, tbls):
        r = crud.create_transaction(USER, {"type": "expense", "category": "Food", "date": "2025-03-01"})
        assert r["statusCode"] == 400
        assert "amount" in json.loads(r["body"])["error"]

    def test_requires_category(self, tbls):
        r = crud.create_transaction(USER, {"amount": "50", "type": "expense", "date": "2025-03-01"})
        assert r["statusCode"] == 400

    def test_requires_date(self, tbls):
        r = crud.create_transaction(USER, {"amount": "50", "type": "expense", "category": "Food"})
        assert r["statusCode"] == 400

    def test_invalid_date_format(self, tbls):
        r = crud.create_transaction(USER, {"amount": "50", "category": "Food", "date": "01-03-2025"})
        assert r["statusCode"] == 400

    def test_invalid_type_rejected(self, tbls):
        r = crud.create_transaction(USER, {"amount": "50", "category": "Food", "date": "2025-03-01", "type": "unknown"})
        assert r["statusCode"] == 400

    def test_creates_expense(self, tbls):
        r = crud.create_transaction(USER, {"amount": "150.50", "type": "expense", "category": "Groceries", "date": "2025-03-05"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["amount"] == "150.50"
        assert body["type"] == "expense"
        assert body["category"] == "Groceries"
        assert "transaction_id" in body
        assert "created_at" in body

    def test_creates_income(self, tbls):
        r = crud.create_transaction(USER, {"amount": "3000", "type": "income", "category": "Salary", "date": "2025-03-01"})
        assert r["statusCode"] == 201
        assert json.loads(r["body"])["type"] == "income"

    def test_creates_debt_payment(self, tbls):
        r = crud.create_transaction(USER, {
            "amount": "500", "type": "debt_payment", "category": "Visa",
            "date": "2025-03-15", "interest_rate": "19.99",
        })
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["type"] == "debt_payment"
        assert body["interest_rate"] == "19.99"

    def test_default_type_is_expense(self, tbls):
        r = crud.create_transaction(USER, {"amount": "10", "category": "Coffee", "date": "2025-03-10"})
        assert json.loads(r["body"])["type"] == "expense"

    def test_amount_stored_as_string(self, tbls):
        r = crud.create_transaction(USER, {"amount": 42.5, "category": "X", "date": "2025-03-01"})
        body = json.loads(r["body"])
        assert isinstance(body["amount"], str)

    def test_user_isolation(self, tbls):
        crud.create_transaction(USER, {"amount": "10", "category": "A", "date": "2025-03-01"})
        items = json.loads(crud.list_transactions("other_user", {})["body"])
        assert len(items) == 0


# ── list_transactions ─────────────────────────────────────────────────────────

class TestListTransactions:
    def test_empty(self, tbls):
        r = crud.list_transactions(USER, {})
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    def test_filter_by_month(self, tbls):
        crud.create_transaction(USER, {"amount": "10", "category": "A", "date": "2025-03-05"})
        crud.create_transaction(USER, {"amount": "20", "category": "B", "date": "2025-04-01"})
        items = json.loads(crud.list_transactions(USER, {"month": "2025-03"})["body"])
        assert len(items) == 1
        assert items[0]["date"] == "2025-03-05"

    def test_filter_by_category(self, tbls):
        crud.create_transaction(USER, {"amount": "10", "category": "Food", "date": "2025-03-01"})
        crud.create_transaction(USER, {"amount": "20", "category": "Rent", "date": "2025-03-01"})
        items = json.loads(crud.list_transactions(USER, {"category": "food"})["body"])
        assert len(items) == 1

    def test_sorted_by_date_desc(self, tbls):
        crud.create_transaction(USER, {"amount": "10", "category": "A", "date": "2025-03-01"})
        crud.create_transaction(USER, {"amount": "10", "category": "B", "date": "2025-03-15"})
        items = json.loads(crud.list_transactions(USER, {})["body"])
        assert items[0]["date"] > items[1]["date"]


# ── get_transaction ───────────────────────────────────────────────────────────

class TestGetTransaction:
    def test_get_existing(self, tbls):
        txn_id = json.loads(
            crud.create_transaction(USER, {"amount": "5", "category": "X", "date": "2025-03-01"})["body"]
        )["transaction_id"]
        r = crud.get_transaction(USER, txn_id)
        assert r["statusCode"] == 200

    def test_not_found(self, tbls):
        assert crud.get_transaction(USER, "ghost")["statusCode"] == 404

    def test_cross_user_isolation(self, tbls):
        txn_id = json.loads(
            crud.create_transaction("alice", {"amount": "5", "category": "X", "date": "2025-03-01"})["body"]
        )["transaction_id"]
        assert crud.get_transaction("bob", txn_id)["statusCode"] == 404


# ── update_transaction ────────────────────────────────────────────────────────

class TestUpdateTransaction:
    def test_updates_fields(self, tbls):
        txn_id = json.loads(
            crud.create_transaction(USER, {"amount": "10", "category": "Old", "date": "2025-03-01"})["body"]
        )["transaction_id"]
        r = crud.update_transaction(USER, txn_id, {"amount": "20", "category": "New"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["amount"] == "20"
        assert body["category"] == "New"

    def test_no_valid_fields_returns_400(self, tbls):
        txn_id = json.loads(
            crud.create_transaction(USER, {"amount": "10", "category": "X", "date": "2025-03-01"})["body"]
        )["transaction_id"]
        r = crud.update_transaction(USER, txn_id, {"bogus": "value"})
        assert r["statusCode"] == 400

    def test_update_nonexistent(self, tbls):
        assert crud.update_transaction(USER, "ghost", {"amount": "5"})["statusCode"] == 404

    def test_invalid_type_rejected(self, tbls):
        txn_id = json.loads(
            crud.create_transaction(USER, {"amount": "10", "category": "X", "date": "2025-03-01"})["body"]
        )["transaction_id"]
        r = crud.update_transaction(USER, txn_id, {"type": "invalid"})
        assert r["statusCode"] == 400


# ── delete_transaction ────────────────────────────────────────────────────────

class TestDeleteTransaction:
    def test_deletes(self, tbls):
        txn_id = json.loads(
            crud.create_transaction(USER, {"amount": "5", "category": "X", "date": "2025-03-01"})["body"]
        )["transaction_id"]
        r = crud.delete_transaction(USER, txn_id)
        assert r["statusCode"] == 204
        assert crud.get_transaction(USER, txn_id)["statusCode"] == 404

    def test_delete_nonexistent(self, tbls):
        assert crud.delete_transaction(USER, "ghost")["statusCode"] == 404


# ── create_budget ─────────────────────────────────────────────────────────────

class TestCreateBudget:
    def test_requires_category(self, tbls):
        r = crud.create_budget(USER, {"limit": "500", "month": "2025-03"})
        assert r["statusCode"] == 400

    def test_requires_limit(self, tbls):
        r = crud.create_budget(USER, {"category": "Food", "month": "2025-03"})
        assert r["statusCode"] == 400

    def test_requires_month(self, tbls):
        r = crud.create_budget(USER, {"category": "Food", "limit": "500"})
        assert r["statusCode"] == 400

    def test_invalid_month_format(self, tbls):
        r = crud.create_budget(USER, {"category": "Food", "limit": "500", "month": "2025/03"})
        assert r["statusCode"] == 400

    def test_creates_budget(self, tbls):
        r = crud.create_budget(USER, {"category": "Groceries", "limit": "400", "month": "2025-03"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["category"] == "Groceries"
        assert body["limit"] == "400"
        assert body["month"] == "2025-03"
        assert "budget_id" in body

    def test_limit_stored_as_string(self, tbls):
        r = crud.create_budget(USER, {"category": "X", "limit": 200.5, "month": "2025-03"})
        body = json.loads(r["body"])
        assert isinstance(body["limit"], str)


# ── list_budgets ──────────────────────────────────────────────────────────────

class TestListBudgets:
    def test_filter_by_month(self, tbls):
        crud.create_budget(USER, {"category": "Food", "limit": "300", "month": "2025-03"})
        crud.create_budget(USER, {"category": "Food", "limit": "300", "month": "2025-04"})
        items = json.loads(crud.list_budgets(USER, {"month": "2025-03"})["body"])
        assert len(items) == 1
        assert items[0]["month"] == "2025-03"


# ── update_budget ─────────────────────────────────────────────────────────────

class TestUpdateBudget:
    def test_updates_limit(self, tbls):
        bdg_id = json.loads(
            crud.create_budget(USER, {"category": "Food", "limit": "300", "month": "2025-03"})["body"]
        )["budget_id"]
        r = crud.update_budget(USER, bdg_id, {"limit": "450"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["limit"] == "450"

    def test_update_nonexistent(self, tbls):
        assert crud.update_budget(USER, "ghost", {"limit": "100"})["statusCode"] == 404


# ── delete_budget ─────────────────────────────────────────────────────────────

class TestDeleteBudget:
    def test_deletes(self, tbls):
        bdg_id = json.loads(
            crud.create_budget(USER, {"category": "X", "limit": "100", "month": "2025-03"})["body"]
        )["budget_id"]
        assert crud.delete_budget(USER, bdg_id)["statusCode"] == 204

    def test_delete_nonexistent(self, tbls):
        assert crud.delete_budget(USER, "ghost")["statusCode"] == 404


# ── get_summary ───────────────────────────────────────────────────────────────

class TestGetSummary:
    def test_requires_valid_month(self, tbls):
        r = crud.get_summary(USER, {"month": "bad"})
        assert r["statusCode"] == 400

    def test_empty_month(self, tbls):
        r = crud.get_summary(USER, {"month": "2025-03"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["total_income"]  == "0"
        assert body["total_expense"] == "0"
        assert body["net"]           == "0"
        assert body["category_breakdown"] == []

    def test_totals_computed_correctly(self, tbls):
        crud.create_transaction(USER, {"amount": "3000", "type": "income",  "category": "Salary",    "date": "2025-03-01"})
        crud.create_transaction(USER, {"amount": "500",  "type": "expense", "category": "Rent",      "date": "2025-03-05"})
        crud.create_transaction(USER, {"amount": "200",  "type": "expense", "category": "Groceries", "date": "2025-03-10"})
        r = crud.get_summary(USER, {"month": "2025-03"})
        body = json.loads(r["body"])
        assert body["total_income"]  == "3000"
        assert body["total_expense"] == "700"
        assert body["net"]           == "2300"
        assert body["transaction_count"] == 3

    def test_excludes_other_months(self, tbls):
        crud.create_transaction(USER, {"amount": "100", "type": "expense", "category": "X", "date": "2025-04-01"})
        r = crud.get_summary(USER, {"month": "2025-03"})
        body = json.loads(r["body"])
        assert body["total_expense"] == "0"

    def test_category_breakdown_includes_budget(self, tbls):
        crud.create_transaction(USER, {"amount": "350", "type": "expense", "category": "Groceries", "date": "2025-03-10"})
        crud.create_budget(USER, {"category": "Groceries", "limit": "400", "month": "2025-03"})
        r = crud.get_summary(USER, {"month": "2025-03"})
        body = json.loads(r["body"])
        cats = {c["category"]: c for c in body["category_breakdown"]}
        assert "Groceries" in cats
        assert cats["Groceries"]["spent"]  == "350"
        assert cats["Groceries"]["limit"]  == "400"

    def test_debt_payment_counts_as_expense(self, tbls):
        crud.create_transaction(USER, {"amount": "200", "type": "debt_payment", "category": "Visa", "date": "2025-03-15"})
        r = crud.get_summary(USER, {"month": "2025-03"})
        body = json.loads(r["body"])
        assert body["total_expense"] == "200"
        assert body["net"] == "-200"

    def test_user_isolation(self, tbls):
        crud.create_transaction("alice", {"amount": "1000", "type": "income", "category": "Job", "date": "2025-03-01"})
        r = crud.get_summary("bob", {"month": "2025-03"})
        body = json.loads(r["body"])
        assert body["total_income"] == "0"
