import asyncio
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import modules.config as cfg
import modules.database as db
import modules.utils as utils
from modules.actions import admin, sync, voice


class TestUxAuditFixes(unittest.TestCase):
    def test_01_summary_and_dump_and_allow_list_patterns(self):
        self.assertTrue(re.search(cfg.SUMMARY_PATTERN, "!сводка"))
        m = re.search(cfg.SUMMARY_PATTERN, "!сводка 50")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "50")
        self.assertTrue(re.search(cfg.SUMMARY_PATTERN, "Фантом, сводка 30"))
        self.assertTrue(re.search(cfg.SUMMARY_PATTERN, "Фантом что происходит"))
        self.assertTrue(re.search(cfg.SUMMARY_PATTERN, "Фантом, че тут"))

        self.assertTrue(re.search(cfg.DUMP_PATTERN, "дамп"))
        self.assertTrue(re.search(cfg.DUMP_PATTERN, "Фантом, дамп 40"))
        self.assertTrue(re.search(admin.ALLOW_LIST_PATTERN, "Фантом, список чатов"))

    def test_02_format_media_text(self):
        photo_msg = SimpleNamespace(text=None, photo=True, video=None, animation=None, document=None, sticker=None, voice=None, video_note=None, audio=None, caption="Котик")
        self.assertEqual(utils.format_media_text(photo_msg), "[Фото] Котик")

        vn_msg = SimpleNamespace(text=None, photo=None, video=None, animation=None, document=None, sticker=None, voice=None, video_note=True, audio=None, caption=None)
        self.assertEqual(utils.format_media_text(vn_msg), "[Видео-кружочек]")

    def test_03_sber_busy_retry_detection(self):
        self.assertTrue(voice.is_sber_busy_retry("Наблюдаем повышенную активность пользователей. Бот вынужден пропускать некоторые сообщения в час пик. Попробуйте ещё раз."))
        self.assertFalse(voice.is_sber_busy_retry("Привет, как дела"))

    def test_04_voice_bg_queue_lowest_priority(self):
        async def _run():
            while not voice.sber_voice_queue.empty():
                voice.sber_voice_queue.get_nowait()
            while not voice.sber_voice_queue_long.empty():
                voice.sber_voice_queue_long.get_nowait()
            while not voice.sber_voice_queue_bg.empty():
                voice.sber_voice_queue_bg.get_nowait()

            voice.sber_voice_queue_bg.put_nowait(("bg",))
            voice.sber_voice_queue.put_nowait(("short",))

            item1, q1 = await voice.get_next_voice_item()
            self.assertEqual(item1, ("short",))
            q1.task_done()

            item2, q2 = await voice.get_next_voice_item()
            self.assertEqual(item2, ("bg",))
            q2.task_done()

        asyncio.run(_run())

    def test_05_sync_recovers_state_on_exception(self):
        async def _run():
            chat_id = -100999888
            ctx = sync.get_sync_context(chat_id)
            ctx.state = sync.STATE_QUEUED
            ctx.temp_buffer = [(999, "User", "Buffered", 123456)]

            bad_client = MagicMock()
            async def _failing_gen(*args, **kwargs):
                raise RuntimeError("Network error")
                yield  # pragma: no cover
            bad_client.get_chat_history = _failing_gen

            trigger_msg = MagicMock()
            trigger_msg.chat.id = chat_id

            with patch("modules.utils.send_as_phantom", new_callable=AsyncMock):
                await sync.run_sync(bad_client, trigger_msg, chat_id=chat_id, silent_status=True)

            self.assertEqual(ctx.state, sync.STATE_NORMAL)
            self.assertEqual(ctx.temp_buffer, [])

        asyncio.run(_run())

    def test_06_pm_restart_only_in_private(self):
        async def _run():
            group_ctx = SimpleNamespace(
                chat_id=-100123,
                message=SimpleNamespace(chat=SimpleNamespace(type=SimpleNamespace(name="SUPERGROUP"))),
            )
            res = await admin.handle_pm_restart(group_ctx)
            self.assertFalse(res)

        asyncio.run(_run())

    def test_07_provider_commands_pm_only(self):
        async def _run():
            pm_ctx = SimpleNamespace(
                chat_id=12345,
                match=re.search(admin.PROVIDER_SET_PATTERN, "Фантом, провайдер openrouter"),
                message=SimpleNamespace(chat=SimpleNamespace(id=12345, type=SimpleNamespace(name="PRIVATE"))),
            )
            with patch("modules.utils.send_as_phantom", new_callable=AsyncMock):
                res = await admin.handle_provider_command(pm_ctx)
            self.assertTrue(res)
            self.assertEqual(cfg.AI_PROVIDER_MODE, "openrouter")

            # Сбрасываем обратно в auto
            cfg.AI_PROVIDER_MODE = "auto"

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
