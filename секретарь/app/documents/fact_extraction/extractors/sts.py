"""
ЭТАП 3.9
Парсер СТС.

Извлекает наблюдаемые данные:

- номер СТС;
- госномер;
- VIN;
- марка;
- модель;
- год выпуска;
- даты, если они действительно находятся в контексте документа.

Не определяет владельца автомобиля.

ВАЖНО:
OCR может искажать русские буквы и отдельные символы.
Поэтому extractor использует:
1. структурные якоря;
2. нормализацию OCR;
3. проверки длины/формата;
4. повышенную осторожность для критических фактов.
"""

import re
from typing import Any, Dict, List

from .base import BaseExtractor


# ============================================================
# ПУНКТ 3.9.1 — БАЗОВЫЕ ШАБЛОНЫ
# ============================================================

DATE_RE = re.compile(
    r"\b\d{2}[./-]\d{2}[./-]\d{4}\b"
)

YEAR_RE = re.compile(
    r"\b(19\d{2}|20\d{2})\b"
)

VIN_RE = re.compile(
    r"\b[A-HJ-NPR-Z0-9]{17}\b",
    re.IGNORECASE,
)

# Российский госномер:
# В263ТЕ43
# А123ВС43
# А123ВС123
PLATE_RE = re.compile(
    r"\b[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}\b",
    re.IGNORECASE,
)


class StsExtractor(BaseExtractor):

    # ========================================================
    # ПУНКТ 3.9.2 — НОРМАЛИЗАЦИЯ OCR
    # ========================================================

    @staticmethod
    def _normalize_ocr_text(text: str) -> str:
        """
        Минимальная нормализация OCR.

        Не исправляем произвольный текст.
        Исправляем только очевидные технические варианты,
        которые мешают поиску структурных признаков.
        """

        value = str(text or "").strip()

        replacements = {
            "Ё": "Е",
            "ё": "е",
        }

        for old, new in replacements.items():
            value = value.replace(old, new)

        return value

    # ========================================================
    # ПУНКТ 3.9.3 — НОРМАЛИЗАЦИЯ VIN
    # ========================================================

    @staticmethod
    def _normalize_vin(value: str) -> str:
        """
        Нормализует VIN после OCR.

        Важно:
        не исправляем произвольные символы.
        Разрешены только безопасные OCR-замены.
        """

        value = str(value or "").upper().strip()

        replacements = {
            "О": "0",
            "O": "0",
            "I": "1",
            "Л": "A",
        }

        for old, new in replacements.items():
            value = value.replace(old, new)

        return value

    # ========================================================
    # ПУНКТ 3.9.4 — ПРОВЕРКА VIN
    # ========================================================

    @staticmethod
    def _is_valid_vin(value: str) -> bool:
        """
        Базовая проверка VIN.

        VIN должен содержать ровно 17 символов.
        Буквы I/O/Q запрещены.
        """

        value = str(value or "").upper().strip()

        if len(value) != 17:
            return False

        if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value):
            return False

        return True

    # ========================================================
    # ПУНКТ 3.9.5 — НОРМАЛИЗАЦИЯ ГОСНОМЕРА
    # ========================================================

    @staticmethod
    def _normalize_plate(value: str) -> str:
        """
        Переводит латинские аналоги российских букв в кириллицу.

        Например:
        B263TE43 -> В263ТЕ43

        Это допустимо только для госномера.
        Для других фактов такую замену делать нельзя.
        """

        value = str(value or "").upper().strip()

        latin_to_cyrillic = {
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
        }

        result = []

        for char in value:
            result.append(latin_to_cyrillic.get(char, char))

        return "".join(result)

    # ========================================================
    # ПУНКТ 3.9.6 — ПРОВЕРКА ГОСНОМЕРА
    # ========================================================

    @classmethod
    def _is_valid_plate(cls, value: str) -> bool:

        value = cls._normalize_plate(value)

        return bool(
            re.fullmatch(
                r"[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}",
                value,
            )
        )

    # ========================================================
    # ПУНКТ 3.9.7 — ПОИСК VIN
    # ========================================================

    def _extract_vins(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []
        seen = set()

        for item in lines:

            data = self._line_data(item)

            text = self._normalize_ocr_text(data["text"])

            for raw_vin in VIN_RE.findall(text):

                value = self._normalize_vin(raw_vin)

                if not self._is_valid_vin(value):
                    continue

                if value in seen:
                    continue

                seen.add(value)

                facts.append(
                    self._create_fact(
                        "VIN",
                        value,
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.90,
                        method="STS",
                    )
                )

        return facts

    # ========================================================
    # ПУНКТ 3.9.8 — ПОИСК ГОСНОМЕРА
    # ========================================================

    def _extract_plates(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []
        seen = set()

        for item in lines:

            data = self._line_data(item)

            text = self._normalize_ocr_text(data["text"])

            for raw_plate in PLATE_RE.findall(text):

                value = self._normalize_plate(raw_plate)

                if not self._is_valid_plate(value):
                    continue

                if value in seen:
                    continue

                seen.add(value)

                facts.append(
                    self._create_fact(
                        "PLATE",
                        value,
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.90,
                        method="STS",
                    )
                )

        return facts

    # ========================================================
    # ПУНКТ 3.9.9 — ПОИСК НОМЕРА СТС
    # ========================================================

    def _extract_sts_number(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []

        anchors = [
            "СВИДЕТЕЛЬСТВО О РЕГИСТРАЦИИ",
            "СВИДЕТЕЛЬСТВО",
            "СТС",
        ]

        idx = self._find_anchor_index(lines, anchors)

        if idx == -1:
            return facts

        patterns = [
            r"\b\d{2}\s?[А-ЯA-Z]{2}\s?\d{6}\b",
            r"\b[А-ЯA-Z]{2}\s?\d{8}\b",
            r"\b\d{10}\b",
        ]

        for j in range(idx, min(idx + 8, len(lines))):

            data = self._line_data(lines[j])
            text = self._normalize_ocr_text(data["text"])

            for pattern in patterns:

                match = re.search(
                    pattern,
                    text,
                    re.IGNORECASE,
                )

                if not match:
                    continue

                value = match.group(0).strip()

                facts.append(
                    self._create_fact(
                        "STS_NUMBER",
                        value,
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.85,
                        method="STS",
                    )
                )

                return facts

        return facts

    # ========================================================
    # ПУНКТ 3.9.10 — МАРКА / МОДЕЛЬ
    # ========================================================

    def _extract_vehicle_text(
        self,
        lines: list,
        anchors: list,
        fact_type: str,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []

        idx = self._find_anchor_index(
            lines,
            anchors,
        )

        if idx == -1:
            return facts

        # Ищем значение только в нескольких строках после якоря.
        for j in range(idx + 1, min(idx + 5, len(lines))):

            data = self._line_data(lines[j])

            text = self._normalize_ocr_text(
                data["text"]
            ).strip()

            if len(text) < 2:
                continue

            # Не принимаем следующую подпись как значение.
            upper = text.upper()

            forbidden = [
                "VIN",
                "ИДЕНТИФИКАЦИОННЫЙ",
                "ГОСУДАРСТВЕННЫЙ",
                "РЕГИСТРАЦИОННЫЙ",
                "ГОД",
                "КУЗОВ",
                "ШАССИ",
                "МОЩНОСТЬ",
            ]

            if any(
                marker in upper
                for marker in forbidden
            ):
                continue

            facts.append(
                self._create_fact(
                    fact_type,
                    text,
                    doc_type,
                    doc_id,
                    data["page"],
                    data["text"],
                    data["confidence"],
                    0.75,
                    method="STS",
                )
            )

            return facts

        return facts

    # ========================================================
    # ПУНКТ 3.9.11 — ГОД ВЫПУСКА
    # ========================================================

    def _extract_vehicle_year(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []

        idx = self._find_anchor_index(
            lines,
            [
                "ГОД ВЫПУСКА",
                "ГОД ИЗГОТОВЛЕНИЯ",
            ],
        )

        if idx == -1:
            return facts

        for j in range(idx, min(idx + 4, len(lines))):

            data = self._line_data(lines[j])

            match = YEAR_RE.search(
                data["text"]
            )

            if not match:
                continue

            year = match.group(1)

            facts.append(
                self._create_fact(
                    "VEHICLE_YEAR",
                    year,
                    doc_type,
                    doc_id,
                    data["page"],
                    data["text"],
                    data["confidence"],
                    0.90,
                    method="STS",
                )
            )

            return facts

        return facts

    # ========================================================
    # ПУНКТ 3.9.12 — ДАТЫ
    # ========================================================

    def _extract_dates(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []

        anchors = [
            "ДАТА ВЫДАЧИ",
            "ДАТА РЕГИСТРАЦИИ",
            "ДАТА",
        ]

        idx = self._find_anchor_index(
            lines,
            anchors,
        )

        if idx == -1:
            return facts

        for j in range(
            idx,
            min(idx + 4, len(lines)),
        ):

            data = self._line_data(lines[j])

            for value in DATE_RE.findall(
                data["text"]
            ):

                facts.append(
                    self._create_fact(
                        "DATE",
                        value,
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.75,
                        method="STS",
                    )
                )

        return facts

    # ========================================================
    # ПУНКТ 3.9.13 — ОСНОВНОЙ EXTRACT
    # ========================================================

    def extract_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []

        # ----------------------------------------------------
        # НОМЕР СТС
        # ----------------------------------------------------

        facts.extend(
            self._extract_sts_number(
                lines,
                doc_type,
                doc_id,
            )
        )

        # ----------------------------------------------------
        # VIN
        # ----------------------------------------------------

        facts.extend(
            self._extract_vins(
                lines,
                doc_type,
                doc_id,
            )
        )

        # ----------------------------------------------------
        # ГОСНОМЕР
        # ----------------------------------------------------

        facts.extend(
            self._extract_plates(
                lines,
                doc_type,
                doc_id,
            )
        )

        # ----------------------------------------------------
        # МАРКА
        # ----------------------------------------------------

        facts.extend(
            self._extract_vehicle_text(
                lines,
                [
                    "МАРКА",
                    "МАРКА ТС",
                    "МАРКА / МОДЕЛЬ",
                ],
                "VEHICLE_BRAND",
                doc_type,
                doc_id,
            )
        )

        # ----------------------------------------------------
        # МОДЕЛЬ
        # ----------------------------------------------------

        facts.extend(
            self._extract_vehicle_text(
                lines,
                [
                    "МОДЕЛЬ",
                    "МОДЕЛЬ ТС",
                ],
                "VEHICLE_MODEL",
                doc_type,
                doc_id,
            )
        )

        # ----------------------------------------------------
        # ГОД
        # ----------------------------------------------------

        facts.extend(
            self._extract_vehicle_year(
                lines,
                doc_type,
                doc_id,
            )
        )

        # ----------------------------------------------------
        # ДАТЫ
        # ----------------------------------------------------

        facts.extend(
            self._extract_dates(
                lines,
                doc_type,
                doc_id,
            )
        )

        return facts
