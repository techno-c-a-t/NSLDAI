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
STATE_SYNCING: str = "SYNCING"

class ChatSyncContext:
    """
    @brief Контекст состояния синхронизации конкретного чата.
    """
    def __init__(self):
        self.state: str = STATE_WAITING_SYNC
        self.temp_buffer: List[Any] = []

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

async def run_sync(client: Any, trigger_msg: Any) -> None:
    """
    @brief Запускает синхронизацию пропущенной истории чата из Telegram API.
    @param client Объект Pyrogram Client.
    @param trigger_msg Сообщение-триггер ("Да"), вызвавшее синхронизацию.
    """
    chat_id = trigger_msg.chat.id
    ctx = get_sync_context(chat_id)
    
    max_id = db.get_max_id_in_db(chat_id)
    fetched: List[Any] = []
    total_needed = cfg.HISTORY_SIZE
    last_id = ctx.temp_buffer[0][0] if ctx.temp_buffer else trigger_msg.id
    found_gap = False

    # Загрузка истории с паузами задержки (Throttling)
    async for old_msg in client.get_chat_history(chat_id, limit=total_needed, offset_id=last_id):
        if not old_msg.text: 
            continue
        if old_msg.id <= max_id:
            found_gap = True
            break
        data = await utils.format_msg(old_msg)
        if data: 
            fetched.append(data)
        if len(fetched) % 25 == 0:
            await asyncio.sleep(0.5)
    
    if not found_gap:
        db.clear_db(chat_id)
        
    for m in reversed(fetched):
        db.save_message(chat_id, *m)
    for m in ctx.temp_buffer:
        db.save_message(chat_id, *m)
    
    ctx.temp_buffer, ctx.state = [], STATE_NORMAL
    msg = "В теме" if found_gap else f"Многа букаф, ниасилил. Последние {total_needed}"
    await utils.send_as_phantom(trigger_msg, msg)
