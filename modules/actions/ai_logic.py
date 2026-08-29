"""
@file ai_logic.py
@brief Модуль генерации кратких сводок и саммари истории чатов.
@details Поддерживает динамическое изменение длины истории (от 20 до 2000 сообщений)
         и тихий режим отклика реакциями (clean_mode).
"""

from typing import List, Optional, Any
import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.ai_service import call_ai
from modules.router import router, EventType, EventContext

@router.on(EventType.COMMAND, pattern=cfg.SUMMARY_LIMIT_SET_PATTERN, admin_only=True, priority=20)
async def handle_set_summary_limit_command(ctx: EventContext) -> None:
    """
    @brief Админ-команда изменения дефолтной длины сводки истории для чата (от 20 до 2000 сообщений).
    """
    limit_str = ctx.match.group(1) if ctx.match else "100"
    requested_limit = int(limit_str)
    actual_limit = db.set_chat_summary_limit(ctx.chat_id, requested_limit)
    
    clean_mode = db.get_chat_clean_mode(ctx.chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, f"Установил длину истории для сводки в этом чате: {actual_limit} сообщений 👌")

@router.on(EventType.COMMAND, pattern=cfg.SUMMARY_PATTERN, priority=20)
async def handle_summary_event(ctx: EventContext) -> None:
    """
    @brief Обработчик команды вызова саммари ("Фантом, что происходит [число]").
    """
    explicit_count = ctx.match.group(2) if (ctx.match and ctx.match.group(2)) else None
    chat_id = ctx.chat_id
    clean_mode = db.get_chat_clean_mode(chat_id)

    if explicit_count:
        count = max(20, min(2000, int(explicit_count)))
    else:
        count = db.get_chat_summary_limit(chat_id)

    status_msg = None
    if clean_mode:
        await utils.set_reaction(ctx.message, "👀")
    else:
        status_msg = await ctx.message.reply_text("Разбираюсь...")

    history = db.get_history_from_db(chat_id, count)
    user_key = cfg.USER_API_KEYS.get(ctx.username)
    res = await get_chat_summary(history, user_key, ctx.user_id, ctx.username, count=count, status_msg=status_msg)
    
    if clean_mode:
        await utils.set_reaction(ctx.message, None)
        await utils.send_as_phantom(ctx.message, f"**Нарыл (по {count} сообщениям):**\n\n{res}", category="AI_SUMMARY")
    else:
        await utils.send_as_phantom(ctx.message, f"**Нарыл (по {count} сообщениям):**\n\n{res}", edit_message=status_msg, category="AI_SUMMARY")

async def get_chat_summary(
    messages_list: List[str], 
    user_api_key: Optional[str], 
    user_id: int, 
    username: Optional[str] = None,
    count: int = 100, 
    status_msg: Optional[Any] = None
) -> str:
    """
    @brief Отправляет последние сообщения истории чата в ИИ для получения аналитического свода.
    """
    if not messages_list: 
        return "В чате пока тихо."
    
    context = "\n".join(messages_list)
    prompt = cfg.AI_PROMPTS["summary_user"].format(context=context, count=count)
    
    res = await call_ai(user_id, username, user_api_key, cfg.AI_PROMPTS["summary_system"], prompt, status_msg=status_msg)    
    for p in ["вот что я нарыл:", "фантом:", "я нарыл:"]:
        if res.lower().startswith(p): 
            res = res[len(p):].strip()
    return res