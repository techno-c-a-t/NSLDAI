"""
@file admin.py
@brief Модуль административных команд (доступен только Никитосу / is_me).
@details Содержит выгрузку историй чата ("дамп [число]"), очистку служебных сообщений ("Фантом, приберись")
         с удалением из Telegram и базы SQLite, а также управление белым списком разрешенных чатов.
"""

import logging
import re
from typing import Any, List
import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.router import router, EventType, EventContext
from modules.actions import tracer

logger = logging.getLogger(__name__)

CLEANUP_PATTERN: str = r"(?i)^фантом,?\s*(приберись|почисти|убери за собой)\b"
ALLOW_CHAT_PATTERN: str = r"(?i)^фантом,?\s*(?:разреши\s+этот\s+чат|добавь\s+этот\s+чат|разреши\s+чат)(?:\s+(-?\d+))?\b"
ALLOW_LIST_PATTERN: str = r"(?i)^фантом,?\s*(список\s+разрешенных\s+чатов|белый\s+список|разрешенные\s+чаты)\b"


def is_service_message(text: str) -> bool:
    """
    @brief Определяет, является ли сообщение служебным/техническим уведомлением Фантома.
    @details Считаются служебными: гайды, подтверждения досье, уведомления режимов, стартовые приветствия.
             НЕ СЧИТАЮТСЯ служебными (НЕ удаляются): ИИ-саммари ("**Нарыл"), ИИ-ответы ("> [Использована модель"), расшифровки ГС ("🗣️ **Расшифровка").
    """
    t = text or ""
    if "**Нарыл" in t or "🗣️ **Расшифровка:" in t or "> [Использована модель:" in t or "> [Все доступные модели" in t:
        return False
    return True


@router.on(EventType.COMMAND, pattern=cfg.DUMP_PATTERN, admin_only=True, priority=20)
async def handle_dump_event(ctx: EventContext) -> None:
    """
    @brief Обработчик события вызова команды дамп.
    """
    count_str = ctx.match.group(1) if ctx.match else "20"
    await do_dump(ctx.message, count_str)
    


@router.on(EventType.COMMAND, pattern=CLEANUP_PATTERN, admin_only=True, priority=20)
async def handle_cleanup_event(ctx: EventContext) -> None:
    """
    @brief Обработчик команды "Фантом, приберись" — удаляет до 10 последних служебных сообщений (category='SERVICE') из Telegram и БД.
    """
    chat_id = ctx.chat_id
    client = ctx.message._client if hasattr(ctx.message, '_client') else None
    clean_mode = db.get_chat_clean_mode(chat_id)

    if clean_mode:
        await utils.set_reaction(ctx.message, "👀")

    # 1. Считываем сообщения с категорией 'SERVICE' напрямую из базы данных
    to_delete = db.get_service_message_ids_from_db(chat_id, limit=10)

    if to_delete and client:
        try:
            # 1. Удаляем из Telegram чата
            await client.delete_messages(chat_id, to_delete)
            # 2. Удаляем из SQLite базы данных
            db.delete_messages_from_db(chat_id, to_delete)
            logger.info(f"🧹 [CLEANUP BY CATEGORY] Удалено {len(to_delete)} служебных сообщений (category='SERVICE') из чата {chat_id} и БД.")
        except Exception as e:
            logger.warning(f"Ошибка при сносе служебных сообщений: {e}")

    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, f"Прибрался! Удалено {len(to_delete)} служебных сообщений (category='SERVICE') из чата и БД 🧹", category="SERVICE")


@router.on(EventType.COMMAND, pattern=cfg.WIPE_PATTERN, admin_only=True, priority=20)
async def handle_wipe_event(ctx: EventContext) -> None:
    """
    @brief Обработчик команды "Фантом, вайп" / "ВАЙП" — удаляет абсолютно ВСЕ сообщения Фантома из Telegram-чата и базы данных SQLite.
    """
    chat_id = ctx.chat_id
    client = ctx.message._client if hasattr(ctx.message, '_client') else None
    clean_mode = db.get_chat_clean_mode(chat_id)

    if clean_mode:
        await utils.set_reaction(ctx.message, "👀")

    total_deleted = 0
    if client:
        batch: List[int] = []
        async for msg in client.get_chat_history(chat_id, limit=2000):
            if msg.from_user and msg.from_user.is_self:
                batch.append(msg.id)
                if len(batch) >= 100:
                    try:
                        await client.delete_messages(chat_id, batch)
                        db.delete_messages_from_db(chat_id, batch)
                        total_deleted += len(batch)
                    except Exception as e:
                        logger.warning(f"Ошибка сноса пачки сообщений при вайпе: {e}")
                    batch = []

        if batch:
            try:
                await client.delete_messages(chat_id, batch)
                db.delete_messages_from_db(chat_id, batch)
                total_deleted += len(batch)
            except Exception as e:
                logger.warning(f"Ошибка сноса финальной пачки при вайпе: {e}")

    logger.info(f"💥 [WIPE COMPLETE] Удалено {total_deleted} сообщений Фантома из чата {chat_id} и БД.")

    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, f"💥 Вайп завершен! Удалено {total_deleted} сообщений Фантома из чата и БД 🧹", category="SERVICE")


@router.on(EventType.COMMAND, pattern=ALLOW_CHAT_PATTERN, admin_only=True, priority=20)
async def handle_allow_chat(ctx: EventContext) -> None:
    """
    @brief Динамически добавляет указанный или текущий чат в белый список ALLOWED_CHAT_IDS.
    """
    text = ctx.text.strip()
    match = re.search(ALLOW_CHAT_PATTERN, text)
    
    if match and match.group(1):
        target_chat_id = int(match.group(1))
    else:
        target_chat_id = ctx.chat_id

    cfg.ALLOWED_CHAT_IDS.add(target_chat_id)
    chat_title = ctx.message.chat.title if target_chat_id == ctx.chat_id else f"Разрешенная группа ({target_chat_id})"
    db.register_chat(target_chat_id, chat_title or "Разрешенная группа")
    db.activate_chat(target_chat_id)
    
    clean_mode = db.get_chat_clean_mode(ctx.chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, f"Группа `{target_chat_id}` успешно добавлена в белый список разрешенных 🟢")


@router.on(EventType.COMMAND, pattern=ALLOW_LIST_PATTERN, admin_only=True, priority=20)
async def handle_allow_list(ctx: EventContext) -> None:
    """
    @brief Показывает список разрешенных чатов из белого списка.
    """
    chats_str = ", ".join(map(str, cfg.ALLOWED_CHAT_IDS)) if cfg.ALLOWED_CHAT_IDS else "Разрешены ВСЕ чаты"
    await utils.send_as_phantom(ctx.message, f"📋 **БЕЛЫЙ СПИСОК ЧАТОВ:**\n{chats_str}")


DISALLOW_CHAT_PATTERN: str = r"(?i)^фантом,?\s*(?:запрети\s+этот\s+чат|отключи\s+этот\s+чат|запрети\s+чат|отключи\s+чат|удали\s+этот\s+чат)(?:\s+(-?\d+))?\b"
QUOTA_MODE_PATTERN: str = r"(?i)^фантом,?\s*(включи|выключи)\s+лимиты(?:\s+(@?[A-Za-z0-9_]+))?\b"
QUOTA_LIMIT_SET_PATTERN: str = r"(?i)^фантом,?\s*(?:лимит\s+запросов|установи\s+лимит\s+запросов)(?:\s+(@?[A-Za-z0-9_]+))?\s+(\d+)$"
PM_DIALOGS_TOGGLE_PATTERN: str = r"(?i)^фантом,?\s*(включи|выключи)\s+(?:диалоги\s+в\s+лс|лс)\b"


@router.on(EventType.COMMAND, pattern=DISALLOW_CHAT_PATTERN, admin_only=True, priority=20)
async def handle_disallow_chat(ctx: EventContext) -> None:
    """
    @brief Отключает отслеживание чата и исключает его из белого списка (is_active = 0).
    @details База данных (таблицы сообщений, история, досье) НЕ удаляется! Бот просто перестает слушать этот чат.
    """
    text = ctx.text.strip()
    match = re.search(DISALLOW_CHAT_PATTERN, text)
    target_chat_id = int(match.group(1)) if (match and match.group(1)) else ctx.chat_id

    db.deactivate_chat(target_chat_id)
    clean_mode = db.get_chat_clean_mode(ctx.chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(
            ctx.message, 
            f"Отслеживание группы `{target_chat_id}` отключено 🔴\n"
            f"_(Все данные и история сохранены в базе данных, бот больше не читает и не отвечает в этом чате)_"
        )


@router.on(EventType.COMMAND, pattern=QUOTA_MODE_PATTERN, admin_only=True, priority=20)
async def handle_quota_mode(ctx: EventContext) -> None:
    """
    @brief Включает или выключает суточный лимит запросов к ИИ в текущем чате или для конкретного пользователя.
    """
    enable = "включи" in ctx.text.lower()
    match = re.search(QUOTA_MODE_PATTERN, ctx.text.strip())
    target_str = match.group(2) if match and match.group(2) else None

    target_chat_id = ctx.chat_id
    target_label = "в этом чате"

    if target_str:
        clean_target = target_str.lstrip("@").strip()
        if clean_target.lstrip("-").isdigit():
            target_chat_id = int(clean_target)
            target_label = f"для пользователя/чата `{target_chat_id}`"
        else:
            found_uid = db.get_user_id_by_username(clean_target)
            if found_uid:
                target_chat_id = found_uid
                target_label = f"для @{clean_target}"
            else:
                target_label = f"для @{clean_target}"

    db.set_chat_quota_mode(target_chat_id, enable)
    limit = db.get_chat_requests_limit(target_chat_id)
    clean_mode = db.get_chat_clean_mode(ctx.chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        state_str = f"ВКЛЮЧЕН 🟢 (лимит: {limit} запр./сутки)" if enable else "ВЫКЛЮЧЕН 🔴 (безлимит)"
        await utils.send_as_phantom(ctx.message, f"Контроль лимитов запросов {target_label}: {state_str}")


@router.on(EventType.COMMAND, pattern=QUOTA_LIMIT_SET_PATTERN, admin_only=True, priority=20)
async def handle_set_quota_limit(ctx: EventContext) -> None:
    """
    @brief Устанавливает суточный лимит запросов к ИИ на человека в данном чате или для конкретного пользователя.
    """
    match = re.search(QUOTA_LIMIT_SET_PATTERN, ctx.text.strip())
    target_str = match.group(1) if match and match.group(1) else None
    limit_val = int(match.group(2)) if match and match.group(2) else 5

    target_chat_id = ctx.chat_id
    target_label = "в этом чате"

    if target_str:
        clean_target = target_str.lstrip("@").strip()
        if clean_target.lstrip("-").isdigit():
            target_chat_id = int(clean_target)
            target_label = f"для пользователя `{target_chat_id}`"
        else:
            found_uid = db.get_user_id_by_username(clean_target)
            if found_uid:
                target_chat_id = found_uid
                target_label = f"для @{clean_target}"
            else:
                target_label = f"для @{clean_target}"

    clamped = db.set_chat_requests_limit(target_chat_id, limit_val)
    clean_mode = db.get_chat_clean_mode(ctx.chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, f"Установлен суточный лимит {target_label}: {clamped} запросов 👌")


@router.on(EventType.COMMAND, pattern=PM_DIALOGS_TOGGLE_PATTERN, admin_only=True, priority=20)
async def handle_pm_dialogs_toggle(ctx: EventContext) -> None:
    """
    @brief Включает или выключает возможность диалогов в личных сообщениях с Фантомом.
    """
    enable = "включи" in ctx.text.lower()
    cfg.ENABLE_PM_DIALOGS = enable
    clean_mode = db.get_chat_clean_mode(ctx.chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        status_text = "ВКЛЮЧЕНЫ 🟢 (Фантом слушает и отвечает в ЛС)" if enable else "ВЫКЛЮЧЕНЫ 🔴 (Фантом игнорирует сообщения в ЛС)"
        await utils.send_as_phantom(ctx.message, f"Диалоги в личных сообщениях: {status_text}")


async def do_dump(message: Any, count_str: str) -> None:
    """
    @brief Выгружает историю сообщений текущего чата в консоль, файл dump.txt или в ЛС (при включенной трассировке).
    """
    count = int(count_str)
    chat_id = message.chat.id

    if count > cfg.HISTORY_SIZE: 
        resp = "Много хочешь"
    else:
        hist = db.get_history_from_db(chat_id, count)
        if len(hist) < count: 
            resp = f"Помню только {len(hist)}"
        else:
            if db.get_chat_trace_mode(chat_id):
                await tracer.queue_trace(chat_id, {
                    "event": "dump_history",
                    "count": count,
                    "history": hist
                })
                resp = "Дамп выгружен и отправлен в ЛС отформатированными JSON-блоками 📩"
            else:
                if count <= 20: 
                    print(f"\n--- ДАМП ---\n" + "\n".join(hist))
                    resp = "В консоли"
                else:
                    with open("dump.txt", "w", encoding="utf-8") as f: 
                        f.write("\n".join(hist))
                    resp = "В файле dump.txt"
    await utils.send_as_phantom(message, resp)
