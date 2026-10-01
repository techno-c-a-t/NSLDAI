"""
@file config.py
@brief Конфигурационный файл проекта NSLDAI.
@details Хранит токены, ключи API, пути к БД, паттерны команд, списки моделей и системные промпты.
"""

import os
import json
from typing import Dict, List, Set, Union
from dotenv import load_dotenv

# Загружаем переменные окружения из файлика .env
load_dotenv()

# Базовые переменные Telegram Bot API & Pyrogram Userbot
API_ID: int = int(os.getenv("API_ID", 0))
API_HASH: str = os.getenv("API_HASH", "")
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Мой личный username администратора (без символа @)
MY_USERNAME: str = os.getenv("MY_USERNAME", "techno_c_a_t").lstrip("@")

# Имя и ID ботов Сбера
GIGACHAT_BOT: str = os.getenv("GIGACHAT_BOT", "gigachat_bot")
_speech_env = os.getenv("SBER_SPEECH_BOT", "5244379085").strip()
SBER_SPEECH_BOT: Union[int, str] = int(_speech_env) if _speech_env.isdigit() else _speech_env
SBER_BOT: Union[int, str] = SBER_SPEECH_BOT

# Базовый URL для обращения к Google Gemini API через OpenAI SDK используя прокси
BASE_URL: str = os.getenv("BASE_PROXIED_URL", "https://generativelanguage.googleapis.com/v1beta/openai")


# ID целевого чата из .env
TARGET_CHAT_ID: int = int(os.getenv("TARGET_CHAT_ID", "0"))

# Размер сохраняемой истории сообщений
HISTORY_SIZE: int = int(os.getenv("HISTORY_SIZE", "2000"))

# Путь к файлу локальной базы данных SQLite3
DB_NAME: str = os.getenv("DB_NAME", "database.db")

# Путь к файлу сессии Pyrogram Userbot
SESSION_PATH: str = os.getenv("SESSION_PATH", "phantom_userbot")

# Дефолтный API ключ Google Gemini (проверяем DEFAULT_API_KEY и GEMINI_API_KEY)
DEFAULT_API_KEY: str = os.getenv("DEFAULT_API_KEY") or os.getenv("GEMINI_API_KEY") or ""

# Белый список чатов (если пуст — разрешены все)
ALLOWED_CHATS: List[int] = []
ALLOWED_CHAT_IDS: Set[int] = set()

raw_allowed = os.getenv("ALLOWED_CHAT_IDS", "")
if raw_allowed:
    for cid in raw_allowed.split(","):
        cid_str = cid.strip()
        if cid_str:
            try:
                ALLOWED_CHAT_IDS.add(int(cid_str))
            except ValueError:
                pass

def is_chat_allowed(chat_id: int) -> bool:
    """
    @brief Проверяет, разрешен ли чат для работы бота.
    @param chat_id ID чата.
    @return True если чат в белом списке или списки пусты.
    """
    if not ALLOWED_CHATS and not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHATS or chat_id in ALLOWED_CHAT_IDS

# Словарь персональных API-ключей пользователей из .env (проверяем USER_API_KEYS_JSON и USER_API_KEYS)
user_keys_raw: str = os.getenv("USER_API_KEYS_JSON") or os.getenv("USER_API_KEYS") or "{}"
try:
    USER_API_KEYS: Dict[str, str] = json.loads(user_keys_raw)
except Exception:
    USER_API_KEYS = {}

# =====================================================================
# ТОЧНЫЙ СПИСОК МОДЕЛЕЙ ИЗ GOOGLE AI STUDIO ПО ИЕРАРХИИ ПОЛЬЗОВАТЕЛЯ
# =====================================================================
AI_MODELS_CHAIN: List[str] = [
    "gemini-3.5-flash-lite",    # 1. Приоритет №1: Gemini 3.5 Flash Lite
    "gemini-3.1-flash-lite",    # 2. Приоритет №2: Gemini 3.1 Flash Lite
    "gemma-4-31b-it",           # 3. Приоритет №3: Gemma 4 31B IT
    "gemma-4-26b-a4b-it",       # 4. Приоритет №4: Gemma 4 26B A4B IT
]

MODEL_PREMIUM: str = AI_MODELS_CHAIN[0]
MODEL_FREE: str = AI_MODELS_CHAIN[-1]
LIMIT_FREE_REQUESTS: int = 5

# Тексты статусов при последовательной смене моделей при ошибках
STATUS_MESSAGES_FALLBACK: List[str] = [
    "Разбираюсь...",
    "Мозг вскипает, пробую модель рангом ниже...",
    "Стараюсь изо всех сил, перехожу на Gemma...",
    "Google AI не отвечает, переключаюсь на Сбер GigaChat..."
]

# Улучшенное регулярное выражение обращения к Фантому (учитывает кириллические границы слов, запятые, кавычки, абзацы)
PHANTOM_NAMES_PATTERN: str = r"(?i)(?<![а-яёa-z0-9_])(фантом(?:чик|ушка|ас)?|phantom|fantom)(?![а-яёa-z0-9_])"

SUMMARY_PATTERN: str = r"(?i)фантом,\s*(что происходит|че творится|введи в курс дела|кратко че тут|че обсуждаете)(?:\s+(\d+))?"
SUMMARY_LIMIT_SET_PATTERN: str = r"(?i)^фантом,?\s*(?:установи\s+длину\s+сводки|длина\s+сводки)\s+(\d+)$"
HELP_PATTERN: str = r"(?i)^(фантом|phantom|@tech_phantom),?\s+(гайд|помощь|help|команды)\b"
YO_PATTERN: str = r"(?i)[йy][оoаa]+,?\s*(фантом|phantom)[^а-яёa-z0-9\s]{0,5}$"
DUMP_PATTERN: str = r"(?i)^дамп\s+(\d+)$"

WIPE_PATTERN: str = r"(?i)^(?:фантом,?\s*вайп\b|ВАЙП$)"

# Системные промпты для ИИ
AI_PROMPTS: Dict[str, str] = {
    "summary_system": "Ты — ассистент чата, аналитик. Пишешь суть без приветствий. Стиль: деловой и понятный.",
    "summary_user": (
        "ИСТОРИЯ ЧАТА:\n{context}\n\n"
        "ЗАДАНИЕ ДЛЯ АНАЛИТИКА:\n"
        "Прочитай историю переписки выше ({count} сообщений). Проанализируй её и выдели ключевые/важные темы, которые обсуждали участники.\n\n"
        "Для КАЖДОЙ ключевой/важной темы сформируй блок СТРОГО по следующему шаблону:\n\n"
        "📌 **[Суть темы]**\n"
        "• **Что выяснили в процессе:** [Подробности обсуждения]\n"
        "• **К чему пришли в итоге:** [Итоговый вывод или решение]\n"
        "• **Участники:** [Ники/имена участников через запятую]\n"
        "• **Цитата:** \"[Дословная емкая цитата из переписки по этой теме, лучше всего ее характеризующая]\"\n\n"
        "В самом конце вывода под заголовком 💬 **Прочее:** напиши коротким простым текстом не особо важные темы и мелкие вопросы, промелькнувшие в чате.\n\n"
        "ИНСТРУКЦИИ:\n"
        "1. НЕ здоровайся и НЕ пиши вводных фраз ('Я Фантом', 'Вот что я нарыл' — ЗАПРЕЩЕНО).\n"
        "2. Цитата должна быть ТОЧНОЙ дословной выдержкой из сообщений выше.\n"
        "3. СТРОГО ЗАПРЕЩЕНО ставить символ '@' перед именами участников.\n"
        "4. Если в истории нет важных тем для обсуждения — дай общую краткую выжимку в 2-3 предложениях."
    ),
    "dialog_system": "Ты Фантом, ассистент чата. Твои ответы неформальные, не слишком длинные и в тему.",
    "dialog_user": "ИСТОРИЯ ЧАТА:\n{context}\n\nЗАДАНИЕ:\n{target}"
}

# Публичная справка для всех пользователей
PUBLIC_HELP_MESSAGE: str = """🤖 **ФАНТОМ: СПРАВОЧНИК КОМАНД**

📝 **Сводка чата:**
• `!сводка [N]` или `Фантом, сводка [N]` — выжимка последних N сообщений (от 20 до 2000, по умолч. 100).
• Синонимы: `Фантом, что происходит`, `че творится`, `че тут`, `введи в курс дела`.

💬 **Диалог с ИИ:**
• `Фантом, [твой вопрос]` — диалог с учетом контекста беседы.
• Реплай на любое сообщение Фантома или тег `@tech_phantom`.
• В личных сообщениях (ЛС) — прямой диалог.

🎙️ **Голосовые и видео-кружочки:**
• Отправь ГС или кружочек — мгновенный текст + краткая выжимка (в режиме «по запросу» — сделай реплай).

🎮 **Пасхалки и традиции:**
• `Я проиграл` — фиксация поражения в The Game.
• `Фантом, лоб` — взаимность. `Йо, Фантом` — приветствие."""

# Краткая справка администратора (для Никитоса)
ADMIN_HELP_MESSAGE: str = """🛠️ **АДМИН-ПАНЕЛЬ ФАНТОМА**

🌐 **Управление чатами:**
• `Фантом, разреши / запрети этот чат` — белый список чатов.
• `Фантом, список чатов` — список активных чатов.
• `Фантом, включи / выключи лс` — диалоги в личных сообщениях.

🔇 **Режимы чата:**
• `Фантом, чистый / обычный режим` — реакции (👀, 👍) вместо сервисных сообщений.
• `Фантом, авто гс / гс по запросу` — режим авто-распознавания аудио.

📊 **Лимиты и квоты:**
• `Фантом, включи / выключи лимиты [@юзер]` — суточные квоты.
• `Фантом, лимит запросов [число]` — размер суточного лимита (дефолт 5).

🗄️ **История и БД:**
• `Фантом, длина сводки [N]` — размер сводки по умолчанию (20..2000).
• `Фантом, приберись` — удалить до 10 последних сервисных сообщений.
• `Фантом, вайп` — полная очистка сообщений бота в чате и БД.
• `дамп [N]` / `дамп > 20` — выгрузка сообщений из БД (в чат / в файл).

📡 **Трассировка и Досье:**
• `Фантом, трассировка вкл / выкл` — трансляция JSON-логов в ЛС.
• `Фантом, записывай / дополни / вычеркивай` — карточки жителей.
• `Фантом, включи / выключи гемму досье` — ИИ-извлечение фактов."""
