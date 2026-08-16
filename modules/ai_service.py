import asyncio
from openai import OpenAI
import modules.config as cfg
import modules.database as db
from modules.actions import gigachat as giga

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

async def _request_openai(model, messages, api_key, max_tokens):
    """Приватный метод для прямого запроса к API"""
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=model,
        messages=messages,
        temperature=0.95,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content.strip()

async def call_ai(user_id, username, user_api_key, system_msg, user_msg, status_msg=None, max_tokens=3000, model = None):
    has_own_key = user_api_key and user_api_key != cfg.DEFAULT_API_KEY
    is_premium = (username == cfg.MY_USERNAME or has_own_key or db.get_user_requests(user_id) < cfg.LIMIT_FREE_REQUESTS)
    
    active_key = user_api_key or cfg.DEFAULT_API_KEY
    # Очередь моделей для попыток
    # Формируем список моделей для попыток
    if model : 
        models_to_try = [model, cfg.MODEL_FREE]
    elif is_premium:
        # Если премиум, пробуем: переданную модель (если есть) -> премиум конфиг -> фри конфиг
        models_to_try = [cfg.MODEL_PREMIUM, cfg.MODEL_FREE]
    else:
        # Если не премиум, используем только фри модель, 
        # игнорируя переданную (или можно разрешить, если хочешь)
        models_to_try = [cfg.MODEL_FREE]
    
    for i, model in enumerate(models_to_try):
        try:
            if model.startswith("gemma"):
                messages = [{"role": "user", "content": f"ИНСТРУКЦИЯ: {system_msg}\n\nЗАПРОС: {user_msg}"}]
            else:
                messages = [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]

            res = await _request_openai(model, messages, active_key, max_tokens)
            db.increment_user_requests(user_id)
            footer = "" if is_premium and model == cfg.MODEL_PREMIUM else "\n\n**> [Использую Gemma]**"
            return res + footer

        except Exception as e:
            err_str = str(e).lower()
            # Если это последняя модель в списке OpenAI или ошибка 503/Quota
            if i == len(models_to_try) - 1 or "503" in err_str or "quota" in err_str or "429" in err_str or "400" in err_str:
                if status_msg:
                    current_text = "Разбираюсь...\nМозг вскипает..."
                    if i == len(models_to_try) - 1:
                        current_text += "\nСтараюсь изо всех сил, но пока что ничего не получилось..."
                    await status_msg.edit_text(current_text)
                continue # Переход к следующей итерации (Gemma) или выход из цикла
            return f"Ошибка AI: {e}"

    # --- FALLBACK: GigaChat ---
    try:
        giga.giga_event.clear()
        giga.giga_response = None
        
        # Отправляем промпт в бота (слитно, чтобы не спамить 100 сообщениями)
        prompt_for_giga = f"{system_msg}\n\nЗАПРОС:\n{user_msg}"
        await status_msg._client.send_message("gigachat_bot", prompt_for_giga) # Лимит сообщения ТГ
        
        # Ждем ответа 60 секунд
        await asyncio.wait_for(giga.giga_event.wait(), timeout=60)
        
        footer = "\n\n**> [Gemini и Gemma недоступны, использован GigaChat]**"
        return giga.giga_response + footer
    except Exception as e:
        return f"Все нейронки легли, даже Гигачат: {e}"

