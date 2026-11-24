"""
@file sync.py
@brief Модуль синхронизации пропущенных сообщений чата при старте бота и по ручному запросу.
@details Подгружает пропущенную историю с троттлингом (0.5с на 25 сообщений) для защиты от бана Telegram API.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.router import router, EventType, EventContext

logger = logging.getLogger(__name__)

STATE_NORMAL: str = "NORMAL"
STATE_WAITING_SYNC: str = "WAITING_SYNC"
STATE_QUEUED: str = "QUEUED"
STATE_SYNCING: str = "SYNCING"

## @brief Глобальный замок синхронизации: строго один чат выкачивает историю через Telegram API в один момент времени.
sync_lock: asyncio.Lock = asyncio.Lock()

class ChatSyncContext:
    """
    @brief Контекст состояния синхронизации конкретного чата.
    """
    def __init__(self):
        self.state: str = STATE_NORMAL
        self.temp_buffer: List[Any] = []
        self.checkpoint_max_id: int = 0

## @brief Словарь контекстов синхронизации для каждого чата (Ключ: chat_id)
chat_sync_contexts: Dict[int, ChatSyncContext] = {}

def get_sync_context(chat_id: int) -> ChatSyncContext:
    """
    @brief Возвращает или создает объект контекста синхронизации для чата.
    @param chat_id ID чата.
    @return Экземпляр ChatSyncContext.
    """
    if chat_id not in chat_sync_contexts:
        chat_sync_contexts[chat_id] = ChatSyncContext()
    return chat_sync_contexts[chat_id]

def prepare_sync(chat_id: int) -> ChatSyncContext:
    """
    @brief Переводит групповой чат в режим очереди синхронизации и фиксирует текущий max_id в БД.
    """
    ctx = get_sync_context(chat_id)
    if chat_id > 0:
        ctx.state = STATE_NORMAL
        return ctx
    ctx.state = STATE_QUEUED
    ctx.checkpoint_max_id = db.get_max_id_in_db(chat_id)
    return ctx

def prepare_waiting_sync(chat_id: int) -> ChatSyncContext:
    """
    @brief Обратная совместимость: делегирует в prepare_sync.
    """
    return prepare_sync(chat_id)

async def run_sync(
    client: Any,
    trigger_msg: Optional[Any],
    chat_id: Optional[int] = None,
    limit: Optional[int] = None,
    silent_status: bool = False,
    reaction_msg: Optional[Any] = None,
    ignore_checkpoint: bool = False,
) -> None:
    """
    @brief Запускает синхронизацию пропущенной истории чата из Telegram API в строгой очереди.
    @param client Объект Pyrogram Client.
    @param trigger_msg Опциональное сообщение-триггер для ответа.
    @param chat_id ID чата (если trigger_msg=None).
    @param limit Явный лимит сообщений для подгрузки (по умолчанию SYNC_HISTORY_LIMIT или 2000).
    @param silent_status Если True — не отправляет текстовые статусы в чат (использует реакции).
    @param reaction_msg Сообщение, с которого нужно снять реакцию 👨‍💻 после завершения.
    """
    target_chat_id = chat_id if chat_id is not None else (trigger_msg.chat.id if trigger_msg else 0)
    if not target_chat_id:
        return

    ctx = get_sync_context(target_chat_id)
    clean_mode = db.get_chat_clean_mode(target_chat_id) or silent_status
    total_needed = int(limit if limit is not None else getattr(cfg, "SYNC_HISTORY_LIMIT", 2000))

    async with sync_lock:
        ctx.state = STATE_SYNCING
        max_id = 0 if ignore_checkpoint else (ctx.checkpoint_max_id if ctx.checkpoint_max_id > 0 else db.get_max_id_in_db(target_chat_id))
        fetched: List[Any] = []
        found_gap = False
        sync_error: Optional[Exception] = None

        initial_buffered = list(ctx.temp_buffer)
        ctx.temp_buffer = []

        try:
            async for old_msg in client.get_chat_history(target_chat_id, limit=total_needed):
                if max_id > 0 and old_msg.id <= max_id:
                    found_gap = True
                    break
                data = await utils.format_msg(old_msg)
                if data:
                    fetched.append(data)
                if len(fetched) % 25 == 0:
                    await asyncio.sleep(0.5)

            if not ignore_checkpoint and not found_gap and max_id > 0:
                db.clear_history_before(target_chat_id, max_id)

            for m in reversed(fetched):
                db.save_message(target_chat_id, *m)
        except Exception as e:
            sync_error = e
            logger.exception(f"💥 [SYNC ERROR] Ошибка синхронизации чата {target_chat_id}: {e}")
        finally:
            for m in initial_buffered:
                db.save_message(target_chat_id, *m)
            for m in ctx.temp_buffer:
                db.save_message(target_chat_id, *m)

            ctx.temp_buffer = []
            ctx.state = STATE_NORMAL
            ctx.checkpoint_max_id = 0

        if clean_mode:
            target_react = reaction_msg or trigger_msg
            if target_react:
                if sync_error:
                    await utils.set_reaction(target_react, "😭")
                else:
                    await utils.set_reaction(target_react, None)
        else:
            if trigger_msg:
                if sync_error:
                    await utils.send_as_phantom(trigger_msg, f"⚠️ Ошибка синхронизации истории: {sync_error}")
                elif ignore_checkpoint:
                    await utils.send_as_phantom(trigger_msg, f"Подтянул {len(fetched)} сообщений.")
                else:
                    msg = "В теме" if found_gap else f"Многа букаф, ниасилил. Последние {len(fetched)}"
                    await utils.send_as_phantom(trigger_msg, msg)


@router.on(EventType.COMMAND, pattern=r"(?i)^фантом,?\s*(?:подтяни|синхронизируй|догрузи)\s+историю(?:\s+(\d+))?\b", admin_only=True, priority=20)
async def handle_manual_sync_command(ctx: EventContext) -> None:
    """
    @brief Админ-команда ручной подгрузки истории чата в произвольный момент.
    """
    chat_id = ctx.chat_id
    client = getattr(ctx.message, "_client", None)
    if not client:
        return

    explicit_limit = ctx.match.group(1) if (ctx.match and ctx.match.group(1)) else None
    limit = max(20, min(2000, int(explicit_limit))) if explicit_limit else int(getattr(cfg, "SYNC_HISTORY_LIMIT", 2000))

    clean_mode = db.get_chat_clean_mode(chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👨‍💻")
    else:
        await utils.send_as_phantom(ctx.message, f"Подтягиваю историю (до {limit} сообщений)...", category="SERVICE")

    sync_ctx = get_sync_context(chat_id)
    sync_ctx.checkpoint_max_id = db.get_max_id_in_db(chat_id)
    asyncio.create_task(
        run_sync(
            client,
            ctx.message,
            chat_id=chat_id,
            limit=limit,
            silent_status=clean_mode,
            reaction_msg=ctx.message,
            ignore_checkpoint=True,
        )
    )
