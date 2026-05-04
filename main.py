import re, asyncio, logging, signal
from pyrogram import Client, filters

import modules.config as cfg
import modules.database as db
import modules.utils as utils
import modules.actions.sync as sync
import modules.actions.ai_logic as ai_summary
import modules.actions.dialog as ai_dialog
import modules.actions.admin as admin
import modules.actions.lose_game as lose_game
import modules.actions.voice as voice
from modules.actions import gigachat
import random

# Флаг для включения режима особых реакций (меняешь руками на True/False)
ENABLE_EVIL_REACTIONS = True

def is_evil_user(user):
    """Проверяет, является ли пользователь тем самым Ивилом"""
    if not user:
        return False
    
    target_name = "𝓔𝓥𝓲𝓛"
    target_username = "XTRaEViLman"
    
    # Проверка имени (first_name или last_name)
    name_check = False
    if user.first_name and target_name in user.first_name:
        name_check = True
    if user.last_name and target_name in user.last_name:
        name_check = True
        
    # Проверка тега (username) без учета регистра и @
    username_check = False
    if user.username and user.username.lower() == target_username.lower():
        username_check = True
    logger.info(f"Evil factor:{name_check or username_check}")
        
    return name_check or username_check


voice_lock = asyncio.Lock()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

app = Client(
    "tech_phantom_session",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    ipv6=False,
    sleep_threshold=20,
    workers=4,
)

shutdown_event = asyncio.Event()


# 1. Ловим ГС в группе
@app.on_message(filters.chat(cfg.TARGET_CHAT_ID) & (filters.voice | filters.audio))
async def voice_handler(client, message):
    async with voice_lock:
        voice.intro_sent = False # <--- СБРОС ФЛАГА ТУТ
        voice.pending_original_msg = message
        voice.sber_ack_id = None
        voice.processing_done.clear()
        
        await message.forward(cfg.SBER_BOT)
        
        # Ждем завершения (Event установится в voice.py)
        try:
            await asyncio.wait_for(voice.processing_done.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
        finally:
            voice.pending_original_msg = None

# 2. Новые сообщения от Сбера (Статус или продолжение текста)
@app.on_message(filters.chat(cfg.SBER_BOT))
async def sber_msg_handler(client, message):
    await voice.handle_sber_message(client, message)

# 3. Редактирование сообщения Сбером (Сама транскрипция)
@app.on_edited_message(filters.chat(cfg.SBER_BOT))
async def sber_edit_handler(client, message):
    await voice.handle_sber_edit(client, message)

# Хендлер для Гигачата
@app.on_message(filters.chat("gigachat_bot"))
async def gigachat_handler(client, message):
    await gigachat.handle_giga_response(message)

@app.on_edited_message(filters.chat("gigachat_bot"))
async def gigachat_edit_handler(client, message):
    await gigachat.handle_giga_response(message)

@app.on_message(filters.chat(cfg.TARGET_CHAT_ID) & filters.text)
async def main_handler(client, message):
    text, user = message.text.strip(), message.from_user
    username, is_me = (user.username if user else None), (user and (user.username == cfg.MY_USERNAME or user.is_self))
    m_data = await utils.format_msg(message)
    if not m_data: return

    # 1. СИНХРОНИЗАЦИЯ
    if sync.current_state == sync.STATE_WAITING_SYNC:
        if is_me and text.lower() in ["да", "нет"]:
            if text.lower() == "нет":
                db.clear_db()
                for m in sync.temp_buffer: db.save_message(*m)
                sync.temp_buffer, sync.current_state = [], sync.STATE_NORMAL
                await utils.send_as_phantom(message, "База очищена. Пишу с нуля.")
            else:
                await message.reply_text("Синхронизирую...")
                await sync.run_sync(client, message)
            return
        sync.temp_buffer.append(m_data); return

    db.save_message(*m_data)

    # 2. КОМАНДЫ И ИИ
    if is_me and (dm := re.search(cfg.DUMP_PATTERN, text)):
        await admin.do_dump(message, dm.group(1))
    elif re.search(cfg.HELP_PATTERN, text.lower()):
        await utils.send_as_phantom(message, f"Йо, {user.first_name}! \n {cfg.HELP_MESSAGE}")
    elif re.search(cfg.SUMMARY_PATTERN, text.lower()):
        status = await message.reply_text("Разбираюсь...")
        res = await ai_summary.get_chat_summary(db.get_history_from_db(100), cfg.USER_API_KEYS.get(username), user.id, username, status_msg=status)
        await utils.send_as_phantom(message, f"**Нарыл:**\n\n{res}", edit_message=status)
    elif "@tech_phantom" in text.lower() or (message.reply_to_message and message.reply_to_message.from_user.is_self and re.search(cfg.PHANTOM_NAMES_PATTERN, text.lower())):
        await ai_dialog.handle_dialog(message, text, username, user.id)

    # 3. ИГРЫ И РЕАКЦИИ
    # Логика случайных реакций для Ивила
    if ENABLE_EVIL_REACTIONS and is_evil_user(message.from_user):
        rand_val = random.random() # Генерирует число от 0.0 до 1.0
        logger.info(f"Random faactor:{rand_val}")
        # 1/20 это 0.05
        if rand_val < 0.05:
            await client.send_reaction(message.chat.id, message.id, "💋")
        # 1/5 это 0.2
        elif rand_val < 0.2:
            await client.send_reaction(message.chat.id, message.id, "🏆")
            
    elif lose_game.check_lose_condition(text):
        await utils.send_as_phantom(message, "Я проиграл")
    elif "лоб" in text.lower():
        # Если это Ивил — просто выходим из этого блока (скипаем)
        if is_evil_user(message.from_user):
            return # или pass, если ниже есть другой код
        # Обычная логика для остальных
        if re.search(cfg.PHANTOM_NAMES_PATTERN, text):
            await utils.send_as_phantom(message, f"Лоб, {user.first_name} )")
        else:
            await client.send_reaction(message.chat.id, message.id, "💋")

    elif re.search(cfg.YO_PATTERN, text):
        await utils.send_as_phantom(message, "Рад видеть, Nikitos" if is_me else f"Йоо, {user.first_name}!")

async def main_loop():
    while not shutdown_event.is_set():
        try:
            logger.info("Запуск сессии...")
            await app.start()
            sync.current_state, sync.temp_buffer = sync.STATE_WAITING_SYNC, []
            try: await app.send_message(cfg.TARGET_CHAT_ID, "Снова в сети. Nikitos, читать историю?")
            except Exception as e: 
                logger.error(f"НЕ УДАЛОСЬ отправить сообщение в чат: {e}")

            while not shutdown_event.is_set():
                if not app.is_connected: raise ConnectionError("Протухший сокет detected")
                await asyncio.sleep(5)
        except (OSError, ConnectionError) as e:
            logger.error(f"Сетевая ошибка: {e}. Реконнект через 10с..."); await app.stop(); await asyncio.sleep(10)
        except Exception as e:
            logger.exception(f"Непредвиденный краш: {e}"); await asyncio.sleep(5)

    logger.info("Выход из цикла...")
    try: 
        await app.send_message(cfg.TARGET_CHAT_ID, "Завершаю работу.... Всем пока")
        await app.stop()
    except: pass

if __name__ == "__main__":
    db.init_db()
    loop = asyncio.get_event_loop()
    for s in (signal.SIGINT, signal.SIGTERM): loop.add_signal_handler(s, lambda: shutdown_event.set())
    try: loop.run_until_complete(main_loop())
    except KeyboardInterrupt: pass