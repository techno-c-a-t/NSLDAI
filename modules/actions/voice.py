import asyncio
import modules.utils as utils
import modules.config as cfg
from modules.ai_service import call_ai

# Глобальные переменные для отслеживания состояния (в рамках одной сессии)
pending_original_msg = None
sber_ack_id = None
processing_done = asyncio.Event()
intro_sent = False 

def is_sber_error(text):
    """Детект специфичных ошибок Сбера"""
    t = text.lower()
    if "слишком большое аудио" in t or ("большое" in t and "8mb" in t):
        return "limit"
    if "данный тип файла не поддерживается" in t:
        return "format"
    return None

async def validate_transcription(text, user_id, username, user_api_key):
    """
    Отправляет текст в ИИ, чтобы понять, мусор это или реальная речь.
    Возвращает True (хороший текст) или False (мусор).
    """
    if not text or len(text.strip()) < 3:
        return False

    system_prompt = "Ты — фильтр качества распознавания речи. Твоя задача: определить, является ли текст осмысленной фразой или это 'галлюцинация' ИИ (шум, тишина, системные сообщения)."
    user_prompt = (
        f"Проанализируй текст расшифровки: '{text}'\n\n"
        "Является ли это связной речью? "
        "Ответь только одним словом: YES если это осмысленное сообщение, и NO если это мусор, тишина или ошибка распознавания."
    )

    try:
        # Используем твою обертку call_ai
        res = await call_ai(user_id, username, user_api_key, system_prompt, user_prompt, model = cfg.MODEL_FREE)
        return "YES" in res.upper()
    except Exception as e:
        print(f"Ошибка при валидации текста: {e}")
        return True # В случае ошибки ИИ пропускаем сообщение на всякий случай

async def handle_sber_message(client, message):
    global sber_ack_id, pending_original_msg, intro_sent
    text = message.text or ""

    # 1. Сбер принял файл
    if "аудиосообщение принято" in text.lower():
        sber_ack_id = message.id
        return

    # 2. Если Сбер прислал новое сообщение с ошибкой
    error_type = is_sber_error(text)
    if error_type and pending_original_msg:
        processing_done.set()
        return

    # 3. Доп. сообщения (если расшифровка разбита на несколько мессаджей)
    if pending_original_msg and not "принято" in text.lower():
        # Ждем, пока основное (отредактированное) сообщение пройдет проверку ИИ и отправит заголовок
        counter = 0
        while not intro_sent and counter < 50: 
            await asyncio.sleep(0.1)
            counter += 1
        
        if intro_sent:
            await message.copy(pending_original_msg.chat.id, reply_to_message_id=pending_original_msg.id)

async def handle_sber_edit(client, message):
    global sber_ack_id, pending_original_msg, intro_sent
    if not sber_ack_id or message.id != sber_ack_id: return
    
    text = message.text or ""
    
    # 1. Сначала проверяем на технические ошибки в тексте (edit)
    error_type = is_sber_error(text)
    if error_type and pending_original_msg:
        processing_done.set()
        return

    # 2. Если пришла транскрипция (текст изменился с "принято" на что-то другое)
    if pending_original_msg and "принято" not in text.lower():
        
        # --- ПОЛУЧАЕМ ДАННЫЕ ДЛЯ AI ---
        user_id = pending_original_msg.from_user.id
        username = pending_original_msg.from_user.username
        # Предполагаем, что ключ лежит в конфиге или получен ранее
        user_api_key = getattr(cfg, "GEMINI_KEY", None) 

        # --- ПРОВЕРКА ЧЕРЕЗ GEMINI ---
        is_valid = await validate_transcription(text, user_id, username, user_api_key)
        
        if not is_valid:
            # Если ИИ сказал NO, просто завершаем процесс, ничего не пересылая
            processing_done.set()
            return

        # --- ЕСЛИ ТЕКСТ ВАЛИДЕН ---
        # Отправляем фразу-вступление        
        # Копируем само сообщение
        await message.copy(pending_original_msg.chat.id, reply_to_message_id=pending_original_msg.id)
        
        # Разрешаем досылать остальные куски (если есть)
        intro_sent = True 
        
        await asyncio.sleep(2) 
        processing_done.set()