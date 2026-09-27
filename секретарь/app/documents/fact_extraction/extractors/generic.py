"""
ЭТАП 3.16–3.17
Generic extractor.

Если документ не удалось уверенно классифицировать,
мы всё равно можем сохранить наблюдаемые кандидаты.

Это НЕ значит, что найденное является установленным фактом
конкретной сущности.

Для Generic особенно важно:
не приписывать датам смысл, которого нет в документе.
"""

import re
from typing import Any, Dict, List

from .base import BaseExtractor


VIN_RE = re.compile(
    r"\b[A-HJ-NPR-Z0-9]{17}\b",
    re.IGNORECASE,
)

PLATE_RE = re.compile(
    r"\b[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}\b",
    re.IGNORECASE,
)

DATE_RE = re.compile(
    r"\b\d{2}[./-]\d{2}[./-]\d{4}\b"
)


class GenericExtractor(BaseExtractor):

    def extract_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:

        facts = []
        used_dates = set()

        # ====================================================
        # VIN
        # ====================================================

        for item in lines:

            data = self._line_data(item)
            text = data["text"].strip()

            if not text:
                continue

            for vin in VIN_RE.findall(text):

                facts.append(
                    self._create_fact(
                        "VIN",
                        self._normalize_vin(vin),
                        doc_type,
                        doc_id,
                        data["page"],
                        text,
                        data["confidence"],
                        0.65,
                        method="GENERIC",
                    )
                )

        # ====================================================
        # ГОСНОМЕР
        # ====================================================

        for item in lines:

            data = self._line_data(item)
            text = data["text"].strip()

            for plate in PLATE_RE.findall(text):

                facts.append(
                    self._create_fact(
                        "PLATE",
                        plate.upper(),
                        doc_type,
                        doc_id,
                        data["page"],
                        text,
                        data["confidence"],
                        0.65,
                        method="GENERIC",
                    )
                )

        # ====================================================
        # ЯВНЫЕ КОНТЕКСТЫ ДАТ
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
                    "DOCUMENT_DATE": [
                        "ДАТА ДОКУМЕНТА",
                        "ДАТА ВЫДАЧИ",
                        "ВЫДАН",
                    ],
                    "CONTRACT_DATE": [
                        "ДАТА ДОГОВОРА",
                    ],
                    "ADDENDUM_DATE": [
                        "ДАТА АДДЕНДУМА",
                        "ДАТА ДОПОЛНЕНИЯ",
                    ],
                },
                method="GENERIC",
                extraction_conf=0.80,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # ЯВНО ОБОЗНАЧЕННЫЙ ПЕРИОД
        # ====================================================

        contextual, used_dates = (
            self._extract_date_range_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                range_anchors=[
                    "СРОК СТРАХОВАНИЯ",
                    "СРОК ДЕЙСТВИЯ",
                ],
                start_fact_type="POLICY_START_DATE",
                end_fact_type="POLICY_END_DATE",
                method="GENERIC",
                extraction_conf=0.80,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # ПЕРИОД ИСПОЛЬЗОВАНИЯ
        # ====================================================

        contextual, used_dates = (
            self._extract_date_range_facts(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                range_anchors=[
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ",
                    "ПЕРИОД ИСПОЛЬЗОВАНИЯ ТС",
                ],
                start_fact_type="USAGE_PERIOD_START",
                end_fact_type="USAGE_PERIOD_END",
                method="GENERIC",
                extraction_conf=0.80,
                used_dates=used_dates,
            )
        )

        facts.extend(contextual)

        # ====================================================
        # ОСТАЛЬНЫЕ ДАТЫ
        #
        # Не угадываем их назначение.
        # ====================================================

        for item in lines:

            data = self._line_data(item)
            text = data["text"]

            for date in DATE_RE.findall(text):

                value = self._normalize_date(date)
                key = self._date_key(
                    value,
                    data["page"],
                )

                if key in used_dates:
                    continue

                facts.append(
                    self._create_fact(
                        "DATE_CANDIDATE",
                        value,
                        doc_type,
                        doc_id,
                        data["page"],
                        text,
                        data["confidence"],
                        0.55,
                        method="GENERIC",
                    )
                )

                used_dates.add(key)

        return self._deduplicate_facts(facts)
