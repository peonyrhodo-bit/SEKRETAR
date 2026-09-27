"""
ЭТАП 3.9–3.13
Парсер заявления на страхование.

Заявление является источником наблюдений.
Оно не создаёт клиента, автомобиль или полис.

Правила:
- Fact != Entity.
- Даты извлекаются с контекстом.
- Периоды использования автомобиля сохраняются отдельно
  от общего срока страхования.
- Если смысл даты не установлен явно — сохраняем DATE.
- ФИО сохраняем как наблюдение, без определения владельца.
"""

import re
from typing import Any, Dict, List

from .base import BaseExtractor


DATE_RE = re.compile(
    r"\b\d{2}[./-]\d{2}[./-]\d{4}\b"
)

VIN_RE = re.compile(
    r"\b[A-HJ-NPR-Z0-9]{17}\b",
    re.IGNORECASE,
)

PLATE_RE = re.compile(
    r"\b[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}\b",
    re.IGNORECASE,
)

POLICY_RE = re.compile(
    r"\b\d{10}\b"
)


class ApplicationExtractor(BaseExtractor):

    def extract_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []
        used_dates = set()

        # ====================================================
        # 1. VIN
        # ====================================================

        for item in lines:

            data = self._line_data(item)

            for vin in VIN_RE.findall(
                data["text"]
            ):

                facts.append(
                    self._create_fact(
                        "VIN",
                        self._normalize_vin(vin),
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.95,
                        method="APPLICATION",
                    )
                )

        # ====================================================
        # 2. ГОСНОМЕР
        # ====================================================

        for item in lines:

            data = self._line_data(item)

            for plate in PLATE_RE.findall(
                data["text"]
            ):

                facts.append(
                    self._create_fact(
                        "PLATE",
                        plate.upper(),
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.95,
                        method="APPLICATION",
                    )
                )

        # ====================================================
        # 3. НОМЕР ПОЛИСА
        # ====================================================

        for item in lines:

            data = self._line_data(item)
            upper = data["text"].upper()

            if (
                "ПОЛИС" not in upper
                and "ДОГОВОР" not in upper
            ):
                continue

            for number in POLICY_RE.findall(
                data["text"]
            ):

                facts.append(
                    self._create_fact(
                        "POLICY_NUMBER",
                        number,
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.85,
                        method="APPLICATION",
                    )
                )

        # ====================================================
        # 4. ДАТА РОЖДЕНИЯ
        # ====================================================

        contextual, used_dates = (
            self._extract_contextual_date_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                contexts={
                    "BIRTH_DATE": [
                        "ДАТА РОЖДЕНИЯ",
                        "ГОД РОЖДЕНИЯ",
                        "Г.Р.",
                        "DATE OF BIRTH",
                    ],
                },
                method="APPLICATION",
                extraction_conf=0.90,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 5. ДАТА ЗАЯВЛЕНИЯ / ДОКУМЕНТА
        # ====================================================

        contextual, used_dates = (
            self._extract_contextual_date_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                contexts={
                    "DOCUMENT_DATE": [
                        "ДАТА ДОКУМЕНТА",
                        "ДАТА ЗАЯВЛЕНИЯ",
                        "ДАТА ПОДАЧИ",
                        "ДАТА ЗАПОЛНЕНИЯ",
                        "ДАТА ПОДПИСАНИЯ",
                    ],
                },
                method="APPLICATION",
                extraction_conf=0.90,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 6. ДАТА ДОГОВОРА
        # ====================================================

        contextual, used_dates = (
            self._extract_contextual_date_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                contexts={
                    "CONTRACT_DATE": [
                        "ДАТА ДОГОВОРА",
                        "ДОГОВОР ОТ",
                        "ДАТА ЗАКЛЮЧЕНИЯ ДОГОВОРА",
                    ],
                },
                method="APPLICATION",
                extraction_conf=0.90,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 7. ОБЩИЙ СРОК СТРАХОВАНИЯ
        # ====================================================

        contextual, used_dates = (
            self._extract_date_range_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                range_anchors=[
                    "СРОК СТРАХОВАНИЯ",
                    "СРОК ДЕЙСТВИЯ",
                    "СТРАХОВАНИЕ С",
                    "ДЕЙСТВУЕТ С",
                ],
                start_fact_type="POLICY_START_DATE",
                end_fact_type="POLICY_END_DATE",
                method="APPLICATION",
                extraction_conf=0.90,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 8. ПЕРИОД ИСПОЛЬЗОВАНИЯ АВТОМОБИЛЯ
        # ====================================================
        #
        # Это отдельный факт от POLICY_START_DATE /
        # POLICY_END_DATE.
        #
        # Для нашего тестового заявления:
        #
        # 20.09.2026 — 19.12.2026
        #
        # должно попасть именно сюда.
        # ====================================================

        contextual, used_dates = (
            self._extract_date_range_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                range_anchors=[
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ",
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ ТС",
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ АВТОМОБИЛЯ",
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ ТРАНСПОРТНОГО СРЕДСТВА",
                    "ИСПОЛЬЗОВАНИЯ ТС",
                ],
                start_fact_type="USAGE_PERIOD_START",
                end_fact_type="USAGE_PERIOD_END",
                method="APPLICATION",
                extraction_conf=0.92,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 9. ОСТАЛЬНЫЕ ДАТЫ
        # ====================================================
        #
        # Если смысл даты не удалось установить,
        # НЕ приписываем ей значение.
        #
        # Например:
        # 19.09.2026 -> DATE,
        # если рядом нет надёжного контекста.
        # ====================================================

        for item in lines:

            data = self._line_data(item)

            for date in DATE_RE.findall(
                data["text"]
            ):

                value = self._normalize_date(
                    date
                )

                key = self._date_key(
                    value,
                    data["page"],
                )

                if key in used_dates:
                    continue

                facts.append(
                    self._create_fact(
                        "DATE",
                        value,
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.70,
                        method="APPLICATION",
                    )
                )

                used_dates.add(key)

        # ====================================================
        # 10. КАНДИДАТЫ ФИО
        # ====================================================
        #
        # Это только наблюдение.
        #
        # Здесь НЕ определяется:
        # - клиент;
        # - собственник;
        # - страхователь;
        # - водитель.
        # ====================================================

        for item in lines:

            data = self._line_data(item)
            text = data["text"].strip()

            if not self._looks_like_person_name(
                text
            ):
                continue

            facts.append(
                self._create_fact(
                    "PERSON_NAME_CANDIDATE",
                    text,
                    doc_type,
                    doc_id,
                    data["page"],
                    data["text"],
                    data["confidence"],
                    0.55,
                    method="APPLICATION",
                )
            )

        return self._deduplicate_facts(
            facts
        )

    # ========================================================
    # ПРОВЕРКА КАНДИДАТА ФИО
    # ========================================================

    def _looks_like_person_name(
        self,
        value: str,
    ) -> bool:
        """
        Очень осторожный фильтр кандидатов ФИО.

        Не определяет человека.
        Только отбрасывает очевидно неподходящий текст.
        """

        text = str(value).strip()

        if not text:
            return False

        if any(
            char.isdigit()
            for char in text
        ):
            return False

        words = [
            word.strip(
                ".,;:()[]{}\"'"
            )
            for word in text.split()
        ]

        words = [
            word
            for word in words
            if word
        ]

        if not (2 <= len(words) <= 4):
            return False

        if not all(
            word[0].isalpha()
            for word in words
        ):
            return False

        if not (8 <= len(text) <= 100):
            return False

        # Исключаем очевидные служебные строки.
        forbidden = {
            "ЗАЯВЛЕНИЕ",
            "ДОГОВОР",
            "ПОЛИС",
            "СТРАХОВАНИЕ",
            "АВТОМОБИЛЬ",
            "ТРАНСПОРТНОГО",
            "СРЕДСТВА",
            "АДРЕС",
            "ГРАЖДАНСТВО",
            "ВОДИТЕЛЬ",
            "СТРАХОВАТЕЛЬ",
            "СОБСТВЕННИК",
        }

        if any(
            word.upper() in forbidden
            for word in words
        ):
            return False

        return True
