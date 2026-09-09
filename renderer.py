"""
Модуль рендеринга PDF-документов через Playwright и Jinja2.
Генерирует Pixel-Perfect PDF из списка распарсенных билетов Apple Wallet.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import jinja2
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)


class PDFRenderer:
    """Класс для управления компиляцией HTML и рендерингом в PDF через headless Chromium."""

    def __init__(self, template_name: str = "ticket_sheet.html"):
        self.template_name = template_name
        self.template = jinja_env.get_template(self.template_name)

    def render_html(self, tickets: List[Dict[str, Any]]) -> str:
        """Компилирует HTML-код из переданного списка билетов."""
        return self.template.render(tickets=tickets)

    async def render_pdf(self, tickets: List[Dict[str, Any]]) -> bytes:
        """
        Рендерит список билетов в единый многостраничный PDF-файл.
        Возвращает байты сгенерированного PDF.
        """
        if not tickets:
            raise ValueError("Список билетов для рендеринга пуст.")

        html_content = self.render_html(tickets)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--font-render-hinting=none",
                ],
            )
            try:
                context = await browser.new_context(
                    viewport={"width": 1200, "height": 1600},
                    device_scale_factor=2,  # Высокое разрешение для ретина-качества
                )
                page = await context.new_page()

                # Загрузка скомпилированного HTML в браузер
                await page.set_content(html_content, wait_until="networkidle")

                # Рендеринг в PDF с сохранением фоновых цветов и CSS-разметки страниц
                pdf_bytes = await page.pdf(
                    print_background=True,
                    prefer_css_page_size=True,
                    margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
                )
                return pdf_bytes
            finally:
                await browser.close()


# Глобальный инстанс рендерера для удобного вызова
_renderer = PDFRenderer()


async def render_tickets_to_pdf(tickets: List[Dict[str, Any]]) -> bytes:
    """Вспомогательная функция для быстрого рендеринга билетов в PDF."""
    return await _renderer.render_pdf(tickets)
