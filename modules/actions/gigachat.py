"""
@file gigachat.py
@brief Модуль интеграции с GigaChat Ботом в Telegram.
@details Служит аварийным каналом (fallback) генерации ответов, если Google API не откликается.
"""

import asyncio
import logging
from typing import Optional, Any
import modules.config as cfg

logger = logging.getLogger(__name__)

## @brief Блокировка для потокобезопасных обращений к GigaChat
giga_lock: asyncio.Lock = asyncio.Lock()

## @brief Событие завершения ответа от GigaChat
giga_event: asyncio.Event = asyncio.Event()

## @brief Сохраненный текст последнего ответа GigaChat
giga_response: Optional[str] = None

async def handle_giga_response(message: Any) -> None:
    """
    @brief Обработчик входящих и отредактированных сообщений от GigaChat Бота.
    @param message Объект сообщения Pyrogram Message.
    """
    global giga_response
    text = message.text or message.caption or ""
    
    # Пропускаем служебные промежуточные уведомления
    if not text.strip() or "Запрос принят" in text or "готовлю ответ" in text:
        logger.info(f"⏳ [GIGACHAT] Служебный промежуточный статус: '{text[:50]}'")
        return
    
    logger.info(f"✅ [GIGACHAT] Получен ответ ({len(text)} симв.): '{text[:60]}...'")
    giga_response = text
    giga_event.set()