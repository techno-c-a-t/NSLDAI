import asyncio
from pyrogram import Client
import modules.config as cfg

# Настройки
TARGET = -1003036875599
WIDTH_EMOJIS = 6
HEIGHT = 6
COLS_PER_EMOJI = 4
TOTAL_COLS = WIDTH_EMOJIS * COLS_PER_EMOJI

# Карта состояний: переводим 4 бита (колонки) в нужную луну
# 1 - свет, 0 - тень
MOON_MAP = {
    (0, 0, 0, 0): "🌑",
    (0, 0, 0, 1): "🌒",
    (0, 0, 1, 1): "🌓",
    (0, 1, 1, 1): "🌔",
    (1, 1, 1, 1): "🌕",
    (1, 1, 1, 0): "🌖",
    
    (1, 1, 0, 0): "🌗",
    (1, 0, 0, 0): "🌘",
}

def get_moon_emoji(cell_index, light_pos):
    """
    cell_index: индекс эмодзи в строке (0-5)
    light_pos: текущая позиция начала светового пятна (0 - TOTAL_COLS)
    """
    # Границы колонок для текущего эмодзи
    cell_start = cell_index * COLS_PER_EMOJI
    
    # Световое пятно имеет ширину 4 колонки
    light_range = range(light_pos, light_pos + 4)
    
    # Проверяем каждую из 4-х колонок этого эмодзи: попадает ли она в зону света
    bits = []
    for col in range(cell_start, cell_start + 4):
        # Используем остаток от деления для цикличного движения
        if col % TOTAL_COLS in [p % TOTAL_COLS for p in light_range]:
            bits.append(1)
        else:
            bits.append(0)
    
    return MOON_MAP.get(tuple(bits), "🌑")

def generate_frame(step):
    """Генерирует матрицу 6x6 для текущего шага анимации"""
    grid = []
    for y in range(HEIGHT):
        row = []
        # Добавляем смещение для каждой строки, чтобы волна шла по диагонали
        # Если хочешь строго горизонтально - убери '+ y*2'
        row_offset = (step + y * 2) % TOTAL_COLS
        
        for x in range(WIDTH_EMOJIS):
            row.append(get_moon_emoji(x, row_offset))
        grid.append("".join(row))
    return "\n".join(grid)

async def main():
    app = Client(
    "tech_phantom_session",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    ipv6=False,
    sleep_threshold=20,
    workers=4,
    )
    
    async with app:
        print("Запуск потоковой луны...")
        
        # Отправляем первое сообщение
        frame_text = generate_frame(0)
        msg = await app.send_message(TARGET, f"\n{frame_text}\n")
        
        # Цикл анимации
        step = 0
        while True:
            step += 1
            frame_text = generate_frame(step)
            
            try:
                await msg.edit_text(f"\n{frame_text}\n")
                # Пауза 0.5-0.8 сек, чтобы Telegram не забанил за частые обновления
                await asyncio.sleep(0.2)
            except Exception as e:
                print(f"Лимит или ошибка: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
