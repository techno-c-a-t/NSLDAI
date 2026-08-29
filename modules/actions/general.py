"""
@file general.py
@brief Модуль общих команд (справка, приветствие, режим ГС, чистый режим админа и реакции).
"""

import re
import random
import logging
from typing import Any
import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.router import router, EventType, EventContext

logger = logging.getLogger(__name__)

ENABLE_EVIL_REACTIONS = True

CLEAN_MODE_ON_PATTERN: str = r"(?i)^фантом,?\s*(чистый\s+режим|тихий\s+режим|включи\s+чистый\s+режим|тихий\s+фантом)\b"
CLEAN_MODE_OFF_PATTERN: str = r"(?i)^фантом,?\s*(обычный\s+режим|выключи\s+чистый\s+режим|выключи\s+тихий\s+режим)\b"

def is_evil_user(user: Any) -> bool:
    """
    @brief Проверяет, является ли пользователь целевым пользователем для особых реакций (Evil).
    @param user Объект пользователя Pyrogram User.
    @return True если пользователь совпадает по имени или юзернейму.
    """
    if not user:
        return False
    target_name = "𝓔𝓥𝓲𝓛"
    target_username = "XTRaEViLman"
    
    name_check = bool(user.first_name and target_name in user.first_name) or bool(user.last_name and target_name in user.last_name)
    username_check = bool(user.username and user.username.lower() == target_username.lower())
    return name_check or username_check

@router.on(EventType.COMMAND, pattern=cfg.HELP_PATTERN, priority=20)
async def handle_help_command(ctx: EventContext) -> None:
    """
    @brief Отправляет ролевое справочное сообщение по командам Фантома с блоком статусов для Никитоса.
    @details Для Никитоса (is_me) динамически подтягиваются актуальные статусы без символа '@'.
    @param ctx Контекст события EventContext.
    """
    user_name = ctx.user.first_name if ctx.user else "друг"
    chat_id = ctx.chat_id
    clean_mode = db.get_chat_clean_mode(chat_id)

    if ctx.is_me:
        summary_limit = db.get_chat_summary_limit(chat_id)
        trace_mode = f"ВКЛЮЧЕНА 🟢 ({cfg.MY_USERNAME})" if db.get_chat_trace_mode(chat_id) else "ВЫКЛЮЧЕНА 🔴"
        voice_mode = "ВСЕ ГС (AUTO)" if db.get_chat_voice_mode(chat_id) == 'AUTO' else "ПО ЗАПРОСУ (ON_DEMAND)"
        clean_mode_str = "ВКЛЮЧЕН 🟢 (реакции 👀 👍)" if clean_mode else "ВЫКЛЮЧЕН 🔴 (текстовые сообщения)"

        dossiers_list = db.get_chat_dossiers_list(chat_id)
        if dossiers_list:
            dossier_names = ", ".join([u[1].lstrip('@') if not u[1].isdigit() else f"ID:{u[0]}" for u in dossiers_list])
            dossier_str = f"{len(dossiers_list)} чел ({dossier_names})"
        else:
            dossier_str = "нет данных"

        status_box = (
            f"\n\n📊 **АКТУАЛЬНЫЙ СТАТУС НАСТРОЕК В ЭТОМ ЧАТЕ:**\n"
            f"• **Чистый режим админа (Reactions):** {clean_mode_str}\n"
            f"• **Длина сводки истории:** {summary_limit} сообщений (из 2000)\n"
            f"• **Трассировка в ЛС:** {trace_mode}\n"
            f"• **Режим расшифровки ГС:** {voice_mode}\n"
            f"• **Досье заполнено на:** {dossier_str}\n"
        )
        
        await utils.send_as_phantom(ctx.message, f"Йо, {user_name}!\n\n{cfg.ADMIN_HELP_MESSAGE}{status_box}", category="SERVICE")
    else:
        await utils.send_as_phantom(ctx.message, f"Йо, {user_name}!\n\n{cfg.PUBLIC_HELP_MESSAGE}", category="SERVICE")

@router.on(EventType.COMMAND, pattern=CLEAN_MODE_ON_PATTERN, admin_only=True, priority=20)
async def handle_clean_mode_on(ctx: EventContext) -> None:
    """
    @brief Включает чистый режим админа (реакции 👀 и 👍 вместо лишних служебных текстов).
    """
    db.set_chat_clean_mode(ctx.chat_id, True)
    await utils.set_reaction(ctx.message, "👍")

@router.on(EventType.COMMAND, pattern=CLEAN_MODE_OFF_PATTERN, admin_only=True, priority=20)
async def handle_clean_mode_off(ctx: EventContext) -> None:
    """
    @brief Выключает чистый режим админа.
    """
    db.set_chat_clean_mode(ctx.chat_id, False)
    await utils.send_as_phantom(ctx.message, "Чистый режим выключен 🔴. Фантом снова отправляет полные служебные сообщения.")

@router.on(EventType.COMMAND, pattern=r"(?i)^фантом,?\s*(слушай все гс|авто\s*гс)", admin_only=True, priority=20)
async def handle_voice_mode_auto(ctx: EventContext) -> None:
    """
    @brief Переключает режим работы ГС в чате на AUTO (слушать все).
    """
    db.set_chat_voice_mode(ctx.chat_id, 'AUTO')
    if db.get_chat_clean_mode(ctx.chat_id):
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, "Понял, слушаю и расшифровываю все ГС в этом чате.")

@router.on(EventType.COMMAND, pattern=r"(?i)^фантом,?\s*(расшифровывай только по запросу|гс по запросу)", admin_only=True, priority=20)
async def handle_voice_mode_ondemand(ctx: EventContext) -> None:
    """
    @brief Переключает режим работы ГС в чате на ON_DEMAND (по реплаю 'Фантом').
    """
    db.set_chat_voice_mode(ctx.chat_id, 'ON_DEMAND')
    if db.get_chat_clean_mode(ctx.chat_id):
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, "Принял, теперь расшифровываю ГС только по запросу-реплаю 'Фантом'.")

@router.on(EventType.COMMAND, pattern=cfg.YO_PATTERN, priority=25)
async def handle_yo_greeting(ctx: EventContext) -> None:
    """
    @brief Отвечает на приветствия вида 'Йо, Фантом'.
    """
    user_name = ctx.user.first_name if ctx.user else "друг"
    reply_text = "Рад видеть, Nikitos" if ctx.is_me else f"Йоо, {user_name}!"
    await utils.send_as_phantom(ctx.message, reply_text)

@router.on(EventType.TEXT_MESSAGE, priority=1)
async def handle_reactions_and_lob(ctx: EventContext) -> bool:
    """
    @brief Обрабатывает пасхалку 'Лоб' и рандомные реакции.
    """
    message = ctx.message
    text = ctx.text
    user = ctx.user
    
    if ENABLE_EVIL_REACTIONS and is_evil_user(user):
        rand_val = random.random()
        if rand_val < 0.05:
            await ctx.client.send_reaction(message.chat.id, message.id, "💋")
        elif rand_val < 0.2:
            await ctx.client.send_reaction(message.chat.id, message.id, "🏆")

    if "лоб" in text.lower():
        if is_evil_user(user):
            return True
        if re.search(cfg.PHANTOM_NAMES_PATTERN, text):
            user_name = user.first_name if user else "друг"
            await utils.send_as_phantom(message, f"Лоб, {user_name} )")
        else:
            await ctx.client.send_reaction(message.chat.id, message.id, "💋")
        return True

    return False
