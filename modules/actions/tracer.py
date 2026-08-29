"""
@file tracer.py
@brief Модуль трассировки и отправки JSON логов взаимодействия с нейросетями в ЛС Никитосу (@techno_c_a_t).
@details Перехватывает запросы/ответы ИИ, Салют/Сбер Спич Бота и дампы, форматирует в JSON,
         гарантированно режет монолитные строки и отправляет с троттлингом (0.7с).
"""

import json
import asyncio
import datetime
import logging
from typing import Dict, Any, List, Optional
import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.router import router, EventType, EventContext

logger = logging.getLogger(__name__)

## @brief Асинхронная очередь сообщений трассировки для безопасной отправки в ЛС без бана за спам
trace_queue: asyncio.Queue = asyncio.Queue()

def format_json_chunks(data_dict: Dict[str, Any], max_chunk_size: int = 3000) -> List[str]:
    """
    @brief Преобразует словарь данных в красиво отформатированный JSON и безопасно разбивает на части.
    @details Даже если внутри JSON длинная монолитная строка (промпт на 10к символов без переноса строк),
             метод гарантирует, что ни один чанк не превысит Telegram-лимит 4096 символов.
    @param data_dict Словарь с данными для сериализации.
    @param max_chunk_size Максимальная длина чистого текста одного блока (по умолчанию 3000).
    @return Список отформатированных строк в тройных кавычках ```json ... ```.
    """
    json_str = json.dumps(data_dict, ensure_ascii=False, indent=2)
    
    if len(json_str) <= max_chunk_size:
        return [f"```json\n{json_str}\n```"]

    raw_chunks: List[str] = []
    lines = json_str.split("\n")
    current_chunk = ""

    for line in lines:
        if len(line) > max_chunk_size:
            if current_chunk:
                raw_chunks.append(current_chunk)
                current_chunk = ""
            for i in range(0, len(line), max_chunk_size):
                raw_chunks.append(line[i:i + max_chunk_size])
            continue

        if len(current_chunk) + len(line) + 1 > max_chunk_size:
            if current_chunk:
                raw_chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk = f"{current_chunk}\n{line}" if current_chunk else line

    if current_chunk:
        raw_chunks.append(current_chunk)

    total_chunks = len(raw_chunks)
    formatted_chunks: List[str] = []
    for i, chunk in enumerate(raw_chunks, 1):
        formatted_chunks.append(f"```json\n// [Чанк {i}/{total_chunks}]\n{chunk}\n```")

    return formatted_chunks

async def queue_trace(chat_id: int, data_dict: Dict[str, Any]) -> None:
    """
    @brief Добавляет событие трассировки в очередь отправки, если для данного чата включена трассировка.
    @param chat_id ID чата.
    @param data_dict Словарь с информацией для трассировки.
    """
    if not db.get_chat_trace_mode(chat_id):
        return

    data_dict["timestamp"] = datetime.datetime.now().isoformat()
    data_dict["chat_id"] = chat_id

    formatted_msgs = format_json_chunks(data_dict)
    for msg_text in formatted_msgs:
        await trace_queue.put(msg_text)

async def trace_worker_loop(client: Any) -> None:
    """
    @brief Бесконечный фоновый воркер: извлекает сообщения из trace_queue и отправляет Никитосу (@techno_c_a_t) в ЛС с паузой 0.7с.
    @param client Объект Pyrogram Client.
    """
    logger.info(f"Запущен фоновый воркер трассировки в ЛС Никитосу (@{cfg.MY_USERNAME})...")
    while True:
        try:
            msg_text = await trace_queue.get()
            try:
                # Отправляем сообщение строго в ЛС Никитосу по юзернейму
                await client.send_message(cfg.MY_USERNAME, msg_text)
            except Exception as e:
                # Резервная попытка отправки через "me" при сбое резолва юзернейма
                try:
                    await client.send_message("me", msg_text)
                except Exception as inner_e:
                    logger.error(f"Ошибка при отправке трассировочного JSON в ЛС: {e} | {inner_e}")
            finally:
                trace_queue.task_done()
                await asyncio.sleep(0.7) # Пауза против спам-бана Telegram
        except Exception as e:
            logger.exception(f"Ошибка воркера трассировки: {e}")
            await asyncio.sleep(1)

# --- АДМИН-КОМАНДЫ ВКЛЮЧЕНИЯ/ВЫКЛЮЧЕНИЯ ТРАССИРОВКИ ---

@router.on(EventType.COMMAND, pattern=r"(?i)^фантом,?\s*(включи трассировку|выключи трассировку|трассировка\s+(вкл|выкл))", admin_only=True, priority=20)
async def handle_trace_toggle_command(ctx: EventContext) -> None:
    """
    @brief Команда переключения режима трассировки логов в ЛС.
    @param ctx Контекст события EventContext.
    """
    text_low = ctx.text.lower()
    enable = "включи" in text_low or "вкл" in text_low
    db.set_chat_trace_mode(ctx.chat_id, enable)

    state_str = f"ВКЛЮЧЕНА 🟢. Логи высылаются в ЛС @{cfg.MY_USERNAME}." if enable else "ВЫКЛЮЧЕНА 🔴."
    await utils.send_as_phantom(ctx.message, f"Трассировка логов в ЛС {state_str}")
