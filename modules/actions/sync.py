"""
@file sync.py
@brief Модуль синхронизации пропущенных сообщений чата при старте бота.
@details Подгружает пропущенную историю с троттлингом (0.5с на 25 сообщений) для защиты от бана Telegram API.
"""

import asyncio
from typing import Dict, List, Any
import modules.config as cfg
import modules.database as db
import modules.utils as utils

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

def prepare_waiting_sync(chat_id: int) -> ChatSyncContext:
    """
    @brief Переводит чат в режим ожидания синхронизации и фиксирует текущий max_id в БД.
    @details Применяется строго к групповым чатам (chat_id < 0). ЛС (chat_id > 0) исключены.
    @param chat_id ID чата.
    @return Экземпляр ChatSyncContext.
    """
    ctx = get_sync_context(chat_id)
    if chat_id > 0:
        ctx.state = STATE_NORMAL
        return ctx
    ctx.state = STATE_WAITING_SYNC
    ctx.checkpoint_max_id = db.get_max_id_in_db(chat_id)
    return ctx

async def run_sync(client: Any, trigger_msg: Any) -> None:
    """
    @brief Запускает синхронизацию пропущенной истории чата из Telegram API в строгой очереди.
    @param client Объект Pyrogram Client.
    @param trigger_msg Сообщение-триггер ("Да"), вызвавшее синхронизацию.
    """
    chat_id = trigger_msg.chat.id
    ctx = get_sync_context(chat_id)
    
    # Если замок уже занят другим чатом — уведомляем и фиксируем стейт очереди
    if sync_lock.locked():
        ctx.state = STATE_QUEUED
        await utils.send_as_phantom(trigger_msg, "⏳ Чат добавлен в очередь синхронизации. Жду завершения текущего чата...")

    async with sync_lock:
        ctx.state = STATE_SYNCING
        # Используем замороженный checkpoint_max_id на момент старта бота
        max_id = ctx.checkpoint_max_id if ctx.checkpoint_max_id > 0 else db.get_max_id_in_db(chat_id)
        fetched: List[Any] = []
        total_needed = int(getattr(cfg, "SYNC_HISTORY_LIMIT", 2000))
        found_gap = False

        # Забираем накопленные в буфере сообщения в локальную копию,
        # чтобы сообщения, приходящие во время сетевой выкачки, складывались в чистый ctx.temp_buffer
        initial_buffered = list(ctx.temp_buffer)
        ctx.temp_buffer = []

        # Загрузка истории: начинаем от САМОГО СВЕЖЕГО сообщения в чате и поднимаемся вверх по истории
        async for old_msg in client.get_chat_history(chat_id, limit=total_needed):
            if not old_msg.text: 
                continue
            if max_id > 0 and old_msg.id <= max_id:
                found_gap = True
                break
            data = await utils.format_msg(old_msg)
            if data: 
                fetched.append(data)
            if len(fetched) % 25 == 0:
                await asyncio.sleep(0.5)
        
        # Если уперлись в лимит (2000) и склейка со старой базой не произошла (бот был оффлайн 3 недели):
        # стираем ТОЛЬКО старую историю сообщений ДО гэпа (id <= max_id),
        # а свежие выкачанные сообщения, досье участников и настройки чата сохраняем!
        if not found_gap and max_id > 0:
            db.clear_history_before(chat_id, max_id)
            
        for m in reversed(fetched):
            db.save_message(chat_id, *m)
        for m in initial_buffered:
            db.save_message(chat_id, *m)
        for m in ctx.temp_buffer:
            db.save_message(chat_id, *m)
        
        ctx.temp_buffer, ctx.state, ctx.checkpoint_max_id = [], STATE_NORMAL, 0
        msg = "В теме" if found_gap else f"Многа букаф, ниасилил. Последние {len(fetched)}"
        await utils.send_as_phantom(trigger_msg, msg)
