import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sqlalchemy.engine import make_url

from app.database_url import normalize_database_url


BACKEND = Path(__file__).resolve().parents[1]


class DatabaseDriverTests(unittest.TestCase):
    def test_postgresql_urls_preserve_connection_parameters(self):
        for driver in ("postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"):
            with self.subTest(driver=driver):
                # Synthetic credentials only; exercise ConfigParser-sensitive characters.
                source = f"{driver}://test:synthetic%40pass%25word@localhost:5432/test?sslmode=require&application_name=club"
                expected = make_url(source).set(drivername="postgresql+psycopg2")
                result = normalize_database_url(source)
                self.assertEqual(make_url(result), expected)
                self.assertEqual(normalize_database_url(result), result)

    def test_sqlite_url_is_unchanged(self):
        source = "sqlite:///relative/test.db"
        self.assertEqual(normalize_database_url(source), source)

    def test_application_and_online_alembic_load_same_driver_without_connecting(self):
        script = r'''
from unittest.mock import patch
import sqlalchemy
from sqlalchemy.engine import Engine, make_url
from alembic import command
from alembic.config import Config
from app.db import engine, DATABASE_URL

assert engine.dialect.driver == "psycopg2"
assert engine.dialect.dbapi.__name__ == "psycopg2"
seen = []
original = sqlalchemy.engine_from_config
def inspect_engine(*args, **kwargs):
    migration_engine = original(*args, **kwargs)
    assert migration_engine.url == engine.url
    assert migration_engine.dialect.dbapi is engine.dialect.dbapi
    seen.append(migration_engine.dialect.driver)
    return migration_engine
class ConnectionNotAllowed(Exception):
    pass
config = Config("alembic.ini")
with patch("sqlalchemy.engine_from_config", inspect_engine), patch.object(Engine, "connect", side_effect=ConnectionNotAllowed):
    try:
        command.upgrade(config, "head")
    except ConnectionNotAllowed:
        pass
    else:
        raise AssertionError("Online migration did not reach its connection stage")
assert seen == ["psycopg2"]
assert make_url(config.get_main_option("sqlalchemy.url")) == engine.url
engine.dispose()
'''
        for driver in ("postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"):
            with self.subTest(driver=driver):
                env = os.environ.copy()
                env["DATABASE_URL"] = f"{driver}://test:synthetic%40pass%25word@localhost:5432/test?sslmode=require"
                result = subprocess.run([sys.executable, "-c", script], cwd=BACKEND, env=env,
                                        capture_output=True, text=True, timeout=30)
                # Avoid reflecting database URLs or credentials in test failures.
                self.assertEqual(result.returncode, 0, "Driver validation subprocess failed")

    def test_upgrade_head_preserves_existing_data_in_isolated_database(self):
        script = r'''
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from app.db import engine
config = Config("alembic.ini")
command.upgrade(config, "efe9de7c931d")
with engine.begin() as connection:
    connection.execute(text("INSERT INTO users (username, password_hash, is_admin) VALUES ('migration_test', 'synthetic', false)"))
command.upgrade(config, "head")
command.upgrade(config, "head")
with engine.connect() as connection:
    assert connection.execute(text("SELECT username FROM users")).scalars().all() == ["migration_test"]
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "h8b9c0d1e2f3"
from app.main import app
assert app is not None
engine.dispose()
'''
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env["DATABASE_URL"] = "sqlite:///" + (Path(directory) / "migration-test.db").as_posix()
            result = subprocess.run([sys.executable, "-c", script], cwd=BACKEND, env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, "Isolated migration validation failed")


if __name__ == "__main__":
    unittest.main()
