"""
===============================================================================
ЭТАП 3 — ДОКУМЕНТЫ → ФАКТЫ
Файл: normalizer.py

Назначение:
    Нормализация значений и OCR-текста.

Реализует:
    3.7  — распознавание типа документа даже при OCR-искажениях
    3.9  — нормализацию фактов
    3.18 — сохранение контекста
    3.20 — проверку критических значений

ВАЖНЫЙ ПРИНЦИП:

    RAW-текст никогда не заменяется нормализованным.

Мы можем иметь одновременно:

    raw_value        = "CBMIETEJIbCTBO..."
    normalized_value = "СВИДЕТЕЛЬСТВО..."

Нормализация используется для поиска и анализа,
но доказательством остаётся исходный фрагмент документа.
===============================================================================
"""

import re
from difflib import SequenceMatcher


# =============================================================================
# ПУНКТ 3.9 — НОРМАЛИЗАЦИЯ VIN
# =============================================================================

def normalize_vin(value: str) -> str:
    """
    Нормализует VIN для технической проверки.

    ВАЖНО:
    исходное значение должно сохраняться отдельно.
    """

    if value is None:
        return ""

    value = str(value).upper().strip()

    value = re.sub(r"[\s\-]", "", value)

    # Частые OCR-ошибки.
    # Используем только для нормализации значения, а не для изменения RAW.
    replacements = {
        "О": "0",
        "О": "0",
        "І": "1",
        "I": "1",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    return value


# =============================================================================
# ПУНКТ 3.9 — НОРМАЛИЗАЦИЯ ГОСНОМЕРА
# =============================================================================

def normalize_plate(value: str) -> str:
    """
    Убирает пробелы и приводит госномер к единому виду.
    """

    if value is None:
        return ""

    value = str(value).upper().strip()

    value = re.sub(r"[\s\-]", "", value)

    return value


# =============================================================================
# ПУНКТ 3.9 — НОРМАЛИЗАЦИЯ ДАТЫ
# =============================================================================

def normalize_date(value: str) -> str:
    """
    Приводит разделители даты к точке.

    21/04/1997 -> 21.04.1997
    21-04-1997 -> 21.04.1997
    """

    if value is None:
        return ""

    value = str(value).strip()

    value = value.replace("/", ".")
    value = value.replace("-", ".")

    return value


# =============================================================================
# ПУНКТ 3.7 — НОРМАЛИЗАЦИЯ OCR-ТЕКСТА ДЛЯ ПОИСКА
# =============================================================================
#
# Очень важно:
#
#     эта функция НЕ изменяет исходную строку.
#
# Она создаёт дополнительное представление,
# пригодное для поиска похожих надписей.
#
# Пример:
#
#     CBMIETEJIbCTBOOPETMCTPAIIMM
#
# может быть сопоставлено с:
#
#     СВИДЕТЕЛЬСТВО О РЕГИСТРАЦИИ
#
# =============================================================================

OCR_CONFUSABLES = str.maketrans({
    # Латиница → визуально похожая кириллица.
    "A": "А",
    "B": "В",
    "C": "С",
    "E": "Е",
    "H": "Н",
    "K": "К",
    "M": "М",
    "O": "О",
    "P": "Р",
    "T": "Т",
    "X": "Х",
    "Y": "У",

    # Частые OCR-ошибки.
    "0": "О",
})


def normalize_ocr_for_search(text: str) -> str:
    """
    Создаёт поисковую форму OCR-текста.

    Не является доказательством.
    Используется только для поиска совпадений.
    """

    if text is None:
        return ""

    text = str(text).upper()

    text = text.translate(OCR_CONFUSABLES)

    # Убираем всё, что мешает сравнению.
    text = re.sub(r"[^А-ЯЁA-Z0-9]", "", text)

    return text


# =============================================================================
# ПУНКТ 3.7 — СРАВНЕНИЕ OCR С ЭТАЛОНОМ
# =============================================================================

def fuzzy_marker_score(text: str, marker: str) -> float:
    """
    Возвращает приблизительное сходство двух OCR-строк.

    1.0 = полное совпадение.
    0.0 = практически никакого совпадения.

    Используется только для классификации.
    """

    normalized_text = normalize_ocr_for_search(text)
    normalized_marker = normalize_ocr_for_search(marker)

    if not normalized_text or not normalized_marker:
        return 0.0

    # Прямое вхождение — самый сильный вариант.
    if normalized_marker in normalized_text:
        return 1.0

    # Если строка очень длинная, сравниваем также фрагменты.
    if len(normalized_text) > len(normalized_marker):
        best = 0.0

        window_size = len(normalized_marker)

        for start in range(
            0,
            len(normalized_text) - window_size + 1,
        ):
            fragment = normalized_text[
                start:start + window_size
            ]

            score = SequenceMatcher(
                None,
                fragment,
                normalized_marker,
            ).ratio()

            if score > best:
                best = score

        return best

    return SequenceMatcher(
        None,
        normalized_text,
        normalized_marker,
    ).ratio()


# =============================================================================
# ПУНКТ 3.9 — ОБЩИЕ НОРМАЛИЗАТОРЫ
# =============================================================================

def normalize_text(value: str) -> str:
    """
    Безопасная нормализация произвольного текста.
    """

    if value is None:
        return ""

    value = str(value)

    value = value.replace("\u00a0", " ")

    value = re.sub(r"[ \t]+", " ", value)

    return value.strip()


def normalize_name(value: str) -> str:
    """
    Нормализация ФИО без попытки исправлять содержание.
    """

    value = normalize_text(value)

    return value.upper()


# =============================================================================
# ПУНКТ 3.20 — ПРОВЕРКА VIN
# =============================================================================

def validate_vin(value: str) -> bool:
    """
    Проверяет технический формат VIN.
    """

    normalized = normalize_vin(value)

    if len(normalized) != 17:
        return False

    return bool(
        re.fullmatch(
            r"[A-HJ-NPR-Z0-9]{17}",
            normalized,
        )
    )


# =============================================================================
# ПУНКТ 3.20 — ПРОВЕРКА ГОСНОМЕРА
# =============================================================================

def validate_plate(value: str) -> bool:
    """
    Проверяет российский формат госномера.

    Не утверждает, что номер существует.
    Только проверяет форму.
    """

    normalized = normalize_plate(value)

    return bool(
        re.fullmatch(
            r"[АВЕКМНОРСТУХABEKMHOPCTYX]"
            r"\d{3}"
            r"[АВЕКМНОРСТУХABEKMHOPCTYX]"
            r"[АВЕКМНОРСТУХABEKMHOPCTYX]"
            r"\d{2,3}",
            normalized,
        )
    )


# =============================================================================
# ПУНКТ 3.20 — ПРОВЕРКА ДАТЫ
# =============================================================================

def validate_date(value: str) -> bool:
    """
    Проверяет дату формата ДД.ММ.ГГГГ.
    """

    normalized = normalize_date(value)

    match = re.fullmatch(
        r"(\d{2})\.(\d{2})\.(\d{4})",
        normalized,
    )

    if not match:
        return False

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    if year < 1900 or year > 2100:
        return False

    if month < 1 or month > 12:
        return False

    if day < 1 or day > 31:
        return False

    return True


# =============================================================================
# ПУНКТ 3.17 — ПРОВЕРКА ШАБЛОННОГО ТЕКСТА
# =============================================================================

def looks_like_template_text(
    value: str,
    template_markers: tuple,
) -> bool:
    """
    Проверяет, не является ли текст частью пустого бланка.
    """

    if not value:
        return False

    upper = str(value).upper()

    return any(
        marker.upper() in upper
        for marker in template_markers
    )
