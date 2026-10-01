"""
@file dossier.py
@brief Закрытый админ-модуль управления приватными характеристиками/досье пользователей и их псевдонимами.
@details Доступен ТОЛЬКО Никитосу (is_me). Запросы обрабатываются на месте БЕЗ роутинга в ИИ.
         В чистом режиме (clean_mode) мгновенно подстверждается реакцией '👍'.
"""

import re
from typing import Any, Tuple, Optional
import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.router import router, EventType, EventContext


def parse_dossier_input(raw_text: str) -> Optional[Tuple[str, str, str, str]]:
    """
    @brief Парсит структурированное сообщение управления досье по новому формату.
    @details
    Формат:
      Команда (Фантом, записывай / дополни / вычеркивай)
      тег без собачки, строго одно неразрывное слово
      (один или более энтеров)
      псевдонимы (каждый с новой строки, ровно один энтер между псевдонимами, могут состоять из 2-3 слов)
      (два или более энтеров)
      текст досье (любые пробелы, переносы строк, форматирование)
    @return (command_type, username, aliases, dossier_text) или None.
    """
    match = re.match(r"(?i)^фантом,?\s*(записывай|дополни|вычеркивай)\b", raw_text.strip())
    if not match:
        return None

    cmd = match.group(1).lower()
    rest = raw_text.strip()[match.end():].strip()

    if cmd == "вычеркивай":
        uname = rest.split()[0].lstrip("@") if rest else ""
        return cmd, uname, "", ""

    blocks = re.split(r"\n\s*\n+", rest)
    if not blocks or not blocks[0].strip():
        return None

    first_block_lines = [l.strip() for l in blocks[0].splitlines() if l.strip()]
    if not first_block_lines:
        return None

    username = first_block_lines[0].lstrip("@").split()[0]
    aliases_list = []
    dossier_text = ""

    if len(first_block_lines) > 1:
        # Псевдонимы шли сразу под юзернеймом через один энтер
        for line in first_block_lines[1:]:
            clean_l = re.sub(r"(?i)^(также|псевдонимы|имена|клички)[:\s]*", "", line).strip()
            if clean_l:
                aliases_list.extend([a.strip() for a in clean_l.split(";") if a.strip()])
        if len(blocks) > 1:
            dossier_text = "\n\n".join(blocks[1:]).strip()
    else:
        # В первом блоке был только юзернейм
        if len(blocks) == 2:
            second_lines = [l.strip() for l in blocks[1].splitlines() if l.strip()]
            if any(re.match(r"(?i)^(также|псевдонимы|имена|клички)", l) for l in second_lines):
                for l in second_lines:
                    clean_l = re.sub(r"(?i)^(также|псевдонимы|имена|клички)[:\s]*", "", l).strip()
                    if clean_l:
                        aliases_list.extend([a.strip() for a in clean_l.split(";") if a.strip()])
            else:
                dossier_text = blocks[1].strip()
        elif len(blocks) >= 3:
            second_lines = [l.strip() for l in blocks[1].splitlines() if l.strip()]
            for l in second_lines:
                clean_l = re.sub(r"(?i)^(также|псевдонимы|имена|клички)[:\s]*", "", l).strip()
                if clean_l:
                    aliases_list.extend([a.strip() for a in clean_l.split(";") if a.strip()])
            dossier_text = "\n\n".join(blocks[2:]).strip()

    # Дедупликация алиасов без учета регистра с сохранением исходного порядка
    seen = set()
    uniq_aliases = []
    for a in aliases_list:
        low = a.lower()
        if low not in seen and low != username.lower():
            seen.add(low)
            uniq_aliases.append(a)

    return cmd, username, ";".join(uniq_aliases), dossier_text


@router.on(EventType.COMMAND, pattern=r"(?i)^фантом,\s*(записывай|дополни|вычеркивай)", admin_only=True, priority=30)
async def handle_new_dossier_syntax_event(ctx: EventContext) -> bool:
    """
    @brief Обработчик трех синтаксисов управления досье по первому строковому заголовку.
    @details Поддерживает новый формат: тег -> псевдонимы (по строкам) -> 2 энтера -> текст досье.
    """
    parsed = parse_dossier_input(ctx.text)
    if not parsed:
        return False

    cmd, target_username, aliases, dossier_text = parsed
    if not target_username:
        return False

    chat_id = ctx.chat_id
    clean_mode = db.get_chat_clean_mode(chat_id)

    # 1. СИНТАКСИС: "Фантом, записывай" (Создание / Перезапись)
    if cmd == "записывай":
        existing = db.get_user_dossier_by_username(chat_id, target_username)
        user_id = existing.user_id if existing else 0
        final_text = dossier_text if dossier_text else "Характеристика не заполнена."

        db.save_user_dossier(chat_id, user_id, target_username, final_text, aliases=aliases)

        if clean_mode:
            await utils.set_reaction(ctx.message, "👍")
        else:
            reply_msg = f"Записал досье для {target_username}."
            if aliases:
                reply_msg += f"\nПсевдонимы: {aliases}"
            await utils.send_as_phantom(ctx.message, reply_msg)
        return True

    # 2. СИНТАКСИС: "Фантом, дополни" (Дополнение)
    if cmd == "дополни":
        existing = db.get_user_dossier_by_username(chat_id, target_username)
        user_id = existing.user_id if existing else 0

        db.append_user_dossier(chat_id, user_id, target_username, dossier_text, new_aliases=aliases)

        if clean_mode:
            await utils.set_reaction(ctx.message, "👍")
        else:
            reply_msg = f"Дополнил досье для {target_username}."
            if aliases:
                reply_msg += f"\nНовые псевдонимы: {aliases}"
            await utils.send_as_phantom(ctx.message, reply_msg)
        return True

    # 3. СИНТАКСИС: "Фантом, вычеркивай" (Удаление)
    if cmd == "вычеркивай":
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
