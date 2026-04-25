import sqlite3
from modules.config import DB_NAME
import datetime

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS messages 
                        (id INTEGER PRIMARY KEY, author TEXT, text TEXT, ts INTEGER)''')

def clear_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM messages")

def save_message(msg_id, author, text, ts):
    timestamp = int(ts.timestamp()) if hasattr(ts, 'timestamp') else int(ts)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR IGNORE INTO messages VALUES (?, ?, ?, ?)", (msg_id, author, text, timestamp))
        conn.execute("DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT 500)")

def update_message_text(msg_id, new_text):
    
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE messages SET text = ? WHERE id = ?", (new_text, msg_id))

def get_max_id_in_db():
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT MAX(id) FROM messages").fetchone()
    return res[0] if res and res[0] else 0

def get_history_from_db(count):
    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute("SELECT author, text FROM messages ORDER BY id DESC LIMIT ?", (count,)).fetchall()
    return [f"[{r[0]}]: {r[1]}" for r in rows][::-1]

def get_messages_before(msg_id, limit=30):
    """Берет сообщения строго ПЕРЕД указанным ID"""
    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute(
            "SELECT author, text FROM messages WHERE id < ? ORDER BY id DESC LIMIT ?", 
            (msg_id, limit)
        ).fetchall()
    return [f"[{r[0]}]: {r[1]}" for r in rows][::-1]

def get_messages_after(msg_id, limit=10):
    """Берет сообщения строго ПОСЛЕ указанного ID"""
    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute(
            "SELECT author, text FROM messages WHERE id > ? ORDER BY id ASC LIMIT ?", 
            (msg_id, limit)
        ).fetchall()
    return [f"[{r[0]}]: {r[1]}" for r in rows]

def get_messages_between(start_id, end_id):
    """Берет сообщения в диапазоне ID включительно"""
    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute(
            "SELECT author, text FROM messages WHERE id >= ? AND id <= ? ORDER BY id ASC", 
            (start_id, end_id)
        ).fetchall()
    return [f"[{r[0]}]: {r[1]}" for r in rows]

# Создаем таблицу для лимитов
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS messages 
                        (id INTEGER PRIMARY KEY, author TEXT, text TEXT, ts INTEGER)''')
        # Таблица лимитов: id_пользователя, дата, кол-во запросов
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_limits 
                        (user_id INTEGER, day TEXT, count INTEGER, PRIMARY KEY(user_id, day))''')

def get_user_requests(user_id):
    """Возвращает кол-во запросов юзера за сегодня"""
    today = datetime.date.today().isoformat()
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT count FROM daily_limits WHERE user_id = ? AND day = ?", (user_id, today)).fetchone()
    return res[0] if res else 0

def increment_user_requests(user_id):
    """Увеличивает счетчик запросов на 1"""
    today = datetime.date.today().isoformat()
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''INSERT INTO daily_limits (user_id, day, count) VALUES (?, ?, 1)
                        ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1''', (user_id, today))