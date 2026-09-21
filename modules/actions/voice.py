"""
@file voice.py
@brief Модуль обработки голосовых сообщений (ГС) и аудиотреков.
@details Использует последовательную очередь (asyncio.Queue) для взаимодействия со Сбер Спич Ботом,
         поддерживает сбор многосоставных ответов Сбера, сжатие транскрипций >30 слов через gemma-4-31b-it,
         чистый режим реакций (👀 при обработке, 😭 при ошибках, тишина при аудио без речи).
"""

import asyncio
import logging
import re
from typing import Optional, Any, Dict
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
        self.collected_messages: Dict[int, str] = {}
        self.debounce_task: Optional[asyncio.Task] = None

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

async def summarize_voice_transcription(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    raw_text: str
) -> str:
    """
    @brief Сокращает длинную транскрипцию ГС через модель gemma-4-31b-it.
    @details Сжимает текст до ~30 слов, убирает эмоциональный спам и подбирает разную эмоциональную вводку.
    """
    system_prompt = (
        "Ты — персональный редактор голосовых сообщений Фантома. Твоя единственная задача — передать краткую суть расшифровки устной речи.\n\n"
        "ПРАВИЛА:\n"
        "1. Ответ должен быть СТРОГО на русском языке.\n"
        "2. Объем пересказа: около 30 слов (в 3-4 раза короче оригинала).\n"
        "3. Начни свой ответ с 1–2 живых слов, описывающих эмоциональное состояние говорящего (например: 'Автор с возмущением сетует на...', 'Спикер позитивно сообщает про...', 'Пользователь с досадой рассказывает о...', 'Спикер с сарказмом подмечает...'). Варьируй эмоциональные вводные слова.\n"
        "4. Выведи ТОЛЬКО финальный сжатый пересказ. Не цитируй эти правила, не пиши списки, не используй английский язык."
    )
    user_prompt = f"Расшифровка устной речи:\n«{raw_text}»\n\nСжатый пересказ на русском языке:"

    try:
        from modules import ai_service
        res = await ai_service.call_ai(
            user_id=user_id,
            username=username,
            user_api_key=None,
            system_msg=system_prompt,
            user_msg=user_prompt,
            max_tokens=300,
            model="gemma-4-31b-it",
            chat_id=chat_id,
            reasoning_effort="minimal",
            temperature=0.7
        )
        cleaned = ai_service.clean_ai_response(res)
        cleaned = re.sub(r"(?s)\n\n\*\*>\s*\[Использована модель:.*?\]\*\*", "", cleaned).strip()

        # Защита от мусорного вывода мета-инструкций на английском
        if re.search(r"(?i)\b(length|removal|tone|output|guidelines|meta-talk|do not think)\b", cleaned):
            logger.warning(f"⚠️ [VOICE AI] Gemma вернула англоязычные мета-инструкции вместо пересказа: {cleaned[:60]}")
            return raw_text

        return cleaned
    except Exception as e:
        logger.error(f"Ошибка сокращения ГС через Gemma-31B: {e}")
        return raw_text

async def queue_voice_message(
    client: Any, 
    message: Any, 
    force: bool = False, 
    status_msg: Optional[Any] = None,
    request_msg: Optional[Any] = None
) -> None:
    """
    @brief Помещает сообщение с ГС/аудио в последовательную очередь sber_voice_queue с созданием служебного сообщения.
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

    # Если НЕ чистый режим и служебного сообщения еще нет — сразу отправляем "Расшифровываю..."
    if not clean_mode and not status_msg:
        try:
            status_msg = await utils.send_as_phantom(target_msg, "Расшифровываю...", category="VOICE_TRANSCRIPTION")
        except Exception as e:
            logger.warning(f"Не удалось отправить начальный статус 'Расшифровываю...': {e}")
    elif clean_mode:
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
                    if active_context.debounce_task and not active_context.debounce_task.done():
                        active_context.debounce_task.cancel()
                    chat_id = original_msg.chat.id
                    clean_mode = db.get_chat_clean_mode(chat_id)
                    if clean_mode or not active_context.status_msg:
                        await utils.set_reaction(active_context.target_message, "😭")
                    if active_context.status_msg:
                        try:
                            await active_context.status_msg.edit_text("Не удалось расшифровать ГС (таймаут ответа).")
                        except Exception:
                            pass
            finally:
                if active_context and active_context.debounce_task and not active_context.debounce_task.done():
                    active_context.debounce_task.cancel()
                active_context = None
                sber_voice_queue.task_done()
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.exception(f"Ошибка воркера ГС: {e}")
            await asyncio.sleep(1)

async def _finalize_sber_transcription(context: VoiceContext) -> None:
    """
    @brief Финализирует накопленные сообщения от Сбер Спич Бота после паузы в поступлении кусков.
    """
    try:
        await asyncio.sleep(2.0)
    except asyncio.CancelledError:
        return

    if not context or context.done_event.is_set():
        return

    sorted_ids = sorted(context.collected_messages.keys())
    chunks = [context.collected_messages[mid] for mid in sorted_ids if context.collected_messages[mid]]
    full_text = " ".join(chunks).strip()

    if not full_text:
        context.done_event.set()
        return

    orig = context.original_message
    chat_id = orig.chat.id
    clean_mode = db.get_chat_clean_mode(chat_id)
    target_msg = context.target_message

    await utils.set_reaction(target_msg, None)

    words = full_text.split()
    final_output = full_text

    if len(words) > 30:
        # Промежуточный статус: редактируем на сырой текст от Сбера с пометкой "⏳ Сокращаю..."
        if context.status_msg and not clean_mode:
            try:
                await context.status_msg.edit_text(f"{full_text}\n\n⏳ Сокращаю...")
            except Exception:
                pass

        user_id = orig.from_user.id if orig.from_user else 0
        username = orig.from_user.username if orig.from_user else None
        logger.info(f"🎙️ [VOICE] Расшифровка содержит {len(words)} слов. Вызываем gemma-4-31b-it (reasoning_effort='off')...")
        shortened = await summarize_voice_transcription(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            raw_text=full_text
        )
        if shortened and shortened.strip() and shortened.strip() != full_text:
            final_output = f"Если кратко:\n{shortened.strip()}"
        else:
            final_output = full_text

    asyncio.create_task(tracer.queue_trace(chat_id, {
        "event": "sber_speech_transcription",
        "message_id": orig.id,
        "raw_transcription": full_text,
        "final_output": final_output,
        "word_count": len(words)
    }))

    if context.status_msg and not clean_mode:
        try:
            await context.status_msg.edit_text(final_output)
            db.update_message_text(chat_id, context.status_msg.id, final_output)
        except Exception:
            await utils.send_as_phantom(target_msg, final_output, category="VOICE_TRANSCRIPTION")
    else:
        await utils.send_as_phantom(target_msg, final_output, category="VOICE_TRANSCRIPTION")

    await asyncio.sleep(0.5)
    context.done_event.set()

def _register_sber_chunk(text: str, msg_id: int) -> None:
    """
    @brief Регистрирует текстовый кусок от Сбера и перезапускает таймер финализации.
    """
    global active_context
    if not active_context:
        return

    active_context.collected_messages[msg_id] = text.strip()
    
    if active_context.debounce_task and not active_context.debounce_task.done():
        active_context.debounce_task.cancel()

    active_context.debounce_task = asyncio.create_task(_finalize_sber_transcription(active_context))

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

    if is_no_speech(text):
        if active_context.debounce_task and not active_context.debounce_task.done():
            active_context.debounce_task.cancel()
        await utils.set_reaction(active_context.target_message, None)
        if active_context.status_msg:
            try: await active_context.status_msg.delete()
            except Exception: pass
        active_context.done_event.set()
        return

    error_type = is_sber_error(text)
    if error_type:
        if active_context.debounce_task and not active_context.debounce_task.done():
            active_context.debounce_task.cancel()
        chat_id = active_context.original_message.chat.id
        clean_mode = db.get_chat_clean_mode(chat_id)
        if clean_mode or not active_context.status_msg:
            await utils.set_reaction(active_context.target_message, "😭")
        if active_context.status_msg:
            try: await active_context.status_msg.delete()
            except Exception: pass
        active_context.done_event.set()
        return

    if text.strip():
        _register_sber_chunk(text, message.id)

async def handle_sber_edit(client: Any, message: Any) -> None:
    """
    @brief Обработчик событий редактирования сообщений Сбером (приход мнемоник/транскрипций).
    """
    global active_context
    if not active_context:
        return

    text = message.text or ""
    
    if is_no_speech(text):
        if active_context.debounce_task and not active_context.debounce_task.done():
            active_context.debounce_task.cancel()
        await utils.set_reaction(active_context.target_message, None)
        if active_context.status_msg:
            try: await active_context.status_msg.delete()
            except Exception: pass
        active_context.done_event.set()
        return

    error_type = is_sber_error(text)
    if error_type:
        if active_context.debounce_task and not active_context.debounce_task.done():
            active_context.debounce_task.cancel()
        target_msg = active_context.target_message
        await utils.set_reaction(target_msg, "😭")
        if active_context.status_msg:
            try: await active_context.status_msg.delete()
            except Exception: pass
        active_context.done_event.set()
        return

    if "принято" not in text.lower() and text.strip():
        _register_sber_chunk(text, message.id)