import re
import time
from typing import Dict
import modules.utils as utils
from modules.router import router, EventType

last_lose_times: Dict[int, float] = {}
COOLDOWN_SECONDS = 3600  # 1 час

@router.on(EventType.TEXT_MESSAGE, priority=5)
async def handle_lose_game_event(ctx):
    if check_lose_condition(ctx.text, chat_id=ctx.chat_id):
        await utils.send_as_phantom(ctx.message, "Я проиграл")
        return True # Handled
    return False

def check_lose_condition(text: str, chat_id: int = 0) -> bool:
    """
    Проверяет, есть ли в тексте отдельное 'я' и отдельное 'проиграл'.
    Соблюдает кулдаун по каждому чату отдельно.
    """
    current_time = time.time()
    last_time = last_lose_times.get(chat_id, 0.0)
    
    if current_time - last_time < COOLDOWN_SECONDS:
        return False

    text_low = text.lower()
    has_ya = re.search(r'\bя\b', text_low)
    has_proigral = re.search(r'\bпроиграл\b', text_low)

    if has_ya and has_proigral:
        last_lose_times[chat_id] = current_time
        return True
    
    return False