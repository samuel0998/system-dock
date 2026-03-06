import os
import unittest
from flask import Flask

from db import init_db


class DbTimezoneConfigTests(unittest.TestCase):
    def test_postgres_sets_utc_timezone_in_engine_options(self):
        old = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/testdb"
            app = Flask(__name__)
            init_db(app)
            self.assertEqual(
                app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {}).get("connect_args", {}).get("options"),
                "-c timezone=UTC",
            )
        finally:
            if old is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old


if __name__ == "__main__":
    unittest.main()
