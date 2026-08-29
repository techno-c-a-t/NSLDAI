#!/usr/bin/env python3
"""
@file test_gemma_dossier.py
@brief Тестовый скрипт проверки ИИ-извлекателя досье через Gemma-4.
@details Тестирует распознавание просклоняемых имен, юзернеймов и псевдонимов (Олеженьку, Никитосу, NSLDNK).
"""

import asyncio
import json
import os
import sys
from typing import List

# Добавляем корневой каталог проекта в sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import modules.config as cfg
import modules.database as db
from modules.ai_service import extract_mentioned_dossiers_via_gemma

async def run_gemma_dossier_tests():
    print("=" * 70)
    print("🧪 [ТЕСТ] ПРОВЕРКА ИИ-ИЗВЛЕКАТЕЛЯ ДОСЬЕ GEMMA-4")
    print("=" * 70)

    db.init_db()
    test_chat_id = -1003036875599

    # Создаем тестовые досье в базе данных
    test_users = [
        (37329040, "techno_c_a_t", "Nikitos;Nikita;Никита;Никитос", "Администратор чата, разработчик"),
        (845502685, "wassapiamoleg", "Олеженька;Олег;Олежка", "Активный участник обсуждений"),
        (999888777, "nsldnk_bot", "NSLDNK;НСЛДНК", "Бот генерации мемов")
    ]

    for uid, uname, aliases, desc in test_users:
        db.save_user_dossier(test_chat_id, uid, uname, desc, aliases=aliases)

    test_cases = [
        {
            "name": "Тест 1: Склонение имени 'Олеженька' -> 'про олеженьку'",
            "user_prompt": "Фантом, что ты можешь сказать про олеженьку?",
            "context": "[Nikitos (@techno_c_a_t)]: Фантом, что ты можешь сказать про олеженьку",
            "expected_uids": [845502685]
        },
        {
            "name": "Тест 2: Склонение дательного падежа 'Никитос' -> 'Никитосу'",
            "user_prompt": "Фантом, передай привет Никитосу",
            "context": "[wassapiamoleg]: Фантом, передай привет Никитосу",
            "expected_uids": [37329040]
        },
        {
            "name": "Тест 3: Упоминание бота по нику 'NSLDNK'",
            "user_prompt": "Фантом, что думаешь по поводу того что NSLDNK прислал?",
            "context": "[Nikitos (@techno_c_a_t)]: Фантом, что думаешь по поводу того что NSLDNK прислал",
            "expected_uids": [37329040, 999888777]
        },
        {
            "name": "Тест 4: Отсутствие упоминаний других людей",
            "user_prompt": "Фантом, какая погода за окном?",
            "context": "[Nikitos (@techno_c_a_t)]: Фантом, какая погода за окном?",
            "expected_uids": []
        }
    ]

    passed_count = 0

    for idx, tc in enumerate(test_cases, 1):
        print(f"\n" + "-" * 60)
        print(f"🔹 {tc['name']}")
        print("-" * 60)
        
        try:
            matched_uids = await extract_mentioned_dossiers_via_gemma(
                chat_id=test_chat_id,
                user_id=5180863604,
                username="techno_c_a_t",
                user_api_key="",
                context_text=tc["context"],
                user_prompt=tc["user_prompt"]
            )
            
            is_success = set(matched_uids) == set(tc["expected_uids"])
            status_str = "PASSED ✅" if is_success else "FAILED ❌"
            print(f"🎯 СТАТУС ТЕСТА: {status_str} | Ожидались UIDs: {tc['expected_uids']} | Извлечены: {matched_uids}")

            if is_success:
                passed_count += 1
        except Exception as e:
            print(f"   💥 ИСКЛЮЧЕНИЕ ПРИ ТЕСТИРОВАНИИ: {e}")

    print("\n" + "=" * 70)
    print(f"📊 ИТОГИ ТЕСТИРОВАНИЯ GEMMA-4: Пройдено {passed_count}/{len(test_cases)} тестов.")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_gemma_dossier_tests())
