"""
@file database.py
@brief Слой работы с базой данных SQLite3 (Master-Table + Per-Chat Tables Architecture).
@details Реализует хранение сообщений с автоматической ротацией (до 2000 записей на чат),
         учет дневных лимитов вызова ИИ, приватные досье с набором псевдонимов/имен, настройки чатов,
         режим трассировки и чистый режим работы админа (clean_mode).
"""

import re
import sqlite3
import datetime
import time
import logging
from typing import List, Optional, Union, Tuple, Dict, Any
import modules.config as cfg
from modules.config import DB_NAME

logger = logging.getLogger(__name__)

class DossierString(str):
    """
    @brief Гибридный строковый тип досье, сохраняющий 100% обратную совместимость как со строковыми equality-сравнениями,
           так и со словарем d['dossier_text'], d['aliases'], d['username'], d['user_id'].
    """
    user_id: int = 0
    username: str = ""
    aliases: str = ""
    dossier_text: str = ""

    def __getitem__(self, item: Any) -> Any:
        if item == "dossier_text":
            return str(self)
        if item == "aliases":
            return getattr(self, "aliases", "")
        if item == "username":
            return getattr(self, "username", "")
        if item == "user_id":
            return getattr(self, "user_id", 0)
        return super().__getitem__(item)

def get_connection() -> sqlite3.Connection:
    """
    @brief Вспомогательная функция открытия соединения с БД.
    @details Включает WAL-режим (Write-Ahead Logging) для потокобезопасной работы в asyncio.
    @return Объект соединения sqlite3.Connection.
    """
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        pass
    return conn

def sanitize_table_name(chat_id: int) -> str:
    """
    @brief Преобразует ID чата Telegram (включая отрицательные числа) в валидное имя таблицы SQL.
    @param chat_id Уникальный идентификатор чата Telegram.
    @return Строка вида 'messages_chat_100123456789'.
    """
    clean_id = str(abs(int(chat_id)))
    return f"messages_chat_{clean_id}"

def init_db() -> None:
    """
    @brief Инициализирует мастер-таблицы базы данных и выполняет миграции.
    @details Создает таблицы chats_master, daily_limits, user_dossiers при их отсутствии.
    """
    try:
        with get_connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS chats_master 
                            (chat_id INTEGER PRIMARY KEY, chat_name TEXT, community_id TEXT, is_active INTEGER DEFAULT 1, voice_mode TEXT DEFAULT 'AUTO', trace_mode INTEGER DEFAULT 0, summary_limit INTEGER DEFAULT 100, clean_mode INTEGER DEFAULT 0, created_at INTEGER)''')
            
            cursor = conn.execute("PRAGMA table_info(chats_master)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'voice_mode' not in columns:
                conn.execute("ALTER TABLE chats_master ADD COLUMN voice_mode TEXT DEFAULT 'AUTO'")
            if 'trace_mode' not in columns:
                conn.execute("ALTER TABLE chats_master ADD COLUMN trace_mode INTEGER DEFAULT 0")
            if 'summary_limit' not in columns:
                conn.execute("ALTER TABLE chats_master ADD COLUMN summary_limit INTEGER DEFAULT 100")
            if 'clean_mode' not in columns:
                conn.execute("ALTER TABLE chats_master ADD COLUMN clean_mode INTEGER DEFAULT 0")
            if 'gemma_dossier_mode' not in columns:
                conn.execute("ALTER TABLE chats_master ADD COLUMN gemma_dossier_mode INTEGER DEFAULT 1")

            conn.execute('''CREATE TABLE IF NOT EXISTS daily_limits 
                            (user_id INTEGER, day TEXT, count INTEGER, PRIMARY KEY(user_id, day))''')
            
            conn.execute('''CREATE TABLE IF NOT EXISTS user_dossiers 
                            (chat_id INTEGER, user_id INTEGER, username TEXT, aliases TEXT, dossier_text TEXT, updated_at INTEGER, PRIMARY KEY (chat_id, user_id))''')

            cursor = conn.execute("PRAGMA table_info(user_dossiers)")
            dossier_cols = [column[1] for column in cursor.fetchall()]
            if 'aliases' not in dossier_cols:
                conn.execute("ALTER TABLE user_dossiers ADD COLUMN aliases TEXT DEFAULT ''")

            # Загружаем все ранее разрешенные чаты из БД в память
            active_rows = conn.execute("SELECT chat_id FROM chats_master WHERE is_active = 1").fetchall()
            for r in active_rows:
                cfg.ALLOWED_CHAT_IDS.add(r[0])
    except sqlite3.OperationalError as e:
        logger.warning(f"Не удалось инициализировать мастер-таблицы БД: {e}")

def register_chat(chat_id: int, chat_name: str = "Unregistered Chat", community_id: Optional[str] = None) -> None:
    """
    @brief Регистрирует чат в мастер-таблице chats_master и создает для него персональную таблицу историй.
    @param chat_id ID чата.
    @param chat_name Человекочитаемое имя чата.
    @param community_id Опциональный ID сообщества/группы для объединенных чатов.
    """
    cfg.ALLOWED_CHAT_IDS.add(int(chat_id))
    table_name = sanitize_table_name(chat_id)
    now = int(time.time())
    try:
        with get_connection() as conn:
            conn.execute('''INSERT INTO chats_master (chat_id, chat_name, community_id, is_active, created_at)
                            VALUES (?, ?, ?, 1, ?)
                            ON CONFLICT(chat_id) DO UPDATE SET chat_name=excluded.chat_name, is_active=1''',
                         (chat_id, chat_name, community_id, now))
            conn.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} 
                            (id INTEGER PRIMARY KEY, author TEXT, text TEXT, ts INTEGER)''')
    except sqlite3.OperationalError as e:
        logger.warning(f"Ошибка регистрации чата {chat_id}: {e}")

def clear_db(chat_id: int) -> None:
    """
    @brief Очищает персональную таблицу историй конкретного чата.
    @param chat_id ID чата.
    """
    table_name = sanitize_table_name(chat_id)
    try:
        with get_connection() as conn:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            register_chat(chat_id)
    except sqlite3.OperationalError:
        pass

def save_message(
    chat_id: int, 
    msg_id: int, 
    author: str, 
    text: str, 
    ts: Union[datetime.datetime, int],
    category: str = 'USER'
) -> None:
    """
    @brief Сохраняет новое сообщение в персональную таблицу чата с категорией и автоматической обрезкой истории.
    @details Поддерживает авто-миграцию колонки category TEXT DEFAULT 'USER'.
    @param chat_id ID чата.
    @param msg_id ID сообщения Telegram.
    @param author Форматированный автор ("Имя (@username)").
    @param text Текст сообщения.
    @param ts Временная метка (datetime или timestamp).
    @param category Категория сообщения ('USER', 'SERVICE', 'AI_SUMMARY', 'AI_RESPONSE', 'VOICE_TRANSCRIPTION').
    """
    table_name = sanitize_table_name(chat_id)
    timestamp = int(ts.timestamp()) if hasattr(ts, 'timestamp') else int(ts)
    try:
        with get_connection() as conn:
            conn.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} 
                            (id INTEGER PRIMARY KEY, author TEXT, text TEXT, ts INTEGER, category TEXT DEFAULT 'USER')''')
            try:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN category TEXT DEFAULT 'USER'")
            except sqlite3.OperationalError:
                pass
            conn.execute(
                f"INSERT OR REPLACE INTO {table_name} (id, author, text, ts, category) VALUES (?, ?, ?, ?, ?)", 
                (msg_id, author, text, timestamp, category)
            )
            conn.execute(f"DELETE FROM {table_name} WHERE id NOT IN (SELECT id FROM {table_name} ORDER BY id DESC LIMIT 2000)")
    except sqlite3.OperationalError as e:
        logger.warning(f"Ошибка сохранения сообщения в БД: {e}")

def update_message_text(chat_id: int, msg_id: int, new_text: str) -> None:
    """
    @brief Обновляет текст существующего сообщения в базе данных.
    @param chat_id ID чата.
    @param msg_id ID сообщения.
    @param new_text Новый отредактированный текст.
    """
    table_name = sanitize_table_name(chat_id)
    try:
        with get_connection() as conn:
            conn.execute(f"UPDATE {table_name} SET text = ? WHERE id = ?", (new_text, msg_id))
    except sqlite3.OperationalError:
        pass

def delete_messages_from_db(chat_id: int, message_ids: List[int]) -> None:
    """
    @brief Удаляет список сообщений по их ID из таблицы конкретного чата в БД SQLite.
    @param chat_id ID чата.
    @param message_ids Список ID сообщений Telegram для удаления.
    """
    if not message_ids:
        return
    table_name = sanitize_table_name(chat_id)
    placeholders = ",".join(["?"] * len(message_ids))
    try:
        with get_connection() as conn:
            conn.execute(f"DELETE FROM {table_name} WHERE id IN ({placeholders})", tuple(message_ids))
    except sqlite3.OperationalError as e:
        logger.warning(f"Ошибка удаления сообщений из БД: {e}")

def get_service_message_ids_from_db(chat_id: int, limit: int = 10) -> List[int]:
    """
    @brief Получает из БД список ID сообщений с категорией 'SERVICE' для конкретного чата.
    @param chat_id ID чата.
    @param limit Максимальное количество сообщений (по умолчанию 10).
    @return Список ID сообщений.
    """
    table_name = sanitize_table_name(chat_id)
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT id FROM {table_name} WHERE category = 'SERVICE' ORDER BY id DESC LIMIT ?", 
                (limit,)
            ).fetchall()
            return [r[0] for r in rows]
    except sqlite3.OperationalError:
        return []
    except sqlite3.OperationalError as e:
        logger.warning(f"Ошибка удаления сообщений из БД: {e}")

def get_max_id_in_db(chat_id: int) -> int:
    """
    @brief Возвращает максимальный ID сообщения, сохраненный в БД для конкретного чата.
    @param chat_id ID чата.
    @return Максимальный ID или 0.
    """
    table_name = sanitize_table_name(chat_id)
    try:
        with get_connection() as conn:
            res = conn.execute(f"SELECT MAX(id) FROM {table_name}").fetchone()
            return res[0] if res and res[0] else 0
    except sqlite3.OperationalError:
        return 0

def is_admin_command_or_service(text: str) -> bool:
    """
    @brief Определяет, является ли сообщение служебной технической командой админа или откликом бота.
    @details Все подобные сообщения отсекаются из контекста ИИ, чтобы не засорять промпт служебным синтаксисом.
    """
    if not text:
        return False
    t = text.strip()
    patterns = [
        r"(?i)^фантом,?\s*(записывай|дополни|вычеркивай|досье|список\s+досье|очисти\s+досье)",
        r"(?i)^досье\b",
        r"(?i)^фантом,?\s*(приберись|почисти|убери за собой|вайп)",
        r"(?i)^ВАЙП$",
        r"(?i)^дамп\s+\d+",
        r"(?i)^фантом,?\s*(включи|выключи)\s+(трассировку|чистый\s+режим|тихий\s+режим)",
        r"(?i)^(фантом|phantom|@tech_phantom),?\s+(гайд|помощь|help|команды)\b",
        r"(?i)^фантом,?\s*(слушай все гс|авто\s*гс|расшифровывай только по запросу|гс по запросу)"
    ]
    for p in patterns:
        if re.search(p, t):
            return True
    return False

def get_history_from_db(chat_id: int, count: int) -> List[str]:
    """
    @brief Считывает последние N обычных сообщений истории чата в хронологическом порядке (исключая служебные записи и команды).
    @param chat_id ID чата.
    @param count Количество запрашиваемых сообщений.
    @return Список строк в формате '[Автор]: Текст'.
    """
    table_name = sanitize_table_name(chat_id)
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT author, text, category FROM {table_name} WHERE category != 'SERVICE' ORDER BY id DESC LIMIT ?", 
                (count * 2,)
            ).fetchall()
            filtered = []
            for r in rows:
                if not is_admin_command_or_service(r[1]):
                    filtered.append(f"[{r[0]}]: {r[1]}")
                if len(filtered) >= count:
                    break
            return filtered[::-1]
    except sqlite3.OperationalError:
        return []

def get_messages_before(chat_id: int, msg_id: int, limit: int = 20) -> List[str]:
    """
    @brief Берет сообщения строго ПЕРЕД указанным ID из таблицы чата (исключая служебные команды).
    """
    table_name = sanitize_table_name(chat_id)
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT author, text FROM {table_name} WHERE id < ? AND category != 'SERVICE' ORDER BY id DESC LIMIT ?", 
                (msg_id, limit * 2)
            ).fetchall()
            filtered = [f"[{r[0]}]: {r[1]}" for r in rows if not is_admin_command_or_service(r[1])]
            return filtered[:limit][::-1]
    except sqlite3.OperationalError:
        return []

def get_messages_after(chat_id: int, msg_id: int, limit: int = 20) -> List[str]:
    """
    @brief Берет сообщения строго ПОСЛЕ указанного ID из таблицы чата (исключая служебные команды).
    """
    table_name = sanitize_table_name(chat_id)
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT author, text FROM {table_name} WHERE id > ? AND category != 'SERVICE' ORDER BY id ASC LIMIT ?", 
                (msg_id, limit * 2)
            ).fetchall()
            filtered = [f"[{r[0]}]: {r[1]}" for r in rows if not is_admin_command_or_service(r[1])]
            return filtered[:limit]
    except sqlite3.OperationalError:
        return []

def get_unique_messages_context(chat_id: int, queries: List[Tuple[str, tuple]]) -> List[str]:
    """
    @brief Безопасно собирает сообщения из нескольких SQL-запросов, фильтрует служебные команды и хронологически дедуплицирует их по ID.
    @param chat_id ID чата.
    @param queries Список кортежей вида (SQL-шаблон с {table_name}, кортеж_параметров).
    @return Хронологически отсортированный список дедуплицированных строк '[Автор]: Текст'.
    """
    table_name = sanitize_table_name(chat_id)
    seen_ids = set()
    messages_with_id: List[Tuple[int, str]] = []

    try:
        with get_connection() as conn:
            for sql_template, params in queries:
                full_sql = sql_template.format(table_name=table_name)
                rows = conn.execute(full_sql, params).fetchall()
                for row_id, author, text in rows:
                    if not is_admin_command_or_service(text):
                        if row_id not in seen_ids:
                            seen_ids.add(row_id)
                            messages_with_id.append((row_id, f"[{author}]: {text}"))
    except sqlite3.OperationalError:
        return []

    messages_with_id.sort(key=lambda x: x[0])
    return [msg_text for _, msg_text in messages_with_id]

def get_user_requests(user_id: int) -> int:
    """
    @brief Возвращает количество сделанных пользователем запросов к ИИ за сегодня.
    @param user_id ID пользователя Telegram.
    @return Число запросов.
    """
    today = datetime.date.today().isoformat()
    try:
        with get_connection() as conn:
            res = conn.execute("SELECT count FROM daily_limits WHERE user_id = ? AND day = ?", (user_id, today)).fetchone()
        return res[0] if res else 0
    except sqlite3.OperationalError:
        return 0

def increment_user_requests(user_id: int) -> None:
    """
    @brief Увеличивает счетчик запросов пользователя к ИИ на 1 за текущий день.
    @details Ошибки прав доступа SQLite не прерывают выполнение основного запроса ИИ.
    @param user_id ID пользователя Telegram.
    """
    today = datetime.date.today().isoformat()
    try:
        with get_connection() as conn:
            conn.execute('''INSERT INTO daily_limits (user_id, day, count) VALUES (?, ?, 1)
                            ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1''', (user_id, today))
    except sqlite3.OperationalError as e:
        logger.warning(f"Не удалось обновить счетчик запросов в БД: {e}")

# --- ФУНКЦИИ ПРИВАТНЫХ ДОСЬЕ ПОЛЬЗОВАТЕЛЕЙ С ПСЕВДОНИМАМИ ---

def get_user_dossier(chat_id: int, user_id: int) -> Optional[DossierString]:
    """
    @brief Считывает досье пользователя в конкретном чате по user_id.
    @param chat_id ID чата.
    @param user_id ID пользователя.
    @return Экземпляр DossierString (100% совместимый с str и d['dossier_text']) или None.
    """
    try:
        with get_connection() as conn:
            res = conn.execute("SELECT user_id, username, aliases, dossier_text FROM user_dossiers WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)).fetchone()
        if res and res[3]:
            ds = DossierString(res[3])
            ds.user_id = res[0]
            ds.username = res[1] or ""
            ds.aliases = res[2] or ""
            ds.dossier_text = res[3]
            return ds
    except sqlite3.OperationalError:
        pass
    return None

def get_user_dossier_by_username(chat_id: int, username: str) -> Optional[DossierString]:
    """
    @brief Ищет досье пользователя по юзернейму (без символа @).
    @param chat_id ID чата.
    @param username Юзернейм пользователя.
    @return Экземпляр DossierString или None.
    """
    clean_uname = username.lstrip("@").strip()
    if not clean_uname:
        return None
    try:
        with get_connection() as conn:
            res = conn.execute("SELECT user_id, username, aliases, dossier_text FROM user_dossiers WHERE chat_id = ? AND LOWER(username) = LOWER(?)", (chat_id, clean_uname)).fetchone()
        if res and res[3]:
            ds = DossierString(res[3])
            ds.user_id = res[0]
            ds.username = res[1] or ""
            ds.aliases = res[2] or ""
            ds.dossier_text = res[3]
            return ds
    except sqlite3.OperationalError:
        pass
    return None

def get_chat_dossiers_list(chat_id: int) -> List[Tuple[int, str]]:
    """
    @brief Возвращает список пользователей (user_id, username), у которых есть досье в данном чате.
    @param chat_id ID чата.
    @return Список кортежей (user_id, username).
    """
    try:
        with get_connection() as conn:
            rows = conn.execute("SELECT user_id, username FROM user_dossiers WHERE chat_id = ?", (chat_id,)).fetchall()
        return [(r[0], r[1] or str(r[0])) for r in rows]
    except sqlite3.OperationalError:
        return []

def get_chat_dossiers_with_aliases(chat_id: int) -> List[Dict[str, Any]]:
    """
    @brief Возвращает полный список всех досье чата с наборами псевдонимов/имен.
    @param chat_id ID чата.
    @return Список словарей [{'user_id', 'username', 'aliases', 'dossier_text'}].
    """
    try:
        with get_connection() as conn:
            rows = conn.execute("SELECT user_id, username, aliases, dossier_text FROM user_dossiers WHERE chat_id = ?", (chat_id,)).fetchall()
        return [{"user_id": r[0], "username": r[1] or str(r[0]), "aliases": r[2] or "", "dossier_text": r[3]} for r in rows]
    except sqlite3.OperationalError:
        return []

def save_user_dossier(chat_id: int, user_id: int, username: str, dossier_text: str, aliases: Optional[str] = None) -> None:
    """
    @brief Перезаписывает досье пользователя и его набор псевдонимов.
    @param chat_id ID чата.
    @param user_id ID пользователя.
    @param username Юзернейм пользователя.
    @param dossier_text Новый текст характеристики.
    @param aliases Набор псевдонимов через точку с запятой ("Олег;Олеженька;Олежка").
    """
    now = int(time.time())
    clean_uname = (username or "").lstrip("@").strip()
    clean_aliases = aliases.strip() if aliases else ""

    if not user_id and clean_uname:
        existing = get_user_dossier_by_username(chat_id, clean_uname)
        if existing:
            user_id = existing.user_id
        else:
            user_id = abs(hash(clean_uname)) % (10**9)

    try:
        with get_connection() as conn:
            if aliases is not None:
                conn.execute('''INSERT INTO user_dossiers (chat_id, user_id, username, aliases, dossier_text, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?)
                                ON CONFLICT(chat_id, user_id) DO UPDATE SET dossier_text=excluded.dossier_text, aliases=excluded.aliases, username=excluded.username, updated_at=excluded.updated_at''',
                             (chat_id, user_id, clean_uname, clean_aliases, dossier_text, now))
            else:
                conn.execute('''INSERT INTO user_dossiers (chat_id, user_id, username, dossier_text, updated_at)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(chat_id, user_id) DO UPDATE SET dossier_text=excluded.dossier_text, username=excluded.username, updated_at=excluded.updated_at''',
                             (chat_id, user_id, clean_uname, dossier_text, now))
    except sqlite3.OperationalError as e:
        logger.warning(f"Не удалось сохранить досье пользователя: {e}")

def append_user_dossier(chat_id: int, user_id: int, username: str, fact_text: str, new_aliases: Optional[str] = None) -> None:
    """
    @brief Добавляет новый факт и опциональные псевдонимы в существующее досье пользователя.
    @param chat_id ID чата.
    @param user_id ID пользователя.
    @param username Юзернейм пользователя.
    @param fact_text Текст добавляемого факта.
    @param new_aliases Опциональные новые псевдонимы через точку с запятой.
    """
    clean_uname = (username or "").lstrip("@").strip()
    current_data = get_user_dossier_by_username(chat_id, clean_uname) if not user_id else get_user_dossier(chat_id, user_id)
    
    if current_data:
        curr_text = current_data.dossier_text
        updated_text = f"{curr_text.strip()}\n- {fact_text.strip()}" if fact_text else curr_text
        curr_aliases = current_data.aliases
        
        if new_aliases:
            all_aliases = list(set([a.strip() for a in (curr_aliases + ";" + new_aliases).split(";") if a.strip()]))
            combined_aliases = ";".join(all_aliases)
        else:
            combined_aliases = curr_aliases

        save_user_dossier(chat_id, current_data.user_id, clean_uname, updated_text, aliases=combined_aliases)
    else:
        new_dossier = f"- {fact_text.strip()}" if fact_text else "Характеристика не заполнена."
        save_user_dossier(chat_id, user_id, clean_uname, new_dossier, aliases=new_aliases)

def clear_user_dossier_by_username(chat_id: int, username: str) -> bool:
    """
    @brief Удаляет досье пользователя в конкретном чате по его юзернейму.
    @param chat_id ID чата.
    @param username Юзернейм пользователя.
    @return True если досье было найдено и удалено.
    """
    clean_uname = username.lstrip("@").strip()
    try:
        with get_connection() as conn:
            cursor = conn.execute("DELETE FROM user_dossiers WHERE chat_id = ? AND LOWER(username) = LOWER(?)", (chat_id, clean_uname))
            return cursor.rowcount > 0
    except sqlite3.OperationalError:
        return False

def clear_user_dossier(chat_id: int, user_id: int) -> None:
    """
    @brief Удаляет досье пользователя в конкретном чате по user_id.
    @param chat_id ID чата.
    @param user_id ID пользователя.
    """
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM user_dossiers WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    except sqlite3.OperationalError:
        pass

# --- ФУНКЦИИ НАСТРОЕК РЕЖИМА ГС В ЧАТЕ ---

def get_chat_voice_mode(chat_id: int) -> str:
    """
    @brief Возвращает режим расшифровки ГС в чате ('AUTO' или 'ON_DEMAND').
    @param chat_id ID чата.
    @return Строка 'AUTO' или 'ON_DEMAND'.
    """
    try:
        with get_connection() as conn:
            res = conn.execute("SELECT voice_mode FROM chats_master WHERE chat_id = ?", (chat_id,)).fetchone()
        return res[0] if res and res[0] else 'AUTO'
    except sqlite3.OperationalError:
        return 'AUTO'

def set_chat_voice_mode(chat_id: int, mode: str) -> None:
    """
    @brief Устанавливает режим расшифровки ГС для конкретного чата.
    @param chat_id ID чата.
    @param mode Имя режима ('AUTO' или 'ON_DEMAND').
    """
    try:
        with get_connection() as conn:
            conn.execute("UPDATE chats_master SET voice_mode = ? WHERE chat_id = ?", (mode, chat_id))
    except sqlite3.OperationalError:
        pass

# --- ФУНКЦИИ НАСТРОЕК РЕЖИМА ТРАССИРОВКИ В ЧАТЕ ---

def get_chat_trace_mode(chat_id: int) -> bool:
    """
    @brief Проверяет, включен ли режим трассировки логов в ЛС для чата.
    @param chat_id ID чата.
    @return True если включен (1), иначе False (0).
    """
    try:
        with get_connection() as conn:
            res = conn.execute("SELECT trace_mode FROM chats_master WHERE chat_id = ?", (chat_id,)).fetchone()
        return bool(res[0]) if res and res[0] else False
    except sqlite3.OperationalError:
        return False

def set_chat_trace_mode(chat_id: int, enabled: bool) -> None:
    """
    @brief Включает или выключает режим трассировки в ЛС для чата.
    @param chat_id ID чата.
    @param enabled Состояние трассировки (True / False).
    """
    try:
        with get_connection() as conn:
            conn.execute("UPDATE chats_master SET trace_mode = ? WHERE chat_id = ?", (1 if enabled else 0, chat_id))
    except sqlite3.OperationalError:
        pass

# --- ФУНКЦИИ НАСТРОЕК ЧИСТОГО РЕЖИМА (CLEAN_MODE) ---

def get_chat_clean_mode(chat_id: int) -> bool:
    """
    @brief Проверяет, включен ли чистый режим тихой работы админа через реакции (clean_mode).
    @param chat_id ID чата.
    @return True если чистый режим включен (1), иначе False (0).
    """
    try:
        with get_connection() as conn:
            res = conn.execute("SELECT clean_mode FROM chats_master WHERE chat_id = ?", (chat_id,)).fetchone()
        return bool(res[0]) if res and res[0] else False
    except sqlite3.OperationalError:
        return False

def set_chat_clean_mode(chat_id: int, enabled: bool) -> None:
    """
    @brief Включает или выключает чистый режим админа для чата.
    @param chat_id ID чата.
    @param enabled Состояние чистого режима (True / False).
    """
    try:
        with get_connection() as conn:
            conn.execute("UPDATE chats_master SET clean_mode = ? WHERE chat_id = ?", (1 if enabled else 0, chat_id))
    except sqlite3.OperationalError:
        pass

# --- ФУНКЦИИ НАСТРОЕК ДЛИНЫ СВОДКИ ---

def get_chat_summary_limit(chat_id: int) -> int:
    """
    @brief Возвращает установленный размер истории (число сообщений) для саммари чата.
    @param chat_id ID чата.
    @return Натуральное число от 20 до 2000 (по умолчанию 100).
    """
    try:
        with get_connection() as conn:
            res = conn.execute("SELECT summary_limit FROM chats_master WHERE chat_id = ?", (chat_id,)).fetchone()
        val = res[0] if res and res[0] else 100
        return max(20, min(2000, int(val)))
    except sqlite3.OperationalError:
        return 100

def set_chat_summary_limit(chat_id: int, limit: int) -> int:
    """
    @brief Устанавливает размер истории для саммари чата с ограничительной вилкой [20..2000].
    @param chat_id ID чата.
    @param limit Запрашиваемый лимит.
    @return Фактически установленный ограниченный лимит.
    """
    clamped_limit = max(20, min(2000, int(limit)))
    try:
        with get_connection() as conn:
            conn.execute("UPDATE chats_master SET summary_limit = ? WHERE chat_id = ?", (clamped_limit, chat_id))
    except sqlite3.OperationalError:
        pass

# --- ФУНКЦИИ НАСТРОЕК ИИ-ИЗВЛЕКАТЕЛЯ ДОСЬЕ (GEMMA) ---

def get_chat_gemma_dossier_mode(chat_id: int) -> bool:
    """
    @brief Проверяет, включен ли ИИ-извлекатель досье (Gemma) для чата.
    @param chat_id ID чата.
    @return True по умолчанию (1), иначе False (0).
    """
    try:
        with get_connection() as conn:
            res = conn.execute("SELECT gemma_dossier_mode FROM chats_master WHERE chat_id = ?", (chat_id,)).fetchone()
        return bool(res[0]) if res and res[0] is not None else True
    except sqlite3.OperationalError:
        return True

def set_chat_gemma_dossier_mode(chat_id: int, enabled: bool) -> None:
    """
    @brief Включает или выключает ИИ-извлекатель досье (Gemma) для чата.
    @param chat_id ID чата.
    @param enabled Состояние (True / False).
    """
    try:
        with get_connection() as conn:
            conn.execute("UPDATE chats_master SET gemma_dossier_mode = ? WHERE chat_id = ?", (1 if enabled else 0, chat_id))
    except sqlite3.OperationalError:
        pass
    return clamped_limit