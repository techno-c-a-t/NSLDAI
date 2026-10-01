#!/usr/bin/env python3
"""
@file migrate_dossiers.py
@brief Скрипт ручной миграции и очистки досье пользователей в базе данных SQLite.
@details Извлекает псевдонимы (алиасы), ошибочно попавшие в колонку dossier_text,
         и переносит их в отдельную колонку aliases таблицы user_dossiers.
"""

import sys
import os
import shutil
import sqlite3
import re
import argparse
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="Сборщик и мигратор псевдонимов в таблице user_dossiers.")
    parser.add_argument("--db", default="database.db", help="Путь к файлу базы данных SQLite (по умолчанию database.db)")
    parser.add_argument("--apply", action="store_true", help="Применить изменения в базе данных (по умолчанию только сухой прогон)")
    return parser.parse_args()

def clean_alias(alias: str) -> str:
    alias = re.sub(r"(?i)^(также|псевдонимы|имена|клички)[:\s]*", "", alias).strip()
    alias = alias.strip(";").strip()
    return alias


def is_alias_line(line: str, current_aliases: list) -> tuple:
    l = line.strip()
    if not l:
        return False, []
    # 1. Строки с разделителем ';'
    if ";" in l:
        raw = re.sub(r"(?i)^[-*]?\s*(также|псевдонимы|имена|клички)[:\s]*", "", l).lstrip("-* ").strip()
        names = [clean_alias(n) for n in raw.split(";") if clean_alias(n)]
        return True, names
    # 2. Ключевые слова 'также:', 'псевдонимы:', 'имена:'
    if re.match(r"(?i)^[-*]?\s*(также|псевдонимы|имена|клички)[:\s]*", l):
        raw = re.sub(r"(?i)^[-*]?\s*(также|псевдонимы|имена|клички)[:\s]*", "", l).strip()
        names = [clean_alias(n) for n in raw.split(";") if clean_alias(n)]
        return True, names
    # 3. Маркированная строка с одним из ранее известных алиасов (артефакт append_user_dossier, напр. '- Даня')
    m = re.match(r"^[-*]\s*([A-Za-zА-Яа-яЁё0-9_\s]{1,30})$", l)
    if m:
        candidate = m.group(1).strip()
        if len(candidate.split()) <= 3 and not any(p in candidate for p in [".", "!", "?", ":", ","]):
            if any(candidate.lower() == a.lower() for a in current_aliases):
                return True, [candidate]
    return False, []

def migrate():
    args = parse_args()
    db_path = args.db

    if not os.path.exists(db_path):
        print(f"❌ Ошибка: Файл базы данных '{db_path}' не найден!")
        sys.exit(1)

    print(f"🔍 Анализ досье в базе: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Проверяем наличие колонки aliases
    cur.execute("PRAGMA table_info(user_dossiers)")
    cols = [row[1] for row in cur.fetchall()]
    if "aliases" not in cols:
        print("ℹ️ Колонка 'aliases' отсутствует. Добавляю колонку...")
        if args.apply:
            cur.execute("ALTER TABLE user_dossiers ADD COLUMN aliases TEXT DEFAULT ''")
            conn.commit()

    cur.execute("SELECT chat_id, user_id, username, aliases, dossier_text FROM user_dossiers")
    rows = cur.fetchall()

    changes = []

    for chat_id, user_id, username, aliases, dos_text in rows:
        if not dos_text:
            continue

        existing_aliases = [clean_alias(a) for a in (aliases or "").split(";") if clean_alias(a)]
        extracted = list(existing_aliases)

        # Проход 1: сбор всех псевдонимов
        for line in dos_text.splitlines():
            is_al, names = is_alias_line(line, extracted)
            if is_al:
                for n in names:
                    if n.lower() not in [x.lower() for x in extracted] and n.lower() != (username or "").lower():
                        extracted.append(n)

        # Проход 2: удаление строк псевдонимов из текста характеристики
        clean_lines = []
        for line in dos_text.splitlines():
            is_al, _ = is_alias_line(line, extracted)
            if not is_al:
                clean_lines.append(line)

        final_aliases_str = ";".join(extracted)
        remaining_text = "\n".join(clean_lines).strip()

        if final_aliases_str != (aliases or "") or remaining_text != dos_text:
            changes.append({
                "chat_id": chat_id,
                "user_id": user_id,
                "username": username or f"id_{user_id}",
                "old_aliases": aliases or "",
                "new_aliases": final_aliases_str,
                "old_text": dos_text,
                "new_text": remaining_text
            })

    if not changes:
        print("✅ Все досье в порядке, миграция не требуется!")
        conn.close()
        return

    print(f"\n📋 Найдено досье для исправления: {len(changes)}\n" + "=" * 60)
    for c in changes:
        print(f"👤 Пользователь: @{c['username']} (Chat: {c['chat_id']}, User ID: {c['user_id']})")
        print(f"   Было псевдонимов: '{c['old_aliases']}'")
        print(f"   Стало псевдонимов: 🟢 '{c['new_aliases']}'")
        print(f"   Остаток текста досье:\n   ---\n   {c['new_text'][:100]}...\n   ---")
        print("-" * 60)

    if not args.apply:
        print("\n⚠️ Это был СУХОЙ ПРОГОН (--dry-run). База данных НЕ изменена.")
        print("👉 Чтобы применить изменения, запустите:")
        print(f"   python3 scripts/migrate_dossiers.py --db {db_path} --apply\n")
        conn.close()
        return

    # Создаем резервную копию перед записью
    backup_file = f"{db_path}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_file)
    print(f"\n💾 Создана резервная копия БД: {backup_file}")

    for c in changes:
        cur.execute(
            "UPDATE user_dossiers SET aliases = ?, dossier_text = ? WHERE chat_id = ? AND user_id = ?",
            (c["new_aliases"], c["new_text"], c["chat_id"], c["user_id"])
        )

    conn.commit()
    conn.close()
    print(f"🎉 Успешно обновлено {len(changes)} записей в {db_path}!\n")

if __name__ == "__main__":
    migrate()
