"""
Discord-бот для конвертации билетов Apple Wallet (.pkpass и .pkpasses) в Pixel-Perfect PDF.
"""

import io
import logging
import os
import sys
from datetime import datetime
from typing import List

import discord
from dotenv import load_dotenv

from parser import parse_pkpass_archive
from renderer import render_tickets_to_pdf

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pkpass-bot")

# Загрузка переменных окружения из .env
load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

MAX_TICKETS = 10


@client.event
async def on_ready():
    logger.info("Бот успешно запущен как %s (ID: %s)", client.user, client.user.id)
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="за билетами (.pkpass / .pkpasses)",
    )
    await client.change_presence(activity=activity)


@client.event
async def on_message(message: discord.Message):
    # Игнорируем сообщения от самого бота
    if message.author == client.user or message.author.bot:
        return

    # Фильтруем вложения с расширениями .pkpass и .pkpasses
    pkpass_attachments = [
        att for att in message.attachments
        if att.filename.lower().endswith((".pkpass", ".pkpasses"))
    ]

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions

    # Сценарий 1: Нет файлов .pkpass / .pkpasses
    if not pkpass_attachments:
        # Отвечаем подсказкой только если боту написали в ЛС или явно тегнули
        if is_dm or is_mentioned:
            await message.reply(
                "👋 Привет! Отправьте мне файлы билетов Apple Wallet (`.pkpass` или `.pkpasses`) в виде вложений "
                "(от 1 до 10 билетов за один раз), и я объединю их в единый качественный PDF-документ."
            )
        return

    # Сценарий 2: Прикреплено более 10 файлов
    if len(pkpass_attachments) > MAX_TICKETS:
        await message.reply(
            "❌ Ошибка: Максимальное количество билетов для единовременной обработки — 10 шт."
        )
        return

    # Сценарий 3: Корректное количество файлов (от 1 до 10)
    # Ставим реакцию-песочные часы ⏳
    try:
        await message.add_reaction("⏳")
    except Exception as e:
        logger.warning("Не удалось поставить реакцию ⏳: %s", e)

    async with message.channel.typing():
        parsed_tickets: List[dict] = []
        errors: List[str] = []

        # Скачиваем и парсим каждый файл/бандл в памяти
        for att in pkpass_attachments:
            try:
                file_bytes = await att.read()
                batch_tickets = parse_pkpass_archive(file_bytes)
                if not batch_tickets:
                    raise ValueError("Файл не содержит билетов для обработки.")

                parsed_tickets.extend(batch_tickets)
                logger.info(
                    "Успешно обработан файл %s: извлечено билетов: %d (всего накоплено: %d)",
                    att.filename, len(batch_tickets), len(parsed_tickets)
                )
            except Exception as e:
                logger.error("Ошибка при обработке файла %s: %s", att.filename, e, exc_info=True)
                errors.append(f"• `{att.filename}`: {str(e)}")

        # Проверка лимита: суммарное количество билетов из всех файлов не должно превышать MAX_TICKETS
        if len(parsed_tickets) > MAX_TICKETS:
            try:
                await message.remove_reaction("⏳", client.user)
                await message.add_reaction("❌")
            except Exception:
                pass
            await message.reply(
                "❌ Ошибка: Максимальное количество билетов для единовременной обработки — 10 шт."
            )
            return

        # Если ни один файл не удалось распарсить
        if not parsed_tickets:
            try:
                await message.remove_reaction("⏳", client.user)
                await message.add_reaction("❌")
            except Exception:
                pass
            err_msg = "❌ Не удалось прочитать переданные файлы .pkpass / .pkpasses:\n" + "\n".join(errors)
            await message.reply(err_msg)
            return

        # Рендерим все билеты в единый PDF через Playwright
        try:
            pdf_bytes = await render_tickets_to_pdf(parsed_tickets)
        except Exception as e:
            logger.error("Ошибка при генерации PDF: %s", e, exc_info=True)
            try:
                await message.remove_reaction("⏳", client.user)
                await message.add_reaction("❌")
            except Exception:
                pass
            await message.reply(f"❌ Произошла ошибка при генерации PDF: {e}")
            return

        # Формирование имени файла: tickets_event_YYYY-MM-DD.pdf
        event_date = parsed_tickets[0].get("event_date") or datetime.now().strftime("%Y-%m-%d")
        pdf_filename = f"tickets_event_{event_date}.pdf"

        # Отправка результата пользователю
        discord_file = discord.File(
            fp=io.BytesIO(pdf_bytes),
            filename=pdf_filename,
        )

        response_text = f"✅ Ваши билеты готовы (кол-во: {len(parsed_tickets)})"
        if errors:
            response_text += f"\n⚠️ Некоторые файлы были пропущены из-за ошибок:\n" + "\n".join(errors)

        await message.reply(response_text, file=discord_file)

        # Смена реакции с ⏳ на ✅
        try:
            await message.remove_reaction("⏳", client.user)
            await message.add_reaction("✅")
        except Exception:
            pass


def main():
    if not TOKEN or TOKEN.strip() == "" or "your_discord_bot_token" in TOKEN:
        logger.error(
            "Не задан токен бота DISCORD_BOT_TOKEN!\n"
            "1. Создайте бота на https://discord.com/developers/applications\n"
            "2. Включите 'Message Content Intent' во вкладке Bot\n"
            "3. Скопируйте токен в файл .env: DISCORD_BOT_TOKEN=ваш_токен"
        )
        sys.exit(1)

    logger.info("Запуск Discord бота...")
    client.run(TOKEN)


if __name__ == "__main__":
    main()
