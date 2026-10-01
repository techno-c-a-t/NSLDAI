"""
@file inspect_incoming_quote.py
@brief Полный трассировщик входящих сообщений и сырых MTProto-обновлений в Pyrogram.
       Выводит ВСЮ информацию (текст, подпись, raw updates, entities, байты) без купюр.

Запуск:
    python scripts/inspect_incoming_quote.py
"""

import sys
import os
import shutil
import asyncio
import logging
import sqlite3

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from hydrogram import Client, filters
import modules.config as cfg

# Отключаем лишний шум библиотек, но оставляем важные логи
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("quote_inspector")

def resolve_test_session() -> str:
    candidates = [
        os.path.join(ROOT_DIR, "phantom_userbot.session"),
        os.path.join(ROOT_DIR, "data", "phantom_userbot.session"),
        os.path.join(ROOT_DIR, "tech_phantom_session.session"),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            try:
                conn = sqlite3.connect(cand, timeout=1)
                conn.execute("SELECT 1 FROM sessions LIMIT 1")
                conn.close()
                temp_base = os.path.join(ROOT_DIR, "temp_inspect_session")
                shutil.copy2(cand, f"{temp_base}.session")
                return temp_base
            except Exception:
                pass
    raise RuntimeError("Не удалось найти доступную сессию!")

def cleanup(base: str):
    for ext in [".session", ".session-journal", ".session-shm", ".session-wal"]:
        f = base + ext
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

async def main():
    temp_base = resolve_test_session()
    app = Client(
        temp_base,
        api_id=cfg.API_ID,
        api_hash=cfg.API_HASH,
        bot_token=cfg.BOT_TOKEN if cfg.BOT_TOKEN else None
    )

    print("=" * 70)
    print("🔍 ФУЛЛ-ТРАССИРОВЩИК ВХОДЯЩИХ MTPROTO ОБНОВЛЕНИЙ")
    print(f"Отправь любое сообщение в ЛС Фантому (со свернутой цитатой)!")
    print("Скрипт НЕ завершается после 1 сообщения, ждет пока не нажмешь Ctrl+C.")
    print("=" * 70 + "\n")

    # 1. Перехват СЫРЫХ обновлений MTProto прямо из сетевого сокета
    @app.on_raw_update()
    async def raw_update_handler(client, update, users, chats):
        up_name = type(update).__name__
        # Фильтруем технический спам (статусы онлайна, тайпинги)
        if up_name in ["UpdateUserStatus", "UpdateChannelMessageViews"]:
            return

        print("\n" + "#" * 60)
        print(f"⚡ [RAW MTPROTO UPDATE] Тип: {up_name}")
        print(f"Сырой объект:\n{update}")
        
        # Если в обновлении есть сообщение
        msg_obj = getattr(update, "message", None)
        if msg_obj:
            print("\n📦 [RAW MESSAGE DETAILS]:")
            print(f"  message_id: {getattr(msg_obj, 'id', None)}")
            print(f"  raw text: {repr(getattr(msg_obj, 'message', None))}")
            raw_entities = getattr(msg_obj, "entities", None)
            print(f"  raw entities count: {len(raw_entities) if raw_entities else 0}")
            if raw_entities:
                for idx, re_entity in enumerate(raw_entities, 1):
                    print(f"    -> [{idx}] {type(re_entity).__name__} (ID: {hex(getattr(re_entity, 'ID', 0))}): {re_entity}")
        print("#" * 60 + "\n")

    # 2. Перехват распарсенного объекта Message от Pyrogram
    @app.on_message()
    async def parsed_message_handler(client, message):
        print("\n" + "=" * 60)
        print("📨 [PARSED PYROGRAM MESSAGE]")
        print(f"ID сообщения: {message.id}")
        print(f"От кого (from_user): {message.from_user.id if message.from_user else None} (@{getattr(message.from_user, 'username', '')})")
        print(f"Чат (chat): {message.chat.id} ({message.chat.type})")
        print(f"Текст (text): {repr(message.text)}")
        print(f"Подпись (caption): {repr(message.caption)}")
        print(f"Сущности текста (entities): {message.entities}")
        print(f"Сущности подписи (caption_entities): {message.caption_entities}")
        
        # Проверяем все атрибуты сообщения
        for attr in ["media", "document", "photo", "voice", "service"]:
            val = getattr(message, attr, None)
            if val:
                print(f"Свойство {attr}: {val}")

        print("=" * 60 + "\n")

    try:
        async with app:
            logger.info("📡 Сессия подключена. Жду сообщения в Telegram (Ctrl+C для выхода)...")
            # Бесконечное ожидание до Ctrl+C
            while True:
                await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\nОстановка трассировщика...")
    finally:
        cleanup(temp_base)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
