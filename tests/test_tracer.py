import unittest
import asyncio
from unittest.mock import MagicMock

from modules.actions.tracer import format_json_chunks

class TestTracerModule(unittest.TestCase):

    def test_01_small_json_single_chunk(self):
        """Проверка форматирования небольшого JSON в 1 блок"""
        data = {
            "event": "test_event",
            "status": "success",
            "details": "Small payload"
        }
        chunks = format_json_chunks(data)
        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0].startswith("```json\n"))
        self.assertTrue(chunks[0].endswith("\n```"))
        self.assertIn('"event": "test_event"', chunks[0])

    def test_02_large_json_chunk_splitting(self):
        """Проверка автоматического разбиения гигантского JSON (> 3800 символов) на чанки с нумерацией"""
        large_list = [f"Item number {i} with long repetitive text data block for payload testing" for i in range(200)]
        data = {
            "event": "large_dump",
            "items": large_list
        }
        chunks = format_json_chunks(data, max_chunk_size=1000)
        
        self.assertGreater(len(chunks), 1)
        self.assertIn("// [Чанк 1/", chunks[0])
        self.assertTrue(chunks[0].startswith("```json\n"))
        self.assertTrue(chunks[0].endswith("\n```"))

    def test_03_huge_single_line_prompt_splitting(self):
        """Проверка резки монолитных строк без переносов строк (одна строка на 10 000 символов)"""
        huge_prompt = "X" * 10000
        data = {
            "event": "huge_prompt",
            "prompt": huge_prompt
        }
        chunks = format_json_chunks(data, max_chunk_size=3000)
        
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4000)

if __name__ == "__main__":
    unittest.main()
