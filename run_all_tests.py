#!/usr/bin/env python3
"""
Сценарий Полной Проверки Ошибок Кода (Test Suite Runner)
Этап 1: Проверка локальных модулей, БД, фильтров, промптов и алгоритмов (без ТГ).
Этап 2: Проверка хендлеров, диспатчера и интеграции Pyrogram (с эмуляцией ТГ).
"""
import unittest
import sys

def main():
    print("=" * 70)
    print("🚀 ЗАПУСК ПОЛНОЙ ПРОВЕРКИ КОДА ПРОЕКТА NSLDAI (ФАНТОМ)")
    print("=" * 70)
    
    loader = unittest.TestLoader()
    suite = loader.discover("tests")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("=" * 70)
    if result.wasSuccessful():
        print("✅ ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ! КРИТИЧЕСКИХ ОШИБОК НЕ ОБНАРУЖЕНО.")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"❌ ОБНАРУЖЕНЫ ОШИБКИ: {len(result.failures)} сбоев, {len(result.errors)} ошибок.")
        print("=" * 70)
        sys.exit(1)

if __name__ == "__main__":
    main()
