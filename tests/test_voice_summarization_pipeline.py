import asyncio
import logging
import sys
import os

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import modules.config as cfg
import modules.database as db
from modules import ai_service
from modules.actions import voice

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def run_pipeline_test():
    print("=" * 80)
    print("🚀 [ТЕСТ] Генерация грязного ГС (150-300 слов) и его сжатие по нейросетевому пайплайну")
    print("=" * 80)

    # 1. Генерация реалистичного "грязного" голосового сообщения через ИИ
    gen_system_prompt = (
        "Ты — генератор тестовых данных. Сгенерируй реалистичную устную расшифровку эмоционального голосового сообщения на русском языке.\n"
        "Требования:\n"
        "1. Объем: СТРОГО от 150 до 300 слов.\n"
        "2. Стиль: разговорный, эмоциональный, с междометиями ('короче', 'ну типа', 'э-э-э', 'знаешь'), повторами, эмоциональными всплесками и возмущениями по поводу работы какого-то сервиса или ситуации.\n"
        "3. Выдай ТОЛЬКО сам текст устной речи без кавычек и служебных помет."
    )
    gen_user_prompt = "Сгенерируй устную речь человека на 200 слов:"

    print("\n⏳ 1. Запрашиваем генерацию грязного текста устной речи через ИИ...")
    raw_speech = await ai_service.call_ai(
        user_id=1001,
        username="test_author",
        user_api_key=None,
        system_msg=gen_system_prompt,
        user_msg=gen_user_prompt,
        max_tokens=600,
        model="gemini-3.5-flash-lite"
    )
    cleaned_speech = ai_service.clean_ai_response(raw_speech)
    word_count_orig = len(cleaned_speech.split())

    print(f"\n📥 [ИСХОДНЫЙ ТЕКСТ ГС] ({word_count_orig} слов):\n{'-'*60}\n{cleaned_speech}\n{'-'*60}")

    # 2. Прогон через созданный модуль сокращения voice.summarize_voice_transcription
    print(f"\n⏳ 2. Запускаем сокращение через voice.summarize_voice_transcription (reasoning_effort='off', gemma-4-31b-it / 26b cascade)...")

    shortened = await voice.summarize_voice_transcription(
        chat_id=-100123456789,
        user_id=1001,
        username="test_author",
        raw_text=cleaned_speech
    )

    word_count_short = len(shortened.split())

    print("\n✅ [РЕЗУЛЬТАТ СОКРАЩЕНИЯ]:")
    print("=" * 80)
    print(f"Если кратко:\n{shortened}")
    print("=" * 80)
    print(f"📊 Свои слова: Исходник = {word_count_orig} слов | Итог = {word_count_short} слов | Коэффициент сжатия = {word_count_orig / max(1, word_count_short):.1f}x")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_pipeline_test())
