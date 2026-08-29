import re
import time
import modules.utils as utils
from modules.router import router, EventType

last_lose_time = 0
COOLDOWN_SECONDS = 3600  # 10 минут

@router.on(EventType.TEXT_MESSAGE, priority=5)
async def handle_lose_game_event(ctx):
    if check_lose_condition(ctx.text):
        await utils.send_as_phantom(ctx.message, "Я проиграл")
        return True # Handled
    return False

def check_lose_condition(text):
    """
    Проверяет, есть ли в тексте отдельное 'я' и отдельное 'проиграл'.
    Соблюдает кулдаун.
    """
    global last_lose_time
    current_time = time.time()
    
    if current_time - last_lose_time < COOLDOWN_SECONDS:
        return False

    text_low = text.lower()
    has_ya = re.search(r'\bя\b', text_low)
    has_proigral = re.search(r'\bпроиграл\b', text_low)

    if has_ya and has_proigral:
        last_lose_time = current_time
        return True
    
    return False