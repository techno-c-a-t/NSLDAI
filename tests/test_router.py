import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from modules.router import EventRouter, EventType, EventContext

class TestEventRouter(unittest.TestCase):

    def test_01_router_subscription_and_priority(self):
        """Проверка регистрации подписчиков по типам событий и их приоритету"""
        test_router = EventRouter()
        calls = []

        @test_router.on(EventType.COMMAND, pattern=r"(?i)^тест", priority=10)
        async def handler1(ctx):
            calls.append("handler1")
            return True

        @test_router.on(EventType.COMMAND, pattern=r"(?i)^тест", priority=20)
        async def handler2(ctx):
            calls.append("handler2")
            return False # Возврат False разрешает продолжение цепи

        mock_msg = MagicMock()
        mock_msg.chat.id = -1001
        mock_msg.text = "Тест"
        mock_msg.from_user.username = "user"
        mock_msg.from_user.is_self = False

        ctx = EventContext(MagicMock(), mock_msg, text="Тест")

        # Диспатчим событие
        asyncio.run(test_router.dispatch(ctx, EventType.COMMAND))

        # Так как handler2 имеет более высокий приоритет (20), он вызовется первым
        self.assertEqual(calls, ["handler2", "handler1"])

    def test_02_admin_only_permission_check(self):
        """Проверка ограничения доступа только для администратора (is_me)"""
        test_router = EventRouter()
        calls = []

        @test_router.on(EventType.COMMAND, pattern=r"(?i)^секрет", admin_only=True)
        async def admin_handler(ctx):
            calls.append("admin_called")

        mock_msg = MagicMock()
        mock_msg.chat.id = -1001
        mock_msg.text = "Секрет"
        
        # 1. Запрос от обычного пользователя -> не должен вызываться
        mock_msg.from_user.username = "user"
        mock_msg.from_user.is_self = False
        ctx_user = EventContext(MagicMock(), mock_msg, text="Секрет")
        asyncio.run(test_router.dispatch(ctx_user, EventType.COMMAND))
        self.assertEqual(len(calls), 0)

        # 2. Запрос от админа (is_me) -> должен вызваться
        import modules.config as cfg
        mock_msg.from_user.username = cfg.MY_USERNAME
        mock_msg.from_user.is_self = True
        ctx_admin = EventContext(MagicMock(), mock_msg, text="Секрет")
        asyncio.run(test_router.dispatch(ctx_admin, EventType.COMMAND))
        self.assertEqual(calls, ["admin_called"])

if __name__ == "__main__":
    unittest.main()
