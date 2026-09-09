"""
Парсер файлов Apple Wallet (.pkpass).
Извлекает pass.json, изображения, цвета, поля билета и генерирует штрих-код/QR-код в памяти.
"""

import base64
import io
import json
import logging
import re
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import barcode
from barcode.writer import SVGWriter
import segno

logger = logging.getLogger(__name__)


def _clean_apple_string(s: str) -> str:
    """Убирает экранирование из строки Apple .strings без повреждения UTF-8."""
    # Обрабатываем \uXXXX
    def replace_unicode(match):
        return chr(int(match.group(1), 16))

    s = re.sub(r"\\u([0-9a-fA-F]{4})", replace_unicode, s)
    # Обрабатываем базовые экранирования \", \\, \n, \r, \t
    s = s.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
    return s


def _parse_apple_strings(raw_bytes: bytes) -> Dict[str, str]:
    """
    Парсит файл Apple .strings (формат: "KEY" = "VALUE";).
    Поддерживает кодировки UTF-8, UTF-16LE, UTF-16BE.
    """
    text = ""
    for enc in ("utf-16", "utf-16-le", "utf-16-be", "utf-8", "latin-1"):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    strings: Dict[str, str] = {}
    pattern = re.compile(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)";')
    for match in pattern.finditer(text):
        key = _clean_apple_string(match.group(1))
        val = _clean_apple_string(match.group(2))
        strings[key] = val
    return strings


def _parse_css_color(color_str: Optional[str], default: str = "#000000") -> str:
    """
    Преобразует строку цвета из Apple Wallet (rgb(r,g,b), rgba(r,g,b,a), hex) в валидный CSS.
    """
    if not color_str or not isinstance(color_str, str):
        return default

    color_str = color_str.strip()
    if color_str.startswith("#"):
        return color_str

    # rgb(r, g, b) или rgba(r, g, b, a)
    rgb_match = re.match(r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)", color_str, re.IGNORECASE)
    if rgb_match:
        r, g, b = rgb_match.group(1), rgb_match.group(2), rgb_match.group(3)
        a = rgb_match.group(4)
        if a is not None:
            return f"rgba({r}, {g}, {b}, {a})"
        return f"rgb({r}, {g}, {b})"

    return color_str


def _is_dark_color(css_color: str) -> bool:
    """
    Определяет, является ли цвет фона темным (для авто-выбора контрастных шрифтов).
    """
    rgb_match = re.match(r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", css_color, re.IGNORECASE)
    if rgb_match:
        r, g, b = int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3))
        # Относительная яркость (luminance formula)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        return lum < 140

    if css_color.startswith("#") and len(css_color) in (4, 7):
        hex_val = css_color.lstrip("#")
        if len(hex_val) == 3:
            hex_val = "".join([c * 2 for c in hex_val])
        try:
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            return lum < 140
        except ValueError:
            pass

    return True


def _format_date_time_value(val: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Пытается распарсить строку даты/времени ISO 8601 и вернуть (time_str, date_str).
    Например: ("1:00 PM", "Sep 6, 2026")
    """
    if not isinstance(val, str):
        return None, str(val) if val is not None else None

    # Проверка на ISO дату
    iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?")
    if iso_pattern.match(val):
        try:
            # Убираем Z или смещение часового пояса для простого парсинга, либо парсим ISO
            dt = datetime.fromisoformat(val)
            # Форматирование времени: 1:00 PM или 13:00
            hour = dt.strftime("%I:%M %p").lstrip("0")
            # Форматирование даты: Sep 6, 2026
            date_str = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
            return hour, date_str
        except Exception:
            pass

    return None, val


def _generate_qr_data_uri(message: str) -> str:
    """Генерирует SVG Data URI QR-кода высокой четкости без потерь качества."""
    qr = segno.make(message, error="M")
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", border=0, dark="#000000", light=None)
    svg_bytes = buffer.getvalue()
    b64 = base64.b64encode(svg_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _generate_barcode128_data_uri(message: str) -> str:
    """Генерирует SVG Data URI 1D-штрихкода (Code 128) высокой четкости."""
    code128 = barcode.get("code128", message, writer=SVGWriter())
    buffer = io.BytesIO()
    code128.write(buffer, options={"write_text": False, "quiet_zone": 1.0, "module_height": 18.0})
    svg_bytes = buffer.getvalue()
    b64 = base64.b64encode(svg_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def parse_pkpass(file_bytes: bytes) -> Dict[str, Any]:
    """
    Распаковывает файл .pkpass из байтов в памяти и извлекает все данные билета.
    
    Возвращает словарь с нормализованными данными для рендеринга карточки.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as e:
        raise ValueError(f"Файл не является корректным ZIP-архивом .pkpass: {e}")

    file_list = zf.namelist()
    
    if "pass.json" not in file_list:
        raise ValueError("Внутри .pkpass архива не найден обязательный файл 'pass.json'")

    # Читаем pass.json
    try:
        pass_data = json.loads(zf.read("pass.json").decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Ошибка чтения pass.json: {e}")

    # Читаем локализацию pass.strings (приоритет: ru.lproj, en.lproj или первый попавшийся)
    localized_strings: Dict[str, str] = {}
    strings_candidates = [
        f for f in file_list if f.lower().endswith("pass.strings")
    ]
    # Сортируем: сначала en.lproj, потом остальные
    strings_candidates.sort(key=lambda s: 0 if "en.lproj" in s.lower() else 1)
    if strings_candidates:
        try:
            localized_strings = _parse_apple_strings(zf.read(strings_candidates[0]))
        except Exception as e:
            logger.warning("Не удалось прочитать файл локализации %s: %s", strings_candidates[0], e)

    def localize(text: Any) -> str:
        if text is None:
            return ""
        s = str(text)
        return localized_strings.get(s, s)

    # Поиск изображений (logo, strip, icon, thumbnail)
    def find_image(prefix: str) -> Optional[str]:
        # Ищем 3x, 2x или обычный png
        for suffix in ("@3x.png", "@2x.png", ".png"):
            target = f"{prefix}{suffix}"
            for f in file_list:
                if f.lower() == target.lower():
                    data = zf.read(f)
                    b64 = base64.b64encode(data).decode("ascii")
                    return f"data:image/png;base64,{b64}"
        return None

    logo_image = find_image("logo")
    strip_image = find_image("strip")
    icon_image = find_image("icon")
    thumbnail_image = find_image("thumbnail")

    # Цвета
    bg_color = _parse_css_color(pass_data.get("backgroundColor"), default="#1C1C1E")
    is_dark = _is_dark_color(bg_color)
    default_fg = "#FFFFFF" if is_dark else "#000000"
    default_lbl = "rgba(255, 255, 255, 0.7)" if is_dark else "rgba(0, 0, 0, 0.6)"

    fg_color = _parse_css_color(pass_data.get("foregroundColor"), default=default_fg)
    lbl_color = _parse_css_color(pass_data.get("labelColor"), default=default_lbl)

    # Определение структуры билета (eventTicket или generic/boardingPass/coupon/storeCard)
    pass_type_structure = None
    pass_type_name = "eventTicket"
    for ptype in ("eventTicket", "generic", "boardingPass", "coupon", "storeCard"):
        if ptype in pass_data:
            pass_type_structure = pass_data[ptype]
            pass_type_name = ptype
            break

    if not pass_type_structure:
        pass_type_structure = {}

    def extract_fields(field_key: str) -> List[Dict[str, str]]:
        raw_list = pass_type_structure.get(field_key, [])
        result = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            lbl = localize(item.get("label", ""))
            raw_val = item.get("value", "")
            val = localize(raw_val)
            result.append({
                "key": item.get("key", ""),
                "label": lbl,
                "value": val,
                "raw_value": str(raw_val),
            })
        return result

    header_fields = extract_fields("headerFields")
    primary_fields = extract_fields("primaryFields")
    secondary_fields = extract_fields("secondaryFields")
    auxiliary_fields = extract_fields("auxiliaryFields")

    # Извлечение даты события для заголовка и имени файла
    event_date_str = None
    header_time_str = None
    header_date_str = None

    # 1. Проверяем relevantDate в pass_data
    relevant_date = pass_data.get("relevantDate")
    if relevant_date:
        t_str, d_str = _format_date_time_value(relevant_date)
        if t_str and d_str:
            header_time_str = t_str
            header_date_str = d_str
            event_date_str = relevant_date[:10]

    # 2. Проверяем headerFields на дату/время
    for hf in header_fields:
        t_str, d_str = _format_date_time_value(hf["raw_value"])
        if t_str and d_str:
            if not header_time_str:
                header_time_str = t_str
            if not header_date_str:
                header_date_str = d_str
            if not event_date_str:
                event_date_str = hf["raw_value"][:10]
        elif not header_date_str and hf["value"]:
            # Например если значение "Sep 5, 2026"
            header_date_str = hf["value"]
            if hf["label"] and not header_time_str:
                header_time_str = hf["label"]

    # Штрих-код / QR-код
    barcode_obj = None
    barcodes_list = pass_data.get("barcodes", [])
    if barcodes_list and isinstance(barcodes_list, list) and len(barcodes_list) > 0:
        barcode_obj = barcodes_list[0]
    elif "barcode" in pass_data and isinstance(pass_data["barcode"], dict):
        barcode_obj = pass_data["barcode"]

    barcode_type = "none"
    barcode_uri = ""
    alt_text = ""

    if barcode_obj:
        message = barcode_obj.get("message", "")
        alt_text = barcode_obj.get("altText", message)
        b_format = barcode_obj.get("format", "PKBarcodeFormatQR")

        if message:
            if "code128" in b_format.lower():
                try:
                    barcode_uri = _generate_barcode128_data_uri(message)
                    barcode_type = "1d"
                except Exception as e:
                    logger.warning("Ошибка генерации Code128, откат к QR: %s", e)
                    barcode_uri = _generate_qr_data_uri(message)
                    barcode_type = "qr"
            else:
                # По умолчанию генерируем QR (PKBarcodeFormatQR, PKBarcodeFormatAztec, PKBarcodeFormatPDF417)
                try:
                    barcode_uri = _generate_qr_data_uri(message)
                    barcode_type = "qr"
                except Exception as e:
                    logger.error("Ошибка генерации QR-кода: %s", e)
                    barcode_type = "none"

    # Если даты так и нет, используем сегодняшнюю для имени файла
    if not event_date_str or not re.match(r"^\d{4}-\d{2}-\d{2}$", event_date_str):
        event_date_str = datetime.now().strftime("%Y-%m-%d")

    logo_text = pass_data.get("logoText", "")
    if logo_text:
        logo_text = localize(logo_text)

    organization_name = pass_data.get("organizationName", "")
    if organization_name:
        organization_name = localize(organization_name)

    return {
        "organization_name": organization_name,
        "logo_text": logo_text,
        "logo_image": logo_image,
        "strip_image": strip_image,
        "icon_image": icon_image,
        "thumbnail_image": thumbnail_image,
        "background_color": bg_color,
        "foreground_color": fg_color,
        "label_color": lbl_color,
        "is_dark_bg": is_dark,
        "header_time": header_time_str,
        "header_date": header_date_str,
        "header_fields": header_fields,
        "primary_fields": primary_fields,
        "secondary_fields": secondary_fields,
        "auxiliary_fields": auxiliary_fields,
        "barcode_type": barcode_type,
        "barcode_uri": barcode_uri,
        "alt_text": alt_text,
        "event_date": event_date_str,
        "pass_type": pass_type_name,
    }
