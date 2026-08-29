import os
import unittest
import tempfile
import time

# Подменяем имя БД на временную тестовую файл-БД
import modules.config as cfg
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(test_db_fd)
cfg.DB_NAME = test_db_path

import modules.database as db

class TestDatabaseModule(unittest.TestCase):

    def setUp(self):
        db.init_db()

    def tearDown(self):
        pass

    def test_01_master_table_registration(self):
        """Проверка регистрации чатов в мастер-таблице"""
        db.register_chat(-1001234567, "Тестовый Чат 1", "community_alpha")
        db.register_chat(-1009876543, "Тестовый Чат 2", "community_beta")
        
        # Проверяем, что таблицы сообщений создались
        conn = db.get_connection()
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        
        self.assertIn("chats_master", tables)
        self.assertIn("messages_chat_1001234567", tables)
        self.assertIn("messages_chat_1009876543", tables)
        self.assertIn("user_dossiers", tables)

    def test_02_per_chat_message_isolation(self):
        """Проверка полной изоляции историй сообщений между разными чатами"""
        chat1 = -100111
        chat2 = -100222
        
        db.save_message(chat1, 100, "Никита", "Сообщение в чате 1", 1700000000)
        db.save_message(chat2, 100, "Алексей", "Сообщение в чате 2 с тем же ID!", 1700000005)
        
        hist1 = db.get_history_from_db(chat1, 10)
        hist2 = db.get_history_from_db(chat2, 10)
        
        self.assertEqual(len(hist1), 1)
        self.assertEqual(len(hist2), 1)
        self.assertIn("Сообщение в чате 1", hist1[0])
        self.assertIn("Сообщение в чате 2", hist2[0])

    def test_03_message_rotation_limit(self):
        """Проверка автоматической обрезки истории до 500 сообщений"""
        chat_id = -100333
        for i in range(1, 550):
            db.save_message(chat_id, i, "User", f"Message {i}", 1700000000 + i)
            
        hist = db.get_history_from_db(chat_id, 1000)
        self.assertEqual(len(hist), 500)
        self.assertIn("Message 549", hist[-1])
        # Старое сообщение #1 должно было удалиться
        self.assertEqual(db.get_max_id_in_db(chat_id), 549)

    def test_04_user_dossiers_per_chat(self):
        """Проверка привязки досье строго к паре (chat_id, user_id)"""
        user_id = 777
        chatA = -100100
        chatB = -100200
        
        # Записываем разные досье для одного и того же юзера в двух разных чатах
        db.save_user_dossier(chatA, user_id, "techno_cat", "В чате А: спокойный и молчаливый")
        db.save_user_dossier(chatB, user_id, "techno_cat", "В чате Б: гиперактивный тролль")
        
        dossierA = db.get_user_dossier(chatA, user_id)
        dossierB = db.get_user_dossier(chatB, user_id)
        
        self.assertEqual(dossierA, "В чате А: спокойный и молчаливый")
        self.assertEqual(dossierB, "В чате Б: гиперактивный тролль")
        
        # Дозапись факта
        db.append_user_dossier(chatA, user_id, "techno_cat", "Любит кошек")
        updatedA = db.get_user_dossier(chatA, user_id)
        self.assertIn("спокойный", updatedA)
        self.assertIn("Любит кошек", updatedA)
        
        # Удаление досье в чате А не должно затронуть чат Б
        db.clear_user_dossier(chatA, user_id)
        self.assertIsNone(db.get_user_dossier(chatA, user_id))
        self.assertIsNotNone(db.get_user_dossier(chatB, user_id))

    def test_05_chat_voice_mode_settings(self):
        """Проверка сохранения настроек режима ГС (AUTO / ON_DEMAND)"""
        chat_id = -100555
        db.register_chat(chat_id, "Чат Настроек")
        
        # По умолчанию 'AUTO'
        self.assertEqual(db.get_chat_voice_mode(chat_id), 'AUTO')
        
        # Переключаем в 'ON_DEMAND'
        db.set_chat_voice_mode(chat_id, 'ON_DEMAND')
        self.assertEqual(db.get_chat_voice_mode(chat_id), 'ON_DEMAND')
        
        # Возвращаем в 'AUTO'
        db.set_chat_voice_mode(chat_id, 'AUTO')
        self.assertEqual(db.get_chat_voice_mode(chat_id), 'AUTO')

if __name__ == "__main__":
    unittest.main()
