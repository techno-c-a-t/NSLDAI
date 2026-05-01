import importlib
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime
from unittest.mock import patch


def load_manuscript(db_path):
    env = {
        "API_ID": "123",
        "API_HASH": "hash",
        "TARGET_CHAT_ID": "-100123",
        "DEFAULT_API_KEY": "key",
        "MANUSCRIPT_DB_PATH": db_path,
    }
    dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    sys.modules.pop("modules.config", None)
    sys.modules.pop("modules.manuscript", None)
    with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"dotenv": dotenv}):
        return importlib.import_module("modules.manuscript")


def load_postgres_manuscript():
    env = {
        "API_ID": "123",
        "API_HASH": "hash",
        "TARGET_CHAT_ID": "-100123",
        "DEFAULT_API_KEY": "key",
        "MANUSCRIPT_DATABASE_URL": "postgresql+psycopg://u:p@db/nsldnk",
    }
    dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    sys.modules.pop("modules.config", None)
    sys.modules.pop("modules.manuscript", None)
    with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"dotenv": dotenv}):
        return importlib.import_module("modules.manuscript")


class FakeCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        return None

    def fetchall(self):
        return [("summary",)]


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_obj


class ManuscriptIntegrationTests(unittest.TestCase):
    def test_save_message_mirrors_nsldnk_message_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript = load_manuscript(f"{tmp}/nsldnk.db")
            user = types.SimpleNamespace(id=7, username="alice", first_name="Alice")
            chat = types.SimpleNamespace(id=-100123)
            message = types.SimpleNamespace(
                id=42,
                chat=chat,
                from_user=user,
                reply_to_message=None,
                text="hello",
                date=datetime(2026, 5, 1, 12, 0, 0),
            )

            manuscript.save_message(message)

            with sqlite3.connect(f"{tmp}/nsldnk.db") as conn:
                row = conn.execute(
                    "SELECT chat_id, telegram_message_id, user_id, username, text FROM messages"
                ).fetchone()
            self.assertEqual(row, (-100123, 42, 7, "alice", "hello"))

    def test_recent_segments_are_prepended(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript = load_manuscript(f"{tmp}/nsldnk.db")
            with sqlite3.connect(f"{tmp}/nsldnk.db") as conn:
                manuscript._ensure_sqlite_tables(conn)
                conn.execute(
                    """INSERT INTO manuscript_segments
                       (chat_id, from_message_id, to_message_id, summary_text)
                       VALUES (?, ?, ?, ?)""",
                    (-100123, 1, 10, "old summary"),
                )
                conn.execute(
                    """INSERT INTO manuscript_segments
                       (chat_id, from_message_id, to_message_id, summary_text)
                       VALUES (?, ?, ?, ?)""",
                    (-100123, 11, 20, "new summary"),
                )

            history = manuscript.prepend_segments(["[Alice]: live message"], -100123)

            self.assertEqual(
                history,
                [
                    "[Манускрипт]: old summary",
                    "[Манускрипт]: new summary",
                    "[Alice]: live message",
                ],
            )

    def test_postgres_url_uses_psycopg_dsn(self):
        manuscript = load_postgres_manuscript()
        fake_conn = FakeConnection()
        fake_psycopg = types.SimpleNamespace(connect=lambda dsn, connect_timeout: fake_conn)
        user = types.SimpleNamespace(id=7, username="alice", first_name="Alice")
        message = types.SimpleNamespace(
            id=42,
            chat=types.SimpleNamespace(id=-100123),
            from_user=user,
            reply_to_message=None,
            text="hello",
            date=datetime(2026, 5, 1, 12, 0, 0),
        )

        with patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            manuscript.save_message(message)
            segments = manuscript.get_recent_segments(-100123)

        self.assertEqual(segments, ["summary"])
        self.assertIn("postgresql://u:p@db/nsldnk", manuscript._postgres_dsn())
        self.assertEqual(len(fake_conn.cursor_obj.calls), 3)


if __name__ == "__main__":
    unittest.main()
