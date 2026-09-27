"""
ЭТАП 3 — ДОКУМЕНТЫ → ФАКТЫ
Файл: extractors/base.py

Единый базовый интерфейс всех extractor'ов.

ВАЖНО:

Fact != Entity.

Extractor только сообщает:
- что написано;
- где написано;
- насколько уверенно распознано.

Extractor НЕ определяет:
- владельца;
- клиента;
- автомобиль;
- полис как сущность;
- окончательное значение при конфликте.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import re

from ..normalizer import normalize_ocr_for_search


class BaseExtractor(ABC):
    # ========================================================
    # ОСНОВНОЙ ИНТЕРФЕЙС
    # ========================================================

    @abstractmethod
    def extract_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Вернуть список наблюдаемых фактов документа.
        """
        raise NotImplementedError

    # ========================================================
    # РАБОТА СО СТРОКАМИ
    # ========================================================

    def _line_data(self, item) -> Dict[str, Any]:
        """
        Приводит строку OCR/text layer к единому виду.

        Поддерживает:

        tuple/list:
            (text, confidence, page)

        dict:
            {
                "text": ...,
                "confidence": ...,
                "page": ...
            }

        str:
            обычная строка.
        """

        text = ""
        confidence = 1.0
        page = 1

        if isinstance(item, (list, tuple)):

            if len(item) >= 1:
                text = str(item[0])

            if len(item) >= 2:
                try:
                    confidence = float(item[1])
                except (TypeError, ValueError):
                    confidence = 1.0

            if len(item) >= 3:
                try:
                    page = int(item[2])
                except (TypeError, ValueError):
                    page = 1

        elif isinstance(item, dict):

            text = str(item.get("text", ""))

            try:
                confidence = float(
                    item.get("confidence", 1.0)
                )
            except (TypeError, ValueError):
                confidence = 1.0

            try:
                page = int(item.get("page", 1))
            except (TypeError, ValueError):
                page = 1

        else:
            text = str(item)

        return {
            "text": text,
            "confidence": max(
                0.0,
                min(1.0, confidence),
            ),
            "page": page,
        }

    # ========================================================
    # НОРМАЛИЗАЦИЯ ДЛЯ ПОИСКА
    # ========================================================

    def _normalize_search(self, text: Any) -> str:
        """
        Нормализация только для поиска.

        Оригинальный fragment никогда не изменяется.
        """

        try:
            return normalize_ocr_for_search(
                str(text)
            ).upper().strip()
        except Exception:
            return str(text).upper().strip()

    def _anchor_exists(
        self,
        text: str,
        anchor: str,
    ) -> bool:
        """
        Проверяет наличие anchor.

        Для коротких якорей используются границы слова,
        чтобы избежать ложных совпадений.
        """

        raw = str(text).upper()
        anchor_upper = str(anchor).upper().strip()

        if not anchor_upper:
            return False

        if anchor_upper == "ПО":
            return bool(
                re.search(
                    r"\bПО\b",
                    raw,
                )
            )

        if anchor_upper == "С НА":
            return bool(
                re.search(
                    r"\bС\s+НА\b",
                    raw,
                )
            )

        if anchor_upper == "Г.Р.":
            return bool(
                re.search(
                    r"\bГ\.?\s*Р\.?\b",
                    raw,
                )
            )

        normalized_text = self._normalize_search(text)
        normalized_anchor = self._normalize_search(anchor)

        return normalized_anchor in normalized_text

    def _find_anchor_index(
        self,
        lines: list,
        anchors: list,
    ) -> int:
        """
        Возвращает индекс первой строки, содержащей anchor.
        """

        for index, item in enumerate(lines):

            data = self._line_data(item)

            for anchor in anchors:

                if self._anchor_exists(
                    data["text"],
                    str(anchor),
                ):
                    return index

        return -1

    # ========================================================
    # ФРАГМЕНТ ДОКАЗАТЕЛЬСТВА
    # ========================================================

    def _build_fragment(
        self,
        lines: list,
        start: int,
        end: Optional[int] = None,
    ) -> str:
        """
        Собирает доказательный фрагмент из нескольких строк.
        """

        if end is None:
            end = start + 1

        parts = []

        for item in lines[start:end]:

            data = self._line_data(item)
            text = data["text"].strip()

            if text:
                parts.append(text)

        return " ".join(parts)

    def _get_ocr_confidence(
        self,
        item,
    ) -> float:

        return self._line_data(item)["confidence"]

    def _clean_value(
        self,
        value: Any,
    ) -> str:

        return str(value).strip()

    # ========================================================
    # ЕДИНАЯ СТРУКТУРА ФАКТА
    # ========================================================

    def _create_fact(
        self,
        fact_type: str,
        value: Any,
        doc_type: str,
        doc_id: str,
        page: Optional[int],
        fragment: str,
        ocr_conf: float,
        extraction_conf: float,
        method: Optional[str] = None,
        status: str = "EXTRACTED",
        source: Optional[str] = None,
        text_method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Единая точка создания факта.

        OCR confidence:
            качество распознавания исходной строки.

        Extraction confidence:
            уверенность правила извлечения.

        Они НЕ смешиваются.

        text_method:
            способ получения исходного текста документа:
            TEXT_LAYER / OCR / STRUCTURED_TEXT / и т.д.

        Важно:
        text_method не заменяет method.

        method = каким extractor/rule получен факт.
        text_method = каким способом был получен исходный текст.
        """

        try:
            ocr = float(ocr_conf)
        except (TypeError, ValueError):
            ocr = 0.0

        try:
            extraction = float(extraction_conf)
        except (TypeError, ValueError):
            extraction = 0.0

        ocr = max(
            0.0,
            min(1.0, ocr),
        )

        extraction = max(
            0.0,
            min(1.0, extraction),
        )

        if page is not None:

            try:
                page = int(page)
            except (TypeError, ValueError):
                page = None

        if method is None:
            method = doc_type

        if source is None:
            source = "DOCUMENT"

        fact = {
            "type": str(fact_type),
            "value": self._clean_value(value),
            "document_id": str(doc_id),
            "page": page,
            "fragment": str(fragment).strip(),
            "confidence": {
                "ocr": round(ocr, 3),
                "extraction": round(
                    extraction,
                    3,
                ),
            },
            "method": str(method),
            "status": str(status),
            "source": str(source),
        }

        # Способ получения исходного текста.
        # Сохраняем только если он реально известен.
        if text_method:
            fact["text_method"] = str(text_method)

        return fact

    def _create_line_fact(
        self,
        fact_type: str,
        value: Any,
        item,
        doc_type: str,
        doc_id: str,
        extraction_conf: float = 0.90,
        fragment: Optional[str] = None,
        method: Optional[str] = None,
        text_method: Optional[str] = None,
    ) -> Dict[str, Any]:

        data = self._line_data(item)

        if fragment is None:
            fragment = data["text"]

        return self._create_fact(
            fact_type=fact_type,
            value=value,
            doc_type=doc_type,
            doc_id=doc_id,
            page=data["page"],
            fragment=fragment,
            ocr_conf=data["confidence"],
            extraction_conf=extraction_conf,
            method=method,
            text_method=text_method,
        )

    # ========================================================
    # ДАТЫ
    # ========================================================

    def _date_matches(
        self,
        text: str,
    ) -> List[str]:
        """
        Возвращает даты в формате DD.MM.YYYY.

        Здесь НЕ определяется смысл даты.
        Эта функция только находит текстовые совпадения.
        """

        pattern = re.compile(
            r"\b\d{2}[./-]\d{2}[./-]\d{4}\b"
        )

        return [
            self._normalize_date(match)
            for match in pattern.findall(str(text))
        ]

    def _normalize_date(
        self,
        value: str,
    ) -> str:

        return (
            str(value)
            .replace("/", ".")
            .replace("-", ".")
        )

    def _date_key(
        self,
        value: str,
        page: Optional[int],
    ) -> Tuple[str, Any]:

        return (
            self._normalize_date(value),
            page,
        )

    # ========================================================
    # КОНТЕКСТ ДАТЫ
    # ========================================================

    def _find_context_dates(
        self,
        lines: list,
        index: int,
        window: int = 2,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Ищет даты только в локальном контексте anchor.

        ВАЖНО:

        Не ищем дату по всему документу.

        Но и не разрешаем произвольно связывать
        далёкую дату с anchor.

        Возвращаются даты в порядке их появления.
        """

        result = []

        end = min(
            index + window + 1,
            len(lines),
        )

        anchor_data = self._line_data(lines[index])

        for current_index in range(
            index,
            end,
        ):

            data = self._line_data(
                lines[current_index]
            )

            # Контекст даты не должен пересекать страницы.
            if data["page"] != anchor_data["page"]:
                break

            for date in self._date_matches(
                data["text"]
            ):

                result.append(
                    (
                        date,
                        data,
                    )
                )

        return result

    def _extract_contextual_date_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
        contexts: Dict[str, List[str]],
        method: str,
        extraction_conf: float = 0.90,
        used_dates: Optional[set] = None,
        text_method: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], set]:
        """
        Извлекает дату только при наличии явного контекста.

        Например:

            ДАТА РОЖДЕНИЯ: 12.03.1985

        даст:

            BIRTH_DATE = 12.03.1985

        Произвольная дата в тексте документа
        не получает смысл BIRTH_DATE.

        ВАЖНО:

        Если anchor найден, но рядом нет даты,
        ничего не придумываем.

        Если рядом несколько дат, берём только
        первую подходящую дату из локального контекста.
        """

        facts = []

        if used_dates is None:
            used_dates = set()

        for fact_type, anchors in contexts.items():

            for index, item in enumerate(lines):

                data = self._line_data(item)

                matched_anchor = False

                for anchor in anchors:

                    if self._anchor_exists(
                        data["text"],
                        anchor,
                    ):
                        matched_anchor = True
                        break

                if not matched_anchor:
                    continue

                candidates = self._find_context_dates(
                    lines,
                    index,
                    window=2,
                )

                if not candidates:
                    continue

                # Берём ближайшую дату к anchor.
                date_value, date_data = candidates[0]

                key = self._date_key(
                    date_value,
                    date_data["page"],
                )

                if key in used_dates:
                    continue

                fragment = self._build_fragment(
                    lines,
                    index,
                    min(index + 3, len(lines)),
                )

                facts.append(
                    self._create_fact(
                        fact_type=fact_type,
                        value=date_value,
                        doc_type=doc_type,
                        doc_id=doc_id,
                        page=date_data["page"],
                        fragment=fragment,
                        ocr_conf=date_data["confidence"],
                        extraction_conf=extraction_conf,
                        method=method,
                        text_method=text_method,
                    )
                )

                used_dates.add(key)

        return facts, used_dates

    # ========================================================
    # ДИАПАЗОН ДАТ
    # ========================================================

    def _extract_date_range_facts(
        self,
        lines: list,
        doc_type: str,
        doc_id: str,
        range_anchors: List[str],
        start_fact_type: str,
        end_fact_type: str,
        method: str,
        extraction_conf: float = 0.90,
        used_dates: Optional[set] = None,
        text_method: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], set]:
        """
        Извлекает две даты из явно обозначенного периода.

        Например:

            СРОК СТРАХОВАНИЯ
            01.01.2025 — 31.12.2025

        даст:

            POLICY_START_DATE
            POLICY_END_DATE

        ВАЖНО:

        Метод работает только рядом с указанным anchor.

        Он НЕ ищет "первую и вторую дату документа"
        по всему документу.

        Также используется только локальный контекст
        на той же странице.
        """

        facts = []

        if used_dates is None:
            used_dates = set()

        for index, item in enumerate(lines):

            data = self._line_data(item)

            matched = any(
                self._anchor_exists(
                    data["text"],
                    anchor,
                )
                for anchor in range_anchors
            )

            if not matched:
                continue

            candidates = self._find_context_dates(
                lines,
                index,
                window=3,
            )

            if len(candidates) < 2:
                continue

            start_value, start_data = candidates[0]
            end_value, end_data = candidates[1]

            start_key = self._date_key(
                start_value,
                start_data["page"],
            )

            end_key = self._date_key(
                end_value,
                end_data["page"],
            )

            fragment = self._build_fragment(
                lines,
                index,
                min(index + 4, len(lines)),
            )

            if start_key not in used_dates:

                facts.append(
                    self._create_fact(
                        fact_type=start_fact_type,
                        value=start_value,
                        doc_type=doc_type,
                        doc_id=doc_id,
                        page=start_data["page"],
                        fragment=fragment,
                        ocr_conf=start_data["confidence"],
                        extraction_conf=extraction_conf,
                        method=method,
                        text_method=text_method,
                    )
                )

                used_dates.add(start_key)

            if end_key not in used_dates:

                facts.append(
                    self._create_fact(
                        fact_type=end_fact_type,
                        value=end_value,
                        doc_type=doc_type,
                        doc_id=doc_id,
                        page=end_data["page"],
                        fragment=fragment,
                        ocr_conf=end_data["confidence"],
                        extraction_conf=extraction_conf,
                        method=method,
                        text_method=text_method,
                    )
                )

                used_dates.add(end_key)

        return facts, used_dates

    # ========================================================
    # ПРОВЕРКА ЛОКАЛЬНОГО КОНТЕКСТА
    # ========================================================

    def _same_page(
        self,
        first_item,
        second_item,
    ) -> bool:
        """
        Проверяет, находятся ли две строки на одной странице.
        """

        first = self._line_data(first_item)
        second = self._line_data(second_item)

        return first["page"] == second["page"]

    def _line_contains_any_anchor(
        self,
        text: str,
        anchors: List[str],
    ) -> bool:
        """
        Проверяет наличие хотя бы одного anchor в строке.
        """

        return any(
            self._anchor_exists(
                text,
                anchor,
            )
            for anchor in anchors
        )

    # ========================================================
    # НОРМАЛИЗАЦИЯ VIN
    # ========================================================

    def _normalize_vin(
        self,
        value: str,
    ) -> str:
        """
        Минимальная OCR-нормализация VIN.

        Это не означает, что VIN признан истинным.
        Это только нормализация наблюдаемой строки.
        """

        return (
            str(value)
            .upper()
            .replace("О", "0")
            .replace("O", "0")
            .replace("I", "1")
        )

    # ========================================================
    # УДАЛЕНИЕ ТОЧНЫХ ДУБЛИКАТОВ
    # ========================================================

    def _deduplicate_facts(
        self,
        facts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Удаляет только точные дубли одного и того же наблюдения.

        Разные документы, страницы или фрагменты
        НЕ объединяются.

        Разные значения одного факта
        НЕ считаются дублями.
        """

        result = []
        seen = set()

        for fact in facts:

            key = (
                fact.get("type"),
                fact.get("value"),
                fact.get("document_id"),
                fact.get("page"),
                fact.get("fragment"),
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(fact)

        return result
