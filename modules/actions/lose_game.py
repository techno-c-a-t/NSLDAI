import re
import time

# Переменная для хранения времени последнего срабатывания (в памяти)
last_lose_time = 0
COOLDOWN_SECONDS = 600  # 10 минут

def check_lose_condition(text):
    """
    Проверяет, есть ли в тексте отдельное 'я' и отдельное 'проиграл'.
    Соблюдает кулдаун 10 минут.
    """
    global last_lose_time
    
    current_time = time.time()
    
    # 1. Проверяем кулдаун первым делом, чтобы не тратить ресурсы на регексы
    if current_time - last_lose_time < COOLDOWN_SECONDS:
        return False

    # 2. Ловеркейсим текст
    text_low = text.lower()

    # 3. Регулярные выражения для поиска ОТДЕЛЬНЫХ слов
    # \b — это граница слова (пробел, начало строки, пунктуация)
    has_ya = re.search(r'\bя\b', text_low)
    has_proigral = re.search(r'\bпроиграл\b', text_low)

    if has_ya and has_proigral:
        # Обновляем время последнего срабатывания
        last_lose_time = current_time
        return True
    
    return False