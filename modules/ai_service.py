"""
@file ai_service.py
@brief Модуль взаимодействия с LLM (Gemini, Gemma, GigaChat).
@details Реализует архитектуру специализированных адаптеров моделей и каскадную цепочку отката СТРОГО ВНИЗ ПО ИЕРАРХИИ:
         1. gemini-3.5-flash-lite
         2. gemini-3.1-flash-lite
         3. gemma-4-31b-it
         4. gemma-4-26b-a4b-it
         5. GigaChat Bot (через Telegram Client)
"""

import asyncio
import json
import logging
import re
from typing import Optional, List, Dict, Any
from openai import OpenAI
import modules.config as cfg
import modules.database as db
from modules.actions import gigachat as giga
from modules.actions import tracer

logger = logging.getLogger(__name__)

## @brief Базовый URL для обращения к Google Gemini API через OpenAI SDK
BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

def clean_ai_response(text: str) -> str:
    """
    @brief Специализированный фильтр для моделей Gemma: вырезает внутренние теги размышления (<thought>...</thought>).
    @param text Сырой текст ответа от модели Gemma.
    @return Очищенный текст ответа.
    """
    if not text:
        return ""
    
    cleaned = re.sub(r"(?s)<thought>.*?</thought>", "", text)
    cleaned = re.sub(r"(?s)<think>.*?</think>", "", cleaned)
    cleaned = re.sub(r"(?s)<thought>.*$", "", cleaned)
    cleaned = re.sub(r"(?s)<think>.*$", "", cleaned)
    
    result = cleaned.strip()
    
    if not result:
        raw_clean = re.sub(r"</?(thought|think)[^>]*>", "", text).strip()
        lines = []
        for line in raw_clean.split("\n"):
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("* ") or line_str.startswith("Instruction:") or line_str.startswith("Request:"):
                continue
            lines.append(line_str)
        result = "\n".join(lines).strip() or raw_clean

    return result.strip()


def resolve_api_key(user_api_key: Optional[str], username: Optional[str]) -> str:
    """
    @brief Надежно извлекает и очищает API-ключ пользователя или глобальный ключ по умолчанию.
    @param user_api_key Явно переданный API-ключ.
    @param username Юзернейм пользователя для поиска в словаре USER_API_KEYS.
    @return Очищенная строка API-ключа.
    """
    if user_api_key and user_api_key.strip():
        return user_api_key.strip()

    if username:
        clean_uname = username.lstrip("@").strip()
        dict_key = cfg.USER_API_KEYS.get(clean_uname) or cfg.USER_API_KEYS.get(username)
        if dict_key and dict_key.strip():
            return dict_key.strip()

    return (cfg.DEFAULT_API_KEY or "").strip()


async def _request_openai_raw(
    model: str, 
    messages: List[Dict[str, str]], 
    api_key: str, 
    max_tokens: int = 3000,
    reasoning_effort: Optional[str] = None,
    temperature: float = 0.95
) -> str:
    """
    @brief Базовый метод отправки сообщений в Google OpenAI-compatible API.
    @details Поддерживает выбор уровня ризонинга и температуры генерации.
    """
    clean_key = (api_key or "").strip()
    if not clean_key:
        clean_key = (cfg.DEFAULT_API_KEY or "").strip()

    client = OpenAI(
        api_key=clean_key, 
        base_url=BASE_URL,
        default_headers={"x-goog-api-key": clean_key}
    )
    
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    # Поддержка уровня рассуждений (reasoning_effort) для Google OpenAI-compatible API ("minimal" или "high")
    if reasoning_effort:
        r_effort = str(reasoning_effort).lower()
        if r_effort in ["off", "none", "disable", "0", "minimal"]:
            kwargs["reasoning_effort"] = "minimal"
        else:
            kwargs["reasoning_effort"] = r_effort

    # Трассировка полных JSON-запросов и ответов в консоль
    try:
        req_json = json.dumps(kwargs, indent=2, ensure_ascii=False)
        logger.info(f"📡 [FULL JSON REQUEST] Model: {model}\n{req_json}")
    except Exception:
        pass

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            **kwargs
        )
        raw_text = (response.choices[0].message.content or "").strip()
        logger.info(f"📩 [FULL JSON RESPONSE] Model: {model}\n{raw_text}")
        return raw_text
    except Exception as e:
        logger.warning(f"⚠️ [OPENAI API RETRY] Error ({e}). Retrying without reasoning_effort...")
        kwargs.pop("reasoning_effort", None)
        response = await asyncio.to_thread(
            client.chat.completions.create,
            **kwargs
        )
        raw_text = (response.choices[0].message.content or "").strip()
        logger.info(f"📩 [FULL JSON RESPONSE RETRY] Model: {model}\n{raw_text}")
        return raw_text

# =====================================================================
# АДАПТЕРЫ МОДЕЛЕЙ (MODEL ADAPTERS)
# =====================================================================

async def _invoke_gemini_model(
    model: str, 
    system_msg: str, 
    user_msg: str, 
    api_key: str, 
    max_tokens: int,
    reasoning_effort: Optional[str] = None,
    temperature: float = 0.95
) -> str:
    """
    @brief Адаптер вызова моделей Gemini.
    """
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": user_msg})
    return await _request_openai_raw(model, messages, api_key, max_tokens, reasoning_effort=reasoning_effort, temperature=temperature)


async def _invoke_gemma_model(
    model: str, 
    system_msg: str, 
    user_msg: str, 
    api_key: str, 
    max_tokens: int,
    reasoning_effort: Optional[str] = None,
    temperature: float = 0.95
) -> str:
    """
    @brief Адаптер вызова моделей Gemma.
    """
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": user_msg})
    raw_response = await _request_openai_raw(model, messages, api_key, max_tokens, reasoning_effort=reasoning_effort, temperature=temperature)
    return clean_ai_response(raw_response)


async def _invoke_gigachat_model(system_msg: str, user_msg: str, status_msg: Optional[Any]) -> str:
    """
    @brief Адаптер вызова fallback-модели Сбер GigaChat через Telegram Userbot Client.
    """
    if not status_msg or not hasattr(status_msg, '_client'):
        return "Не удалось задействовать GigaChat fallback (нет клиента)"

    if hasattr(status_msg, 'edit_text'):
        try:
            await status_msg.edit_text(cfg.STATUS_MESSAGES_FALLBACK[-1])
        except Exception:
            pass

    giga.giga_event.clear()
    giga.giga_response = None
    
    prompt_for_giga = f"{system_msg}\n\nЗАПРОС:\n{user_msg}"
    await status_msg._client.send_message(cfg.GIGACHAT_BOT, prompt_for_giga)
    await asyncio.wait_for(giga.giga_event.wait(), timeout=60)
    
    return giga.giga_response or ""


async def should_assistant_respond(
    user_id: int, 
    username: Optional[str], 
    user_api_key: Optional[str], 
    reply_text: str, 
    target_text: str,
    chat_id: int = 0
) -> bool:
    """
    @brief Быстрый ИИ-классификатор (Gatekeeper): оценивает, обращен ли реплай к Фантому и стоит ли отвечать.
    @param user_id ID пользователя.
    @param username Юзернейм пользователя.
    @param user_api_key API-ключ.
    @param reply_text Текст ответа пользователя.
    @param target_text Текст сообщения, на которое ответили.
    @param chat_id ID чата для трассировки в ЛС.
    @return True если модель ответила YES, иначе False.
    """
    system_msg = (
        "Ты — строгий фильтр сообщений для ассистента 'Фантом' в групповом чате Telegram.\n"
        "Твоя задача — определить, требуется ли НЕПОСРЕДСТВЕННЫЙ и СРОЧНЫЙ ответ ИМЕННО от ассистента 'Фантом'.\n\n"
        "ПРАВИЛА ОЦЕНКИ:\n"
        "1. Отвечай YES СТРОГО ЕСЛИ:\n"
        "   - Сообщение напрямую адресовано Фантому и требует мгновенного ответа именно от него.\n"
        "2. Отвечай NO ВО ВСЕХ ОСТАЛЬНЫХ СЛУЧАЯХ, а именно:\n"
        "   - Сообщение не требует мгновенного ответа (обычный треп, болтовня по мелочи).\n"
        "   - Вопрос или реплика адресованы людям/чату вообще, а не лично Фантому.\n"
        "   - Требуется ответ от другого участника разговора, а не от Фантома.\n"
        "   - Фантом упомянут в 3-м лице по мелочи без явного призыва отвечать.\n\n"
        "Твой вердикт должен содержать СТРОГО одно слово: YES или NO."
    )
    user_msg = (
        f"КОНТЕКСТ ПЕРЕПИСКИ В ЧАТЕ:\n"
        f"Предыдущее сообщение: '{target_text}'\n"
        f"Входящее сообщение: '{reply_text}'\n\n"
        "Требует ли это сообщение НЕМЕДЛЕННОГО ответа ИМЕННО от Фантома? Ответь строго YES или NO."
    )
    try:
        classifier_model = "gemma-4-26b-a4b-it"
        res = await call_ai(
            user_id=user_id, 
            username=username, 
            user_api_key=user_api_key, 
            system_msg=system_msg, 
            user_msg=user_msg, 
            max_tokens=500, 
            model=classifier_model, 
            chat_id=chat_id,
            reasoning_effort="low"
        )
        cleaned_res = clean_ai_response(res).upper()
        decision = "YES" if "YES" in cleaned_res else "NO"

        # Трассировка в ЛС Никитосу
        if chat_id and db.get_chat_trace_mode(chat_id):
            from modules.actions import tracer
            asyncio.create_task(tracer.queue_trace(chat_id, {
                "event": "gatekeeper_gemma_check",
                "model": classifier_model,
                "input_reply": reply_text,
                "target_msg": target_text,
                "raw_response": res,
                "cleaned_response": cleaned_res,
                "decision": decision
            }))

        return decision == "YES"
    except Exception as e:
        logger.error(f"Ошибка ИИ-классификатора ответов: {e}")
        return False


async def extract_mentioned_dossiers_via_gemma(
    chat_id: int, 
    user_id: int, 
    username: Optional[str], 
    user_api_key: Optional[str], 
    context_text: str, 
    user_prompt: str
) -> List[int]:
    """
    @brief Извлекатель упоминаний через модель gemma-4-26b-a4b-it.
    @details Сверяет псевдонимы и имена из БД с контекстом вопроса и возвращает список user_id.
    @return Список user_id совпавших пользователей.
    """
    dossiers = db.get_chat_dossiers_with_aliases(chat_id)
    if not dossiers:
        return []

    dossier_keys_info = []
    for d in dossiers:
        tag = f"USER_{d['user_id']}"
        parts = []
        if d['username']:
            parts.append(f"@{d['username']}")
        if d['aliases']:
            parts.extend([a.strip() for a in d['aliases'].split(";") if a.strip()])
        dossier_keys_info.append(f"- {tag}: {', '.join(parts)}")

    keys_block = "\n".join(dossier_keys_info)

    system_msg = ""

    user_msg = (
        "Do not think step-by-step. Do not provide internal reasoning or chain-of-thought. Provide only the direct, immediate final answer.\n"
        "Task: Identify matching participant USER tags mentioned in the query or context (handles Russian inflections).\n"
        "Rules: Output ONLY the comma-separated USER tags (e.g. USER_12345) or NONE.\n\n"
        f"Participants:\n{keys_block}\n\n"
        f"Context:\n{context_text}\n\n"
        f"Query: {user_prompt}\n\n"
        "Tags:"
    )

    try:
        gemma_res = await call_ai(
            user_id=user_id,
            username=username,
            user_api_key=user_api_key or "",
            system_msg=system_msg,
            user_msg=user_msg,
            max_tokens=60,
            model="gemma-4-26b-a4b-it",
            chat_id=chat_id,
            reasoning_effort="low",
            temperature=0.0
        )
        
        clean_res = re.sub(r"(?s)<thought>.*?</thought>", "", gemma_res).strip()
        clean_res = re.sub(r"(?s)<think>.*?</think>", "", clean_res).strip()
        
        first_line = clean_res.split("\n")[0].strip() if clean_res else ""
        found_tags = set(re.findall(r"USER_\d+", first_line or clean_res))

        matched_uids: List[int] = []
        for d in dossiers:
            tag = f"USER_{d['user_id']}"
            if tag in found_tags:
                matched_uids.append(d["user_id"])

        debug_payload = {
            "event": "gemma_dossier_extractor",
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "model": "gemma-4-26b-a4b-it",
            "system_prompt": system_msg,
            "user_prompt": user_msg,
            "raw_gemma_response": gemma_res,
            "clean_response": clean_res,
            "extracted_tags": list(found_tags),
            "matched_uids": matched_uids
        }
        print(json.dumps(debug_payload, indent=2, ensure_ascii=False))

        return matched_uids
    except Exception as e:
        logger.error(f"Ошибка при работе Gemma 26 Extractor: {e}")
        return []


async def call_ai(
    user_id: int, 
    username: Optional[str], 
    user_api_key: Optional[str], 
    system_msg: str, 
    user_msg: str, 
    status_msg: Optional[Any] = None, 
    max_tokens: int = 3000, 
    model: Optional[str] = None,
    chat_id: int = 0,
    reasoning_effort: Optional[str] = None,
    temperature: float = 0.95
) -> str:
    """
    @brief Главная функция обращения к ИИ с каскадом отката СТРОГО ВНИЗ ПО ИЕРАРХИИ.
    @details
      - Если передана конкретная модель (model), откат происходит ТОЛЬКО к моделям ниже ее по иерархии!
      - Премиальные верхние модели никогда не вызываются при сбоях младших моделей.
      - Использует специализированные адаптеры (_invoke_gemini_model, _invoke_gemma_model).
    """
    active_key = resolve_api_key(user_api_key, username)
    if not chat_id and status_msg and hasattr(status_msg, 'chat'):
        chat_id = status_msg.chat.id

    # ---------------------------------------------------------------------
    # СТРОГОЕ ФОРМИРОВАНИЕ ЦЕПОЧКИ ОТКАТА (ТОЛЬКО ВНИЗ ПО ИЕРАРХИИ)
    # ---------------------------------------------------------------------
    if model == "gemma-4-31b-it":
        # При запросе Gemma 31B совершаем до 6 попыток с чередованием (31B <-> 26B по 3 раза)
        models_to_try = [
            "gemma-4-31b-it", "gemma-4-26b-a4b-it",
            "gemma-4-31b-it", "gemma-4-26b-a4b-it",
            "gemma-4-31b-it", "gemma-4-26b-a4b-it"
        ]
    elif model and model in cfg.AI_MODELS_CHAIN:
        start_idx = cfg.AI_MODELS_CHAIN.index(model)
        models_to_try = cfg.AI_MODELS_CHAIN[start_idx:]
    elif model:
        models_to_try = [model]
    else:
        models_to_try = list(cfg.AI_MODELS_CHAIN)

    # 1. ТРИАЛ ПО СРЕЗУ ЦЕПОЧКИ МОДЕЛЕЙ (ТОЛЬКО ВНИЗ)
    for i, target_model in enumerate(models_to_try):
        try:
            if target_model.startswith("gemma"):
                res = await _invoke_gemma_model(target_model, system_msg, user_msg, active_key, max_tokens, reasoning_effort=reasoning_effort, temperature=temperature)
            else:
                res = await _invoke_gemini_model(target_model, system_msg, user_msg, active_key, max_tokens, reasoning_effort=reasoning_effort, temperature=temperature)

            db.increment_user_requests(user_id)

            footer = "" if target_model == models_to_try[0] else f"\n\n**> [Использована модель: {target_model}]**"

            if chat_id:
                asyncio.create_task(tracer.queue_trace(chat_id, {
                    "event": "ai_response",
                    "user_id": user_id,
                    "username": username,
                    "model": target_model,
                    "system_prompt": system_msg,
                    "user_prompt": user_msg,
                    "response": res
                }))

            return res + footer

        except Exception as e:
            logger.warning(f"Сбой модели {target_model} (ошибка: {e}). Пробуем модель рангом ниже...")
            
            if chat_id:
                asyncio.create_task(tracer.queue_trace(chat_id, {
                    "event": "ai_error_fallback",
                    "user_id": user_id,
                    "username": username,
                    "failed_model": target_model,
                    "error": str(e)
                }))

            if status_msg and i + 1 < len(status_msg_texts := cfg.STATUS_MESSAGES_FALLBACK):
                try:
                    next_status = status_msg_texts[min(i + 1, len(status_msg_texts) - 1)]
                    await status_msg.edit_text(next_status)
                except Exception:
                    pass
            continue

    # 2. FALLBACK: СБЕР GIGACHAT BOT (Если все модели в срезе не ответили)
    try:
        giga_res = await _invoke_gigachat_model(system_msg, user_msg, status_msg)
        footer = "\n\n**> [Все доступные модели Google недоступны, использован Сбер GigaChat]**"
        
        if chat_id:
            asyncio.create_task(tracer.queue_trace(chat_id, {
                "event": "ai_gigachat_fallback",
                "user_id": user_id,
                "username": username,
                "model": "gigachat_bot",
                "system_prompt": system_msg,
                "user_prompt": user_msg,
                "response": giga_res
            }))

        return giga_res + footer
    except Exception as e:
        return f"Все доступные модели нейросетей недоступны: {e}"
