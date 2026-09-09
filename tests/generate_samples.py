"""
Скрипт для генерации образцов PDF и скриншотов карточек
на основе предоставленных эталонных изображений.
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from parser import parse_pkpass
from renderer import PDFRenderer
from tests.test_parser import create_mock_pkpass


async def generate_samples():
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # 1. Красный билет (Wicked)
    red_pass_json = {
        "formatVersion": 1,
        "organizationName": "DMPA",
        "logoText": "DMPA",
        "backgroundColor": "rgb(186, 42, 42)",
        "foregroundColor": "#FFFFFF",
        "labelColor": "rgba(255, 255, 255, 0.75)",
        "relevantDate": "2026-09-06T13:00:00-05:00",
        "eventTicket": {
            "primaryFields": [
                {"key": "title", "label": "TITLE", "value": "Wicked"}
            ],
            "secondaryFields": [
                {"key": "venue", "label": "VENUE", "value": "Civic Center"}
            ],
            "auxiliaryFields": [
                {"key": "sec", "label": "SECTION", "value": "Door 8W"},
                {"key": "row", "label": "ROW", "value": "MM"},
                {"key": "seat", "label": "SEAT", "value": "22"}
            ]
        },
        "barcodes": [
            {
                "format": "PKBarcodeFormatQR",
                "message": "99000002009395564985",
                "altText": "99000002009395564985"
            }
        ]
    }

    # 2. Синий билет (Etix / The Temptations) с 1D Code128
    blue_pass_json = {
        "formatVersion": 1,
        "organizationName": "etix",
        "logoText": "etix",
        "backgroundColor": "rgb(55, 114, 209)",
        "foregroundColor": "#FFFFFF",
        "labelColor": "rgba(255, 255, 255, 0.75)",
        "relevantDate": "2026-09-05T20:00:00-07:00",
        "eventTicket": {
            "primaryFields": [
                {"key": "title", "label": "STARLIGHT THEATER AT PALA CASINO SPA RESORT", "value": "The Temptations"}
            ],
            "secondaryFields": [
                {"key": "seats", "label": "SECTION / ROW / SEAT", "value": "SEC D / 18 / 11"}
            ],
            "auxiliaryFields": [
                {"key": "order", "label": "ORDER ID", "value": "466497976"},
                {"key": "price", "label": "PRICE CODE", "value": "ADULT"}
            ]
        },
        "barcodes": [
            {
                "format": "PKBarcodeFormatCode128",
                "message": "14924796100",
                "altText": "14924796100"
            }
        ]
    }

    # 3. Белый билет (CSO / LA LA LAND)
    white_pass_json = {
        "formatVersion": 1,
        "organizationName": "CSO",
        "logoText": "CSO",
        "backgroundColor": "#FFFFFF",
        "foregroundColor": "#111111",
        "labelColor": "#555555",
        "relevantDate": "2026-09-05T19:30:00-05:00",
        "eventTicket": {
            "primaryFields": [
                {"key": "title", "label": "MUSIC HALL", "value": "LA LA LAND in Concert"}
            ],
            "secondaryFields": [
                {"key": "section", "label": "SECTION", "value": "Gallery Sect.3 - Door A"}
            ],
            "auxiliaryFields": [
                {"key": "row", "label": "ROW", "value": "H"},
                {"key": "seat", "label": "SEAT", "value": "301"},
                {"key": "type", "label": "TYPE", "value": "Adult"}
            ]
        },
        "barcodes": [
            {
                "format": "PKBarcodeFormatQR",
                "message": "99000004018564626644",
                "altText": "99000004018564626644"
            }
        ]
    }

    # 4. Билет Bankhead Theater (Paula Poundstone)
    bankhead_pass_json = {
        "formatVersion": 1,
        "organizationName": "LVA",
        "logoText": "LVA",
        "backgroundColor": "rgb(42, 45, 62)",
        "foregroundColor": "#FFFFFF",
        "labelColor": "rgba(255, 255, 255, 0.75)",
        "relevantDate": "2026-09-06T03:00:00Z",
        "eventTicket": {
            "headerFields": [
                {"key": "date", "label": "SEP 5, 2026", "value": "8:00 PM"}
            ],
            "primaryFields": [
                {"key": "title", "label": "BANKHEAD THEATER", "value": "Paula Poundstone"}
            ],
            "secondaryFields": [
                {"key": "sec", "label": "SECTION", "value": "All Seating"},
                {"key": "seat", "label": "ROW / SEAT", "value": "P / 6"}
            ]
        },
        "barcodes": [
            {
                "format": "PKBarcodeFormatQR",
                "message": "ITEM-002102110",
                "altText": "ITEM-002102110"
            }
        ]
    }

    tickets = [
        parse_pkpass(create_mock_pkpass(red_pass_json)),
        parse_pkpass(create_mock_pkpass(blue_pass_json)),
        parse_pkpass(create_mock_pkpass(white_pass_json)),
        parse_pkpass(create_mock_pkpass(bankhead_pass_json)),
    ]

    renderer = PDFRenderer()
    html_content = renderer.render_html(tickets)

    # Сохраняем скомпилированный HTML для отладки
    (output_dir / "preview.html").write_text(html_content, encoding="utf-8")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1200, "height": 1600}, device_scale_factor=2)
        await page.set_content(html_content, wait_until="networkidle")

        # Генерация единого PDF
        pdf_bytes = await page.pdf(
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
        )
        (output_dir / "sample_tickets.pdf").write_bytes(pdf_bytes)

        # Скриншоты отдельных карточек для визуальной сверки
        cards = await page.query_selector_all(".wallet-card")
        for i, card in enumerate(cards, 1):
            await card.screenshot(path=str(output_dir / f"ticket_card_{i}.png"))

        await browser.close()

    print(f"[OK] Samples generated successfully in {output_dir.resolve()}")


if __name__ == "__main__":
    asyncio.run(generate_samples())
