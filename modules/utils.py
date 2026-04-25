import modules.database as db

async def format_msg(msg):
    if not msg or not msg.text: return None
    author = "Я (Фантом)" if (msg.from_user and msg.from_user.is_self) else (msg.from_user.first_name if msg.from_user else "Unknown")
    if msg.reply_to_message:
        r = msg.reply_to_message
        r_author = "Я (Фантом)" if (r.from_user and r.from_user.is_self) else (r.from_user.first_name if r.from_user else "Unknown")
        snippet = " ".join((r.text or "").split()[:3]) + "..."
        author = f"{author} ответ {r_author} на \"{snippet}\""
    return (msg.id, author, msg.text, msg.date)

async def send_as_phantom(message, text, edit_message=None):
    """Отправляет/редактирует сообщение и сразу пишет в БД"""
    if edit_message:
        sent = await edit_message.edit_text(text)
        db.update_message_text(sent.id, text)
    else:
        sent = await message.reply_text(text)
        data = await format_msg(sent)
        if data: db.save_message(*data)
    return sent