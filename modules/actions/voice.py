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
import html
import time
from typing import Optional, Any, Dict, Tuple, List
from hydrogram import enums

import modules.utils as utils
import modules.config as cfg
import modules.database as db
from modules.actions import tracer
from modules.router import router, EventType, EventContext

logger = logging.getLogger(__name__)

## @brief Асинхронная очередь обычных ГС (<= 3 минут) для последовательной отправки в Сбер Спич Бот
sber_voice_queue: asyncio.Queue = asyncio.Queue()

## @brief Отдельная асинхронная очередь длинных ГС (> 3 минут)
sber_voice_queue_long: asyncio.Queue = asyncio.Queue()

## @brief Событие уведомления о поступлении новой задачи в любую из очередей
voice_queue_notify: asyncio.Event = asyncio.Event()

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
        self.start_time: float = time.time()
        self.is_long: bool = False
        self.estimated_time: int = 5

## @brief Ссылка на текущий обрабатываемый контекст ГС
active_context: Optional[VoiceContext] = None

def get_audio_duration(message: Any) -> int:
    """
    @brief Возвращает длительность голосового или аудио сообщения в секундах.
    """
    if message and getattr(message, "voice", None) and getattr(message.voice, "duration", None):
        return int(message.voice.duration)
    if message and getattr(message, "audio", None) and getattr(message.audio, "duration", None):
        return int(message.audio.duration)
    if message and getattr(message, "video_note", None) and getattr(message.video_note, "duration", None):
        return int(message.video_note.duration)
    return 0

def estimate_sber_time(is_long: bool) -> int:
    """
    @brief Время распознавания речи Сбером: 5с для обычных (до 3 мин) и 10с для длинных (> 3 мин).
    """
    return 10 if is_long else 5

def calculate_queue_wait_estimate(is_long: bool) -> int:
    """
    @brief Вычисляет суммарный эстимейт ожидания:
           - До 3 мин: 5с на 1 элемент очереди + остаток текущего + 5с (самому сообщению)
           - Длинная очередь (>3 мин): размер очереди коротких * 5с + 10с * количество элементов длинной очереди + 10с
    """
    now = time.time()
    rem_active = 0
    if active_context:
        elapsed = int(now - getattr(active_context, "start_time", now))
        rem_active = max(1, getattr(active_context, "estimated_time", 5) - elapsed)
    
    q_short = sber_voice_queue.qsize()
    q_long = sber_voice_queue_long.qsize()

    if not is_long:
        total = rem_active + (q_short * 5) + 5
    else:
        total = rem_active + (q_short * 5) + (q_long * 10) + 10

    return max(1, total)

def get_queue_position(started_event: Optional[asyncio.Event]) -> int:
    """
    @brief Возвращает точную порядковую позицию задачи в очереди.
    """
    if not started_event:
        return 1
    pos = 1 if active_context else 0
    for idx, item in enumerate(list(sber_voice_queue._queue)):
        if len(item) == 4 and item[3] is started_event:
            return pos + idx + 1
    pos += sber_voice_queue.qsize()
    for idx, item in enumerate(list(sber_voice_queue_long._queue)):
        if len(item) == 4 and item[3] is started_event:
            return pos + idx + 1
    return max(1, pos)

async def _live_countdown_ticker(
    status_msg: Any, 
    get_text_func: Any, 
    initial_seconds: int, 
    stop_event: asyncio.Event,
    is_queue: bool = False
) -> None:
    """
    @brief Интерактивный обратный отсчет:
           - Для топа очереди (позиция 1) и активной расшифровки: раз в 1 секунду.
           - Для остальных позиций в очереди (позиция >= 2): раз в 5 секунд.
    """
    rem = initial_seconds
    while not stop_event.is_set() and rem > 0:
        if is_queue:
            cur_pos = get_queue_position(stop_event)
            step = 1 if cur_pos <= 1 else 5
        else:
            step = 1

        actual_step = min(step, rem)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=float(actual_step))
            break
        except asyncio.TimeoutError:
            if stop_event.is_set():
                break
            rem -= actual_step
            try:
                new_text = get_text_func(rem)
                if getattr(status_msg, "text", "") != new_text:
                    await status_msg.edit_text(new_text)
            except Exception as e:
                if "FLOOD_WAIT" in str(e).upper():
                    await asyncio.sleep(2.0)

def is_music_track(message: Any) -> bool:
    """
    @brief Определяет, является ли медиафайл песней/музыкальным треком (.mp3).
    @details Обычные голосовые сообщения (voice) не считаются музыкой независимо от длительности.
    """
    if message.audio:
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
    raw_text: str,
    status_msg: Optional[Any] = None
) -> str:
    """
    @brief Сокращает длинную транскрипцию ГС через пайплайн: 3 круга Gemma 31B/26B -> GigaChat fallback.
    @details Сжимает текст до ~30 слов, убирает эмоциональный спам и подбирает разную эмоциональную вводку.
             Применяет reasoning_effort='minimal' для полного отключения мышления (thinking 100% OFF).
    """
    system_prompt = (
        "Ты — персональный редактор голосовых сообщений Фантома. Твоя единственная задача — передать краткую суть расшифровки устной речи.\n\n"
        "ПРАВИЛА:\n"
        "1. Ответ должен быть СТРОГО на русском языке.\n"
        "2. Объем пересказа: минимум около 30 слов, цель - в 3-5 раза короче оригинала или сильнее, если оригинал полон бссмысленных слов\n"
        "3. Начни свой ответ с 1–2 живых слов, описывающих эмоциональное состояние говорящего (например: 'Автор с возмущением сетует на...', 'Спикер позитивно сообщает про...', 'Пользователь с досадой рассказывает о...', 'Спикер с сарказмом подмечает...'). Варьируй эмоциональные вводные слова.\n"
        "4. Выведи ТОЛЬКО финальный сжатый пересказ. Не цитируй эти правила, не пиши списки, не используй английский язык."
    )
    user_prompt = f"Расшифровка устной речи:\n«{raw_text}»\n\nСжатый пересказ на русском языке:"

    try:
        from modules import ai_service
        # Пайплайн call_ai для gemma-4-31b-it:
        # 3 круга чередования (gemma-4-31b-it <-> gemma-4-26b-a4b-it) -> GigaChat
        res = await ai_service.call_ai(
            user_id=user_id,
            username=username,
            user_api_key=None,
            system_msg=system_prompt,
            user_msg=user_prompt,
            status_msg=None,
            max_tokens=300,
            model="gemma-4-31b-it",
            chat_id=chat_id,
            reasoning_effort="minimal",
            temperature=0.7
        )
        cleaned = ai_service.clean_ai_response(res)
        cleaned = re.sub(r"(?s)\n\n\*\*>\s*\[.*?\]\*\*", "", cleaned).strip()

        # Защита от возврата системных ошибок call_ai и мусора
        is_err = (
            not cleaned or
            "все доступные модели" in cleaned.lower() or
            "все нейронки легли" in cleaned.lower() or
            "недоступны" in cleaned.lower() or
            cleaned.startswith("Ошибка")
        )
        if is_err:
            logger.warning(f"⚠️ [VOICE AI] Gemma вернула сообщение об ошибке/недоступности: {cleaned[:60]}")
            return ""

        # Защита от мусорного вывода мета-инструкций на английском
        if re.search(r"(?i)\b(length|removal|tone|output|guidelines|meta-talk|do not think)\b", cleaned):
            logger.warning(f"⚠️ [VOICE AI] Gemma вернула англоязычные мета-инструкции вместо пересказа: {cleaned[:60]}")
            return ""

        return cleaned
    except Exception as e:
        logger.error(f"Ошибка сокращения ГС через Gemma-31B: {e}")
        return ""

async def get_next_voice_item() -> Tuple[Any, asyncio.Queue]:
    """
    @brief Извлекает следующее ГС для обработки со строгим приоритетом:
           1. Сначала полностью опустошается основная очередь (ГС <= 3 минут).
           2. Когда основная очередь пустует — берутся сообщения из отдельной очереди длинных ГС (> 3 минут),
              отсортированные по времени поступления (FIFO).
    """
    while True:
        # Приоритет №1: основная очередь коротких сообщений (FIFO)
        if not sber_voice_queue.empty():
            return sber_voice_queue.get_nowait(), sber_voice_queue

        # Приоритет №2: длинные сообщения (> 3 мин) по времени прилета (FIFO)
        if not sber_voice_queue_long.empty():
            return sber_voice_queue_long.get_nowait(), sber_voice_queue_long

        # Если обе очереди пусты — сбрасываем флаг и ожидаем уведомления
        voice_queue_notify.clear()
        if not sber_voice_queue.empty():
            return sber_voice_queue.get_nowait(), sber_voice_queue
        if not sber_voice_queue_long.empty():
            return sber_voice_queue_long.get_nowait(), sber_voice_queue_long

        try:
            await asyncio.wait_for(voice_queue_notify.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

async def queue_voice_message(
    client: Any, 
    message: Any, 
    force: bool = False, 
    status_msg: Optional[Any] = None,
    request_msg: Optional[Any] = None
) -> None:
    """
    @brief Помещает сообщение с ГС/аудио в соответствующую очередь (основная <=3 мин или длинная >3 мин).
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
    duration = get_audio_duration(message)
    is_long = duration > 180
    started_event = asyncio.Event()

    # Если НЕ чистый режим и служебного сообщения еще нет — сразу отправляем статус (забиваем место под ГС)
    if not clean_mode and not status_msg:
        try:
            is_busy = (active_context is not None) or (not sber_voice_queue.empty()) or (not sber_voice_queue_long.empty())
            if is_busy:
                q_pos = sber_voice_queue.qsize() + sber_voice_queue_long.qsize() + (1 if active_context else 0)
                wait_est = calculate_queue_wait_estimate(is_long)
                status_text = f"⏳ В очереди на расшифровку (позиция: {q_pos}, ~{wait_est}с)..."
            else:
                self_est = estimate_sber_time(is_long)
                status_text = f"Расшифровываю (длинное ГС >3 мин, ~{self_est}с)..." if is_long else f"Расшифровываю (~{self_est}с)..."
            status_msg = await utils.send_as_phantom(target_msg, status_text, category="VOICE_TRANSCRIPTION")
            
            # Если задача встала в очередь — запускаем интерактивный отсчет (топ очереди: 1с, остальные: 5с)
            if is_busy and status_msg:
                def get_queue_text(rem_sec: int) -> str:
                    cur_pos = get_queue_position(started_event)
                    return f"⏳ В очереди на расшифровку (позиция: {cur_pos}, ~{max(1, rem_sec)}с)..."
                asyncio.create_task(_live_countdown_ticker(status_msg, get_queue_text, wait_est, started_event, is_queue=True))
        except Exception as e:
            logger.warning(f"Не удалось отправить начальный статус: {e}")
    elif clean_mode:
        await utils.set_reaction(target_msg, "👀")

    item = (message, status_msg, target_msg, started_event)
    if is_long:
        logger.info(f"⏳ [VOICE QUEUE] Длинное ГС id={message.id} ({duration} сек) помещено в очередь длинных аудио (>3 мин).")
        sber_voice_queue_long.put_nowait(item)
    else:
        logger.info(f"⚡ [VOICE QUEUE] Короткое ГС id={message.id} ({duration} сек) помещено в основную приоритетную очередь.")
        sber_voice_queue.put_nowait(item)

    voice_queue_notify.set()

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
    @brief Бесконечный фоновый воркер: извлекает ГС с приоритетом основной очереди (короткие <=3 мин)
           и длинной очереди (>3 мин, когда пустует основная), отправляя Сбер Спич Боту по одному.
    """
    global active_context
    logger.info("Запущен приоритетный воркер ГС (Sber Speech Bot)...")
    while True:
        try:
            item, source_queue = await get_next_voice_item()
            started_event = None
            if isinstance(item, tuple) and len(item) == 4:
                original_msg, status_msg, target_msg, started_event = item
            elif isinstance(item, tuple) and len(item) == 3:
                original_msg, status_msg, target_msg = item
            elif isinstance(item, tuple):
                original_msg, status_msg = item
                target_msg = status_msg or original_msg
            else:
                original_msg, status_msg, target_msg = item, None, item

            if started_event:
                started_event.set()

            active_context = VoiceContext(original_msg, status_msg, target_msg)
            chat_id = original_msg.chat.id
            clean_mode = db.get_chat_clean_mode(chat_id)
            duration = get_audio_duration(original_msg)
            is_long = duration > 180
            self_est = estimate_sber_time(is_long)
            active_context.is_long = is_long
            active_context.start_time = time.time()
            active_context.estimated_time = self_est
            
            # Интерактивный посекундный отсчет этапа «Расшифровываю (~Xс)...»
            if status_msg and not clean_mode:
                def get_transcribe_text(rem_sec: int) -> str:
                    prefix = "Расшифровываю (длинное ГС >3 мин" if is_long else "Расшифровываю"
                    if rem_sec > 0:
                        return f"{prefix}, ~{rem_sec}с)..."
                    return f"{prefix})..."

                try:
                    initial_st = get_transcribe_text(self_est)
                    if getattr(status_msg, "text", "") != initial_st:
                        await status_msg.edit_text(initial_st)
                except Exception:
                    pass

                asyncio.create_task(_live_countdown_ticker(status_msg, get_transcribe_text, self_est, active_context.done_event, is_queue=False))

            try:
                await original_msg.forward(cfg.SBER_SPEECH_BOT)
                duration = get_audio_duration(original_msg)
                timeout_sec = max(180, duration + 60)
                await asyncio.wait_for(active_context.done_event.wait(), timeout=timeout_sec)
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут обработки ГС для сообщения {original_msg.id} (таймаут {timeout_sec}с)")
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
            except Exception as e:
                logger.exception(f"Ошибка воркера ГС: {e}")
                if active_context and active_context.status_msg:
                    try:
                        await active_context.status_msg.edit_text("Не удалось отправить ГС на распознавание.")
                    except Exception:
                        pass
            finally:
                if active_context and active_context.debounce_task and not active_context.debounce_task.done():
                    active_context.debounce_task.cancel()
                active_context = None
                source_queue.task_done()
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.exception(f"Критическая ошибка цикла воркера ГС: {e}")
            await asyncio.sleep(1)

async def _async_summarize_and_update(
    chat_id: int,
    orig: Any,
    status_msg: Optional[Any],
    target_msg: Any,
    full_text: str,
    words: List[str],
    clean_mode: bool
) -> None:
    """
    @brief Асинхронная фоновая задача: выполняет сжатие текста через Gemma/GigaChat и обновляет сообщение в Telegram.
    @details Не блокирует воркер Сбера, позволяя ему сразу перейти к обработке следующего аудиосообщения.
    """
    user_id = orig.from_user.id if orig.from_user else 0
    username = orig.from_user.username if orig.from_user else None
    logger.info(f"🎙️ [VOICE AI] Запуск фонового сжатия ({len(words)} слов) через пайплайн Gemma 31B/26B -> GigaChat...")

    shortened = await summarize_voice_transcription(
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        raw_text=full_text,
        status_msg=status_msg or orig
    )
    is_valid_shortened = (
        bool(shortened) and 
        shortened.strip() != "" and 
        shortened.strip() != full_text.strip() and 
        "все доступные модели" not in shortened.lower() and 
        "все нейронки легли" not in shortened.lower() and 
        "недоступны" not in shortened.lower()
    )

    safe_full = html.escape(full_text.strip())
    if is_valid_shortened:
        safe_short = html.escape(shortened.strip())
        header = f"<b>Если кратко:</b>\n{safe_short}\n\n<blockquote expandable>\n"
        footer = "\n</blockquote>"
    else:
        # Все круги ИИ не ответили — сырой текст не пропадает, а оформляется скрытой цитатой
        header = "<blockquote expandable>\n"
        footer = "\n</blockquote>"

    # Защита от лимита 4096 символов Telegram: гарантируем, что safe_full с тегами точно помещается в одно сообщение
    max_full_len = 3800 - len(header) - len(footer)
    if len(safe_full) > max_full_len:
        safe_full = safe_full[:max_full_len].rsplit(" ", 1)[0] + "...\n[Текст обрезан по лимиту Telegram]"

    final_output = f"{header}{safe_full}{footer}"

    asyncio.create_task(tracer.queue_trace(chat_id, {
        "event": "sber_speech_transcription",
        "message_id": orig.id,
        "raw_transcription": full_text,
        "final_output": final_output,
        "word_count": len(words)
    }))

    if status_msg and not clean_mode:
        try:
            await status_msg.edit_text(final_output, parse_mode=enums.ParseMode.HTML)
            db.update_message_text(chat_id, status_msg.id, final_output)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отредактировать сообщение ГС после сжатия ({e}). Отправка отдельным...")
            await utils.send_as_phantom(target_msg, final_output, category="VOICE_TRANSCRIPTION", parse_mode=enums.ParseMode.HTML)
    elif not clean_mode:
        await utils.send_as_phantom(target_msg, final_output, category="VOICE_TRANSCRIPTION", parse_mode=enums.ParseMode.HTML)

async def _finalize_sber_transcription(context: VoiceContext) -> None:
    """
    @brief Финализирует накопленные сообщения от Сбер Спич Бота после ультра-быстрой паузы (дебаунс 0.35с).
    @details Сразу же отображает распознанный текст в Telegram и мгновенно освобождает воркер для следующего ГС!
    """
    try:
        await asyncio.sleep(0.35)
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

    if len(words) <= 30:
        # 1. КОРОТКОЕ ГС (<=30 слов): сжатие не требуется, мгновенно выводим сырой текст и завершаем
        if context.status_msg and not clean_mode:
            try:
                await context.status_msg.edit_text(full_text)
                db.update_message_text(chat_id, context.status_msg.id, full_text)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отредактировать статус короткого ГС ({e}): {full_text[:50]}")
                await utils.send_as_phantom(target_msg, full_text, category="VOICE_TRANSCRIPTION")
        else:
            await utils.send_as_phantom(target_msg, full_text, category="VOICE_TRANSCRIPTION")

        asyncio.create_task(tracer.queue_trace(chat_id, {
            "event": "sber_speech_transcription",
            "message_id": orig.id,
            "raw_transcription": full_text,
            "final_output": full_text,
            "word_count": len(words)
        }))

        # Мгновенно освобождаем очередь воркера Сбера
        context.done_event.set()
    else:
        # 2. ДЛИННОЕ ГС (>30 слов): МГНОВЕННО заменяем «Расшифровываю...» на распознанный текст Сбера!
        interim_text = full_text if len(full_text) <= 3800 else full_text[:3800].rsplit(" ", 1)[0] + "..."
        if context.status_msg and not clean_mode:
            try:
                await context.status_msg.edit_text(f"{interim_text}\n\n⏳ Сокращаю...")
                db.update_message_text(chat_id, context.status_msg.id, full_text)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось вывести промежуточный текст ГС ({e}): {full_text[:50]}")
        elif not clean_mode:
            sent_status = await utils.send_as_phantom(target_msg, f"{interim_text}\n\n⏳ Сокращаю...", category="VOICE_TRANSCRIPTION")
            context.status_msg = sent_status

        # МГНОВЕННО освобождаем воркер Сбера! Пошел таймер и обработка следующего ГС в очереди!
        context.done_event.set()

        # А процесс сжатия через Gemma 31B/26B и GigaChat запускаем АСИНХРОННО В ФОНЕ!
        asyncio.create_task(
            _async_summarize_and_update(
                chat_id=chat_id,
                orig=orig,
                status_msg=context.status_msg,
                target_msg=target_msg,
                full_text=full_text,
                words=words,
                clean_mode=clean_mode
            )
        )

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