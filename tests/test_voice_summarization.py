import unittest
from unittest.mock import MagicMock
from modules.actions.voice import VoiceContext, is_no_speech, is_sber_error

class TestVoiceModule(unittest.TestCase):
    def test_voice_context_init(self):
        msg = MagicMock()
        ctx = VoiceContext(msg)
        self.assertEqual(ctx.collected_messages, {})
        self.assertIsNone(ctx.debounce_task)

    def test_is_no_speech(self):
        self.assertTrue(is_no_speech("Аудио без речи"))
        self.assertTrue(is_no_speech("Не удалось ничего распознать"))
        self.assertFalse(is_no_speech("Привет мир"))

    def test_is_sber_error(self):
        self.assertEqual(is_sber_error("Слишком большое аудиофайл 8MB"), "limit")
        self.assertEqual(is_sber_error("Данный тип файла не поддерживается"), "format")
        self.assertIsNone(is_sber_error("Обычная речь"))

if __name__ == "__main__":
    unittest.main()
