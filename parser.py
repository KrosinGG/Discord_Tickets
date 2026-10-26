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


def _extract_iso_or_text_date(val: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Парсит дату/время и возвращает (time_str, date_str, yyyy_mm_dd).
    Для ISO 8601 сохраняет локальное время билета без ошибочного сдвига в UTC.
    Например: ("8:00 PM", "Sep 5, 2026", "2026-09-05").
    """
    if not isinstance(val, str):
        return None, None, None

    val_str = val.strip()

    # 1. ISO 8601 формат
    iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2})?", val_str)
    if iso_match:
        try:
            year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            hour, minute = int(iso_match.group(4)), int(iso_match.group(5))
            dt = datetime(year, month, day, hour, minute)
            time_str = dt.strftime("%I:%M %p").lstrip("0")
            date_str = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
            ymd_str = f"{year:04d}-{month:02d}-{day:02d}"
            return time_str, date_str, ymd_str
        except Exception:
            pass

    # 2. Текстовая дата вроде "Sep 5, 2026" или "September 5, 2026"
    date_text_match = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", val_str)
    if date_text_match:
        m_name, day, year = date_text_match.group(1), date_text_match.group(2), date_text_match.group(3)
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                dt = datetime.strptime(f"{m_name[:3].capitalize()} {day} {year}", "%b %d %Y")
                return None, f"{dt.strftime('%b')} {dt.day}, {dt.year}", dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

    return None, None, None


def _format_date_time_value(val: Any) -> Tuple[Optional[str], Optional[str]]:
    """Вспомогательная функция для совместимости, возвращает (time_str, date_str)."""
    t, d, _ = _extract_iso_or_text_date(val)
    return t, d


def _generate_qr_data_uri(message: str, encoding: Optional[str] = None) -> str:
    """
    Генерирует SVG Data URI полноценного стандартного QR-кода (ISO/IEC 18004) с 3 угловыми метками.
    Использует segno.make_qr (без Micro QR), в точности как генератор CoreImage PassKit в iOS.
    """
    qr = segno.make_qr(message, error="M", encoding=encoding)
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

    # Извлечение полей заголовка (headerFields) и даты события
    # В Apple Wallet правый верхний угол формируется строго из headerFields (label сверху, value снизу)
    normalized_header_fields = []
    event_date_str = None

    for hf in header_fields:
        lbl = hf.get("label", "").strip()
        val = hf.get("value", "").strip()
        raw_val = hf.get("raw_value", "").strip()

        # Проверяем, содержит ли значение или сырое значение дату в формате ISO
        iso_time, iso_date, iso_ymd = _extract_iso_or_text_date(raw_val)
        if not iso_time and not iso_date:
            iso_time, iso_date, iso_ymd = _extract_iso_or_text_date(val)

        if iso_time and iso_date:
            if not event_date_str:
                event_date_str = iso_ymd
            # Если label пустой или системный ("DATE", "TIME"), выводим дату в label, а время в value
            if not lbl or lbl.lower() in ("date", "time", "event date", "date & time"):
                normalized_header_fields.append({
                    "label": iso_date,
                    "value": iso_time,
                })
            else:
                normalized_header_fields.append({
                    "label": lbl,
                    "value": iso_time,
                })
        else:
            # Значение уже является отформатированной строкой (например, label="SEP 5, 2026", value="8:00 PM")
            _, _, ymd1 = _extract_iso_or_text_date(lbl)
            _, _, ymd2 = _extract_iso_or_text_date(val)
            if not event_date_str:
                event_date_str = ymd1 or ymd2

            normalized_header_fields.append({
                "label": lbl,
                "value": val,
            })

    # Если в headerFields ничего не найдено, используем fallback на relevantDate
    if not normalized_header_fields:
        relevant_date = pass_data.get("relevantDate")
        if relevant_date:
            r_time, r_date, r_ymd = _extract_iso_or_text_date(relevant_date)
            if r_time and r_date:
                normalized_header_fields.append({
                    "label": r_date,
                    "value": r_time,
                })
                if not event_date_str:
                    event_date_str = r_ymd

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
        encoding = barcode_obj.get("messageEncoding")

        if message:
            if "code128" in b_format.lower():
                try:
                    barcode_uri = _generate_barcode128_data_uri(message)
                    barcode_type = "1d"
                except Exception as e:
                    logger.warning("Ошибка генерации Code128, откат к QR: %s", e)
                    barcode_uri = _generate_qr_data_uri(message, encoding=encoding)
                    barcode_type = "qr"
            else:
                # По умолчанию генерируем полноценный QR (PKBarcodeFormatQR, PKBarcodeFormatAztec, PKBarcodeFormatPDF417)
                try:
                    barcode_uri = _generate_qr_data_uri(message, encoding=encoding)
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
        "header_time": normalized_header_fields[0]["value"] if normalized_header_fields else "",
        "header_date": normalized_header_fields[0]["label"] if normalized_header_fields else "",
        "header_fields": normalized_header_fields,
        "primary_fields": primary_fields,
        "secondary_fields": secondary_fields,
        "auxiliary_fields": auxiliary_fields,
        "barcode_type": barcode_type,
        "barcode_uri": barcode_uri,
        "alt_text": alt_text,
        "event_date": event_date_str,
        "pass_type": pass_type_name,
    }


def extract_pkpass_files(file_bytes: bytes) -> List[bytes]:
    """
    Распаковывает архив в памяти и определяет его тип:
    - Если это составной бандл .pkpasses (содержит внутри файлы *.pkpass) -> возвращает список байтов каждого *.pkpass.
    - Если это одиночный билет .pkpass (содержит pass.json) -> возвращает [file_bytes].
    - Если архив некорректен или пуст -> возбуждает ValueError.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as e:
        raise ValueError(f"Файл не является корректным ZIP-архивом Apple Pass: {e}")

    file_list = zf.namelist()

    # 1. Проверяем наличие вложенных файлов .pkpass (пакетный архив .pkpasses)
    nested_pkpasses = [
        f for f in file_list
        if f.lower().endswith(".pkpass") and not f.startswith("__MACOSX") and not f.endswith("/")
    ]

    if nested_pkpasses:
        # Сортируем по имени для детерминированного порядка страниц
        nested_pkpasses.sort()
        logger.info("Обнаружен составной архив .pkpasses с %d билетами", len(nested_pkpasses))
        extracted: List[bytes] = []
        for name in nested_pkpasses:
            extracted.append(zf.read(name))
        return extracted

    # 2. Проверяем, является ли архив одиночным .pkpass (содержит pass.json)
    has_pass_json = any(
        f.lower() == "pass.json" or f.lower().endswith("/pass.json")
        for f in file_list
    )
    if has_pass_json:
        return [file_bytes]

    raise ValueError("Архив не содержит файлов билетов (.pkpass) или файла pass.json")


def parse_pkpass_archive(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Универсальный парсер для одиночных .pkpass и пакетных архивов .pkpasses.
    Возвращает список словарей распарсенных билетов.
    """
    pkpass_bytes_list = extract_pkpass_files(file_bytes)
    parsed_tickets: List[Dict[str, Any]] = []
    for raw_bytes in pkpass_bytes_list:
        parsed_tickets.append(parse_pkpass(raw_bytes))
    return parsed_tickets
