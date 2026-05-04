import asyncio
from openai import OpenAI

# Базовый URL остается прежним
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

async def get_chat_summary(messages_list, user_api_key):
    """Суммаризация с жестким ограничением на краткость и отсутствие воды"""
    if not messages_list:
        return "В чате пока тихо."

    client = OpenAI(
        api_key=user_api_key,
        base_url=BASE_URL
    )

    context = "\n".join(messages_list)
    
    # Мы максимально конкретизируем задачу, чтобы ИИ не уходил в "творчество"
    prompt = f"""
    Ты — аналитик. Твоя задача: прочитать последние 100 сообщений и составить сверхкраткий отчет.
    
    ИНСТРУКЦИИ:
    - НЕ здоровайся, НЕ представляйся ("Я Фантом", "Фантом на связи" — ЗАПРЕЩЕНО).
    - Твой ответ приклеивается к фразе "Вот что я нарыл:", поэтому начни сразу с сути.
    - Используй 3-4 пункта или один короткий абзац.
    - Максимальная длина ответа: 6-8 предложений.
    - Если обсуждают бота (меня), упомяни это кратко.
    - Пиши в стиле "Свой парень", не формально, просто коротки
    
    ИСТОРИЯ ЧАТА:
    {context}
    
    Твой ответ (начни сразу с сути):
    """

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gemini-2.5-flash",
            messages=[
                {
                    "role": "system", 
                    "content": "Ты — лаконичный робот-аналитик. Ты пишешь только суть, без вступлений и приветствий. Твой стиль: деловой, но дружелюбный."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.95, # Снизили температуру для большей конкретики
            max_tokens=2500   # Уменьшили до 600, чтобы он не пытался писать мемуары и не обрывался
        )
        
        content = response.choices[0].message.content.strip()
        
        # Если ИИ все равно начал с "Вот что я нарыл" или "Фантом:", обрежем это
        bad_prefixes = ["вот что я нарыл:", "фантом:", "я нарыл:"]
        for prefix in bad_prefixes:
            if content.lower().startswith(prefix):
                content = content[len(prefix):].strip()
        
        return content
        
    except Exception as e:
        if "429" in str(e):
            return "Лимиты ключа исчерпаны. Попробуй позже."
        return f"Ошибка AI: {str(e)}"
    
async def validate_transcription(text, user_api_key):
    """Проверяет, является ли текст осмысленной расшифровкой или мусором"""
    if not text or len(text.strip()) < 2:
        return False

    client = OpenAI(
        api_key=user_api_key,
        base_url=BASE_URL
    )

    prompt = f"""
    Проанализируй текст расшифровки аудиосообщения. 
    Определи, является ли это связной речью (пусть даже с ошибками) или это бессмысленный набор звуков, шум, галлюцинация ИИ или просто обрывки слов (например: "подпишитесь", "сообщения", "просто шум").

    Текст: "{text}"

    Ответь строго одним словом: YES если это похоже на реальное сообщение, и NO если это мусор/ошибка распознавания.
    """

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gemini-1.5-flash", # Используем 1.5, так как 2.5 еще не вышла
            messages=[
                {"role": "system", "content": "Ты — фильтр качества транскрипции. Отвечаешь только YES или NO."},
                {"role": "user", "content": prompt}
            ],
            temperature=0, # Нужна максимальная точность
        )
        
        answer = response.choices[0].message.content.strip().upper()
        return "YES" in answer
    except Exception:
        return True # В случае ошибки AI лучше пропустить сообщение, чем удалить полезное