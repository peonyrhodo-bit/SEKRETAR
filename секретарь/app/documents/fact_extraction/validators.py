"""
ЭТАП 3.20–3.23
Проверка качества извлечённых фактов.

Validator НЕ исправляет факт и НЕ выбирает между конфликтами.
Он только сообщает о качестве.
"""

import re
from typing import Any, Dict


VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)
PLATE_RE = re.compile(
    r"^[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}$",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def _value(fact):
    return str(fact.get("value", "")).strip()


def validate_fact(fact: Dict[str, Any]) -> Dict[str, Any]:
    """
    Возвращает результат проверки, не изменяя исходный факт.
    """

    fact_type = fact.get("type", "")
    value = _value(fact)

    confidence = fact.get("confidence", {})

    if not isinstance(confidence, dict):
        confidence = {}

    ocr_conf = float(confidence.get("ocr", 0.0) or 0.0)
    extraction_conf = float(
        confidence.get("extraction", 0.0) or 0.0
    )

    warnings = []

    # ------------------------------------------------------------
    # ПУСТОЕ ЗНАЧЕНИЕ
    # ------------------------------------------------------------

    if not value:

        return {
            "status": "INVALID",
            "warnings": ["Пустое значение факта."],
        }

    # ------------------------------------------------------------
    # VIN
    # ------------------------------------------------------------

    if fact_type == "VIN":

        if not VIN_RE.match(value):
            warnings.append("Некорректный формат VIN.")

    # ------------------------------------------------------------
    # ГОСНОМЕР
    # ------------------------------------------------------------

    if fact_type == "PLATE":

        if not PLATE_RE.match(value):
            warnings.append("Некорректный формат госномера.")

    # ------------------------------------------------------------
    # ДАТА
    # ------------------------------------------------------------

    if fact_type in {
        "BIRTH_DATE",
        "POLICY_START_DATE",
        "POLICY_END_DATE",
        "USAGE_PERIOD_START",
        "USAGE_PERIOD_END",
        "ADDENDUM_DATE",
        "DOCUMENT_DATE",
        "CONTRACT_DATE",
        "DATE",
    }:

        if not DATE_RE.match(value):
            warnings.append("Некорректный формат даты.")

    # ------------------------------------------------------------
    # НИЗКАЯ УВЕРЕННОСТЬ OCR
    # ------------------------------------------------------------

    if ocr_conf < 0.70:
        warnings.append(
            f"Низкая уверенность OCR: {ocr_conf:.2f}"
        )

    # ------------------------------------------------------------
    # НИЗКАЯ УВЕРЕННОСТЬ ИЗВЛЕЧЕНИЯ
    # ------------------------------------------------------------

    if extraction_conf < 0.70:
        warnings.append(
            f"Низкая уверенность извлечения: "
            f"{extraction_conf:.2f}"
        )

    if warnings:

        return {
            "status": "SUSPICIOUS",
            "warnings": warnings,
        }

    return {
        "status": "VALID",
        "warnings": [],
    }
