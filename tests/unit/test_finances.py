"""Unit tests for lambda/finances/crud.py."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["DEBTS_TABLE"]    = "test-debts"
os.environ["INCOME_TABLE"]   = "test-income"
os.environ["EXPENSES_TABLE"] = "test-fixed-expenses"

crud = load_lambda("finances", "crud.py")

DEBTS_TABLE    = "test-debts"
INCOME_TABLE   = "test-income"
EXPENSES_TABLE = "test-fixed-expenses"


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, DEBTS_TABLE,    "user_id", "debt_id")
        make_table(ddb, INCOME_TABLE,   "user_id", "income_id")
        make_table(ddb, EXPENSES_TABLE, "user_id", "expense_id")
        yield


# ── _compute_debt_fields ──────────────────────────────────────────────────────

class TestComputeDebtFields:
    def _run(self, balance, apr, payment):
        from decimal import Decimal
        return crud._compute_debt_fields(Decimal(balance), Decimal(apr), Decimal(payment))

    def test_annual_interest(self):
        r = self._run("10000", "6", "200")
        assert r["annual_interest"] == "600.00"

    def test_payoff_months_basic(self):
        # $1000 at 0% APR, $100/month → 10 months
        r = self._run("1000", "0", "100")
        assert r["payoff_months"] == 10
        assert r["total_interest_remaining"] == "0"

    def test_payment_below_interest_returns_none(self):
        # $10000 at 24% APR, $200/month — interest alone is $200/month, so never pays off
        r = self._run("10000", "24", "200")
        assert r["payoff_months"] is None
        assert r["total_interest_remaining"] is None

    def test_zero_payment_returns_none(self):
        r = self._run("5000", "5", "0")
        assert r["payoff_months"] is None

    def test_zero_apr_no_interest(self):
        r = self._run("2000", "0", "500")
        assert r["total_interest_remaining"] == "0"
        assert r["payoff_months"] == 4


# ── Debts ─────────────────────────────────────────────────────────────────────

class TestCreateDebt:
    def test_requires_name(self, tbls):
        r = crud.create_debt(USER, {"balance": "10000", "apr": "6.99", "monthly_payment": "250"})
        assert r["statusCode"] == 400

    def test_requires_balance(self, tbls):
        r = crud.create_debt(USER, {"name": "Car", "apr": "6.99", "monthly_payment": "250"})
        assert r["statusCode"] == 400

    def test_requires_apr(self, tbls):
        r = crud.create_debt(USER, {"name": "Car", "balance": "10000", "monthly_payment": "250"})
        assert r["statusCode"] == 400

    def test_requires_monthly_payment(self, tbls):
        r = crud.create_debt(USER, {"name": "Car", "balance": "10000", "apr": "6.99"})
        assert r["statusCode"] == 400

    def test_invalid_type_rejected(self, tbls):
        r = crud.create_debt(USER, {"name": "Car", "balance": "10000", "apr": "6.99", "monthly_payment": "250", "type": "unknown"})
        assert r["statusCode"] == 400

    def test_creates_with_computed_fields(self, tbls):
        r = crud.create_debt(USER, {
            "name": "Car loan", "type": "auto_loan",
            "balance": "15000", "apr": "7.99", "monthly_payment": "350",
        })
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["name"] == "Car loan"
        assert body["type"] == "auto_loan"
        assert "annual_interest" in body
        assert "payoff_months" in body
        assert "total_interest_remaining" in body
        assert "debt_id" in body
        # original_balance defaults to balance
        assert body["original_balance"] == "15000"
        assert body["total_months"] == body["payoff_months"]

    def test_original_balance_stored(self, tbls):
        r = crud.create_debt(USER, {
            "name": "Mortgage", "type": "mortgage",
            "original_balance": "300000", "balance": "250000",
            "apr": "3.5", "monthly_payment": "1500",
        })
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["original_balance"] == "300000"
        assert body["total_months"] is not None
        # total_months > payoff_months since original > current balance
        assert body["total_months"] > body["payoff_months"]

    def test_apr_zero_allowed(self, tbls):
        r = crud.create_debt(USER, {"name": "Interest-free", "balance": "1000", "apr": "0", "monthly_payment": "100"})
        assert r["statusCode"] == 201

    def test_user_isolation(self, tbls):
        crud.create_debt(USER, {"name": "Mine", "balance": "5000", "apr": "5", "monthly_payment": "100"})
        items = json.loads(crud.list_debts("other")["body"])
        assert len(items) == 0


class TestUpdateDebt:
    def _make(self, tbls):
        return json.loads(
            crud.create_debt(USER, {"name": "Car", "balance": "10000", "apr": "7", "monthly_payment": "300"})["body"]
        )["debt_id"]

    def test_updates_balance(self, tbls):
        debt_id = self._make(tbls)
        r = crud.update_debt(USER, debt_id, {"balance": "9000"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["balance"] == "9000"

    def test_updates_original_balance(self, tbls):
        debt_id = self._make(tbls)
        r = crud.update_debt(USER, debt_id, {"original_balance": "12000"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["original_balance"] == "12000"
        assert body["total_months"] is not None

    def test_invalid_apr_returns_400(self, tbls):
        debt_id = self._make(tbls)
        assert crud.update_debt(USER, debt_id, {"apr": "-1"})["statusCode"] == 400

    def test_invalid_type_returns_400(self, tbls):
        debt_id = self._make(tbls)
        assert crud.update_debt(USER, debt_id, {"type": "unknown"})["statusCode"] == 400

    def test_no_valid_fields_returns_400(self, tbls):
        debt_id = self._make(tbls)
        assert crud.update_debt(USER, debt_id, {"bogus": "x"})["statusCode"] == 400

    def test_update_nonexistent(self, tbls):
        assert crud.update_debt(USER, "ghost", {"balance": "100"})["statusCode"] == 404


class TestDeleteDebt:
    def test_deletes(self, tbls):
        debt_id = json.loads(
            crud.create_debt(USER, {"name": "X", "balance": "1000", "apr": "5", "monthly_payment": "50"})["body"]
        )["debt_id"]
        assert crud.delete_debt(USER, debt_id)["statusCode"] == 204

    def test_delete_nonexistent(self, tbls):
        assert crud.delete_debt(USER, "ghost")["statusCode"] == 404


# ── Income ────────────────────────────────────────────────────────────────────

class TestCreateIncome:
    def test_requires_name(self, tbls):
        assert crud.create_income(USER, {"amount": "3000", "frequency": "monthly"})["statusCode"] == 400

    def test_requires_amount(self, tbls):
        assert crud.create_income(USER, {"name": "Salary", "frequency": "monthly"})["statusCode"] == 400

    def test_invalid_frequency(self, tbls):
        assert crud.create_income(USER, {"name": "Salary", "amount": "3000", "frequency": "daily"})["statusCode"] == 400

    def test_creates_monthly(self, tbls):
        r = crud.create_income(USER, {"name": "Salary", "amount": "3000", "frequency": "monthly"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["monthly_amount"] == "3000"

    def test_biweekly_normalized(self, tbls):
        r = crud.create_income(USER, {"name": "Pay", "amount": "2000", "frequency": "biweekly"})
        body = json.loads(r["body"])
        # 2000 * 26 / 12 ≈ 4333.33...
        assert float(body["monthly_amount"]) == pytest.approx(2000 * 26 / 12, rel=1e-4)

    def test_annual_normalized(self, tbls):
        r = crud.create_income(USER, {"name": "Bonus", "amount": "12000", "frequency": "annual"})
        body = json.loads(r["body"])
        assert float(body["monthly_amount"]) == pytest.approx(1000.0, rel=1e-4)


class TestUpdateIncome:
    def _make(self, tbls):
        return json.loads(
            crud.create_income(USER, {"name": "Job", "amount": "3000", "frequency": "monthly"})["body"]
        )["income_id"]

    def test_updates_amount(self, tbls):
        inc_id = self._make(tbls)
        r = crud.update_income(USER, inc_id, {"amount": "3500"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["amount"] == "3500"

    def test_updates_frequency(self, tbls):
        inc_id = self._make(tbls)
        r = crud.update_income(USER, inc_id, {"frequency": "biweekly"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["frequency"] == "biweekly"
        assert float(body["monthly_amount"]) == pytest.approx(3000 * 26 / 12, rel=1e-4)

    def test_invalid_frequency_returns_400(self, tbls):
        inc_id = self._make(tbls)
        assert crud.update_income(USER, inc_id, {"frequency": "daily"})["statusCode"] == 400

    def test_no_valid_fields_returns_400(self, tbls):
        inc_id = self._make(tbls)
        assert crud.update_income(USER, inc_id, {"bogus": "x"})["statusCode"] == 400

    def test_update_nonexistent(self, tbls):
        assert crud.update_income(USER, "ghost", {"amount": "100"})["statusCode"] == 404


class TestDeleteIncome:
    def test_deletes(self, tbls):
        inc_id = json.loads(
            crud.create_income(USER, {"name": "X", "amount": "100", "frequency": "monthly"})["body"]
        )["income_id"]
        assert crud.delete_income(USER, inc_id)["statusCode"] == 204

    def test_delete_nonexistent(self, tbls):
        assert crud.delete_income(USER, "ghost")["statusCode"] == 404


# ── Fixed Expenses ────────────────────────────────────────────────────────────

class TestCreateExpense:
    def test_requires_name(self, tbls):
        assert crud.create_expense(USER, {"amount": "100", "frequency": "monthly", "category": "housing"})["statusCode"] == 400

    def test_requires_amount(self, tbls):
        assert crud.create_expense(USER, {"name": "Rent", "frequency": "monthly", "category": "housing"})["statusCode"] == 400

    def test_invalid_category(self, tbls):
        assert crud.create_expense(USER, {"name": "X", "amount": "100", "frequency": "monthly", "category": "bad"})["statusCode"] == 400

    def test_creates(self, tbls):
        r = crud.create_expense(USER, {"name": "Netflix", "amount": "17", "frequency": "monthly", "category": "subscriptions"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["category"] == "subscriptions"
        assert body["monthly_amount"] == "17"

    def test_due_day_stored(self, tbls):
        r = crud.create_expense(USER, {"name": "Hydro", "amount": "120", "frequency": "monthly", "category": "utilities", "due_day": 15})
        assert r["statusCode"] == 201
        assert json.loads(r["body"])["due_day"] == 15

    def test_due_day_optional(self, tbls):
        r = crud.create_expense(USER, {"name": "Rent", "amount": "1500", "frequency": "monthly", "category": "housing"})
        assert r["statusCode"] == 201
        assert "due_day" not in json.loads(r["body"])

    def test_due_day_invalid(self, tbls):
        assert crud.create_expense(USER, {"name": "X", "amount": "50", "frequency": "monthly", "category": "other", "due_day": 0})["statusCode"] == 400
        assert crud.create_expense(USER, {"name": "X", "amount": "50", "frequency": "monthly", "category": "other", "due_day": 32})["statusCode"] == 400
        assert crud.create_expense(USER, {"name": "X", "amount": "50", "frequency": "monthly", "category": "other", "due_day": "bad"})["statusCode"] == 400


class TestUpdateExpense:
    def _make(self, tbls):
        return json.loads(
            crud.create_expense(USER, {"name": "Rent", "amount": "1500", "frequency": "monthly", "category": "housing"})["body"]
        )["expense_id"]

    def test_updates_amount(self, tbls):
        exp_id = self._make(tbls)
        r = crud.update_expense(USER, exp_id, {"amount": "1600"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["amount"] == "1600"

    def test_updates_due_day(self, tbls):
        exp_id = self._make(tbls)
        r = crud.update_expense(USER, exp_id, {"due_day": 1})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["due_day"] == 1

    def test_invalid_due_day_returns_400(self, tbls):
        exp_id = self._make(tbls)
        assert crud.update_expense(USER, exp_id, {"due_day": 99})["statusCode"] == 400

    def test_invalid_category_returns_400(self, tbls):
        exp_id = self._make(tbls)
        assert crud.update_expense(USER, exp_id, {"category": "bad"})["statusCode"] == 400

    def test_invalid_frequency_returns_400(self, tbls):
        exp_id = self._make(tbls)
        assert crud.update_expense(USER, exp_id, {"frequency": "daily"})["statusCode"] == 400

    def test_no_valid_fields_returns_400(self, tbls):
        exp_id = self._make(tbls)
        assert crud.update_expense(USER, exp_id, {"bogus": "x"})["statusCode"] == 400

    def test_update_nonexistent(self, tbls):
        assert crud.update_expense(USER, "ghost", {"amount": "100"})["statusCode"] == 404


class TestDeleteExpense:
    def test_deletes(self, tbls):
        exp_id = json.loads(
            crud.create_expense(USER, {"name": "X", "amount": "50", "frequency": "monthly", "category": "other"})["body"]
        )["expense_id"]
        assert crud.delete_expense(USER, exp_id)["statusCode"] == 204

    def test_delete_nonexistent(self, tbls):
        assert crud.delete_expense(USER, "ghost")["statusCode"] == 404


# ── List endpoints ────────────────────────────────────────────────────────────

class TestListDebts:
    def test_list_returns_computed_fields(self, tbls):
        crud.create_debt(USER, {"name": "Car", "balance": "10000", "apr": "7", "monthly_payment": "300"})
        items = json.loads(crud.list_debts(USER)["body"])
        assert len(items) == 1
        assert "payoff_months" in items[0]
        assert "total_months" in items[0]
        assert "annual_interest" in items[0]

    def test_list_sorted_by_name(self, tbls):
        crud.create_debt(USER, {"name": "Zebra", "balance": "1000", "apr": "5", "monthly_payment": "100"})
        crud.create_debt(USER, {"name": "Apple", "balance": "2000", "apr": "5", "monthly_payment": "100"})
        items = json.loads(crud.list_debts(USER)["body"])
        assert items[0]["name"] == "Apple"


class TestListIncome:
    def test_list_returns_monthly_amount(self, tbls):
        crud.create_income(USER, {"name": "Salary", "amount": "5000", "frequency": "monthly"})
        items = json.loads(crud.list_income(USER)["body"])
        assert len(items) == 1
        assert items[0]["monthly_amount"] == "5000"


class TestListExpenses:
    def test_list_returns_monthly_amount(self, tbls):
        crud.create_expense(USER, {"name": "Hydro", "amount": "120", "frequency": "monthly", "category": "utilities"})
        items = json.loads(crud.list_expenses(USER)["body"])
        assert len(items) == 1
        assert items[0]["monthly_amount"] == "120"


# ── Summary ───────────────────────────────────────────────────────────────────

class TestGetSummary:
    def test_empty(self, tbls):
        r = crud.get_summary(USER)
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["total_monthly_income"] == "0.00"
        assert body["net_monthly_cash_flow"] == "0.00"

    def test_totals_computed(self, tbls):
        crud.create_income(USER,  {"name": "Salary",    "amount": "5000",  "frequency": "monthly"})
        crud.create_debt(USER,    {"name": "Car",        "balance": "15000","apr": "7.99", "monthly_payment": "400"})
        crud.create_expense(USER, {"name": "Rent",       "amount": "1500",  "frequency": "monthly", "category": "housing"})
        crud.create_expense(USER, {"name": "Hydro",      "amount": "120",   "frequency": "monthly", "category": "utilities"})

        r = crud.get_summary(USER)
        body = json.loads(r["body"])
        assert float(body["total_monthly_income"])        == pytest.approx(5000.0)
        assert float(body["total_monthly_debt_payments"]) == pytest.approx(400.0)
        assert float(body["total_monthly_expenses"])      == pytest.approx(1620.0)
        assert float(body["total_monthly_outflow"])       == pytest.approx(2020.0)
        assert float(body["net_monthly_cash_flow"])       == pytest.approx(2980.0)
        assert float(body["total_debt_balance"])          == pytest.approx(15000.0)
        assert len(body["debts"])    == 1
        assert len(body["income"])   == 1
        assert len(body["expenses"]) == 2

    def test_user_isolation(self, tbls):
        crud.create_income("alice", {"name": "Job", "amount": "9000", "frequency": "monthly"})
        body = json.loads(crud.get_summary("bob")["body"])
        assert body["total_monthly_income"] == "0.00"

    def test_annual_income_normalized_in_summary(self, tbls):
        crud.create_income(USER, {"name": "Bonus", "amount": "12000", "frequency": "annual"})
        body = json.loads(crud.get_summary(USER)["body"])
        assert float(body["total_monthly_income"]) == pytest.approx(1000.0)
