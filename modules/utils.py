"""
@file utils.py
@brief Модуль вспомогательных функций форматирования, управления реакциями и отправки сообщений.
"""

import logging
from typing import Optional, Tuple, Any
import datetime
import modules.database as db

logger = logging.getLogger(__name__)

def format_author(msg: Any) -> str:
    """
    @brief Формирует человекочитаемое имя автора сообщения для логов и БД.
    @param msg Объект сообщения Pyrogram Message.
    @return Строка вида 'Никита (@techno_c_a_t)' или 'Собеседник'.
    """
    if not msg or not msg.from_user:
        return "Неизвестный"
    if msg.from_user.is_self:
        return "Я (Фантом)"
    fname = msg.from_user.first_name or "Пользователь"
    uname = f" (@{msg.from_user.username})" if msg.from_user.username else ""
    return f"{fname}{uname}"


async def format_msg(msg: Any) -> Optional[Tuple[int, str, str, Any]]:
    """
    @brief Форматирует входящее сообщение Telegram в кортеж данных для сохранения в БД.
    @param msg Объект сообщения Pyrogram Message.
    @return Кортеж (id_сообщения, автор_с_контекстом_реплая, текст_сообщения, дата) или None.
    """
    if not msg or not msg.text: 
        return None
        
    author = format_author(msg)
    
    if msg.reply_to_message:
        r = msg.reply_to_message
        r_author = format_author(r)
        snippet = " ".join((r.text or "").split()[:3]) + "..."
        author = f"{author} ответ {r_author} на \"{snippet}\""
        
    return (msg.id, author, msg.text, msg.date)


async def set_reaction(message: Any, emoji: Optional[str] = None) -> bool:
    """
    @brief Безопасно устанавливает или снимает реакцию на сообщении Telegram.
    @param message Объект сообщения Pyrogram Message.
    @param emoji Строка emoji (например '👀' или '👍') или None/"" для отмены реакции.
    @return True при успешной установке реакции.
    """
    if not message:
        return False
    try:
        if hasattr(message, "react"):
            if emoji:
                await message.react(emoji)
            else:
                await message.react([])
            return True
        elif hasattr(message, "_client"):
            client = message._client
            chat_id = message.chat.id
            msg_id = message.id
            if emoji:
                await client.send_reaction(chat_id, msg_id, emoji)
            else:
                await client.send_reaction(chat_id, msg_id, [])
            return True
    except Exception as e:
        logger.debug(f"Не удалось выставить реакцию '{emoji}': {e}")
    return False


async def send_as_phantom(message: Any, text: str, edit_message: Optional[Any] = None, category: str = 'SERVICE') -> Any:
    """
    @brief Безопасно отправляет или редактирует ответ от лица Фантома с автоматической записью в БД с категорией.
    @param message Исходное сообщение пользователя.
    @param text Текст ответа Фантома.
    @param edit_message Опциональное сообщение статуса для редактирования ('Вникаю...').
    @param category Категория сообщения ('SERVICE', 'AI_SUMMARY', 'AI_RESPONSE', 'VOICE_TRANSCRIPTION').
    @return Объект отправленного/отредактированного сообщения Pyrogram Message.
    """
    chat_id = message.chat.id
    if edit_message:
        sent = await edit_message.edit_text(text)
        db.update_message_text(chat_id, sent.id, text)
    else:
        sent = await message.reply_text(text)
        data = await format_msg(sent)
        if data:
            db.save_message(chat_id, data[0], data[1], data[2], data[3], category=category)
    return sent