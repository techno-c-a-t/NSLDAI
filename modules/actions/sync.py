import asyncio
import modules.config as cfg
import modules.database as db
import modules.utils as utils

STATE_NORMAL, STATE_WAITING_SYNC = "NORMAL", "WAITING_SYNC"
current_state = STATE_WAITING_SYNC
temp_buffer = []

async def run_sync(client, trigger_msg):
    global current_state, temp_buffer
    max_id = db.get_max_id_in_db()
    fetched, total_needed = [], 2000
    last_id = temp_buffer[0][0] if temp_buffer else trigger_msg.id
    found_gap = False

    async for old_msg in client.get_chat_history(cfg.TARGET_CHAT_ID, limit=total_needed, offset_id=last_id):
        if not old_msg.text: continue
        if old_msg.id <= max_id:
            found_gap = True; break
        data = await utils.format_msg(old_msg)
        if data: fetched.append(data)
        if len(fetched) % 25 == 0: await asyncio.sleep(0.2)
    
    if not found_gap: db.clear_db()
    for m in reversed(fetched): db.save_message(*m)
    for m in temp_buffer: db.save_message(*m)
    
    temp_buffer, current_state = [], STATE_NORMAL
    msg = "В теме" if found_gap else f"Многа букаф, ниасилил. Последние {total_needed}"
    await utils.send_as_phantom(trigger_msg, msg)