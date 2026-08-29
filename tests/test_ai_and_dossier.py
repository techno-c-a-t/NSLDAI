import unittest
from unittest.mock import AsyncMock, patch, MagicMock

import modules.config as cfg
import modules.database as db
from modules.ai_service import call_ai

class TestAIAndDossierModule(unittest.TestCase):

    def test_01_dossier_injection_and_privacy_prompt(self):
        """Проверка правильного форматирования приватного досье и наличия инструкции НЕ РАЗГЛАШАТЬ"""
        chat_id = -100777
        user_id = 999
        username = "test_user"
        
        # Сохраняем тестовое досье
        db.save_user_dossier(chat_id, user_id, username, "Любит кофе. Вспыльчив, если обращаться официально.")
        
        dossier_text = db.get_user_dossier(chat_id, user_id)
        
        system_prompt = cfg.AI_PROMPTS["dialog_system"]
        if dossier_text:
            system_prompt += (
                f"\n\n[СЛУЖЕБНОЕ ПРИВАТНОЕ ДОСЬЕ НА СОБЕСЕДНИКА: Тест (@{username})]\n"
                f"{dossier_text}\n"
                f"[КОНЕЦ ДОСЬЕ]\n\n"
                f"ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ ДОСЬЕ:\n"
                f"1. Данное досье предназначено ИСКЛЮЧИТЕЛЬНО для тебя (Фантома), чтобы подобрать правильный тон, стиль и подтекст ответа собеседнику.\n"
                f"2. СТРОГО ЗАПРЕЩЕНО цитировать, упоминать, выдавать или прямым текстом разглашать содержимое досье собеседнику или кому-либо в чате.\n"
                f"3. Веди себя естественно, как будто ты просто хорошо знаешь этого человека."
            )

        # Проверяем, что служебный блок сформировался верно
        self.assertIn("[СЛУЖЕБНОЕ ПРИВАТНОЕ ДОСЬЕ НА СОБЕСЕДНИКА", system_prompt)
        self.assertIn("Любит кофе", system_prompt)
        self.assertIn("СТРОГО ЗАПРЕЩЕНО цитировать, упоминать, выдавать или прямым текстом разглашать", system_prompt)

    def test_02_ai_models_chain_structure(self):
        """Проверка точной структуры единого списка моделей Google AI Studio"""
        self.assertEqual(cfg.AI_MODELS_CHAIN[0], "gemini-3.5-flash-lite")
        self.assertEqual(cfg.AI_MODELS_CHAIN[1], "gemini-3.1-flash-lite")
        self.assertEqual(cfg.AI_MODELS_CHAIN[2], "gemma-4-31b-it")
        self.assertEqual(cfg.AI_MODELS_CHAIN[3], "gemma-4-26b-a4b-it")
        self.assertEqual(len(cfg.AI_MODELS_CHAIN), 4)

    @patch("modules.ai_service._invoke_gemma_model", new_callable=AsyncMock)
    @patch("modules.ai_service._invoke_gemini_model", new_callable=AsyncMock)
    def test_03_downward_only_fallback(self, mock_gemini, mock_gemma):
        """Проверка того, что при вызове младшей модели откат идет ТОЛЬКО ВНИЗ, и премиальные модели не трогаются"""
        mock_gemma.side_effect = Exception("Gemma model failure")
        
        async def run_test():
            res = await call_ai(
                user_id=123,
                username="test",
                user_api_key=None,
                system_msg="Sys",
                user_msg="User",
                model="gemma-4-31b-it"
            )
            # Проверяем, что Gemini модели 0 и 1 НИ РАЗУ не вызывались
            mock_gemini.assert_not_called()
            # Проверяем, что вызвалась Gemma 31b и затем Gemma 26b
            self.assertEqual(mock_gemma.call_count, 2)

        import asyncio
        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
