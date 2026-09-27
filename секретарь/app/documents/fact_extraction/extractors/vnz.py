"""
ЭТАП 3.9–3.13
Парсер ВНЖ.

Извлекаем только наблюдаемые факты.
Не пытаемся определить владельца.

Даты сохраняются с контекстом.
"""

import re
from typing import Any, Dict, List

from .base import BaseExtractor


DATE_RE = re.compile(
    r"\b\d{2}[./-]\d{2}[./-]\d{4}\b"
)


class VnzExtractor(BaseExtractor):

    def extract_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []
        used_dates = set()

        # ====================================================
        # НОМЕР ВНЖ
        # ====================================================

        idx = self._find_anchor_index(
            lines,
            [
                "ВИД НА ЖИТЕЛЬСТВО В РОССИЙСКОЙ ФЕДЕРАЦИИ",
                "ВИД НА ЖИТЕЛЬСТВО",
                "ВНЖ",
            ],
        )

        if idx != -1:

            for j in range(
                idx,
                min(idx + 8, len(lines)),
            ):

                data = self._line_data(
                    lines[j]
                )

                candidates = re.findall(
                    r"\b\d{2,4}[\s-]?\d{4,10}\b",
                    data["text"],
                )

                if candidates:

                    facts.append(
                        self._create_fact(
                            "RESIDENCE_PERMIT_NUMBER",
                            candidates[0],
                            doc_type,
                            doc_id,
                            data["page"],
                            data["text"],
                            data["confidence"],
                            0.70,
                            method="VNZ",
                        )
                    )

                    break

        # ====================================================
        # ФИО
        # ====================================================

        for anchor in [
            "ФАМИЛИЯ",
            "ИМЯ",
            "ОТЧЕСТВО",
        ]:

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

                data = self._line_data(
                    lines[j]
                )

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
                        0.80,
                        method="VNZ",
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
                method="VNZ",
                extraction_conf=0.88,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # ДАТА ВЫДАЧИ / ДОКУМЕНТА
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
                        "ДАТА ОФОРМЛЕНИЯ",
                    ],
                },
                method="VNZ",
                extraction_conf=0.85,
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
                        method="VNZ",
                    )
                )

                used_dates.add(key)

        return self._deduplicate_facts(facts)
