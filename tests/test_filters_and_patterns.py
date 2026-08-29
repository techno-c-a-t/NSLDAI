import unittest
import re
from unittest.mock import MagicMock

import modules.config as cfg
import modules.actions.voice as voice

class TestFiltersAndPatterns(unittest.TestCase):

    def test_01_allowed_chats_filtering(self):
        """Проверка отсечения неограниченных/неразрешенных чатов ('Топор')"""
        cfg.ALLOWED_CHAT_IDS = {-100111111, -100222222}
        
        self.assertTrue(cfg.is_chat_allowed(-100111111))
        self.assertTrue(cfg.is_chat_allowed(-100222222))
        
        # Чат "Топор" (-100999999) не в списке -> должен быть заблокирован
        self.assertFalse(cfg.is_chat_allowed(-100999999))
        self.assertFalse(cfg.is_chat_allowed(123456))

    def test_02_music_track_detection(self):
        """Проверка детектора музыкальных файлов (отличие ГС от песен)"""
        # 1. Голосовая заметка (Voice) короткая -> НЕ музыка
        short_voice = MagicMock()
        short_voice.voice.duration = 45
        short_voice.audio = None
        self.assertFalse(voice.is_music_track(short_voice))

        # 2. Голосовая заметка длиннее 3 мин (181 сек) -> Считается возможной музыкой/пением
        long_voice = MagicMock()
        long_voice.voice.duration = 200
        long_voice.audio = None
        self.assertTrue(voice.is_music_track(long_voice))

        # 3. Аудиофайл (Audio, например .mp3) -> ВСЕГДА Музыка
        audio_msg = MagicMock()
        audio_msg.voice = None
        audio_msg.audio.performer = "Linkin Park"
        audio_msg.audio.title = "Numb"
        self.assertTrue(voice.is_music_track(audio_msg))

    def test_03_exact_phantom_reply_pattern(self):
        """Проверка строгого регекса реплая 'Фантом' (только одно слово, никаких фраз)"""
        EXACT_PATTERN = r"^(@tech_phantom|[йy][оoаa]+,?\s*)?(фантом(чик|ушка|ас)?|phantom|fantom)[!?.~]*$"

        # Положительные совпадения (ДОЛЖНЫ расшифровать)
        self.assertTrue(bool(re.match(EXACT_PATTERN, "Фантом", re.IGNORECASE)))
        self.assertTrue(bool(re.match(EXACT_PATTERN, "фантом", re.IGNORECASE)))
        self.assertTrue(bool(re.match(EXACT_PATTERN, "Фантом!", re.IGNORECASE)))
        self.assertTrue(bool(re.match(EXACT_PATTERN, "@tech_phantom", re.IGNORECASE)))
        self.assertTrue(bool(re.match(EXACT_PATTERN, "phantom...", re.IGNORECASE)))
        self.assertTrue(bool(re.match(EXACT_PATTERN, "Йо, фантом", re.IGNORECASE)))

        # Отрицательные совпадения (НЕ ДОЛЖНЫ расшифровывать)
        self.assertFalse(bool(re.match(EXACT_PATTERN, "Ты прямо как фантом", re.IGNORECASE)))
        self.assertFalse(bool(re.match(EXACT_PATTERN, "Фантом переведи это", re.IGNORECASE)))
        self.assertFalse(bool(re.match(EXACT_PATTERN, "Фантом, ты тут?", re.IGNORECASE)))
        self.assertFalse(bool(re.match(EXACT_PATTERN, "Привет фантом", re.IGNORECASE)))

    def test_04_admin_humanized_voice_mode_regex(self):
        """Проверка админских команд смены режима расшифровки ГС"""
        AUTO_PATTERN = r"(?i)^фантом,?\s*(слушай все гс|авто\s*гс)"
        ON_DEMAND_PATTERN = r"(?i)^фантом,?\s*(расшифровывай только по запросу|гс по запросу)"

        self.assertTrue(bool(re.search(AUTO_PATTERN, "Фантом, слушай все гс")))
        self.assertTrue(bool(re.search(AUTO_PATTERN, "фантом авто гс")))

        self.assertTrue(bool(re.search(ON_DEMAND_PATTERN, "Фантом, расшифровывай только по запросу")))
        self.assertTrue(bool(re.search(ON_DEMAND_PATTERN, "фантом гс по запросу")))

    def test_05_phantom_names_pattern_boundaries(self):
        """Проверка регекса обращения Фантом с учетом запятых, кавычек, абзацев и границ слова"""
        pat = cfg.PHANTOM_NAMES_PATTERN

        # Должны совпадать (обращения, запятые, кавычки, абзацы)
        self.assertTrue(bool(re.search(pat, "Фантом, привет!")))
        self.assertTrue(bool(re.search(pat, "Эй, Фантом!")))
        self.assertTrue(bool(re.search(pat, "«Фантом»")))
        self.assertTrue(bool(re.search(pat, "\nФантом,\nкак дела?")))
        self.assertTrue(bool(re.search(pat, "(Фантом)")))

        # НЕ должны совпадать (склеенные части других слов)
        self.assertFalse(bool(re.search(pat, "суперфантомщик")))
        self.assertFalse(bool(re.search(pat, "фантомомания")))

if __name__ == "__main__":
    unittest.main()
