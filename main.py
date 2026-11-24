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
from hydrogram import Client, filters, idle
from hydrogram.types import Message

import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.router import router, EventType, EventContext
from modules.actions import voice, tracer, sync, gigachat as giga

# Настройка системного логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация клиента Pyrogram
app = Client(
    cfg.SESSION_PATH,
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

@app.on_message(filters.chat(cfg.GIGACHAT_BOT), group=0)
async def gigachat_bot_handler(client: Client, message: Message) -> None:
    """
    @brief Обработчик ответов от GigaChat Бота (Group 0).
    """
    logger.info(f"📩 [GIGACHAT БОТ] Получен ответ (id={message.id})")
    await giga.handle_giga_response(message)

@app.on_edited_message(filters.chat(cfg.GIGACHAT_BOT), group=0)
async def gigachat_bot_edited_handler(client: Client, message: Message) -> None:
    """
    @brief Обработчик редактируемых ответов от GigaChat Бота (Group 0).
    """
    logger.info(f"✏️ [GIGACHAT БОТ] Получен отредактированный ответ (id={message.id})")
    await giga.handle_giga_response(message)

async def sync_pm_history_silently(client: Client, chat_id: int, limit: int = 100) -> None:
    """
    @brief Бесшумно подгружает последние N сообщений в ЛС без отправки уведомлений в чат.
    """
    try:
        msgs = []
        async for m in client.get_chat_history(chat_id, limit=limit):
            author = utils.format_author(m)
            m_text = m.text or m.caption or ""
            msgs.append((m.id, author, m_text, m.date))
        for item in reversed(msgs):
            db.save_message(chat_id, *item)
        logger.info(f"📥 [PM SYNC] Бесшумно подгружено {len(msgs)} сообщений в историю ЛС {chat_id}.")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка бесшумной подгрузки истории в ЛС {chat_id}: {e}")

@app.on_message(group=1)
async def main_handler(client: Client, message: Message) -> None:
    """
    @brief Главный перехватчик всех входящих сообщений Telegram (Group 1).
    @details Реагирует на чаты из белого списка ALLOWED_CHAT_IDS и разрешенные диалоги в ЛС.
    """
    chat_id = message.chat.id
    is_private = (message.chat and message.chat.type and message.chat.type.name == "PRIVATE") or (chat_id > 0)
    
    # Пропускаем технические ответы бота Сбер и бота GigaChat
    is_giga = (chat_id == cfg.GIGACHAT_BOT) or (message.chat and message.chat.username and message.chat.username.lower() == str(cfg.GIGACHAT_BOT).lower().lstrip("@"))
    if chat_id == cfg.SBER_BOT or is_giga:
        return

    # 1. ПРОВЕРКА БЕЛОГО СПИСКА ЧАТОВ И АКТИВНОСТИ (Строгий фильтр с обходом для админа)
    user_id = message.from_user.id if message.from_user else 0
    username = message.from_user.username if message.from_user else None
    is_self = bool(message.from_user and message.from_user.is_self)
    is_admin_sender = bool(
        is_self or
        (cfg.MY_USER_ID and user_id == cfg.MY_USER_ID) or
        (username and str(username).lower() == cfg.MY_USERNAME.lower())
    )
    text = message.text or message.caption or ""

    if is_private and is_admin_sender:
        pass
    elif not cfg.is_chat_allowed(chat_id, is_private=is_private) or not db.is_chat_active(chat_id):
        from modules.actions import admin as admin_mod
        if is_admin_sender and re.search(admin_mod.ALLOW_CHAT_PATTERN, text.strip()):
            pass
        else:
            return

    author = utils.format_author(message)
    text_for_db = utils.format_media_text(message)

    logger.info(f"📩 [ВХОДЯЩЕЕ В РАЗРЕШЕННОМ ЧАТЕ] Chat: {chat_id} (is_private={is_private}) | Author: {author} (id={user_id}, is_self={is_self}) | Text: '{text[:80]}'")

    # Авто-регистрация чата в мастер-таблице БД
    chat_title = (message.chat.title or message.chat.first_name or f"Chat_{chat_id}") if message.chat else f"Chat_{chat_id}"
    db.register_chat(chat_id, chat_title)

    # Для новых/пустых ЛС — бесшумно подгружаем до 100 последних сообщений
    if is_private and not is_self and db.get_chat_messages_count(chat_id) == 0:
        await sync_pm_history_silently(client, chat_id, limit=cfg.PM_SYNC_LIMIT)

    m_data = (message.id, author, text_for_db, message.date)

    # 2. ПРОВЕРКА И ОБРАБОТКА РЕЖИМА СИНХРОНИЗАЦИИ (QUEUED / SYNCING)
    # Личные сообщения (ЛС) никогда не блокируются синхронизацией!
    sync_ctx = sync.get_sync_context(chat_id)
    if is_private and sync_ctx.state != sync.STATE_NORMAL:
        for m in sync_ctx.temp_buffer:
            db.save_message(chat_id, *m)
        sync_ctx.temp_buffer, sync_ctx.state, sync_ctx.checkpoint_max_id = [], sync.STATE_NORMAL, 0

    logger.info(f"🔄 [SYNC CHECK] Режим синхронизации чата {chat_id}: state={sync_ctx.state}")

    if not is_private and sync_ctx.state in [sync.STATE_QUEUED, sync.STATE_SYNCING]:
        if is_self:
            return
        logger.info(f"📦 [SYNC BUFFER] Сообщение id={message.id} кэшировано в буфер синхронизации чата {chat_id}.")
        sync_ctx.temp_buffer.append(m_data)
        if message.voice or message.video_note:
            asyncio.create_task(voice.queue_voice_message(client, message, force=False, silent=True))
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
    is_reply_to_phantom = bool(
        message.reply_to_message and 
        message.reply_to_message.from_user and 
        message.reply_to_message.from_user.is_self
    )

    if is_private:
        # В ЛС триггерится:
        # 1) Начало строки с 'Фантом...'
        # 2) Тег @tech_phantom
        # 3) Прямой реплай на Фантома
        starts_with_phantom = bool(re.match(r"(?i)^(?:фантом(?:чик|ушка|ас)?|phantom)\b", text.strip()))
        should_trigger_dialog = starts_with_phantom or is_direct_tag or is_reply_to_phantom
    else:
        has_phantom_name = bool(re.search(cfg.PHANTOM_NAMES_PATTERN, text.lower()))
        should_trigger_dialog = is_direct_tag or (is_reply_to_phantom and has_phantom_name) or has_phantom_name

    # Голосовые и кружочки без текстового обращения не перехватываем в DIALOG, чтобы они дошли до авто-ГС
    if (message.voice or message.video_note) and not text.strip():
        should_trigger_dialog = False

    logger.info(f"🧐 [DIALOG TRIGGER CHECK] is_private={is_private}, trigger={should_trigger_dialog}, tag={is_direct_tag}, reply={is_reply_to_phantom}")

    if should_trigger_dialog:
        logger.info(f"🔀 [STAGES 2, 3, 4] Диспетчеризация типа DIALOG...")
        if await router.dispatch(ctx, EventType.DIALOG):
            return

    # ЭТАП 5: Фоновые текстовые сообщения (EventType.TEXT_MESSAGE)
    logger.info(f"🔀 [STAGE 5] Диспетчеризация типа TEXT_MESSAGE...")
    await router.dispatch(ctx, EventType.TEXT_MESSAGE)

@app.on_edited_message(group=1)
async def main_edited_handler(client: Client, message: Message) -> None:
    """
    @brief Обновляет отредактированные сообщения пользователей в БД.
    """
    if not message or not message.chat:
        return
    chat_id = message.chat.id
    is_private = (message.chat.type and message.chat.type.name == "PRIVATE") or (chat_id > 0)
    is_giga = (chat_id == cfg.GIGACHAT_BOT) or (message.chat.username and message.chat.username.lower() == str(cfg.GIGACHAT_BOT).lower().lstrip("@"))
    if chat_id == cfg.SBER_BOT or is_giga:
        return
    if not cfg.is_chat_allowed(chat_id, is_private=is_private) or not db.is_chat_active(chat_id):
        return
    new_text = utils.format_media_text(message)
    if new_text:
        db.update_message_text(chat_id, message.id, new_text)

async def setup_background_tasks() -> None:
    """
    @brief Запуск фоновой подгрузки access_hash диалогов и воркеров бота на общем Event Loop.
    """
    try:
        logger.info("🔍 [PEER RESOLUTION] Подгрузка списка диалогов пользователя...")
        count = 0
        cached_dialog_ids = set()
        async for dialog in app.get_dialogs(limit=100):
            count += 1
            if dialog.chat:
                cached_dialog_ids.add(dialog.chat.id)
        logger.info(f"✅ [PEER RESOLUTION] Подгружено и закэшировано {count} диалогов.")
        
        # Опрос разрешенных ГРУППОВЫХ чатов о синхронизации истории (ЛС исключены!)
        target_chats = set()
        if cfg.TARGET_CHAT_ID and cfg.TARGET_CHAT_ID < 0:
            target_chats.add(cfg.TARGET_CHAT_ID)
        if cfg.ALLOWED_CHAT_IDS:
            target_chats.update(cid for cid in cfg.ALLOWED_CHAT_IDS if cid < 0)

        for cid in target_chats:
            if cached_dialog_ids and cid not in cached_dialog_ids:
                logger.info(f"⏭️ [SYNC SKIP] Чат {cid} отсутствует в активных диалогах аккаунта. Пропуск.")
                continue
            sync.prepare_sync(cid)
            clean_mode = db.get_chat_clean_mode(cid)
            logger.info(f"💬 Автоматическая синхронизация истории в чате {cid} (clean_mode={clean_mode})...")
            try:
                if clean_mode:
                    last_msg = None
                    async for m in app.get_chat_history(cid, limit=1):
                        last_msg = m
                        break
                    if last_msg:
                        await utils.set_reaction(last_msg, "👨‍💻")
                    asyncio.create_task(sync.run_sync(app, None, chat_id=cid, silent_status=True, reaction_msg=last_msg))
                else:
                    start_msg = await app.send_message(cid, "Снова в сети, ща почитаем, че тут было")
                    asyncio.create_task(sync.run_sync(app, start_msg, chat_id=cid))
            except Exception as e:
                logger.warning(f"⚠️ Не удалось запустить автосинхронизацию в чате {cid}: {e}")
                sync_ctx = sync.get_sync_context(cid)
                sync_ctx.state = sync.STATE_NORMAL
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при подгрузке диалогов: {e}")

    # Запуск фоновых воркеров ГС и трассировки
    asyncio.create_task(voice.sber_worker_loop(app))
    asyncio.create_task(tracer.tracer_worker_loop(app) if hasattr(tracer, 'tracer_worker_loop') else tracer.trace_worker_loop(app))

async def start_bot() -> None:
    """
    @brief Асинхронный запуск бота, фоновых задач и переход в режим ожидания сообщений (idle).
    """
    logger.info("🚀 Запуск сессии Hydrogram Userbot...")

    await app.start()
    asyncio.create_task(setup_background_tasks())
    logger.info("🟢 Hydrogram Userbot полностью запущен и слушает разрешенные чаты!")
    await idle()
    logger.info("🛑 Остановка сессии Hydrogram...")
    if getattr(app, "is_connected", False):
        try:
            await app.stop()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        app.run(start_bot())
    except (KeyboardInterrupt, SystemExit):
        pass
