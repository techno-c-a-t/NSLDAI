import asyncio
import modules.utils as utils

pending_original_msg = None
sber_ack_id = None
processing_done = asyncio.Event()
intro_sent = False # Флаг очередности

def is_sber_error(text):
    """Детект специфичных ошибок Сбера"""
    t = text.lower()
    # Ошибка размера
    if "слишком большое аудио" in t or ("большое" in t and "8mb" in t):
        return "limit"
    # Ошибка формата
    if "данный тип файла не поддерживается" in t:
        return "format"
    return None

async def handle_sber_message(client, message):
    global sber_ack_id, pending_original_msg, intro_sent
    text = message.text or ""

    # 1. Сбер принял файл
    if "аудиосообщение принято" in text.lower():
        sber_ack_id = message.id
        return

    # 2. Если это не статус, проверяем на ошибку (иногда Сбер шлет ошибку НОВЫМ сообщением)
    error_type = is_sber_error(text)
    if error_type and pending_original_msg:
        if error_type == "limit":
            await utils.send_as_phantom(pending_original_msg, "Сорян, много текста, послушать не смогу, долго. Скинь че поменьше (до 8мб)")
        else:
            await utils.send_as_phantom(pending_original_msg, "Жаль, что формат не mp3, я не умею такое слушать")
        processing_done.set()
        return

    # 3. Доп. сообщения (транскрипция) - копируем только если это НЕ ошибка
    if pending_original_msg and not "принято" in text.lower():
        counter = 0
        while not intro_sent and counter < 50: # Ждем до 5 сек
            await asyncio.sleep(0.1)
            counter += 1
            
        await message.copy(pending_original_msg.chat.id, reply_to_message_id=pending_original_msg.id)

async def handle_sber_edit(client, message):
    global sber_ack_id, pending_original_msg, intro_sent
    if not sber_ack_id or message.id != sber_ack_id: return
    
    text = message.text or ""
    
    # Сначала проверяем на ошибку
    error_type = is_sber_error(text)
    if error_type and pending_original_msg:
        if error_type == "limit":
            await utils.send_as_phantom(pending_original_msg, "Сорян, много текста, послушать не смогу, долго. Скинь че поменьше (до 8мб)")
        else:
            await utils.send_as_phantom(pending_original_msg, "Жаль, что формат не mp3, я не умею такое слушать")
        processing_done.set()
        return

    # Если это не ошибка и не статус "принято", значит это пришла транскрипция
    if pending_original_msg and "принято" not in text.lower():
        # Сначала заголовок
        await utils.send_as_phantom(pending_original_msg, "Послушал твое, перепишу его сюда:")
        # Сразу копируем 1-ю часть
        await message.copy(pending_original_msg.chat.id, reply_to_message_id=pending_original_msg.id)
        
        # Разрешаем остальным частям отправляться
        intro_sent = True 
        
        await asyncio.sleep(3) 
        processing_done.set()