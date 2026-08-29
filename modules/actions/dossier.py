"""
@file dossier.py
@brief Закрытый админ-модуль управления приватными характеристиками/досье пользователей и их псевдонимами.
@details Доступен ТОЛЬКО Никитосу (is_me). Запросы обрабатываются на месте БЕЗ роутинга в ИИ.
         В чистом режиме (clean_mode) мгновенно подстверждается реакцией '👍'.
"""

import re
from typing import Any
import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.router import router, EventType, EventContext

@router.on(EventType.COMMAND, pattern=r"(?i)^фантом,\s*(записывай|дополни|вычеркивай)", admin_only=True, priority=30)
async def handle_new_dossier_syntax_event(ctx: EventContext) -> bool:
    """
    @brief Обработчик новых трех синтаксисов управления досье по первому строковому заголовку.
    @details Критерий: Первая строка до абзаца на 100% совпадает с одной из 3 команд и отправитель админ.
             Запрос гарантированно НЕ роутится на AI (возвращает True).
    @param ctx Контекст события EventContext.
    """
    text = ctx.text
    chat_id = ctx.chat_id
    clean_mode = db.get_chat_clean_mode(chat_id)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    if not lines or len(lines) < 2:
        return False

    first_line_low = lines[0].lower()
    target_username = lines[1].lstrip("@").strip()

    # 1. СИНТАКСИС: "Фантом, записывай" (Создание / Перезапись)
    if first_line_low == "фантом, записывай":
        aliases = ""
        dossier_lines = []

        for line in lines[2:]:
            if line.lower().startswith("также "):
                aliases = line[6:].strip()
            else:
                dossier_lines.append(line)

        dossier_text = "\n".join(dossier_lines) if dossier_lines else "Характеристика не заполнена."
        
        existing = db.get_user_dossier_by_username(chat_id, target_username)
        user_id = existing.user_id if existing else 0

        db.save_user_dossier(chat_id, user_id, target_username, dossier_text, aliases=aliases)
        
        if clean_mode:
            await utils.set_reaction(ctx.message, "👍")
        else:
            reply_msg = f"Записал досье для {target_username}."
            if aliases:
                reply_msg += f" Псевдонимы: {aliases}"
            await utils.send_as_phantom(ctx.message, reply_msg)
        return True

    # 2. СИНТАКСИС: "Фантом, дополни" (Дополнение)
    if first_line_low == "фантом, дополни":
        new_aliases = ""
        fact_lines = []

        for line in lines[2:]:
            if line.lower().startswith("также "):
                new_aliases = line[6:].strip()
            else:
                fact_lines.append(line)

        fact_text = "\n".join(fact_lines) if fact_lines else ""
        
        existing = db.get_user_dossier_by_username(chat_id, target_username)
        user_id = existing.user_id if existing else 0

        db.append_user_dossier(chat_id, user_id, target_username, fact_text, new_aliases=new_aliases)
        
        if clean_mode:
            await utils.set_reaction(ctx.message, "👍")
        else:
            reply_msg = f"Дополнил досье для {target_username}."
            if new_aliases:
                reply_msg += f" Новые псевдонимы: {new_aliases}"
            await utils.send_as_phantom(ctx.message, reply_msg)
        return True

    # 3. СИНТАКСИС: "Фантом, вычеркивай" (Удаление)
    if first_line_low == "фантом, вычеркивай":
        deleted = db.clear_user_dossier_by_username(chat_id, target_username)
        if clean_mode:
            await utils.set_reaction(ctx.message, "👍" if deleted else "❌")
        else:
            if deleted:
                await utils.send_as_phantom(ctx.message, f"Вычеркнул {target_username} из списка досье.")
            else:
                await utils.send_as_phantom(ctx.message, f"Досье на {target_username} в этом чате не найдено.")
        return True

    return False


@router.on(EventType.COMMAND, pattern=r"(?i)^досье", admin_only=True, priority=20)
async def handle_legacy_dossier_event(ctx: EventContext) -> None:
    """
    @brief Обработчик legacy вызова команд управления досье по реплаю.
    """
    await handle_legacy_dossier_command(ctx.message, ctx.text, ctx.is_me)


async def handle_legacy_dossier_command(message: Any, text: str, is_me: bool) -> None:
    """
    @brief Поддержка классических админ-команд 'досье +', 'досье set', 'досье del' в реплае.
    """
    if not is_me:
        return

    chat_id = message.chat.id
    clean_mode = db.get_chat_clean_mode(chat_id)
    target_user = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    elif message.entities:
        for entity in message.entities:
            if entity.type == "text_mention" and entity.user:
                target_user = entity.user
                break

    if not target_user:
        if not clean_mode:
            await utils.send_as_phantom(message, "Ответь на сообщение пользователя (Reply) или напиши 'Фантом, записывай'.")
        return

    target_uname = target_user.username or str(target_user.id)

    # Установка набора имен
    if match := re.search(r"(?i)^досье\s+имена:\s*(.+)", text):
        aliases_raw = match.group(1).strip()
        current_dos = db.get_user_dossier(chat_id, target_user.id)
        current_text = current_dos.dossier_text if current_dos else "Характеристика не заполнена."
        db.save_user_dossier(chat_id, target_user.id, target_uname, current_text, aliases=aliases_raw)
        if clean_mode:
            await utils.set_reaction(message, "👍")
        else:
            await utils.send_as_phantom(message, f"Обновил псевдонимы для {target_user.first_name}: {aliases_raw}")
        return

    # Перезапись досье
    if match := re.search(r"(?i)^досье\s*set\s*(.+)", text):
        content = match.group(1).strip()
        db.save_user_dossier(chat_id, target_user.id, target_uname, content)
        if clean_mode:
            await utils.set_reaction(message, "👍")
        else:
            await utils.send_as_phantom(message, f"Зафиксировал характеристику для {target_user.first_name}.")
        return

    # Добавление нового факта
    if match := re.search(r"(?i)^досье\s*\+\s*(.+)", text):
        fact = match.group(1).strip()
        db.append_user_dossier(chat_id, target_user.id, target_uname, fact)
        if clean_mode:
            await utils.set_reaction(message, "👍")
        else:
            await utils.send_as_phantom(message, f"Обновил характеристики для {target_user.first_name}.")
        return

    # Удаление досье
    if re.search(r"(?i)^досье\s*del$", text):
        db.clear_user_dossier(chat_id, target_user.id)
        if clean_mode:
            await utils.set_reaction(message, "👍")
        else:
            await utils.send_as_phantom(message, f"Очистил досье для {target_user.first_name}.")
        return

@router.on(EventType.COMMAND, pattern=r"(?i)^фантом,?\s*(включи|подключи)\s+(ии\s*досье|гемм[уа]\s*досье)\b", admin_only=True, priority=29)
async def handle_gemma_dossier_on(ctx: EventContext) -> bool:
    db.set_chat_gemma_dossier_mode(ctx.chat_id, True)
    clean_mode = db.get_chat_clean_mode(ctx.chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, "ИИ-извлекатель досье (Gemma-4) подключен к работе 🟢")
    return True

@router.on(EventType.COMMAND, pattern=r"(?i)^фантом,?\s*(выключи|отключи)\s+(ии\s*досье|гемм[уа]\s*досье)\b", admin_only=True, priority=29)
async def handle_gemma_dossier_off(ctx: EventContext) -> bool:
    db.set_chat_gemma_dossier_mode(ctx.chat_id, False)
    clean_mode = db.get_chat_clean_mode(ctx.chat_id)
    if clean_mode:
        await utils.set_reaction(ctx.message, "👍")
    else:
        await utils.send_as_phantom(ctx.message, "ИИ-извлекатель досье (Gemma-4) отключен 🔴. Работает только локальный поиск.")
    return True
