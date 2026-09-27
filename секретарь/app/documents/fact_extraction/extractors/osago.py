"""
ЭТАП 3.9–3.13
Парсер полиса ОСАГО.

Извлекает только наблюдаемые факты документа.

ВАЖНО:
- Fact != Entity.
- Даты извлекаются только с контекстом.
- Если контекст недостаточен — не угадываем.
- Лучше пропустить факт, чем создать неправильный факт.
"""

import re
from typing import Any, Dict, List

from .base import BaseExtractor
from ..config import TEMPLATE_MARKERS


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


class OsagoExtractor(BaseExtractor):

    # ========================================================
    # ОСНОВНОЙ EXTRACTOR
    # ========================================================

    def extract_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []
        used_dates = set()

        # ====================================================
        # 1. НОМЕР ПОЛИСА
        # ====================================================

        idx = self._find_anchor_index(
            lines,
            [
                "СТРАХОВОЙ ПОЛИС",
                "ПОЛИС ОСАГО",
                "СЕРИЯ И НОМЕР ПОЛИСА",
                "НОМЕР ПОЛИСА",
            ],
        )

        if idx != -1:

            for j in range(
                idx,
                min(idx + 5, len(lines)),
            ):

                data = self._line_data(lines[j])

                match = POLICY_RE.search(
                    data["text"]
                )

                if not match:
                    continue

                facts.append(
                    self._create_fact(
                        "POLICY_NUMBER",
                        match.group(0),
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.99,
                        method="OSAGO",
                    )
                )

                break

        # ====================================================
        # 2. ФИО СТРАХОВАТЕЛЯ / СОБСТВЕННИКА
        # ====================================================

        for anchor in [
            "СТРАХОВАТЕЛЬ:",
            "СТРАХОВАТЕЛЬ",
            "СОБСТВЕННИК:",
            "СОБСТВЕННИК",
        ]:

            idx = self._find_anchor_index(
                lines,
                [anchor],
            )

            if idx == -1:
                continue

            # Сначала проверяем значение в той же строке.
            anchor_data = self._line_data(lines[idx])
            anchor_text = anchor_data["text"]

            if ":" in anchor_text:

                candidate = (
                    anchor_text.split(":", 1)[1]
                    .strip()
                )

                if self._looks_like_person_name(
                    candidate
                ):

                    facts.append(
                        self._create_fact(
                            "PERSON_FULL_NAME",
                            candidate,
                            doc_type,
                            doc_id,
                            anchor_data["page"],
                            anchor_text,
                            anchor_data["confidence"],
                            0.92,
                            method="OSAGO",
                        )
                    )

                    break

            # Если значение находится ниже label.
            for j in range(
                idx + 1,
                min(idx + 5, len(lines)),
            ):

                data = self._line_data(lines[j])
                text = data["text"].strip()

                if not text:
                    continue

                if any(
                    marker.upper() in text.upper()
                    for marker in TEMPLATE_MARKERS
                ):
                    continue

                if not self._looks_like_person_name(
                    text
                ):
                    continue

                candidate = (
                    text
                    .split(",")[0]
                    .strip()
                )

                facts.append(
                    self._create_fact(
                        "PERSON_FULL_NAME",
                        candidate,
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.88,
                        method="OSAGO",
                    )
                )

                break

            if any(
                fact.get("type") == "PERSON_FULL_NAME"
                for fact in facts
            ):
                break

        # ====================================================
        # 3. СТРАХОВЩИК
        # ====================================================
        #
        # ВАЖНО:
        # Раньше здесь достаточно было найти слово
        # "СТРАХОВЩИК", а затем взять следующую строку.
        #
        # Это приводило к ошибке:
        #
        # INSURER =
        # "В случае возникновения спора..."
        #
        # Теперь лучше НЕ извлечь страховщика вообще,
        # чем записать в INSURER посторонний текст.
        # ====================================================

        idx = self._find_anchor_index(
            lines,
            [
                "СТРАХОВЩИК:",
                "СТРАХОВАЯ КОМПАНИЯ:",
                "СТРАХОВАЯ ОРГАНИЗАЦИЯ:",
                "СТРАХОВЩИК",
                "СТРАХОВАЯ КОМПАНИЯ",
                "СТРАХОВАЯ ОРГАНИЗАЦИЯ",
            ],
        )

        if idx != -1:

            data = self._line_data(lines[idx])
            text = data["text"].strip()

            # Самый безопасный случай:
            # значение находится после ":" в той же строке.
            if ":" in text:

                candidate = (
                    text.split(":", 1)[1]
                    .strip()
                )

                if self._looks_like_insurer(
                    candidate
                ):

                    facts.append(
                        self._create_fact(
                            "INSURER",
                            candidate,
                            doc_type,
                            doc_id,
                            data["page"],
                            data["text"],
                            data["confidence"],
                            0.92,
                            method="OSAGO",
                        )
                    )

            else:
                # Следующую строку разрешаем брать только
                # если она действительно похожа на название
                # страховой организации.
                for j in range(
                    idx + 1,
                    min(idx + 3, len(lines)),
                ):

                    next_data = self._line_data(
                        lines[j]
                    )

                    candidate = (
                        next_data["text"]
                        .strip()
                    )

                    if not candidate:
                        continue

                    if self._looks_like_insurer(
                        candidate
                    ):

                        facts.append(
                            self._create_fact(
                                "INSURER",
                                candidate,
                                doc_type,
                                doc_id,
                                next_data["page"],
                                self._build_fragment(
                                    lines,
                                    idx,
                                    j + 1,
                                ),
                                next_data["confidence"],
                                0.85,
                                method="OSAGO",
                            )
                        )

                        break

        # ====================================================
        # 4. VIN
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
                        method="OSAGO",
                    )
                )

        # ====================================================
        # 5. ГОСНОМЕР
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
                        method="OSAGO",
                    )
                )

        # ====================================================
        # 6. ДАТА РОЖДЕНИЯ
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
                    ],
                },
                method="OSAGO",
                extraction_conf=0.90,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 7. СРОК СТРАХОВАНИЯ
        # ====================================================

        contextual, used_dates = (
            self._extract_date_range_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                range_anchors=[
                    "СРОК СТРАХОВАНИЯ",
                    "СРОК ДЕЙСТВИЯ",
                    "СРОК СТРАХОВАНИЯ С",
                    "НАЧАЛО СТРАХОВАНИЯ",
                ],
                start_fact_type="POLICY_START_DATE",
                end_fact_type="POLICY_END_DATE",
                method="OSAGO",
                extraction_conf=0.92,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 8. ПЕРИОД ИСПОЛЬЗОВАНИЯ
        # ====================================================

        contextual, used_dates = (
            self._extract_date_range_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                range_anchors=[
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ",
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ ТС",
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ ТРАНСПОРТНОГО СРЕДСТВА",
                ],
                start_fact_type="USAGE_PERIOD_START",
                end_fact_type="USAGE_PERIOD_END",
                method="OSAGO",
                extraction_conf=0.92,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 9. ДАТА ЗАКЛЮЧЕНИЯ ДОГОВОРА
        # ====================================================

        contextual, used_dates = (
            self._extract_contextual_date_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                contexts={
                    "CONTRACT_DATE": [
                        "ДАТА ДОГОВОРА",
                        "ДАТА ЗАКЛЮЧЕНИЯ ДОГОВОРА",
                        "ЗАКЛЮЧЕНИЕ ДОГОВОРА",
                        "ДАТА ПОДПИСАНИЯ ДОГОВОРА",
                    ],
                },
                method="OSAGO",
                extraction_conf=0.92,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 10. ДАТА ВЫДАЧИ ПОЛИСА / ДОКУМЕНТА
        # ====================================================

        contextual, used_dates = (
            self._extract_contextual_date_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                contexts={
                    "DOCUMENT_DATE": [
                        "ДАТА ДОКУМЕНТА",
                        "ДАТА ВЫДАЧИ",
                        "ДАТА ВЫДАЧИ ПОЛИСА",
                    ],
                },
                method="OSAGO",
                extraction_conf=0.92,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # 11. ОСТАЛЬНЫЕ ДАТЫ
        # ====================================================
        #
        # Здесь специально НЕ пытаемся определить смысл даты.
        #
        # Но даты, которые уже были распознаны как:
        #
        # BIRTH_DATE
        # POLICY_START_DATE
        # POLICY_END_DATE
        # USAGE_PERIOD_START
        # USAGE_PERIOD_END
        # CONTRACT_DATE
        # DOCUMENT_DATE
        #
        # сюда не попадают.
        #
        # Это сохраняет наблюдаемую дату, но не выдаёт ей
        # ложный смысл.
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
                        method="OSAGO",
                    )
                )

                used_dates.add(key)

        return self._deduplicate_facts(
            facts
        )

    # ========================================================
    # ПРОВЕРКА ФИО
    # ========================================================

    def _looks_like_person_name(
        self,
        value: str,
    ) -> bool:
        """
        Осторожная проверка кандидата на ФИО.

        Не пытается определить Person.
        Только отбрасывает явно неподходящие строки.
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
            word.strip(".,;:()[]")
            for word in text.split()
            if word.strip(".,;:()[]")
        ]

        if len(words) < 2 or len(words) > 5:
            return False

        # Не принимаем длинные служебные фразы.
        forbidden = {
            "В",
            "С",
            "ПО",
            "ДЛЯ",
            "ПРИ",
            "СЛУЧАЕ",
            "РАЗМЕР",
            "СТРАХОВАНИЯ",
            "ДОКУМЕНТ",
            "ПОЛИС",
            "ДОГОВОР",
        }

        if any(
            word.upper() in forbidden
            for word in words
        ):
            return False

        return True

    # ========================================================
    # ПРОВЕРКА СТРАХОВЩИКА
    # ========================================================

    def _looks_like_insurer(
        self,
        value: str,
    ) -> bool:
        """
        Проверяет, похожа ли строка на название
        страховой организации.

        Цель — НЕ угадать страховщика,
        а отсеять явно посторонний текст.

        Если уверенности нет — возвращаем False.
        """

        text = str(value).strip()

        if not text:
            return False

        upper = text.upper()

        # Явно не принимаем длинные служебные предложения.
        if len(text) > 180:
            return False

        forbidden_phrases = [
            "В СЛУЧАЕ",
            "ОБРАЩАТЬСЯ",
            "ОБРАТИТЬСЯ",
            "СПОРА",
            "ФИНАНСОВОМУ",
            "СУД",
            "ДОЛЖНЫ",
            "ВЫ ДОЛЖНЫ",
            "УРЕГУЛИРОВАНИЯ",
        ]

        if any(
            phrase in upper
            for phrase in forbidden_phrases
        ):
            return False

        # Типичные юридические формы организаций.
        organization_markers = [
            "ООО",
            "АО",
            "ПАО",
            "САО",
            "ОСАО",
            "СПАО",
            "ЗАО",
            "СТРАХ",
            "INSURANCE",
            "INSUR",
        ]

        if any(
            marker in upper
            for marker in organization_markers
        ):
            return True

        # Если нет организационной формы или слова,
        # явно указывающего на страховщика,
        # лучше ничего не извлекать.
        return False
