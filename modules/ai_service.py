import asyncio
from openai import OpenAI
import modules.config as cfg
import modules.database as db

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

async def call_ai(user_id, username, user_api_key, system_msg, user_msg, max_tokens=3000):
    # 1. Выбор модели и ключа
    has_own_key = user_api_key and user_api_key != cfg.DEFAULT_API_KEY
    is_premium = (username == cfg.MY_USERNAME or has_own_key or db.get_user_requests(user_id) < cfg.LIMIT_FREE_REQUESTS)
    
    target_model = cfg.MODEL_PREMIUM if is_premium else cfg.MODEL_FREE
    active_key = user_api_key or cfg.DEFAULT_API_KEY
    
    # 2. Формирование сообщений (DRY для разных форматов)
    if target_model.startswith("gemma"):
        messages = [{"role": "user", "content": f"ИНСТРУКЦИЯ: {system_msg}\n\nЗАПРОС: {user_msg}"}]
    else:
        messages = [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]

    # 3. Запрос
    client = OpenAI(api_key=active_key, base_url=BASE_URL)
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=target_model,
            messages=messages,
            temperature=0.95,
            max_tokens=max_tokens
        )
        db.increment_user_requests(user_id)
        
        footer = "" if is_premium else "\n\n** [Лимит Flash исчерпан. Использую Gemma]**"
        return response.choices[0].message.content.strip() + footer
    except Exception as e:
        return f"Бро, что-то меня переклинило (ошибка AI): {e}"