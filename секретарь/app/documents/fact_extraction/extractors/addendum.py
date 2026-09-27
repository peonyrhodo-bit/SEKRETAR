"""
ЭТАП 3.14
Извлечение наблюдаемых признаков изменения договора.

ВАЖНО:
Не предполагаем, что документ содержит слово «АДДЕНДУМ».
Не объявляем документ addendum только по имени файла.

Если тип уже определён классификатором как АДДЕНДУМ,
извлекаем связанные факты:

- номер;
- дату;
- номера полисов;
- даты;
- текстовые признаки изменения.

Само изменение в CRM НЕ применяется.
"""

import re
from typing import Any, Dict, List

from .base import BaseExtractor


DATE_RE = re.compile(r"\b\d{2}[./-]\d{2}[./-]\d{4}\b")
POLICY_RE = re.compile(r"\b\d{10}\b")


class AddendumExtractor(BaseExtractor):

    def extract_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []
        used_dates = set()

        # ====================================================
        # НОМЕР ДОКУМЕНТА / ИЗМЕНЕНИЯ
        # ====================================================

        idx = self._find_anchor_index(
            lines,
            [
                "НОМЕР ИЗМЕНЕНИЯ",
                "НОМЕР ДОКУМЕНТА",
                "НОМЕР АДДЕНДУМА",
                "№ АДДЕНДУМА",
            ],
        )

        if idx != -1:

            for j in range(idx, min(idx + 4, len(lines))):

                data = self._line_data(lines[j])

                # Ищем короткий идентификатор.
                # Не берём дату как номер.
                matches = re.findall(
                    r"\b\d{1,6}\b",
                    data["text"],
                )

                for number in matches:

                    if len(number) == 4 and DATE_RE.search(data["text"]):
                        continue

                    facts.append(
                        self._create_fact(
                            "ADDENDUM_NUMBER",
                            number,
                            doc_type,
                            doc_id,
                            data["page"],
                            data["text"],
                            data["confidence"],
                            0.80,
                            method="ADDENDUM",
                        )
                    )

                    break

                if facts:
                    break

        # ====================================================
        # ДАТА АДДЕНДУМА
        #
        # ВАЖНО:
        # Раньше здесь каждая дата документа объявлялась
        # ADDENDUM_DATE.
        #
        # Теперь сначала ищем явный контекст.
        # ====================================================

        contextual_date_facts, used_dates = (
            self._extract_contextual_date_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                contexts={
                    "ADDENDUM_DATE": [
                        "ДАТА АДДЕНДУМА",
                        "ДАТА ДОПОЛНЕНИЯ",
                        "ДАТА ИЗМЕНЕНИЯ",
                    ],
                },
                method="ADDENDUM",
                extraction_conf=0.90,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual_date_facts)

        # ----------------------------------------------------
        # Дополнительный безопасный контекст:
        #
        # "АДДЕНДУМ № 2 ОТ 12.03.2025"
        #
        # Дата становится ADDENDUM_DATE только если в той же
        # строке есть признак addendum + "ОТ".
        # ----------------------------------------------------

        for index, item in enumerate(lines):

            data = self._line_data(item)
            text = data["text"]
            upper = text.upper()

            if "АДДЕНДУМ" not in upper and "ДОПОЛНЕНИ" not in upper:
                continue

            match = re.search(
                r"\bОТ\s+(\d{2}[./-]\d{2}[./-]\d{4})\b",
                upper,
            )

            if not match:
                continue

            value = self._normalize_date(match.group(1))
            key = self._date_key(value, data["page"])

            if key in used_dates:
                continue

            facts.append(
                self._create_fact(
                    "ADDENDUM_DATE",
                    value,
                    doc_type,
                    doc_id,
                    data["page"],
                    data["text"],
                    data["confidence"],
                    0.88,
                    method="ADDENDUM",
                )
            )

            used_dates.add(key)

        # ====================================================
        # НОМЕРА ПОЛИСОВ / ДОГОВОРОВ
        # ====================================================

        for item in lines:

            data = self._line_data(item)
            text_upper = data["text"].upper()

            if (
                "ПОЛИС" not in text_upper
                and "ДОГОВОР" not in text_upper
            ):
                continue

            for number in POLICY_RE.findall(data["text"]):

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
                        method="ADDENDUM",
                    )
                )

        # ====================================================
        # ЯВНО УКАЗАННЫЕ ДРУГИЕ ДАТЫ
        #
        # Если дата не имеет установленного контекста,
        # сохраняем её как DATE, а не как ADDENDUM_DATE.
        # ====================================================

        for item in lines:

            data = self._line_data(item)

            for date in DATE_RE.findall(data["text"]):

                value = self._normalize_date(date)
                key = self._date_key(value, data["page"])

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
                        method="ADDENDUM",
                    )
                )

                used_dates.add(key)

        # ====================================================
        # ТИП ИЗМЕНЕНИЯ
        # ====================================================

        change_markers = [
            "ВНЕСТИ ИЗМЕНЕНИЯ",
            "ИЗМЕНЕНИЕ",
            "ИЗМЕНЕН",
            "ИЗМЕНИТЬ",
            "ДОПОЛНИТЬ",
            "ДОПОЛНЕНИЕ",
            "ЗАМЕНИТЬ",
        ]

        for item in lines:

            data = self._line_data(item)
            text_upper = data["text"].upper()

            for marker in change_markers:

                if marker in text_upper:

                    facts.append(
                        self._create_fact(
                            "ADDENDUM_CHANGE_TYPE",
                            data["text"].strip(),
                            doc_type,
                            doc_id,
                            data["page"],
                            data["text"],
                            data["confidence"],
                            0.70,
                            method="ADDENDUM",
                        )
                    )

                    break

        return self._deduplicate_facts(facts)
