"""
Модульные тесты для парсера .pkpass.
"""

import io
import json
import zipfile
import pytest

from parser import parse_pkpass, _is_dark_color, _parse_css_color, _format_date_time_value


def create_mock_pkpass(
    pass_json: dict,
    strings_content: str = None,
    add_logo: bool = True,
    add_strip: bool = False,
) -> bytes:
    """Создает в памяти валидный ZIP-архив .pkpass для тестов."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pass.json", json.dumps(pass_json))
        if strings_content:
            zf.writestr("en.lproj/pass.strings", strings_content.encode("utf-8"))
        if add_logo:
            # Минимальный валидный PNG (1x1 transparent)
            dummy_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
                b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            zf.writestr("logo.png", dummy_png)
        if add_strip:
            zf.writestr("strip.png", dummy_png)
    return buffer.getvalue()


def test_parse_red_ticket_wicked():
    """Тест парсинга красного билета (стиль Wicked) с QR-кодом."""
    pass_json = {
        "formatVersion": 1,
        "passTypeIdentifier": "pass.com.dmpa.tickets",
        "serialNumber": "99000002009395564985",
        "organizationName": "DMPA",
        "backgroundColor": "rgb(190, 43, 43)",
        "foregroundColor": "rgb(255, 255, 255)",
        "labelColor": "rgb(240, 240, 240)",
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
                "messageEncoding": "iso-8859-1",
                "altText": "99000002009395564985"
            }
        ]
    }

    raw_bytes = create_mock_pkpass(pass_json)
    result = parse_pkpass(raw_bytes)

    assert result["organization_name"] == "DMPA"
    assert result["background_color"] == "rgb(190, 43, 43)"
    assert result["is_dark_bg"] is True
    assert result["header_time"] == "1:00 PM"
    assert result["header_date"] == "Sep 6, 2026"
    assert result["barcode_type"] == "qr"
    assert result["alt_text"] == "99000002009395564985"
    assert result["barcode_uri"].startswith("data:image/svg+xml;base64,")
    assert result["logo_image"].startswith("data:image/png;base64,")
    assert len(result["primary_fields"]) == 1
    assert result["primary_fields"][0]["value"] == "Wicked"
    assert len(result["auxiliary_fields"]) == 3


def test_parse_blue_ticket_1d_barcode():
    """Тест парсинга синего билета (стиль Etix) с 1D штрихкодом Code128."""
    pass_json = {
        "formatVersion": 1,
        "organizationName": "etix",
        "backgroundColor": "rgb(59, 115, 207)",
        "foregroundColor": "#FFFFFF",
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

    raw_bytes = create_mock_pkpass(pass_json)
    result = parse_pkpass(raw_bytes)

    assert result["barcode_type"] == "1d"
    assert result["alt_text"] == "14924796100"
    assert result["header_time"] == "8:00 PM"
    assert result["header_date"] == "Sep 5, 2026"


def test_parse_white_ticket_light_mode():
    """Тест распознавания светлого фона и авто-контраста."""
    pass_json = {
        "formatVersion": 1,
        "organizationName": "CSO",
        "backgroundColor": "#FFFFFF",
        "eventTicket": {
            "primaryFields": [
                {"key": "artist", "label": "MUSIC HALL", "value": "LA LA LAND in Concert"}
            ]
        },
        "barcode": {
            "format": "PKBarcodeFormatQR",
            "message": "99000004018564626644",
            "altText": "99000004018564626644"
        }
    }

    raw_bytes = create_mock_pkpass(pass_json)
    result = parse_pkpass(raw_bytes)

    assert result["background_color"] == "#FFFFFF"
    assert result["is_dark_bg"] is False
    assert result["foreground_color"] == "#000000"


def test_parse_localization():
    """Тест подстановки строк из pass.strings."""
    pass_json = {
        "organizationName": "ORG_NAME_KEY",
        "eventTicket": {
            "primaryFields": [
                {"label": "EVENT_LBL", "value": "EVENT_VAL"}
            ]
        }
    }
    strings = (
        '"ORG_NAME_KEY" = "Большой Театр";\n'
        '"EVENT_LBL" = "СОБЫТИЕ";\n'
        '"EVENT_VAL" = "Лебединое Озеро";\n'
    )

    raw_bytes = create_mock_pkpass(pass_json, strings_content=strings)
    result = parse_pkpass(raw_bytes)

    assert result["organization_name"] == "Большой Театр"
    assert result["primary_fields"][0]["label"] == "СОБЫТИЕ"
    assert result["primary_fields"][0]["value"] == "Лебединое Озеро"


def test_invalid_zip_raises_error():
    """Проверка ошибки при передаче невалидных байтов."""
    with pytest.raises(ValueError, match="не является корректным ZIP-архивом"):
        parse_pkpass(b"not a zip file content")


def test_missing_pass_json_raises_error():
    """Проверка ошибки при отсутствии pass.json."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("dummy.txt", "hello")
    with pytest.raises(ValueError, match="не найден обязательный файл 'pass.json'"):
        parse_pkpass(buffer.getvalue())


def test_parse_bankhead_theater_timezone_issue():
    """Тест случая, когда relevantDate в UTC (03:00 Sep 6), а headerFields содержит локальное время (8:00 PM SEP 5, 2026)."""
    pass_json = {
        "formatVersion": 1,
        "organizationName": "LVA",
        "relevantDate": "2026-09-06T03:00:00Z",  # UTC время, не должно затирать локальный заголовок
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
            {"format": "PKBarcodeFormatQR", "message": "ITEM-002102110", "altText": "ITEM-002102110"}
        ]
    }
    raw_bytes = create_mock_pkpass(pass_json)
    result = parse_pkpass(raw_bytes)

    assert len(result["header_fields"]) == 1
    assert result["header_fields"][0]["label"] == "SEP 5, 2026"
    assert result["header_fields"][0]["value"] == "8:00 PM"
    assert result["event_date"] == "2026-09-05"

