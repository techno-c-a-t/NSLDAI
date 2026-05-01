# [Nasledniki](https://t.me/clown_crown "Наше сообщество")
## Nasledniki AI представляет Phantom Userbot
### *by @techno_c_a_t*
Техническая документация

Ассистент чата на базе Pyrogram (MTProto), предназначенный для анализа истории, ведения контекстных диалогов через LLM и транскрипции медиафайлов.

### Архитектура проекта
Проект реализован по принципу **Decoupled Logic**: точка входа (`main.py`) отделена от бизнес-логики (`modules/actions/`).

#### Структура директорий
*   `main.py` — Инициализация клиента, регистрация хендлеров и управление жизненным циклом сессии.
*   `modules/ai_service.py` — Ядро взаимодействия с LLM (Gemini/Gemma). Унифицирует запросы, управляет выбором моделей и лимитами.
*   `modules/actions/` — Директория атомарных модулей логики:
    *   `ai_logic.py` — Формирование саммари (анализ контекста).
    *   `dialog.py` — Контекстный чат (сбор истории вокруг сообщения).
    *   `voice.py` — Асинхронный пайплайн транскрипции ГС через Sber SmartSpeech.
    *   `sync_logic.py` — Синхронизация пропущенных сообщений при старте.
    *   `admin.py` — Утилиты выгрузки БД (дамп).
*   `modules/database.py` — Слой доступа к данным (SQLite).
*   `modules/utils.py` — Вспомогательные функции (форматирование сообщений, DRY-обертки для отправки).

### Технический стек
*   **Runtime:** Python 3.10+
*   **Library:** Pyrogram 2.0 (Asynchronous)
*   **Database:** SQLite3 (хранение последних 500 сообщений + ежедневные лимиты юзеров)
*   **AI:** Google Gemini 3.1 Flash Lite (Premium) / Gemma 2 27b (Free) через OpenAI-compatible API. + Sber AI для voice recognition

### Ключевые механизмы

#### 1. Unified AI Service (DRY)
Модуль `ai_service.py` инкапсулирует:
*   **Freemium-логику:** Переключение на Gemma при исчерпании лимита (5 запросов/сутки) или отсутствии личного API-ключа.
*   **Модели:** Gemini (System/User roles) и Gemma (Instruction wrapping).
*   **Асинхронность:** Вызовы API обернуты в `asyncio.to_thread` для предотвращения блокировки Event Loop.

#### 2. Voice Transcription Pipeline
Реализован в `modules/actions/voice.py` для интеграции с `@smartspeech_sber_bot`.
*   **Concurrency Control:** Использование `asyncio.Lock` в `main.py` гарантирует последовательную обработку нескольких ГС (FIFO).
*   **State Management:** Флаги `intro_sent` и `processing_done` (Event) управляют порядком вывода сообщений при транскрипции (сначала заголовок, затем части текста по порядку).
*   **Error Handling:** Детект специфических ответов Sber (лимиты 8МБ, неподдерживаемые кодеки `x-vorbis`) через анализ текста и `on_edited_message`.

#### 3. Database & Sync
*   **Rolling Buffer:** БД хранит только последние 500 записей (автоматическая очистка при инсерте).
*   **Synchronization:** При старте бот запрашивает последние `total_needed` сообщений через `get_chat_history`, заполняя пробел между `max_id` в БД и текущим состоянием чата.

### Конфигурация (.env)
*   `API_ID` / `API_HASH` — Данные приложения Telegram.
*   `TARGET_CHAT_ID` — ID группы для работы.
*   `DEFAULT_API_KEY` — Мастер-ключ для LLM.
*   `USER_API_KEYS_JSON` — Словарь личных ключей пользователей.
*   `MANUSCRIPT_DATABASE_URL` — Опциональная Postgres-БД NSLDNK для записи сообщений и чтения сегментов манускрипта.
*   `MANUSCRIPT_DB_PATH` — Локальный SQLite fallback для разработки.
*   `MANUSCRIPT_SEGMENTS_LIMIT` — Сколько последних сегментов манускрипта добавлять в контекст (по умолчанию 3).

### Установка и запуск
1. `python3 -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt` (pyrogram, tgcrypto, openai, python-dotenv)
3. Создать `.env` по шаблону.
4. `python3 main.py`

#### Особенности развертывания на Ubuntu 24.04
Для стабильности в `main.py` реализован механизм пересоздания сокета при `ConnectionError` и обработка сигналов `SIGINT/SIGTERM` для корректного закрытия сессии Pyrogram.

*Благодарности Альберту за вдохновение, Компании™ за стимулирование и **каждому** из народа Наследников за поддержку!*
