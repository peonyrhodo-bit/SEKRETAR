"""
ЭТАП 3.9–3.13
Парсер паспорта РФ.

Извлекает наблюдаемые факты.
Не определяет сущность Person.

Даты сохраняются с контекстом.
"""

import re
from typing import Any, Dict, List

from .base import BaseExtractor


PASSPORT_RE = re.compile(
    r"\b\d{4}\s?\d{6}\b"
)

DATE_RE = re.compile(
    r"\b\d{2}[./-]\d{2}[./-]\d{4}\b"
)


class PassportExtractor(BaseExtractor):

    def extract_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []
        used_dates = set()

        # ====================================================
        # ПАСПОРТ
        # ====================================================

        idx = self._find_anchor_index(
            lines,
            [
                "ПАСПОРТ ГРАЖДАНИНА РОССИЙСКОЙ ФЕДЕРАЦИИ",
                "ПАСПОРТ ГРАЖДАНИНА РФ",
                "ПАСПОРТ РФ",
            ],
        )

        if idx != -1:

            for j in range(
                idx,
                min(idx + 8, len(lines)),
            ):

                data = self._line_data(lines[j])

                match = PASSPORT_RE.search(
                    data["text"]
                )

                if match:

                    value = re.sub(
                        r"\s+",
                        "",
                        match.group(0),
                    )

                    facts.append(
                        self._create_fact(
                            "PASSPORT_SERIES",
                            value[:4],
                            doc_type,
                            doc_id,
                            data["page"],
                            data["text"],
                            data["confidence"],
                            0.90,
                            method="PASSPORT",
                        )
                    )

                    facts.append(
                        self._create_fact(
                            "PASSPORT_NUMBER",
                            value[4:],
                            doc_type,
                            doc_id,
                            data["page"],
                            data["text"],
                            data["confidence"],
                            0.90,
                            method="PASSPORT",
                        )
                    )

                    break

        # ====================================================
        # ФИО
        # ====================================================

        anchors = [
            "ФАМИЛИЯ",
            "ИМЯ",
            "ОТЧЕСТВО",
        ]

        for anchor in anchors:

            idx = self._find_anchor_index(
                lines,
                [anchor],
            )

            if idx == -1:
                continue

            for j in range(
                idx + 1,
                min(idx + 4, len(lines)),
            ):

                data = self._line_data(lines[j])
                value = data["text"].strip()

                if len(value) < 2:
                    continue

                if re.search(
                    r"\d",
                    value,
                ):
                    continue

                fact_type = {
                    "ФАМИЛИЯ": "PERSON_SURNAME",
                    "ИМЯ": "PERSON_NAME",
                    "ОТЧЕСТВО": "PERSON_PATRONYMIC",
                }[anchor]

                facts.append(
                    self._create_fact(
                        fact_type,
                        value,
                        doc_type,
                        doc_id,
                        data["page"],
                        data["text"],
                        data["confidence"],
                        0.85,
                        method="PASSPORT",
                    )
                )

                break

        # ====================================================
        # ДАТА РОЖДЕНИЯ
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
                method="PASSPORT",
                extraction_conf=0.90,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # ДАТА ВЫДАЧИ
        # ====================================================

        contextual, used_dates = (
            self._extract_contextual_date_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                contexts={
                    "DOCUMENT_DATE": [
                        "ДАТА ВЫДАЧИ",
                        "ВЫДАН",
                    ],
                },
                method="PASSPORT",
                extraction_conf=0.88,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # ПРОЧИЕ ДАТЫ
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
                        method="PASSPORT",
                    )
                )

                used_dates.add(key)

        return self._deduplicate_facts(facts)
