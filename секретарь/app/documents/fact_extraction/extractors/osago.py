"""
ЭТАП 3.9–3.13
Парсер полиса ОСАГО.
Извлекает только наблюдаемые факты документа.
ВАЖНО:
Fact != Entity.
Даты извлекаются только с контекстом.
Если контекст недостаточен — не угадываем.
Лучше пропустить факт, чем создать неправильный факт.
"""
import re
from typing import Any, Dict, List
from .base import BaseExtractor
from ..config import TEMPLATE_MARKERS

DATE_RE = re.compile(
    r"\b\d{2}[./-]\d{2}[./-]\d{4}\b"
)

VISUAL_DATE_TOKEN_RE = re.compile(
    r"^(?:0?[0-9]|[12][0-9]|3[01])$"
)

VISUAL_MONTH_RE = re.compile(
    r"^(?:0?[1-9]|1[0-2])$"
)

VISUAL_YEAR_RE = re.compile(
    r"^(?:19|20)\d{2}$"
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


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ВИЗУАЛЬНОГО OCR
# ============================================================

def _box_bounds(box):
    if not box:
        return None

    try:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        return (
            min(xs),
            min(ys),
            max(xs),
            max(ys),
        )
    except (TypeError, ValueError, IndexError):
        return None


def _visual_item_data(item):
    """
    Возвращает данные OCR-бокса, если они присутствуют.

    Важно:
    координаты используются только для реконструкции
    наблюдаемого значения. Они не определяют сущность.
    """
    if not isinstance(item, dict):
        return None

    box = _box_bounds(item.get("box"))
    if box is None:
        return None

    try:
        confidence = float(item.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    try:
        page = int(item.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    return {
        "text": str(item.get("text", "")).strip(),
        "confidence": max(0.0, min(1.0, confidence)),
        "page": page,
        "box": box,
    }


def _visual_numeric_token(text):
    """
    Оставляет только безопасные цифровые OCR-токены.
    """
    value = str(text).strip()

    # Частые OCR-артефакты вокруг цифр.
    value = (
        value.replace("[", "")
        .replace("]", "")
        .replace("(", "")
        .replace(")", "")
        .replace("<", "")
        .replace(">", "")
    )

    if not value.isdigit():
        return None

    if len(value) > 4:
        return None

    return value


def _visual_reconstruct_date(
    items,
    anchor_item,
    *,
    max_y_distance=38,
):
    """
    Восстанавливает DD.MM.YYYY из отдельных OCR-боксов.

    Пример:
        20 | 09 | 20 | 26
    ->
        20.09.2026

    Используется только рядом с конкретным смысловым
    anchor. Даты из других частей страницы сюда не попадают.
    """
    anchor = _visual_item_data(anchor_item)
    if anchor is None:
        return None

    ax1, ay1, ax2, ay2 = anchor["box"]
    anchor_y = (ay1 + ay2) / 2

    candidates = []

    for item in items:
        data = _visual_item_data(item)
        if data is None:
            continue

        if data["page"] != anchor["page"]:
            continue

        text = data["text"]
        token = _visual_numeric_token(text)

        if token is None:
            continue

        x1, y1, x2, y2 = data["box"]
        center_y = (y1 + y2) / 2
        center_x = (x1 + x2) / 2

        if abs(center_y - anchor_y) > max_y_distance:
            continue

        # Значение должно находиться правее anchor.
        if center_x <= ax2:
            continue

        if len(token) not in (1, 2, 4):
            continue

        candidates.append(
            {
                "token": token.zfill(2)
                if len(token) == 1
                else token,
                "data": data,
                "x": center_x,
                "y": center_y,
            }
        )

    candidates.sort(key=lambda item: item["x"])

    # Ищем последовательность DD MM YYYY.
    for i in range(len(candidates)):
        first = candidates[i]

        try:
            day = int(first["token"])
        except ValueError:
            continue

        if not 1 <= day <= 31:
            continue

        for j in range(i + 1, min(i + 5, len(candidates))):
            second = candidates[j]

            try:
                month = int(second["token"])
            except ValueError:
                continue

            if not 1 <= month <= 12:
                continue

            # Между DD и MM не должно быть большого
            # горизонтального разрыва.
            if second["x"] - first["x"] > 120:
                continue

            for k in range(j + 1, min(j + 6, len(candidates))):
                year = candidates[k]

                if len(year["token"]) != 4:
                    continue

                try:
                    year_value = int(year["token"])
                except ValueError:
                    continue

                if not 1900 <= year_value <= 2100:
                    continue

                if year["x"] - second["x"] > 150:
                    continue

                confidence = min(
                    first["data"]["confidence"],
                    second["data"]["confidence"],
                    year["data"]["confidence"],
                )

                return {
                    "value": (
                        f"{day:02d}."
                        f"{month:02d}."
                        f"{year_value:04d}"
                    ),
                    "page": first["data"]["page"],
                    "confidence": confidence,
                    "items": [
                        first["data"],
                        second["data"],
                        year["data"],
                    ],
                }

    return None


class OsagoExtractor(BaseExtractor):

    # ========================================================
    # ВИЗУАЛЬНЫЙ OCR СРОКА СТРАХОВАНИЯ
    # ========================================================
    def _extract_visual_policy_dates(
        self,
        lines,
        doc_type,
        doc_id,
        used_dates,
    ):
        """
        Извлекает даты срока страхования из визуального OCR.

        Не использует произвольные даты документа.
        Сначала требуется смысловой anchor.
        """
        facts = []

        visual_items = [
            item
            for item in lines
            if isinstance(item, dict)
            and item.get("box")
        ]

        if not visual_items:
            return facts, used_dates

        start_anchors = [
            "СРОК СТРАХОВАНИЯ С",
            "СРОК СТРАХОВАНИЯ",
            "СРОК ДЕЙСТВИЯ",
            "НАЧАЛО СТРАХОВАНИЯ",
        ]

        end_anchors = [
            "СРОК СТРАХОВАНИЯ ПО",
            "ПО",
            "ОКОНЧАНИЕ СТРАХОВАНИЯ",
        ]

        for anchor_item in visual_items:
            anchor_text = anchor_item.get("text", "")

            normalized = self._normalize_search(
                anchor_text
            )

            if not any(
                self._normalize_search(anchor)
                in normalized
                for anchor in start_anchors
            ):
                continue

            reconstructed = _visual_reconstruct_date(
                visual_items,
                anchor_item,
            )

            if not reconstructed:
                continue

            value = reconstructed["value"]
            page = reconstructed["page"]

            key = self._date_key(
                value,
                page,
            )

            if key in used_dates:
                continue

            fragment = (
                f'{anchor_text} → '
                + " ".join(
                    item["text"]
                    for item in reconstructed["items"]
                )
                + f" → {value}"
            )

            facts.append(
                self._create_fact(
                    fact_type="POLICY_START_DATE",
                    value=value,
                    doc_type=doc_type,
                    doc_id=doc_id,
                    page=page,
                    fragment=fragment,
                    ocr_conf=reconstructed[
                        "confidence"
                    ],
                    extraction_conf=0.88,
                    method="OSAGO_VISUAL_OCR",
                )
            )

            used_dates.add(key)

            break

        return facts, used_dates

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
        # 7.1. ВИЗУАЛЬНЫЙ OCR СРОКА СТРАХОВАНИЯ
        # ====================================================
        #
        # Нужен для PDF, где дата находится в отдельных
        # графических ячейках:
        #
        # 20 | 09 | 20 | 26
        #
        # Обычный text-layer такую дату не возвращает.
        # ====================================================
        visual_policy_dates, used_dates = (
            self._extract_visual_policy_dates(
                lines=lines,
                doc_type=doc_type,
                doc_id=doc_id,
                used_dates=used_dates,
            )
        )

        facts.extend(
            visual_policy_dates
        )

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
        """
        text = str(value).strip()
        if not text:
            return False
        upper = text.upper()
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
        return False
