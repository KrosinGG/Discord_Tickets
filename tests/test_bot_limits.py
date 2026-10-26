"""
Тесты бизнес-логики бота и валидации лимитов.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from bot import MAX_TICKETS, on_message
from tests.test_parser import create_mock_bundle, create_mock_pkpass


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


@pytest.mark.asyncio
async def test_bot_rejects_pkpasses_bundle_over_10_tickets():
    """Бот отклоняет бандл .pkpasses, если внутри содержится более 10 билетов."""
    message = MagicMock()
    message.author.bot = False
    message.reply = AsyncMock()
    message.add_reaction = AsyncMock()
    message.remove_reaction = AsyncMock()
    message.channel.typing = MagicMock()
    message.channel.typing.return_value.__aenter__ = AsyncMock()
    message.channel.typing.return_value.__aexit__ = AsyncMock()

    # Создаем 1 бандл с 11 билетами
    raw_tickets = [
        create_mock_pkpass({"formatVersion": 1, "organizationName": f"T{i}", "eventTicket": {}})
        for i in range(11)
    ]
    bundle_bytes = create_mock_bundle(raw_tickets)

    message.attachments = [DummyAttachment("orders.pkpasses", bundle_bytes)]

    await on_message(message)

    message.reply.assert_called_once_with(
        "❌ Ошибка: Максимальное количество билетов для единовременной обработки — 10 шт."
    )


def test_max_tickets_constant():
    """Лимит строго равен 10."""
    assert MAX_TICKETS == 10
