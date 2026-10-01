"""
@file test_collapsed_quote.py
@brief Тестовый скрипт для отправки свернутых цитат через Hydrogram (Layer 181).
Запуск:
    python scripts/test_collapsed_quote.py
"""

import sys
import os
import shutil
import asyncio
import logging
import sqlite3

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from hydrogram import Client, enums, raw
import modules.config as cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("quote_tester")

SAMPLE_TEXT = (
    "Строка 1: Это полный текст голосового сообщения, спрятанный в цитату.\n"
    "Строка 2: В нем подробно описываются детали разговора и нюансы задачи.\n"
    "Строка 3: Telegram сворачивает этот блок под стрелочку 'Показать полностью'.\n"
    "Строка 4: Нажми на блок, чтобы он плавно раскрылся на весь экран.\n"
    "Строка 5: Завершающая строка длинного голосового сообщения."
)

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
                temp_base = os.path.join(ROOT_DIR, "temp_test_session")
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
    print("=" * 60)
    print("🚀 ОТПРАВКА СВЕРНУТЫХ ЦИТАТ ЧЕРЕЗ HYDROGRAM (LAYER 181)")
    print(f"🎯 Адресат: @{cfg.MY_USERNAME} (ID: {cfg.MY_USER_ID})")
    print("=" * 60)

    temp_base = None
    try:
        temp_base = resolve_test_session()

        app = Client(
            temp_base,
            api_id=cfg.API_ID,
            api_hash=cfg.API_HASH,
            bot_token=cfg.BOT_TOKEN if cfg.BOT_TOKEN else None
        )

        async with app:
            target_username = cfg.MY_USERNAME.lstrip("@")
            logger.info(f"🔍 Резолв пользователя @{target_username}...")
            user = await app.get_users(target_username)
            target = user.id
            logger.info(f"✅ Пользователь найден: {user.first_name} (ID: {target})\n")

            # 1. Тест через HTML <blockquote expandable>
            print("1. Отправка через HTML <blockquote expandable>...")
            html_text = (
                "<b>Тест 1 (HTML &lt;blockquote expandable&gt;):</b>\n"
                "Если кратко: <i>Проверяем свернутую цитату</i>\n\n"
                f"<blockquote expandable>\n{SAMPLE_TEXT}\n</blockquote>"
            )
            msg1 = await app.send_message(chat_id=target, text=html_text, parse_mode=enums.ParseMode.HTML)
            logger.info(f"✅ [Тест 1] Отправлено! ID: {msg1.id}")
            await asyncio.sleep(1)

            # 2. Тест через Raw MTProto MessageEntityBlockquote(collapsed=True)
            print("\n2. Отправка через Raw MessageEntityBlockquote(collapsed=True)...")
            header = "<b>Тест 2 (Raw MTProto collapsed=True):</b>\nЕсли кратко: <i>Напрямую через сырую сущность</i>\n\n"
            full_raw_text = "Тест 2 (Raw MTProto collapsed=True):\nЕсли кратко: Напрямую через сырую сущность\n\n" + SAMPLE_TEXT
            offset = len("Тест 2 (Raw MTProto collapsed=True):\nЕсли кратко: Напрямую через сырую сущность\n\n".encode('utf-16-le')) // 2
            length = len(SAMPLE_TEXT.encode('utf-16-le')) // 2

            raw_entity = raw.types.MessageEntityBlockquote(offset=offset, length=length, collapsed=True)
            peer = await app.resolve_peer(target)
            await app.invoke(
                raw.functions.messages.SendMessage(
                    peer=peer,
                    message=full_raw_text,
                    random_id=app.rnd_id(),
                    entities=[raw_entity]
                )
            )
            logger.info(f"✅ [Тест 2] Отправлено через raw MTProto!")

            print("\n" + "=" * 60)
            print("🎉 Проверь Telegram! Оба сообщения должны быть со стрелочкой сворачивания!")
            print("=" * 60 + "\n")

    finally:
        if temp_base:
            cleanup(temp_base)

if __name__ == "__main__":
    asyncio.run(main())
