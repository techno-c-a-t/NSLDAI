"""
@file voice.py
@brief Модуль обработки голосовых сообщений (ГС) и аудиотреков.
@details Использует последовательную очередь (asyncio.Queue) для взаимодействия со Сбер Спич Ботом,
         поддерживает чистый режим реакций (👀 при обработке, 😭 при ошибках, тишина при аудио без речи)
         и отмену лишних ИИ-фильтров.
"""

import asyncio
import logging
from typing import Optional, Any
import modules.utils as utils
import modules.config as cfg
import modules.database as db
from modules.actions import tracer
from modules.router import router, EventType, EventContext

logger = logging.getLogger(__name__)

## @brief Асинхронная очередь ГС для последовательной отправки в Сбер Спич Бот
sber_voice_queue: asyncio.Queue = asyncio.Queue()

class VoiceContext:
    """
    @brief Контекст состояния обработки конкретного голосового сообщения.
    """
    def __init__(self, original_message: Any, status_msg: Optional[Any] = None, target_message: Optional[Any] = None):
        """
        @param original_message Исходное сообщение пользователя с ГС.
        @param status_msg Опциональное служебное сообщение статуса ("Закинул на расшифровку").
        @param target_message Целевое сообщение для установки реакций Telegram (ГС или запрос).
        """
        self.original_message = original_message
        self.status_msg: Optional[Any] = status_msg
        self.target_message: Any = target_message or status_msg or original_message
        self.sber_ack_id: Optional[int] = None
        self.done_event: asyncio.Event = asyncio.Event()

## @brief Ссылка на текущий обрабатываемый контекст ГС
active_context: Optional[VoiceContext] = None

def is_music_track(message: Any) -> bool:
    """
    @brief Определяет, является ли медиафайл песней/музыкальным треком.
    """
    if message.audio:
        return True
    if message.voice and message.voice.duration and message.voice.duration > 180:
        return True
    return False

def is_sber_error(text: str) -> Optional[str]:
    """
    @brief Проверяет текст ответа Сбер Спич Бота на наличие типичных системных ошибок.
    """
    t = text.lower()
    if "слишком большое аудио" in t or ("большое" in t and "8mb" in t):
        return "limit"
    if "данный тип файла не поддерживается" in t:
        return "format"
    return None

def is_no_speech(text: str) -> bool:
    """
    @brief Проверяет, вернул ли Сбер системный ответ об отсутствии речи в аудио.
    """
    t = text.lower()
    return "не удалось ничего распознать" in t or "без речи" in t or "аудио без речи" in t

async def queue_voice_message(
    client: Any, 
    message: Any, 
    force: bool = False, 
    status_msg: Optional[Any] = None,
    request_msg: Optional[Any] = None
) -> None:
    """
    @brief Помещает сообщение с ГС/аудио в последовательную очередь sber_voice_queue с установкой реакций.
    """
    chat_id = message.chat.id
    clean_mode = db.get_chat_clean_mode(chat_id)

    if not force:
        if is_music_track(message):
            logger.info(f"Музыкальный файл {message.id} пропущен в авто-режиме.")
            if status_msg:
                try: await status_msg.delete()
                except Exception: pass
            return

        chat_mode = db.get_chat_voice_mode(chat_id)
        if chat_mode == 'ON_DEMAND':
            logger.info(f"ГС {message.id} пропущено: в чате {chat_id} включен режим по запросу.")
            if status_msg:
                try: await status_msg.delete()
                except Exception: pass
            return

    target_msg = request_msg or status_msg or message

    if clean_mode:
        await utils.set_reaction(target_msg, "👀")

    await sber_voice_queue.put((message, status_msg, target_msg))

@router.on(EventType.TEXT_MESSAGE, priority=10)
async def handle_auto_voice_message(ctx: EventContext) -> bool:
    """
    @brief Перехватчик всех входящих голосовых и аудио сообщений в разрешенных чатах.
    """
    message = ctx.message
    if message and (message.voice or message.audio):
        asyncio.create_task(queue_voice_message(None, message, force=False))
        return True
    return False

async def sber_worker_loop(client: Any) -> None:
    """
    @brief Бесконечный фоновый воркер: извлекает ГС из очереди и отправляет Сбер Спич Боту по одному.
    """
    global active_context
    logger.info("Запущен последовательный воркер ГС (Sber Speech Bot)...")
    while True:
        try:
            item = await sber_voice_queue.get()
            if isinstance(item, tuple) and len(item) == 3:
                original_msg, status_msg, target_msg = item
            elif isinstance(item, tuple):
                original_msg, status_msg = item
                target_msg = status_msg or original_msg
            else:
                original_msg, status_msg, target_msg = item, None, item

            active_context = VoiceContext(original_msg, status_msg, target_msg)
            
            await original_msg.forward(cfg.SBER_SPEECH_BOT)
            
            try:
                await asyncio.wait_for(active_context.done_event.wait(), timeout=180)
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут обработки ГС для сообщения {original_msg.id}")
                if active_context:
                    chat_id = original_msg.chat.id
                    clean_mode = db.get_chat_clean_mode(chat_id)
                    if clean_mode or not active_context.status_msg:
                        await utils.set_reaction(active_context.target_message, "😭")
                    if active_context.status_msg:
                        try: await active_context.status_msg.delete()
                        except Exception: pass
            finally:
                active_context = None
                sber_voice_queue.task_done()
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.exception(f"Ошибка воркера ГС: {e}")
            await asyncio.sleep(1)

async def handle_sber_message(client: Any, message: Any) -> None:
    """
    @brief Обработчик входящих сообщений от Сбер Спич Бота.
    """
    global active_context
    if not active_context:
        return

    text = message.text or ""

    if "аудиосообщение принято" in text.lower():
        active_context.sber_ack_id = message.id
        return

    error_type = is_sber_error(text)
    if error_type:
        chat_id = active_context.original_message.chat.id
        clean_mode = db.get_chat_clean_mode(chat_id)
        if clean_mode or not active_context.status_msg:
            await utils.set_reaction(active_context.target_message, "😭")
        if active_context.status_msg:
            try: await active_context.status_msg.delete()
            except Exception: pass
        active_context.done_event.set()
        return

async def handle_sber_edit(client: Any, message: Any) -> None:
    """
    @brief Обработчик событий редактирования сообщений Сбером (приход финального текста).
    """
    global active_context
    if not active_context or not active_context.sber_ack_id or message.id != active_context.sber_ack_id:
        return

    text = message.text or ""
    orig = active_context.original_message
    chat_id = orig.chat.id
    clean_mode = db.get_chat_clean_mode(chat_id)
    target_msg = active_context.target_message
    
    # 1. ТИХОЕ ЗАВЕРШЕНИЕ: АУДИО БЕЗ РЕЧИ
    if is_no_speech(text):
        await utils.set_reaction(target_msg, None)
        if active_context.status_msg:
            try: await active_context.status_msg.delete()
            except Exception: pass
        active_context.done_event.set()
        return

    # 2. ОШИБКА СБЕРА
    error_type = is_sber_error(text)
    if error_type:
        await utils.set_reaction(target_msg, "😭")
        if active_context.status_msg:
            try: await active_context.status_msg.delete()
            except Exception: pass
        active_context.done_event.set()
        return

    # 3. УСПЕШНАЯ РАСШИФРОВКА БЕЗ ИИ-ВАЛИДАТОРА
    if "принято" not in text.lower():
        await utils.set_reaction(target_msg, None)

        asyncio.create_task(tracer.queue_trace(chat_id, {
            "event": "sber_speech_transcription",
            "message_id": orig.id,
            "transcription": text
        }))

        formatted_transcription = f"{text}"
        if active_context.status_msg and not clean_mode:
            try:
                await active_context.status_msg.edit_text(formatted_transcription)
                db.save_message(chat_id, active_context.status_msg.id, "Я (Фантом)", formatted_transcription, active_context.status_msg.date, category="VOICE_TRANSCRIPTION")
            except Exception:
                await utils.send_as_phantom(target_msg, formatted_transcription, category="VOICE_TRANSCRIPTION")
        else:
            await utils.send_as_phantom(target_msg, formatted_transcription, category="VOICE_TRANSCRIPTION")

        await asyncio.sleep(1.0)
        active_context.done_event.set()