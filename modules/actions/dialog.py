"""
@file dialog.py
@brief Модуль интерактивного разговора и нейродиалога с Фантомом.
@details Поддерживает гибридный Gatekeeper-классификатор целесообразности ответов (gemma-4-26b-a4b-it)
         для случайных сообщений, гарантированный ответ на прямые теги/реплаи Фантому,
         адаптивную сборку контекста, чистый режим отклика реакциями (clean_mode) и плачущую реакцию 😭 при сбоях ИИ.
"""

import re
from typing import Optional, Any, List, Tuple, Set
import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.ai_service import call_ai, extract_mentioned_dossiers_via_gemma, should_assistant_respond
from modules.router import router, EventType, EventContext

@router.on(EventType.DIALOG, priority=15)
async def handle_dialog_event(ctx: EventContext) -> None:
    """
    @brief Обработчик события разговора (тег @tech_phantom, ответ на Фантома или упоминание по имени).
    @param ctx Контекст события EventContext.
    """
    await handle_dialog(ctx.message, ctx.text, ctx.username, ctx.user_id)

async def handle_dialog(message: Any, text: str, username: Optional[str], user_id: int) -> None:
    """
    @brief Оркестратор разговора: человекоподобная верификация -> сбор контекста -> досье -> ИИ.
    """
    chat_id = message.chat.id
    user_key = cfg.USER_API_KEYS.get(username) or cfg.DEFAULT_API_KEY
    author_name = message.from_user.first_name if message.from_user else "Собеседник"
    clean_author_uname = (username or author_name).lstrip("@")
    clean_mode = db.get_chat_clean_mode(chat_id)

    is_direct_tag = "@tech_phantom" in text.lower()
    is_reply = bool(message.reply_to_message)
    replied_msg = message.reply_to_message if is_reply else None

    # 0. ПРОВЕРКА РЕПЛАЯ НА ГОЛОСОВОЕ СООБЩЕНИЕ / АУДИО (ГС ПО ЗАПРОСУ)
    if is_reply and replied_msg and (replied_msg.voice or replied_msg.audio or replied_msg.video_note):
        from modules.actions import voice
        client = message._client if hasattr(message, '_client') else None
        await voice.queue_voice_message(client, replied_msg, force=True, request_msg=message)
        return
    
    is_reply_to_phantom = bool(
        is_reply and 
        replied_msg and 
        replied_msg.from_user and 
        replied_msg.from_user.is_self and 
        re.search(cfg.PHANTOM_NAMES_PATTERN, text.lower())
    )

    # ---------------------------------------------------------------------
    # 1. ПРОВЕРКА ГАРАНТИРОВАННОГО ОТВЕТА ИЛИ ИИ-ВЕРИФИКАЦИЯ (GATEKEEPER)
    # ---------------------------------------------------------------------
    is_guaranteed = is_direct_tag or is_reply_to_phantom

    if clean_mode:
        await utils.set_reaction(message, "👀")

    if not is_guaranteed:
        # Это случайное сообщение в чате, содержащее упоминание Фантома.
        # Вызываем Gatekeeper ИИ-классификатор (gemma-4-26b-a4b-it).
        target_text = replied_msg.text if (is_reply and replied_msg and replied_msg.text) else ""
        should_respond = await should_assistant_respond(user_id, username, user_key, text, target_text, chat_id=chat_id)
        if not should_respond:
            # ИИ-классификатор ответил NO — убираем глаза и молча игнорируем
            if clean_mode:
                await utils.set_reaction(message, None)
            return

    # ---------------------------------------------------------------------
    # 2. АДАПТИВНАЯ СБОРКА КОНТЕКСТА ЧАТА И ПОДГРУЗКА РЕПЛАЕВ
    # ---------------------------------------------------------------------
    user_prompt = re.sub(r"(?i)@tech_phantom[,:\s]*", "", text).strip()
    if not user_prompt:
        user_prompt = "Выскажи свое мнение по поводу сообщения выше."

    if is_reply and replied_msg:
        replied_id = replied_msg.id
        msg_id = message.id

        # Начинаем снизу (от текущего сообщения msg_id) и идем вверх до сообщения replied_id (максимум 40 сообщений)
        queries: List[Tuple[str, tuple]] = [
            ("SELECT id, author, text FROM {table_name} WHERE id >= ? AND id <= ? ORDER BY id ASC LIMIT 40", (replied_id, msg_id))
        ]
        ctx_lines = db.get_unique_messages_context(chat_id, queries)

        replied_author = utils.format_author(replied_msg)
        replied_text_full = replied_msg.text or replied_msg.caption or "медиа/сообщение"
        reply_context_header = f"[КОНТЕКСТ РЕПЛАЯ: Сообщение '{author_name}' является ПРЯМЫМ ОТВЕТОМ на сообщение '{replied_author}': \"{replied_text_full}\"]\n"
        context_text = reply_context_header + "\n".join(ctx_lines)
    else:
        ctx_lines = db.get_history_from_db(chat_id, 40)
        context_text = "\n".join(ctx_lines)

    # ---------------------------------------------------------------------
    # 3. МУЛЬТИ-ПОИСК И ПОДГРУЗКА ПРИВАТНЫХ ДОСЬЕ (БЕЗ СОБАЧЕК '@')
    # ---------------------------------------------------------------------
    dossiers_to_inject: List[str] = []
    processed_uids: Set[int] = set()

    author_dossier_data = db.get_user_dossier(chat_id, user_id)
    if author_dossier_data:
        processed_uids.add(user_id)
        dossiers_to_inject.append(
            f"[СЛУЖЕБНОЕ ПРИВАТНОЕ ДОСЬЕ НА АВТОРА ЗАПРОСА: {author_name} ({clean_author_uname})]\n{author_dossier_data['dossier_text']}\n[КОНЕЦ ДОСЬЕ]"
        )

    if replied_msg and replied_msg.from_user and not replied_msg.from_user.is_self:
        target_uid = replied_msg.from_user.id
        if target_uid not in processed_uids:
            target_uname = (replied_msg.from_user.username or replied_msg.from_user.first_name).lstrip("@")
            target_dos_data = db.get_user_dossier(chat_id, target_uid)
            if target_dos_data:
                processed_uids.add(target_uid)
                dossiers_to_inject.append(
                    f"[СЛУЖЕБНОЕ ПРИВАТНОЕ ДОСЬЕ НА СОБЕСЕДНИКА В РЕПЛАЕ: {replied_msg.from_user.first_name} ({target_uname})]\n{target_dos_data['dossier_text']}\n[КОНЕЦ ДОСЬЕ]"
                )

    # 3.3. Мгновенный сопоставитель имен/псевдонимов в тексте (Python String & Alias Matcher)
    all_dossiers = db.get_chat_dossiers_with_aliases(chat_id)
    combined_search_text = (user_prompt + " " + context_text).lower()

    for d in all_dossiers:
        d_uid = d["user_id"]
        if d_uid not in processed_uids:
            match_found = False
            uname = (d["username"] or "").lower().lstrip("@")
            if uname and uname in combined_search_text:
                match_found = True
            elif d["aliases"]:
                aliases_list = [a.strip().lower() for a in d["aliases"].split(";") if a.strip()]
                for alias in aliases_list:
                    if alias and len(alias) >= 2 and alias in combined_search_text:
                        match_found = True
                        break

            if match_found:
                g_dos_data = db.get_user_dossier(chat_id, d_uid)
                if g_dos_data:
                    processed_uids.add(d_uid)
                    d_uname = (d["username"] or str(d_uid)).lstrip("@")
                    dossiers_to_inject.append(
                        f"[СЛУЖЕБНОЕ ПРИВАТНОЕ ДОСЬЕ НА УПОМЯНУТОГО УЧАСТНИКА: {d_uname}]\n{g_dos_data['dossier_text']}\n[КОНЕЦ ДОСЬЕ]"
                    )

    # 3.4. ИИ-ИЗВЛЕКАТЕЛЬ ДОСЬЕ (Gemma-4) — Склонение имен и смысловой поиск (управляется админом)
    if db.get_chat_gemma_dossier_mode(chat_id):
        matched_gemma_uids = await extract_mentioned_dossiers_via_gemma(
            chat_id, user_id, username, user_key, context_text, user_prompt
        )
        for g_uid in matched_gemma_uids:
            if g_uid not in processed_uids:
                g_dos_data = db.get_user_dossier(chat_id, g_uid)
                if g_dos_data:
                    processed_uids.add(g_uid)
                    d_uname = (g_dos_data['username'] or str(g_uid)).lstrip("@")
                    dossiers_to_inject.append(
                        f"[СЛУЖЕБНОЕ ПРИВАТНОЕ ДОСЬЕ НА УПОМЯНУТОГО УЧАСТНИКА (найдено Gemma): {d_uname}]\n{g_dos_data['dossier_text']}\n[КОНЕЦ ДОСЬЕ]"
                    )

    # ---------------------------------------------------------------------
    # 4. ФОРМИРОВАНИЕ СТРУКТУРИРОВАННОГО ПРОМПТА И ВЫЗОВ ИИ
    #    ПОРЯДОК: 1. История -> 2. Характеристика/Досье -> 3. Промпт/Задание
    # ---------------------------------------------------------------------
    system_prompt = cfg.AI_PROMPTS["dialog_system"]

    dossier_text_block = ""
    if dossiers_to_inject:
        dossier_text_block = (
            "\n\n[ХАРАКТЕРИСТИКИ И ДОСЬЕ УЧАСТНИКОВ]:\n" + 
            "\n\n".join(dossiers_to_inject) + 
            "\n[КОНЕЦ ХАРАКТЕРИСТИК]\n\n"
        )

    full_user_prompt = (
        f"ИСТОРИЯ ЧАТА:\n"
        f"{context_text}"
        f"{dossier_text_block}"
        f"\nИНСТРУКЦИЯ И ЗАДАНИЕ ДЛЯ ФАНТОМА:\n"
        f"1. Ты — Фантом, ассистент чата. Твои ответы неформальные, краткие и в тему ('свой парень').\n"
        f"2. Если выше представлены характеристики/досье участников: они предназначены ИСКЛЮЧИТЕЛЬНО для тебя, чтобы понять характер собеседников. СТРОГО ЗАПРЕЩЕНО признавать наличие досье, цитировать характеристики или писать 'мне передали досье'/'как сказано в досье'/'как указано в характеристике'.\n"
        f"3. СТРОГО ЗАПРЕЩЕНО ставить символ '@' перед юзернеймами людей (пиши просто имена/псевдонимы).\n"
        f"4. Прочитай переписку выше и ответь на вопрос/задание пользователя: '{user_prompt}'"
    )

    status_msg = None
    if not clean_mode:
        status_msg = await message.reply_text(cfg.STATUS_MESSAGES_FALLBACK[0])

    response = await call_ai(
        user_id=user_id,
        username=username,
        user_api_key=user_key,
        system_msg=system_prompt,
        user_msg=full_user_prompt,
        status_msg=status_msg,
        chat_id=chat_id
    )

    # При сбое всех нейросетей выставляем плачущую реакцию 😭
    if not response or "Все доступные модели" in response or response.startswith("Все нейронки легли"):
        if clean_mode:
            await utils.set_reaction(message, "😭")
        elif status_msg:
            try: await status_msg.edit_text("😢 Все нейросети недоступны.")
            except Exception: pass
        return

    if clean_mode:
        await utils.set_reaction(message, None)

    if response:
        await utils.send_as_phantom(message, response, edit_message=status_msg, category="AI_RESPONSE")
    else:
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass