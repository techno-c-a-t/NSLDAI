import json
import sqlite3

import modules.config as cfg


def _database_url():
    return cfg.MANUSCRIPT_DATABASE_URL


def _sqlite_path():
    if cfg.MANUSCRIPT_DB_PATH:
        return cfg.MANUSCRIPT_DB_PATH
    url = _database_url()
    if not url:
        return None
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            return url[len(prefix):]
    return None


def _postgres_dsn():
    url = _database_url()
    if not url or not url.startswith(("postgresql://", "postgresql+psycopg://")):
        return None
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def is_enabled():
    return bool(_postgres_dsn() or _sqlite_path())


def _message_values(message):
    user = message.from_user
    return {
        "chat_id": message.chat.id if message.chat else cfg.TARGET_CHAT_ID,
        "telegram_message_id": message.id,
        "user_id": user.id if user else 0,
        "username": user.username if user else None,
        "text": message.text,
        "language": None,
        "reply_to_message_id": message.reply_to_message.id if message.reply_to_message else None,
        "created_at": message.date.isoformat() if hasattr(message.date, "isoformat") else message.date,
        "raw_payload": json.dumps(
            {
                "source": "phantom",
                "message_id": message.id,
                "username": user.username if user else None,
                "first_name": user.first_name if user else None,
            },
            ensure_ascii=False,
        ),
    }


def save_message(message):
    if _postgres_dsn():
        _save_message_postgres(_message_values(message))
    elif _sqlite_path():
        _save_message_sqlite(_message_values(message))


def _save_message_postgres(values):
    try:
        import psycopg

        with psycopg.connect(_postgres_dsn(), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM messages WHERE chat_id = %s AND telegram_message_id = %s LIMIT 1",
                    (values["chat_id"], values["telegram_message_id"]),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """UPDATE messages
                           SET user_id = %(user_id)s, username = %(username)s, text = %(text)s,
                               language = %(language)s, reply_to_message_id = %(reply_to_message_id)s,
                               created_at = %(created_at)s, raw_payload = %(raw_payload)s::json
                           WHERE id = %(id)s""",
                        values | {"id": existing[0]},
                    )
                else:
                    cur.execute(
                        """INSERT INTO messages
                           (chat_id, telegram_message_id, user_id, username, text, language,
                            reply_to_message_id, created_at, raw_payload)
                           VALUES
                           (%(chat_id)s, %(telegram_message_id)s, %(user_id)s, %(username)s,
                            %(text)s, %(language)s, %(reply_to_message_id)s, %(created_at)s,
                            %(raw_payload)s::json)""",
                        values,
                    )
    except Exception:
        pass


def _save_message_sqlite(values):
    try:
        with sqlite3.connect(_sqlite_path()) as conn:
            _ensure_sqlite_tables(conn)
            existing = conn.execute(
                "SELECT id FROM messages WHERE chat_id = ? AND telegram_message_id = ? LIMIT 1",
                (values["chat_id"], values["telegram_message_id"]),
            ).fetchone()
            params = (
                values["chat_id"],
                values["telegram_message_id"],
                values["user_id"],
                values["username"],
                values["text"],
                values["language"],
                values["reply_to_message_id"],
                values["created_at"],
                values["raw_payload"],
            )
            if existing:
                conn.execute(
                    """UPDATE messages
                       SET chat_id = ?, telegram_message_id = ?, user_id = ?, username = ?,
                           text = ?, language = ?, reply_to_message_id = ?, created_at = ?,
                           raw_payload = ?
                       WHERE id = ?""",
                    params + (existing[0],),
                )
            else:
                conn.execute(
                    """INSERT INTO messages
                       (chat_id, telegram_message_id, user_id, username, text, language,
                        reply_to_message_id, created_at, raw_payload)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    params,
                )
    except sqlite3.Error:
        pass


def get_recent_segments(chat_id, limit=None):
    if _postgres_dsn():
        return _get_recent_segments_postgres(chat_id, limit)
    if _sqlite_path():
        return _get_recent_segments_sqlite(chat_id, limit)
    return []


def _get_recent_segments_postgres(chat_id, limit=None):
    try:
        import psycopg

        with psycopg.connect(_postgres_dsn(), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT summary_text
                       FROM manuscript_segments
                       WHERE chat_id = %s
                       ORDER BY to_message_id DESC
                       LIMIT %s""",
                    (chat_id, limit or cfg.MANUSCRIPT_SEGMENTS_LIMIT),
                )
                rows = cur.fetchall()
    except Exception:
        rows = []
    return [row[0] for row in rows if row[0]][::-1]


def _get_recent_segments_sqlite(chat_id, limit=None):
    try:
        with sqlite3.connect(_sqlite_path()) as conn:
            _ensure_sqlite_tables(conn)
            rows = conn.execute(
                """SELECT summary_text
                   FROM manuscript_segments
                   WHERE chat_id = ?
                   ORDER BY to_message_id DESC
                   LIMIT ?""",
                (chat_id, limit or cfg.MANUSCRIPT_SEGMENTS_LIMIT),
            ).fetchall()
    except sqlite3.Error:
        rows = []
    return [row[0] for row in rows if row[0]][::-1]


def _ensure_sqlite_tables(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id BIGINT,
            telegram_message_id BIGINT,
            user_id BIGINT,
            username VARCHAR(64),
            text TEXT,
            language VARCHAR(8),
            reply_to_message_id BIGINT,
            created_at DATETIME,
            raw_payload JSON
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS manuscript_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id BIGINT,
            from_message_id BIGINT,
            to_message_id BIGINT,
            summary_text TEXT,
            model VARCHAR(64),
            token_usage JSON,
            created_at DATETIME
        )"""
    )


def prepend_segments(history, chat_id):
    segments = get_recent_segments(chat_id)
    if not segments:
        return history
    manuscript = ["[Манускрипт]: " + text for text in segments]
    return manuscript + history
