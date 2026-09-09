"""
Модульные тесты для рендерера PDF и HTML.
"""

import pytest
from renderer import PDFRenderer, render_tickets_to_pdf


@pytest.fixture
def sample_ticket():
    return {
        "organization_name": "DMPA",
        "logo_text": "DMPA",
        "logo_image": None,
        "strip_image": None,
        "background_color": "rgb(190, 43, 43)",
        "foreground_color": "#FFFFFF",
        "label_color": "rgba(255, 255, 255, 0.7)",
        "is_dark_bg": True,
        "header_time": "1:00 PM",
        "header_date": "Sep 6, 2026",
        "primary_fields": [
            {"label": "TITLE", "value": "Wicked"}
        ],
        "secondary_fields": [
            {"label": "VENUE", "value": "Civic Center"}
        ],
        "auxiliary_fields": [
            {"label": "SECTION", "value": "Door 8W"},
            {"label": "ROW", "value": "MM"},
            {"label": "SEAT", "value": "22"}
        ],
        "barcode_type": "qr",
        "barcode_uri": "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSIxMCI+PHJlY3Qgd2lkdGg9IjEwIiBoZWlnaHQ9IjEwIiBmaWxsPSIjMDAwIi8+PC9zdmc+",
        "alt_text": "99000002009395564985",
        "event_date": "2026-09-06",
        "pass_type": "eventTicket"
    }


def test_html_rendering(sample_ticket):
    """Проверка генерации HTML строки и наличия всех элементов."""
    renderer = PDFRenderer()
    html = renderer.render_html([sample_ticket])

    assert "Wicked" in html
    assert "Civic Center" in html
    assert "Door 8W" in html
    assert "99000002009395564985" in html
    assert "ticket-notch" in html
    assert "rgb(190, 43, 43)" in html


@pytest.mark.asyncio
async def test_pdf_rendering_single_and_multi(sample_ticket):
    """Проверка генерации PDF через Playwright Chromium."""
    # 1 билет -> 1 страница
    pdf_single = await render_tickets_to_pdf([sample_ticket])
    assert pdf_single.startswith(b"%PDF-")
    assert len(pdf_single) > 1000

    # 3 билета -> единый многостраничный PDF
    tickets_batch = [sample_ticket, sample_ticket, sample_ticket]
    pdf_multi = await render_tickets_to_pdf(tickets_batch)
    assert pdf_multi.startswith(b"%PDF-")
    assert len(pdf_multi) > len(pdf_single)
