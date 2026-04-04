"""Unit tests for lambda/home/handler.py — admin/stats access control."""

import os
import sys
import unittest


from conftest import load_lambda

os.environ["PROJECT_NAME"]    = "test"
os.environ["FUNCTION_PREFIX"] = "test"
os.environ["FRONTEND_BUCKET"] = "test-bucket"
os.environ["TASKS_TABLE"]     = "test-tasks"
os.environ["JOURNAL_TABLE"]   = "test-journal"
os.environ["NOTES_TABLE"]     = "test-notes"
os.environ["FOLDERS_TABLE"]   = "test-folders"
os.environ["HABITS_TABLE"]    = "test-habits"
os.environ["HEALTH_TABLE"]    = "test-health"
os.environ["NUTRITION_TABLE"] = "test-nutrition"
os.environ["SETTINGS_TABLE"]  = "test-settings"


ADMIN_ID = "admin-sub-001"
USER_ID  = "regular-user-002"


def _event(path, user_id=""):
    return {
        "requestContext": {
            "http": {"method": "GET"},
            "authorizer": {"lambda": {"user_id": user_id}},
        },
        "rawPath": path,
    }


class TestAdminStats(unittest.TestCase):

    def setUp(self):
        # Reload the handler with the desired ADMIN_USER_IDS for each test.
        # We manipulate the module-level set directly to avoid full reloads.
        self._orig = None

    def _load_with_admins(self, admin_ids: str):
        os.environ["ADMIN_USER_IDS"] = admin_ids
        # Remove cached module so it re-executes with new env
        for key in list(sys.modules.keys()):
            if "home" in key.lower() and "handler" in key.lower():
                del sys.modules[key]
        return load_lambda("home", "handler.py")

    def test_admin_can_access_stats(self):
        handler = self._load_with_admins(ADMIN_ID)
        r = handler.lambda_handler(_event("/admin/stats", ADMIN_ID), None)
        # get_stats() may error internally (no real AWS), but the auth check passes
        self.assertNotEqual(r["statusCode"], 403)

    def test_non_admin_blocked(self):
        handler = self._load_with_admins(ADMIN_ID)
        r = handler.lambda_handler(_event("/admin/stats", USER_ID), None)
        self.assertEqual(r["statusCode"], 403)

    def test_empty_user_id_blocked(self):
        handler = self._load_with_admins(ADMIN_ID)
        r = handler.lambda_handler(_event("/admin/stats", ""), None)
        self.assertEqual(r["statusCode"], 403)

    def test_no_admin_ids_configured_blocks_all(self):
        handler = self._load_with_admins("")
        r = handler.lambda_handler(_event("/admin/stats", ADMIN_ID), None)
        self.assertEqual(r["statusCode"], 403)

    def test_multiple_admins_allowed(self):
        other_admin = "admin-sub-002"
        handler = self._load_with_admins(f"{ADMIN_ID},{other_admin}")
        r = handler.lambda_handler(_event("/admin/stats", other_admin), None)
        self.assertNotEqual(r["statusCode"], 403)

    def test_costs_does_not_require_admin(self):
        """GET /home/costs is scoped per-user and should not require admin."""
        handler = self._load_with_admins(ADMIN_ID)
        r = handler.lambda_handler(_event("/home/costs", USER_ID), None)
        # May fail with 500 (no real Cost Explorer) but not 403
        self.assertNotEqual(r["statusCode"], 403)

    def test_unknown_path_returns_404(self):
        handler = self._load_with_admins(ADMIN_ID)
        r = handler.lambda_handler(_event("/admin/unknown", ADMIN_ID), None)
        self.assertEqual(r["statusCode"], 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
