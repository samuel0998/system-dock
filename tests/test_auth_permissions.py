import unittest

from api.auth import _resolve_role_from_row, _normalize_bool


class AuthPermissionTests(unittest.TestCase):
    def test_normalize_bool(self):
        self.assertTrue(_normalize_bool(True))
        self.assertTrue(_normalize_bool("true"))
        self.assertFalse(_normalize_bool(False))
        self.assertFalse(_normalize_bool("false"))

    def test_dockview_false_blocks_even_if_level_exists(self):
        row = {
            "login": "alepluc",
            "permission_dockview": False,
            "permission_level_dockview": "LC1",
        }
        self.assertIsNone(_resolve_role_from_row(row))

    def test_dockview_true_uses_level(self):
        row = {
            "login": "operador1",
            "permission_dockview": True,
            "permission_level_dockview": "LC3",
        }
        self.assertEqual(_resolve_role_from_row(row), "LC3")

    def test_legacy_only_boolean_true_falls_back_to_lc5(self):
        row = {
            "login": "operador2",
            "permission_dockview": True,
        }
        self.assertEqual(_resolve_role_from_row(row), "LC5")


if __name__ == "__main__":
    unittest.main()
