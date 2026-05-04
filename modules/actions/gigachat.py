import asyncio
import modules.config as cfg

giga_event = asyncio.Event()
giga_response = None
target_user = None

async def handle_giga_response(message):
    global giga_response
    text = message.text or ""
    # Пропускаем техническое сообщение
    if "Запрос принят" in text or "готовлю ответ" in text:
        return
    
    giga_response = text
    giga_event.set()