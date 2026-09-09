"""
Тесты бизнес-логики бота и валидации лимитов.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from bot import MAX_TICKETS, on_message


class DummyAttachment:
    def __init__(self, filename: str, content: bytes = b"dummy"):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


@pytest.mark.asyncio
async def test_bot_ignores_own_messages():
    """Бот игнорирует собственные сообщения."""
    message = MagicMock()
    message.author.bot = True
    message.reply = AsyncMock()

    await on_message(message)
    message.reply.assert_not_called()


@pytest.mark.asyncio
async def test_bot_rejects_over_10_tickets():
    """Бот отклоняет запрос с > 10 билетами с точным текстом ошибки."""
    message = MagicMock()
    message.author.bot = False
    message.reply = AsyncMock()

    # Создаем 11 вложений с .pkpass
    attachments = [DummyAttachment(f"ticket_{i}.pkpass") for i in range(11)]
    message.attachments = attachments

    await on_message(message)

    message.reply.assert_called_once_with(
        "❌ Ошибка: Максимальное количество билетов для единовременной обработки — 10 шт."
    )


def test_max_tickets_constant():
    """Лимит строго равен 10."""
    assert MAX_TICKETS == 10
