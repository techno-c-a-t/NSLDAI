import modules.config as cfg
from modules.ai_service import call_ai

async def get_chat_summary(messages_list, user_api_key, user_id, username=None):
    if not messages_list: return "В чате пока тихо."
    
    context = "\n".join(messages_list)
    prompt = cfg.AI_PROMPTS["summary_user"].format(context=context)
    
    res = await call_ai(user_id, username, user_api_key, cfg.AI_PROMPTS["summary_system"], prompt)
    
    # Очистка префиксов
    for p in ["вот что я нарыл:", "фантом:", "я нарыл:"]:
        if res.lower().startswith(p): res = res[len(p):].strip()
    return res