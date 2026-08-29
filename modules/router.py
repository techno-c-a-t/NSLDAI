"""
@file router.py
@brief Реестр плагинов и шина событий (Event Bus Router) для Telegram-бота Фантом.
@details Модуль реализует событийно-ориентированную архитектуру (Event-Driven Plugin Architecture).
         Позволяет автоматически находить плагины из папки modules/actions и подписывать их на события.
"""

import re
import os
import importlib
import pkgutil
import logging
from enum import Enum, auto
from typing import Callable, Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class EventType(Enum):
    """
    @brief Перечисление поддерживаемых типов событий Telegram.
    """
    TEXT_MESSAGE = auto()     #< Обычные текстовые сообщения
    COMMAND = auto()          #< Команды и регулярные выражения (Саммари, Хелп, Дамп)
    DIALOG = auto()           #< Обращение к Фантому (@tech_phantom или реплай)
    VOICE_AUDIO = auto()      #< Голосовые сообщения (.ogg) и аудиотреки (.mp3)
    EXACT_REPLY = auto()      #< Строгий реплай со словом "Фантом" на ГС
    SBER_UPDATE = auto()      #< Сообщения и транскрипция от Сбер Спич Бота
    GIGACHAT_UPDATE = auto()  #< Сообщения от GigaChat Бота


class EventContext:
    """
    @brief Единый контейнер (контекст) события, передаваемый во все плагины-обработчики.
    """
    def __init__(self, message: Any, chat_id: Optional[int] = None, user_id: Optional[int] = None, username: Optional[str] = None, text: Optional[str] = None, match: Optional[re.Match] = None):
        """
        @brief Инициализатор контекста события.
        @param message Объект входящего сообщения Pyrogram Message.
        @param chat_id ID чата.
        @param user_id ID пользователя.
        @param username Юзернейм пользователя.
        @param text Очищенный текст сообщения.
        @param match Объект совпадения регулярного выражения (re.Match).
        """
        self.message = message
        self.chat_id: int = chat_id if chat_id is not None else (message.chat.id if message and message.chat else 0)
        
        user = message.from_user if message else None
        self.user = user
        self.user_id: int = user_id if user_id is not None else (user.id if user else 0)
        self.username: Optional[str] = username if username is not None else (user.username if user else None)
        
        import modules.config as cfg
        self.is_me: bool = bool(user and (user.username == cfg.MY_USERNAME or user.is_self))
        self.text: str = text if text is not None else (message.text.strip() if message and message.text else "")
        self.match: Optional[re.Match] = match


class EventRouter:
    """
    @brief Центральный маршрутизатор событий и менеджер реестра плагинов.
    """
    def __init__(self):
        """
        @brief Конструктор маршрутизатора. Инициализирует пустой список подписчиков.
        """
        self.subscribers: List[Dict[str, Any]] = []

    def on(self, event_type: EventType, pattern: Optional[str] = None, admin_only: bool = False, priority: int = 10):
        """
        @brief Декоратор для подписки функции на тип события Telegram.
        """
        def decorator(func: Callable):
            regex = re.compile(pattern, re.IGNORECASE) if pattern else None
            self.subscribers.append({
                'event_type': event_type,
                'pattern': pattern,
                'regex': regex,
                'admin_only': admin_only,
                'priority': priority,
                'handler': func
            })
            self.subscribers.sort(key=lambda x: x['priority'], reverse=True)
            return func
        return decorator

    def load_plugins(self, package_name: str = "modules.actions") -> None:
        """
        @brief Динамически находит и импортирует все Python-модули в указанном пакете.
        """
        try:
            package = importlib.import_module(package_name)
            package_path = package.__path__
            
            for _, module_name, is_pkg in pkgutil.iter_modules(package_path):
                if not is_pkg and not module_name.startswith("__"):
                    full_module_name = f"{package_name}.{module_name}"
                    importlib.import_module(full_module_name)
                    logger.info(f"🔌 Загружен плагин: {full_module_name}")
        except Exception as e:
            logger.error(f"Ошибка автоматической загрузки плагинов из {package_name}: {e}")

    async def dispatch(self, ctx: EventContext, event_type: Optional[EventType] = None) -> bool:
        """
        @brief Маршрутизирует входящее событие по зарегистрированным плагинам-подписчикам.
        """
        handled = False
        target_event_type = event_type or EventType.TEXT_MESSAGE

        for sub in self.subscribers:
            # 1. Проверка совпадения типа события
            if sub['event_type'] != target_event_type:
                continue

            # 2. Проверка прав администратора
            if sub['admin_only'] and not ctx.is_me:
                logger.info(f"🔒 [ROUTER] Обработчик {sub['handler'].__name__} пропущен (требуются права админа is_me=False)")
                continue

            # 3. Проверка соответствия регулярного выражения
            match = None
            if sub['regex']:
                if not ctx.text:
                    continue
                match = sub['regex'].search(ctx.text)
                if not match:
                    continue
                ctx.match = match

            # 4. Вызов обработчика
            try:
                logger.info(f"🎯 [ROUTER] Вызов обработчика {sub['handler'].__name__} (Event={target_event_type.name}, Pattern='{sub['pattern']}')")
                res = await sub['handler'](ctx)
                handled = True
                if res is not False:
                    break
            except Exception as e:
                logger.exception(f"💥 Ошибка при исполнении обработчика {sub['handler'].__name__}: {e}")

        return handled

## @brief Единый глобальный объект маршрутизатора событий для всего проекта.
router = EventRouter()
