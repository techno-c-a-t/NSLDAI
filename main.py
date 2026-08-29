"""
@file main.py
@brief Главная точка входа приложения NSLDAI (Nasledniki AI / Фантом Userbot).
@details Инициализирует Pyrogram Client в едином asyncio event loop, авто-кэширует диалоги,
         подключает модули команд и обработчиков, управляет фоновой синхронизацией истории и реконнектами.
"""

import asyncio
import logging
import re
from typing import Any
from pyrogram import Client, filters, idle
from pyrogram.types import Message

import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.router import router, EventType, EventContext
from modules.actions import voice, tracer, sync

# Настройка системного логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация клиента Pyrogram
app = Client(
    "phantom_userbot",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN if cfg.BOT_TOKEN else None
)

# Инициализация базы данных SQLite3
db.init_db()

# Регистрация динамических плагинов команд
router.load_plugins("modules.actions")

@app.on_message(filters.chat(cfg.SBER_BOT), group=0)
async def sber_bot_handler(client: Client, message: Message) -> None:
    """
    @brief Обработчик ответов от бота Сбер Спич Бот (Group 0).
    """
    logger.info(f"📩 [СБЕР СПИЧ БОТ] Получен ответ (id={message.id})")
    await voice.handle_sber_message(client, message)

@app.on_edited_message(filters.chat(cfg.SBER_BOT), group=0)
async def sber_bot_edited_handler(client: Client, message: Message) -> None:
    """
    @brief Обработчик редактируемых сообщений Сбер Спич Бот (Group 0).
    """
    logger.info(f"✏️ [СБЕР СПИЧ БОТ] Получена отредактированная транскрипция (id={message.id})")
    await voice.handle_sber_edit(client, message)

@app.on_message(group=1)
async def main_handler(client: Client, message: Message) -> None:
    """
    @brief Главный перехватчик всех входящих сообщений Telegram (Group 1).
    @details Реагирует СТРОГО на чаты из белого списка ALLOWED_CHAT_IDS.
    """
    chat_id = message.chat.id
    
    # Пропускаем технические ответы бота Сбер (они обрабатываются в sber_bot_handler)
    if chat_id == cfg.SBER_BOT:
        return

    # 1. ПРОВЕРКА БЕЛОГО СПИСКА ЧАТОВ (Строгий фильтр)
    if not cfg.is_chat_allowed(chat_id):
        return

    text = message.text or message.caption or ""
    author = utils.format_author(message)
    user_id = message.from_user.id if message.from_user else 0
    username = message.from_user.username if message.from_user else None
    is_self = bool(message.from_user and message.from_user.is_self)

    logger.info(f"📩 [ВХОДЯЩЕЕ В РАЗРЕШЕННОМ ЧАТЕ] Chat: {chat_id} | Author: {author} (id={user_id}, is_self={is_self}) | Text: '{text[:80]}'")

    # Авто-регистрация чата в мастер-таблице БД
    chat_title = (message.chat.title or message.chat.first_name or f"Chat_{chat_id}") if message.chat else f"Chat_{chat_id}"
    db.register_chat(chat_id, chat_title)

    m_data = (message.id, author, text, message.date)

    # 2. ПРОВЕРКА И ОБРАБОТКА РЕЖИМА СИНХРОНИЗАЦИИ (WAITING_SYNC / SYNCING)
    sync_ctx = sync.get_sync_context(chat_id)
    logger.info(f"🔄 [SYNC CHECK] Режим синхронизации чата {chat_id}: state={sync_ctx.state}")

    if sync_ctx.state in [sync.STATE_WAITING_SYNC, sync.STATE_SYNCING]:
        if is_self:
            return

        clean_text = text.strip().lower()

        if sync_ctx.state == sync.STATE_WAITING_SYNC:
            if clean_text in ["да", "yes", "давай"]:
                logger.info(f"✅ [SYNC] Получен ответ 'ДА' от {author}. Запуск офлайн-синхронизации!")
                sync_ctx.state = sync.STATE_SYNCING
                await message.reply_text("Начинаю загрузку пропущенной истории...")
                asyncio.create_task(sync.run_sync(client, message))
                return
            elif clean_text in ["нет", "no", "отмена"]:
                logger.info(f"🛑 [SYNC] Получен ответ 'НЕТ' от {author}. Синхронизация отменена.")
                for m in sync_ctx.temp_buffer:
                    db.save_message(chat_id, *m)
                db.save_message(chat_id, *m_data)
                sync_ctx.temp_buffer, sync_ctx.state = [], sync.STATE_NORMAL
                await message.reply_text("Синхронизация отменена. Пишу с текущего момента.")
                return

        # Во время WAITING_SYNC и SYNCING кэшируем все текущие сообщения в temp_buffer и НЕ высылаем в ИИ
        logger.info(f"📦 [SYNC BUFFER] Сообщение id={message.id} кэшировано в буфер синхронизации чата {chat_id}.")
        sync_ctx.temp_buffer.append(m_data)
        return

    # 3. В ОБЫЧНОМ РЕЖИМЕ (STATE_NORMAL) — СОХРАНЯЕМ В БД И ИДЕМ В ИИ
    db.save_message(chat_id, *m_data)
    logger.info(f"💾 [БД] Сообщение id={message.id} сохранено в историю chat_{chat_id}")

    if is_self:
        logger.info(f"⏭️ [SKIP] Сообщение отправлено аккаунтом Фантома (is_self=True). ИИ-обработка не запускается.")
        return

    # Формируем контекст события для маршрутизатора
    ctx = EventContext(message=message, chat_id=chat_id, user_id=user_id, username=username, text=text)

    # ---------------------------------------------------------------------
    # ПОСЛЕДОВАТЕЛЬНЫЙ КОНВЕЙЕР МАРШРУТИЗАЦИИ (5 СТРОГИХ ЭТАПОВ)
    # ---------------------------------------------------------------------
    # ЭТАП 1: Проверка регулярных выражений Команд и Сводки (EventType.COMMAND)
    logger.info(f"🔀 [STAGE 1] Диспетчеризация типа COMMAND (Команды и Сводка)...")
    if await router.dispatch(ctx, EventType.COMMAND):
        return

    # ЭТАПЫ 2, 3, 4: Проверка реплаев на ГС, прямых обращений и имя (EventType.DIALOG)
    is_direct_tag = "@tech_phantom" in text.lower()
    is_reply_to_phantom = bool(message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self and re.search(cfg.PHANTOM_NAMES_PATTERN, text.lower()))
    has_phantom_name = bool(re.search(cfg.PHANTOM_NAMES_PATTERN, text.lower()))

    logger.info(f"🧐 [DIALOG TRIGGER CHECK] tag={is_direct_tag}, reply={is_reply_to_phantom}, name_regex={has_phantom_name}")

    if is_direct_tag or is_reply_to_phantom or has_phantom_name:
        logger.info(f"🔀 [STAGES 2, 3, 4] Диспетчеризация типа DIALOG...")
        if await router.dispatch(ctx, EventType.DIALOG):
            return

    # ЭТАП 5: Фоновые текстовые сообщения (EventType.TEXT_MESSAGE)
    logger.info(f"🔀 [STAGE 5] Диспетчеризация типа TEXT_MESSAGE...")
    await router.dispatch(ctx, EventType.TEXT_MESSAGE)

async def setup_background_tasks() -> None:
    """
    @brief Запуск фоновой подгрузки access_hash диалогов и воркеров бота на общем Event Loop.
    """
    try:
        logger.info("🔍 [PEER RESOLUTION] Подгрузка списка диалогов пользователя...")
        count = 0
        async for _ in app.get_dialogs(limit=100):
            count += 1
        logger.info(f"✅ [PEER RESOLUTION] Подгружено и закэшировано {count} диалогов.")
        
        if cfg.TARGET_CHAT_ID:
            sync_ctx = sync.get_sync_context(cfg.TARGET_CHAT_ID)
            sync_ctx.state = sync.STATE_WAITING_SYNC
            logger.info(f"💬 Отправка стартового запроса синхронизации в TARGET_CHAT_ID ({cfg.TARGET_CHAT_ID})...")
            try:
                await app.send_message(cfg.TARGET_CHAT_ID, "Снова в сети. Nikitos, читать историю?")
                logger.info("✅ Стартовый запрос синхронизации успешно отправлен.")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить приветственное сообщение: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при подгрузке диалогов: {e}")

    # Запуск фоновых воркеров ГС и трассировки
    asyncio.create_task(voice.sber_worker_loop(app))
    asyncio.create_task(tracer.trace_worker_loop(app))

if __name__ == "__main__":
    logger.info("🚀 Запуск сессии Pyrogram Userbot...")
    app.start()
    app.loop.create_task(setup_background_tasks())
    logger.info("🟢 Pyrogram Userbot полностью запущен и слушает разрешенные чаты!")
    idle()
    logger.info("🛑 Остановка сессии Pyrogram...")
    if getattr(app, "is_connected", False):
        try:
            app.stop()
        except Exception:
            pass
