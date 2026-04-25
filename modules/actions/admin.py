import modules.config as cfg
import modules.database as db
import modules.utils as utils

async def do_dump(message, count_str):
    count = int(count_str)
    if count > 100: resp = "Много хочешь"
    else:
        hist = db.get_history_from_db(count)
        if len(hist) < count: resp = f"Помню только {len(hist)}"
        else:
            if count <= 20: 
                print(f"\n--- ДАМП ---\n" + "\n".join(hist))
                resp = "В консоли"
            else:
                with open(cfg.DUMP_FILE, "w") as f: f.write("\n".join(hist))
                resp = f"В файле {cfg.DUMP_FILE}"
    await utils.send_as_phantom(message, resp)