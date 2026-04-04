#!/usr/bin/env python3
"""
End-to-end test script for the Memoire Tasks API.

Tests all CRUD operations including validation and error cases.

Required environment variables:
    API_URL           - Base API URL (terraform output api_url)
    COGNITO_CLIENT_ID - Cognito App Client ID (terraform output cognito_client_id)
    TEST_EMAIL        - Email of an existing Cognito user
    TEST_PASSWORD     - Password of that user

Optional:
    COGNITO_USER_POOL_ID - Required only if using --create-user flag
    AWS_REGION           - Defaults to us-east-1

Usage:
    # Run tests against a deployed stack
    python tests/test_tasks_api.py

    # Create the test user in Cognito first, then run tests
    python tests/test_tasks_api.py --create-user
"""

import argparse
import os
import sys
import traceback

import boto3
import requests


# ── Config ────────────────────────────────────────────────────────────────────

API_URL = os.environ.get("API_URL", "").rstrip("/")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# ── Output helpers ────────────────────────────────────────────────────────────

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"

results = {"passed": 0, "failed": 0, "errors": []}


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        print(f"  [{PASS}] {label}")
        results["passed"] += 1
    else:
        print(f"  [{FAIL}] {label}")
        if detail:
            print(f"         {detail}")
        results["failed"] += 1
        results["errors"].append(label)
    return condition


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")
    print("-" * (len(title) + 2))


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_token() -> str:
    """Authenticate with Cognito and return an ID token."""
    client = boto3.client("cognito-idp", region_name=AWS_REGION)
    resp = client.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": TEST_EMAIL, "PASSWORD": TEST_PASSWORD},
        ClientId=COGNITO_CLIENT_ID,
    )
    return resp["AuthenticationResult"]["IdToken"]


def create_test_user() -> None:
    """Create and auto-confirm a test user in the Cognito User Pool."""
    if not COGNITO_USER_POOL_ID:
        print("COGNITO_USER_POOL_ID is required to create a user.")
        sys.exit(1)

    client = boto3.client("cognito-idp", region_name=AWS_REGION)

    print(f"Creating test user: {TEST_EMAIL}")
    try:
        client.admin_create_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=TEST_EMAIL,
            UserAttributes=[{"Name": "email", "Value": TEST_EMAIL}, {"Name": "email_verified", "Value": "true"}],
            TemporaryPassword=TEST_PASSWORD,
            MessageAction="SUPPRESS",
        )
    except client.exceptions.UsernameExistsException:
        print("User already exists, continuing.")
        return

    # Force-set a permanent password so we skip the NEW_PASSWORD_REQUIRED challenge
    client.admin_set_user_password(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=TEST_EMAIL,
        Password=TEST_PASSWORD,
        Permanent=True,
    )
    print("Test user created and confirmed.")


# ── Request helpers ───────────────────────────────────────────────────────────

def api(method: str, path: str, token: str, body: dict = None) -> requests.Response:
    url = f"{API_URL}{path}"
    headers = {"Authorization": token, "Content-Type": "application/json"}
    kwargs = {"headers": headers, "timeout": 10}
    if body is not None:
        kwargs["json"] = body
    return requests.request(method, url, **kwargs)


# ── Test suites ───────────────────────────────────────────────────────────────

def test_list_empty(token: str) -> None:
    section("List tasks (empty)")
    r = api("GET", "/tasks", token)
    check("Returns 200", r.status_code == 200, f"Got {r.status_code}")
    check("Body is a list", isinstance(r.json(), list), f"Got {type(r.json())}")
    check("List is empty", r.json() == [], f"Got {r.json()}")


def test_create(token: str) -> str | None:
    section("Create task")

    # Valid create
    r = api("POST", "/tasks", token, {
        "title": "Test task",
        "description": "Created by test script",
        "status": "todo",
        "priority": "high",
        "due_date": "2025-12-31",
    })
    check("Returns 201", r.status_code == 201, f"Got {r.status_code}: {r.text}")

    task = r.json()
    check("Has task_id", "task_id" in task, str(task))
    check("Title matches", task.get("title") == "Test task")
    check("Status is todo", task.get("status") == "todo")
    check("Priority is high", task.get("priority") == "high")
    check("Has created_at", "created_at" in task)
    check("Has updated_at", "updated_at" in task)

    task_id = task.get("task_id")

    # Missing title
    r2 = api("POST", "/tasks", token, {"description": "No title"})
    check("Missing title returns 400", r2.status_code == 400, f"Got {r2.status_code}: {r2.text}")

    # Invalid status
    r3 = api("POST", "/tasks", token, {"title": "Bad status", "status": "invalid"})
    check("Invalid status returns 400", r3.status_code == 400, f"Got {r3.status_code}: {r3.text}")

    # Invalid priority
    r4 = api("POST", "/tasks", token, {"title": "Bad priority", "priority": "critical"})
    check("Invalid priority returns 400", r4.status_code == 400, f"Got {r4.status_code}: {r4.text}")

    # Minimal valid create (title only)
    r5 = api("POST", "/tasks", token, {"title": "Minimal task"})
    check("Title-only create returns 201", r5.status_code == 201, f"Got {r5.status_code}: {r5.text}")
    minimal = r5.json()
    check("Defaults status to todo", minimal.get("status") == "todo")
    check("Defaults priority to medium", minimal.get("priority") == "medium")

    # Clean up the minimal task
    if minimal.get("task_id"):
        api("DELETE", f"/tasks/{minimal['task_id']}", token)

    return task_id


def test_get(token: str, task_id: str) -> None:
    section("Get task")

    r = api("GET", f"/tasks/{task_id}", token)
    check("Returns 200", r.status_code == 200, f"Got {r.status_code}: {r.text}")
    task = r.json()
    check("task_id matches", task.get("task_id") == task_id)
    check("Title is correct", task.get("title") == "Test task")

    # Non-existent task
    r2 = api("GET", "/tasks/does-not-exist-00000000", token)
    check("Non-existent returns 404", r2.status_code == 404, f"Got {r2.status_code}: {r2.text}")


def test_list_after_create(token: str, task_id: str) -> None:
    section("List tasks (after create)")
    r = api("GET", "/tasks", token)
    check("Returns 200", r.status_code == 200)
    items = r.json()
    check("List has 1 item", len(items) == 1, f"Got {len(items)} items")
    check("Item has correct task_id", items[0].get("task_id") == task_id)


def test_update(token: str, task_id: str) -> None:
    section("Update task")

    # Partial update
    r = api("PUT", f"/tasks/{task_id}", token, {
        "status": "in_progress",
        "priority": "low",
    })
    check("Partial update returns 200", r.status_code == 200, f"Got {r.status_code}: {r.text}")
    task = r.json()
    check("Status updated", task.get("status") == "in_progress")
    check("Priority updated", task.get("priority") == "low")
    check("Title unchanged", task.get("title") == "Test task")
    check("updated_at changed", task.get("updated_at") != task.get("created_at"))

    # Full update
    r2 = api("PUT", f"/tasks/{task_id}", token, {
        "title": "Updated title",
        "description": "Updated description",
        "status": "done",
        "priority": "medium",
        "due_date": "2026-01-15",
    })
    check("Full update returns 200", r2.status_code == 200, f"Got {r2.status_code}: {r2.text}")
    task2 = r2.json()
    check("Title updated", task2.get("title") == "Updated title")
    check("Status is done", task2.get("status") == "done")

    # Invalid status on update
    r3 = api("PUT", f"/tasks/{task_id}", token, {"status": "not_a_status"})
    check("Invalid status update returns 400", r3.status_code == 400, f"Got {r3.status_code}")

    # Empty body
    r4 = api("PUT", f"/tasks/{task_id}", token, {})
    check("Empty body returns 400", r4.status_code == 400, f"Got {r4.status_code}")

    # Non-existent task
    r5 = api("PUT", "/tasks/does-not-exist-00000000", token, {"title": "Ghost"})
    check("Update non-existent returns 404", r5.status_code == 404, f"Got {r5.status_code}")


def test_delete(token: str, task_id: str) -> None:
    section("Delete task")

    r = api("DELETE", f"/tasks/{task_id}", token)
    check("Returns 204", r.status_code == 204, f"Got {r.status_code}: {r.text}")

    # Confirm it is gone
    r2 = api("GET", f"/tasks/{task_id}", token)
    check("Deleted task returns 404", r2.status_code == 404, f"Got {r2.status_code}")

    # Double delete
    r3 = api("DELETE", f"/tasks/{task_id}", token)
    check("Double delete returns 404", r3.status_code == 404, f"Got {r3.status_code}")


def test_list_after_delete(token: str) -> None:
    section("List tasks (after delete)")
    r = api("GET", "/tasks", token)
    check("Returns 200", r.status_code == 200)
    items = r.json()
    check("List is empty again", items == [], f"Got {len(items)} items")


def test_auth_required() -> None:
    section("Auth enforcement")

    r = requests.get(f"{API_URL}/tasks", timeout=10)
    check("No token returns 401", r.status_code == 401, f"Got {r.status_code}")

    r2 = requests.get(f"{API_URL}/tasks", headers={"Authorization": "Bearer invalid.token.here"}, timeout=10)
    check("Invalid token returns 401", r2.status_code == 401, f"Got {r2.status_code}")


# ── Entry point ───────────────────────────────────────────────────────────────

def validate_config() -> None:
    missing = [name for name, val in {
        "API_URL": API_URL,
        "COGNITO_CLIENT_ID": COGNITO_CLIENT_ID,
        "TEST_EMAIL": TEST_EMAIL,
        "TEST_PASSWORD": TEST_PASSWORD,
    }.items() if not val]

    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        print("\nSet them and re-run:")
        for var in missing:
            print(f"  export {var}=...")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Memoire Tasks API end-to-end tests")
    parser.add_argument("--create-user", action="store_true", help="Create the test Cognito user before running tests")
    args = parser.parse_args()

    validate_config()

    print(f"\n{BOLD}Memoire Tasks API - End-to-End Tests{RESET}")
    print(f"API URL: {API_URL}")
    print(f"User:    {TEST_EMAIL}")

    if args.create_user:
        print()
        create_test_user()

    # Authenticate
    print("\nAuthenticating...")
    try:
        token = get_token()
        print("Authentication successful.")
    except Exception as e:
        print(f"Authentication failed: {e}")
        print("Run with --create-user to create the test user first.")
        sys.exit(1)

    # Run all test suites
    task_id = None
    try:
        test_auth_required()
        test_list_empty(token)
        task_id = test_create(token)
        if task_id:
            test_list_after_create(token, task_id)
            test_get(token, task_id)
            test_update(token, task_id)
            test_delete(token, task_id)
            test_list_after_delete(token)
        else:
            print(f"\n  [{SKIP}] Skipping get/update/delete — task creation failed")
    except Exception:
        print(f"\n  [{FAIL}] Unexpected error during tests:")
        traceback.print_exc()
        results["failed"] += 1

    # Summary
    total = results["passed"] + results["failed"]
    print(f"\n{'=' * 40}")
    print(f"{BOLD}Results: {results['passed']}/{total} passed{RESET}")
    if results["errors"]:
        print("\nFailed checks:")
        for err in results["errors"]:
            print(f"  - {err}")
    print()

    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
