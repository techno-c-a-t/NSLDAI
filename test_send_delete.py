import asyncio
import time
from pyrogram import Client, errors
import modules.config as cfg

# Настройки
TARGET = -1003036875599 
WIDTH_EMOJIS = 6
HEIGHT = 6
COLS_PER_EMOJI = 4
TOTAL_COLS = WIDTH_EMOJIS * COLS_PER_EMOJI

# Карта лун
MOON_MAP = {
    (0, 0, 0, 0): "🌑", (0, 0, 0, 1): "🌒", (0, 0, 1, 1): "🌓", (0, 1, 1, 1): "🌔",
    (1, 1, 1, 1): "🌕", (1, 1, 1, 0): "🌖", (1, 1, 0, 0): "🌗", (1, 0, 0, 0): "🌘",
}

def get_moon_emoji(cell_index, light_pos):
    cell_start = cell_index * COLS_PER_EMOJI
    light_range = range(light_pos, light_pos + 4)
    bits = []
    for col in range(cell_start, cell_start + 4):
        if col % TOTAL_COLS in [p % TOTAL_COLS for p in light_range]:
            bits.append(1)
        else:
            bits.append(0)
    return MOON_MAP.get(tuple(bits), "🌑")

def generate_frame(step):
    grid = []
    for y in range(HEIGHT):
        row_offset = (step + y * 2) % TOTAL_COLS
        row = [get_moon_emoji(x, row_offset) for x in range(WIDTH_EMOJIS)]
        grid.append("".join(row))
    return "\n".join(grid)

async def main():
    # Используем существующую сессию
    app = Client(
    "tech_phantom_session",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    ipv6=False,
    sleep_threshold=20,
    workers=4,
    ) 
    
    async with app:
        print("Запуск теста 'Удалить + Отправить'...")
        
        step = 0
        last_msg = None
        timestamps = []
        
        # С отправкой новых сообщений даже 1.0 сек может быть мало
        DELAY = 1.2 

        while True:
            try:
                step += 1
                moon_grid = generate_frame(step)
                
                # Замеряем время
                current_time = time.perf_counter()
                timestamps.append(current_time)
                if len(timestamps) > 10: timestamps.pop(0)
                real_hz = (len(timestamps)-1)/(timestamps[-1]-timestamps[0]) if len(timestamps)>1 else 0

                text = f"```\n{moon_grid}\n```\n**Метод:** `Delete + Send`\n**Speed:** `{real_hz:.2f} Hz`"

                # 1. Удаляем старое (если есть)
                if last_msg:
                    await last_msg.delete()
                
                # 2. Отправляем новое
                last_msg = await app.send_message(TARGET, text, disable_notification=True)

                await asyncio.sleep(DELAY)

            except errors.FloodWait as e:
                print(f"⚠️ Жёсткий бан на {e.value} сек. Останавливаемся.")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"Ошибка: {e}")
                await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())