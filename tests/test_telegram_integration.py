import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import modules.config as cfg
import modules.database as db
import modules.actions.voice as voice
import main

class TestTelegramIntegration(unittest.TestCase):

    def setUp(self):
        db.init_db()
        cfg.ALLOWED_CHAT_IDS = {-100100200}
        cfg.MY_USERNAME = "nikitos_admin"

    def test_01_unallowed_chat_ignored_completely(self):
        """Сообщения из незарегистрированных чатов (например, 'Топор') НЕ должны сохраняться в БД"""
        unallowed_msg = MagicMock()
        unallowed_msg.chat.id = -100999999 # Неразрешенный чат Топор
        unallowed_msg.text = "Свежая новость от Топора!"
        unallowed_msg.from_user.username = "topor_news"
        unallowed_msg.from_user.is_self = False

        # Вызываем main_handler
        asyncio.run(main.main_handler(MagicMock(), unallowed_msg))

        # База данных не должна содержать эту таблицу или эти сообщения
        hist = db.get_history_from_db(-100999999, 10)
        self.assertEqual(len(hist), 0)

    def test_02_allowed_chat_saved_to_db(self):
        """Сообщения из разрешенного чата должны сохраняться в персональную таблицу БД"""
        allowed_msg = MagicMock()
        allowed_msg.chat.id = -100100200
        allowed_msg.chat.title = "Тестовая Группа"
        allowed_msg.id = 55
        allowed_msg.text = "Привет фантом!"
        allowed_msg.from_user.username = "ordinary_user"
        allowed_msg.from_user.first_name = "Иван"
        allowed_msg.from_user.is_self = False

        asyncio.run(main.main_handler(MagicMock(), allowed_msg))

        hist = db.get_history_from_db(-100100200, 10)
        self.assertGreater(len(hist), 0)
        self.assertIn("Привет фантом!", hist[0])

    @patch("modules.utils.send_as_phantom", new_callable=AsyncMock)
    def test_03_admin_humanized_voice_mode_commands(self, mock_send_phantom):
        """Админ-команды очеловеченного изменения режима ГС только от Никитоса"""
        chat_id = -100100200
        
        # 1. Запрос от НЕ-админа (обычный юзер) -> команда не должна сработать
        user_msg = MagicMock()
        user_msg.chat.id = chat_id
        user_msg.text = "Фантом, расшифровывай только по запросу"
        user_msg.from_user.username = "random_user"
        user_msg.from_user.is_self = False

        asyncio.run(main.main_handler(MagicMock(), user_msg))
        self.assertEqual(db.get_chat_voice_mode(chat_id), 'AUTO')

        # 2. Запрос от Никитоса (админ, is_me) -> должен переключить в ON_DEMAND
        admin_msg = MagicMock()
        admin_msg.chat.id = chat_id
        admin_msg.text = "Фантом, расшифровывай только по запросу"
        admin_msg.from_user.username = "nikitos_admin"
        admin_msg.from_user.is_self = True

        asyncio.run(main.main_handler(MagicMock(), admin_msg))
        self.assertEqual(db.get_chat_voice_mode(chat_id), 'ON_DEMAND')

        # 3. Переключаем обратно в AUTO
        admin_msg.text = "Фантом, слушай все гс"
        asyncio.run(main.main_handler(MagicMock(), admin_msg))
        self.assertEqual(db.get_chat_voice_mode(chat_id), 'AUTO')

    @patch("modules.actions.voice.sber_voice_queue.put", new_callable=AsyncMock)
    @patch("modules.utils.send_as_phantom", new_callable=AsyncMock)
    def test_04_exact_phantom_reply_to_voice(self, mock_send_phantom, mock_queue_put):
        """Реплай строго словом 'Фантом' на ГС вызывает принудительную расшифровку"""
        reply_voice_msg = MagicMock()
        reply_voice_msg.voice.duration = 10
        reply_voice_msg.audio = None

        trigger_msg = MagicMock()
        trigger_msg.chat.id = -100100200
        trigger_msg.text = "Фантом"
        trigger_msg.from_user.username = "user"
        trigger_msg.from_user.is_self = False
        trigger_msg.reply_to_message = reply_voice_msg

        asyncio.run(main.main_handler(MagicMock(), trigger_msg))

        # Очередь должна зафиксировать запуск с force=True
        mock_queue_put.assert_called_once_with(reply_voice_msg)

if __name__ == "__main__":
    unittest.main()
