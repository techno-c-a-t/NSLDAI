"""
@file utils.py
@brief Модуль вспомогательных функций форматирования, управления реакциями и отправки сообщений.
"""

import logging
from typing import Optional, Tuple, Any, List
import datetime
import modules.database as db

logger = logging.getLogger(__name__)

def truncate_by_words(text: str, max_len: int = 3900) -> str:
    """
    @brief Обрезает текст по границе слов до max_len символов.
    @param text Исходный текст.
    @param max_len Максимальная допустимая длина в символах.
    @return Обрезанный текст.
    """
    if not text or len(text) <= max_len:
        return text
    truncated = text[:max_len]
    split_pos = max(truncated.rfind("\n"), truncated.rfind(" "))
    if split_pos > int(max_len * 0.5):
        truncated = truncated[:split_pos]
    return truncated.rstrip()


def split_text_by_words(text: str, max_chunk_size: int = 4000) -> List[str]:
    """
    @brief Безопасно нарезает длинный текст на блоки не более max_chunk_size символов (лимит Telegram 4096),
           стараясь резать строго по границам абзацев или слов.
    @param text Исходный длинный текст.
    @param max_chunk_size Максимальный размер блока (по умолчанию 4000).
    @return Список непустых чанков.
    """
    if not text or len(text) <= max_chunk_size:
        return [text] if text else [""]

    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chunk_size:
            chunks.append(remaining)
            break

        candidate = remaining[:max_chunk_size]
        split_pos = candidate.rfind("\n")
        if split_pos < int(max_chunk_size * 0.7):
            split_pos = candidate.rfind(" ")

        if split_pos <= 0:
            split_pos = max_chunk_size

        chunk = remaining[:split_pos].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_pos:].lstrip()

    return chunks or [text[:max_chunk_size]]


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


async def send_as_phantom(message: Any, text: str, edit_message: Optional[Any] = None, category: str = 'SERVICE', parse_mode: Any = None) -> Any:
    """
    @brief Безопасно отправляет или редактирует ответ от лица Фантома с автоматической нарезкой
           длинных текстов до 4000 символов (защита от лимита 4096 Telegram API) и записью в БД.
    @param message Исходное сообщение пользователя.
    @param text Текст ответа Фантома.
    @param edit_message Опциональное сообщение статуса для редактирования ('Вникаю...').
    @param category Категория сообщения ('SERVICE', 'AI_SUMMARY', 'AI_RESPONSE', 'VOICE_TRANSCRIPTION').
    @param parse_mode Режим парсинга разметки (enums.ParseMode.HTML или None).
    @return Объект отправленного/отредактированного сообщения Pyrogram Message.
    """
    chat_id = message.chat.id
    chunks = split_text_by_words(text, max_chunk_size=4000)

    last_sent = None
    first_chunk = chunks[0] if chunks else ""

    send_kwargs = {}
    if parse_mode is not None:
        send_kwargs["parse_mode"] = parse_mode

    if edit_message:
        try:
            sent = await edit_message.edit_text(first_chunk, **send_kwargs)
            db.update_message_text(chat_id, sent.id, first_chunk)
            last_sent = sent
        except Exception as e:
            logger.warning(f"Ошибка редактирования статуса сообщения {edit_message.id}: {e}. Отправка новым сообщением.")
            sent = await message.reply_text(first_chunk, **send_kwargs)
            data = await format_msg(sent)
            if data:
                db.save_message(chat_id, data[0], data[1], data[2], data[3], category=category)
            last_sent = sent
    else:
        sent = await message.reply_text(first_chunk, **send_kwargs)
        data = await format_msg(sent)
        if data:
            db.save_message(chat_id, data[0], data[1], data[2], data[3], category=category)
        last_sent = sent

    # Отправляем оставшиеся чанки, если текст превысил 4000 символов
    for extra_chunk in chunks[1:]:
        sent_extra = await message.reply_text(extra_chunk, **send_kwargs)
        data_extra = await format_msg(sent_extra)
        if data_extra:
            db.save_message(chat_id, data_extra[0], data_extra[1], data_extra[2], data_extra[3], category=category)
        last_sent = sent_extra

    return last_sent