"""
ЭТАП 3 — ДОКУМЕНТЫ → ФАКТЫ
Файл: classifier.py
Назначение:
Определение типа документа.
Реализует:
3.7 — определение типа документа
3.8 — confidence классификации
3.21 — направление сомнительных документов на REVIEW
ВАЖНЫЙ ПРИНЦИП:
Классификатор не делает вывод по одному случайному слову.
Для OCR-документов допускаются специальные структурные правила,
если одновременно присутствует несколько независимых признаков.
Особенно важно:
заявление может содержать слова "полис", "ОСАГО", "СТС";
поэтому отдельные слова не должны автоматически менять тип;
СТС на фотографии может иметь сильно искажённый OCR;
поэтому для СТС используется отдельное OCR-правило:
VIN + госномер + признаки автомобиля.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher
import re
from .config import (
    DOCUMENT_STRONG_MARKERS,
    DOCUMENT_WEAK_MARKERS,
    CLASSIFICATION_MIN_SCORE,
    CLASSIFICATION_REVIEW_THRESHOLD,
)
from .normalizer import normalize_ocr_for_search


# =============================================================================
# РЕЗУЛЬТАТ КЛАССИФИКАЦИИ
# =============================================================================
@dataclass
class ClassificationResult:
    doc_type: str = "НЕ ОПРЕДЕЛЕНО"
    confidence: float = 0.0
    requires_review: bool = True
    all_scores: Dict[str, float] = None
    evidence: List[Dict] = None
    reason: str = ""

    def __post_init__(self):
        if self.all_scores is None:
            self.all_scores = {}
        if self.evidence is None:
            self.evidence = []


# =============================================================================
# ПУНКТ 3.7 / 3.8 — КЛАССИФИКАТОР
# =============================================================================
class DocumentClassifier:
    # -------------------------------------------------------------------------
    # Общие параметры
    # -------------------------------------------------------------------------
    HEADER_LINES = 25
    FUZZY_STRONG_THRESHOLD = 0.78
    FUZZY_WEAK_THRESHOLD = 0.88
    STRONG_EXACT_SCORE = 60.0
    STRONG_HEADER_BONUS = 35.0
    STRONG_FUZZY_SCORE = 45.0
    STRONG_FUZZY_HEADER_BONUS = 25.0
    WEAK_EXACT_SCORE = 10.0
    WEAK_HEADER_BONUS = 5.0
    MIN_SCORE_GAP = 20.0

    # -------------------------------------------------------------------------
    # ЗАЯВЛЕНИЕ
    # -------------------------------------------------------------------------
    APPLICATION_STRUCTURAL_BONUS = 70.0
    APPLICATION_HEADER_BONUS = 50.0
    APPLICATION_REQUEST_BONUS = 35.0
    APPLICATION_HEADER_MARKERS = (
        "ЗАЯВЛЕНИЕ НА СТРАХОВАНИЕ",
        "ЗАЯВЛЕНИЕ",
    )
    APPLICATION_STRUCTURE_MARKERS = (
        "ПРОШУ ЗАКЛЮЧИТЬ",
        "СТРАХОВАТЕЛЬ",
        "ТРАНСПОРТНОЕ СРЕДСТВО БУДЕТ ИСПОЛЬЗОВАТЬСЯ",
        "ДВА БЛАНКА ИЗВЕЩЕНИЯ",
        "СОГЛАСЕН НА ОБРАБОТКУ ПЕРСОНАЛЬНЫХ ДАННЫХ",
        "СТРАХОВАТЕЛЬ ШИРАНОВ",
    )

    # -------------------------------------------------------------------------
    # ПОЛИС
    # -------------------------------------------------------------------------
    POLICY_STRUCTURAL_BONUS = 45.0
    POLICY_HEADER_BONUS = 55.0
    POLICY_HEADER_MARKERS = (
        "СТРАХОВОЙ ПОЛИС",
        "ПОЛИС ОСАГО",
    )
    POLICY_STRUCTURE_MARKERS = (
        "СТРАХОВЫЕ ПРЕМИИ",
        "СТРАХОВАЯ СУММА",
        "СТРАХОВАЯ ПРЕМИЯ",
        "СРОК СТРАХОВАНИЯ",
        "СТРАХОВЩИК",
        "СТРАХОВАТЕЛЬ",
    )
    POLICY_STRONG_CONTEXT_MARKERS = (
        "СРОК СТРАХОВАНИЯ",
        "СТРАХОВАЯ ПРЕМИЯ",
        "СТРАХОВАЯ СУММА",
        "СТРАХОВЩИК",
    )

    # -------------------------------------------------------------------------
    # СТС
    # -------------------------------------------------------------------------
    STS_STRUCTURAL_BONUS = 35.0
    STS_HEADER_BONUS = 55.0
    STS_HEADER_MARKERS = (
        "СВИДЕТЕЛЬСТВО О РЕГИСТРАЦИИ",
        "СВИДЕТЕЛЬСТВО О РЕГИСТРАЦИИ ТРАНСПОРТНОГО СРЕДСТВА",
    )
    STS_STRUCTURE_MARKERS = (
        "ГОСУДАРСТВЕННЫЙ РЕГИСТРАЦИОННЫЙ ЗНАК",
        "ИДЕНТИФИКАЦИОННЫЙ НОМЕР ТРАНСПОРТНОГО СРЕДСТВА",
        "МАРКА, МОДЕЛЬ",
        "МОЩНОСТЬ ДВИГАТЕЛЯ",
        "ГОД ИЗГОТОВЛЕНИЯ",
        "КУЗОВ",
        "ШАССИ",
    )

    # -------------------------------------------------------------------------
    # OCR-признаки СТС
    # -------------------------------------------------------------------------
    STS_OCR_VEHICLE_MARKERS = (
        "VIN",
        "CHEVROLET",
        "МАРКА",
        "МОДЕЛЬ",
        "КУЗОВ",
        "ШАССИ",
        "ГОД",
        "ИЗГОТОВ",
        "ТРАНСПОРТ",
        "АВТОМОБ",
    )

    VIN_RE = re.compile(
        r"(?<![A-Z0-9])"
        r"[A-HJ-NPR-Z0-9]{17}"
        r"(?![A-Z0-9])",
        re.IGNORECASE,
    )

    PLATE_RE = re.compile(
        r"(?<![А-ЯA-Z0-9])"
        r"[АВЕКМНОРСТУХA-Z]\s*\d{3}\s*"
        r"[АВЕКМНОРСТУХA-Z]{2}\s*\d{2,3}"
        r"(?![А-ЯA-Z0-9])",
        re.IGNORECASE,
    )

    # =============================================================================
    # ПУНКТ 3.7 — ОСНОВНОЙ МЕТОД
    # =============================================================================
    def classify(self, lines):
        if not lines:
            return ClassificationResult(
                reason="Нет строк текста для классификации."
            )

        clean_lines = []
        for item in lines:
            if not item:
                continue
            try:
                text = str(item[0]).strip()
            except Exception:
                continue
            if not text:
                continue
            try:
                page = item[2] if len(item) > 2 else 1
            except Exception:
                page = 1
            clean_lines.append(
                {
                    "text": text,
                    "page": page,
                }
            )

        if not clean_lines:
            return ClassificationResult(
                reason="После очистки не осталось строк текста."
            )

        full_text = "\n".join(
            item["text"]
            for item in clean_lines
        ).upper()

        header_lines = clean_lines[: self.HEADER_LINES]
        header_text = "\n".join(
            item["text"]
            for item in header_lines
        ).upper()

        scores = {
            doc_type: 0.0
            for doc_type in DOCUMENT_STRONG_MARKERS
        }
        scores.setdefault("СТС", 0.0)
        scores.setdefault("Заявление", 0.0)
        scores.setdefault("Полис ОСАГО", 0.0)
        evidence = []

        # =============================================================================
        # ПУНКТ 3.7 — СИЛЬНЫЕ МАРКЕРЫ
        # =============================================================================
        for doc_type, markers in DOCUMENT_STRONG_MARKERS.items():
            for marker in markers:
                marker_upper = marker.upper()

                if marker_upper in header_text:
                    score = (
                        self.STRONG_EXACT_SCORE
                        + self.STRONG_HEADER_BONUS
                    )
                    scores[doc_type] += score
                    evidence.append(
                        {
                            "doc_type": doc_type,
                            "marker": marker,
                            "match_type": "strong_exact_header",
                            "score": score,
                        }
                    )
                    continue

                if marker_upper in full_text:
                    score = self.STRONG_EXACT_SCORE
                    scores[doc_type] += score
                    evidence.append(
                        {
                            "doc_type": doc_type,
                            "marker": marker,
                            "match_type": "strong_exact",
                            "score": score,
                        }
                    )
                    continue

                fuzzy_result = self._best_fuzzy_match(
                    clean_lines,
                    marker,
                )
                if fuzzy_result is not None:
                    similarity, matched_line, page = fuzzy_result
                    if similarity >= self.FUZZY_STRONG_THRESHOLD:
                        score = self.STRONG_FUZZY_SCORE
                        first_page = (
                            header_lines[0]["page"]
                            if header_lines
                            else None
                        )
                        if page == first_page:
                            score += self.STRONG_FUZZY_HEADER_BONUS
                        scores[doc_type] += score
                        evidence.append(
                            {
                                "doc_type": doc_type,
                                "marker": marker,
                                "match_type": "strong_fuzzy",
                                "similarity": round(similarity, 3),
                                "line": matched_line,
                                "page": page,
                                "score": score,
                            }
                        )

        # =============================================================================
        # ПУНКТ 3.7 — СЛАБЫЕ МАРКЕРЫ
        # =============================================================================
        for doc_type, markers in DOCUMENT_WEAK_MARKERS.items():
            for marker in markers:
                marker_upper = marker.upper()
                if marker_upper in header_text:
                    score = (
                        self.WEAK_EXACT_SCORE
                        + self.WEAK_HEADER_BONUS
                    )
                    scores[doc_type] += score
                    evidence.append(
                        {
                            "doc_type": doc_type,
                            "marker": marker,
                            "match_type": "weak_header",
                            "score": score,
                        }
                    )
                elif marker_upper in full_text:
                    score = self.WEAK_EXACT_SCORE
                    scores[doc_type] += score
                    evidence.append(
                        {
                            "doc_type": doc_type,
                            "marker": marker,
                            "match_type": "weak_exact",
                            "score": score,
                        }
                    )

        # =============================================================================
        # ПУНКТ 3.7 — СТРУКТУРНЫЕ ПРАВИЛА
        # =============================================================================
        self._apply_application_structure_rule(
            full_text=full_text,
            header_text=header_text,
            scores=scores,
            evidence=evidence,
        )
        self._apply_policy_structure_rule(
            full_text=full_text,
            header_text=header_text,
            scores=scores,
            evidence=evidence,
        )
        self._apply_sts_structure_rule(
            full_text=full_text,
            header_text=header_text,
            lines=clean_lines,
            scores=scores,
            evidence=evidence,
        )

        # =============================================================================
        # СОРТИРОВКА
        # =============================================================================
        sorted_scores = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        best_type, best_score = sorted_scores[0]
        second_score = (
            sorted_scores[1][1]
            if len(sorted_scores) > 1
            else 0.0
        )
        score_gap = best_score - second_score

        # =============================================================================
        # НЕДОСТАТОЧНО ПРИЗНАКОВ
        # =============================================================================
        if best_score < CLASSIFICATION_MIN_SCORE:
            return ClassificationResult(
                doc_type="НЕ ОПРЕДЕЛЕНО",
                confidence=best_score,
                requires_review=True,
                all_scores=scores,
                evidence=evidence,
                reason=(
                    "Недостаточно признаков для надёжного определения "
                    "типа документа."
                ),
            )

        # =============================================================================
        # КОНФЛИКТ КАНДИДАТОВ
        # =============================================================================
        if score_gap < self.MIN_SCORE_GAP:
            confidence = min(
                69.0,
                best_score,
            )
            return ClassificationResult(
                doc_type=best_type,
                confidence=confidence,
                requires_review=True,
                all_scores=scores,
                evidence=evidence,
                reason=(
                    "Есть конкурирующие признаки нескольких типов "
                    "документов."
                ),
            )

        # =============================================================================
        # РЕЗУЛЬТАТ
        # =============================================================================
        confidence = min(
            100.0,
            best_score,
        )
        requires_review = (
            confidence < CLASSIFICATION_REVIEW_THRESHOLD
        )
        if requires_review:
            reason = (
                "Тип документа определён, но уверенность ниже "
                "порога автоматического принятия."
            )
        else:
            reason = (
                "Тип документа определён по совокупности "
                "структурных и текстовых признаков."
            )

        return ClassificationResult(
            doc_type=best_type,
            confidence=confidence,
            requires_review=requires_review,
            all_scores=scores,
            evidence=evidence,
            reason=reason,
        )

    # =============================================================================
    # ПУНКТ 3.7 — ПРАВИЛО ЗАЯВЛЕНИЯ
    # =============================================================================
    def _apply_application_structure_rule(
        self,
        full_text: str,
        header_text: str,
        scores: Dict[str, float],
        evidence: List[Dict],
    ):
        application_score = 0.0
        has_application_header = any(
            marker in header_text
            for marker in self.APPLICATION_HEADER_MARKERS
        )
        if has_application_header:
            application_score += self.APPLICATION_HEADER_BONUS
            evidence.append(
                {
                    "doc_type": "Заявление",
                    "marker": "APPLICATION_HEADER",
                    "match_type": "structural_header",
                    "score": self.APPLICATION_HEADER_BONUS,
                }
            )

        structure_hits = []
        for marker in self.APPLICATION_STRUCTURE_MARKERS:
            if marker in full_text:
                structure_hits.append(marker)

        has_request = "ПРОШУ ЗАКЛЮЧИТЬ" in full_text
        if has_request:
            application_score += self.APPLICATION_REQUEST_BONUS
            evidence.append(
                {
                    "doc_type": "Заявление",
                    "marker": "ПРОШУ ЗАКЛЮЧИТЬ",
                    "match_type": "application_request",
                    "score": self.APPLICATION_REQUEST_BONUS,
                }
            )

        if len(structure_hits) >= 2:
            application_score += self.APPLICATION_STRUCTURAL_BONUS
            evidence.append(
                {
                    "doc_type": "Заявление",
                    "marker": "APPLICATION_STRUCTURE",
                    "match_type": "structural",
                    "matched_markers": structure_hits,
                    "score": self.APPLICATION_STRUCTURAL_BONUS,
                }
            )

        if (
            has_application_header
            and len(structure_hits) >= 1
        ):
            application_score += 25.0
            evidence.append(
                {
                    "doc_type": "Заявление",
                    "marker": "APPLICATION_HEADER_PLUS_STRUCTURE",
                    "match_type": "structural_combination",
                    "score": 25.0,
                }
            )

        scores["Заявление"] += application_score

    # =============================================================================
    # ПУНКТ 3.7 — ПРАВИЛО ПОЛИСА
    # =============================================================================
    def _apply_policy_structure_rule(
        self,
        full_text: str,
        header_text: str,
        scores: Dict[str, float],
        evidence: List[Dict],
    ):
        policy_score = 0.0
        has_policy_header = any(
            marker in header_text
            for marker in self.POLICY_HEADER_MARKERS
        )
        if has_policy_header:
            policy_score += self.POLICY_HEADER_BONUS
            evidence.append(
                {
                    "doc_type": "Полис ОСАГО",
                    "marker": "POLICY_HEADER",
                    "match_type": "structural_header",
                    "score": self.POLICY_HEADER_BONUS,
                }
            )

        context_hits = []
        for marker in self.POLICY_STRONG_CONTEXT_MARKERS:
            if marker in full_text:
                context_hits.append(marker)

        if len(context_hits) >= 2:
            policy_score += self.POLICY_STRUCTURAL_BONUS
            evidence.append(
                {
                    "doc_type": "Полис ОСАГО",
                    "marker": "POLICY_STRUCTURE",
                    "match_type": "structural",
                    "matched_markers": context_hits,
                    "score": self.POLICY_STRUCTURAL_BONUS,
                }
            )

        has_application_structure = (
            "ПРОШУ ЗАКЛЮЧИТЬ" in full_text
            and (
                "СТРАХОВАТЕЛЬ" in full_text
                or
                "ТРАНСПОРТНОЕ СРЕДСТВО БУДЕТ ИСПОЛЬЗОВАТЬСЯ"
                in full_text
            )
        )

        if has_application_structure and not has_policy_header:
            policy_score = max(
                0.0,
                policy_score - 25.0,
            )
            evidence.append(
                {
                    "doc_type": "Полис ОСАГО",
                    "marker": "APPLICATION_CONTEXT",
                    "match_type": "negative_context",
                    "score": -25.0,
                    "reason": (
                        "Полисные слова находятся внутри "
                        "структуры заявления."
                    ),
                }
            )

        scores["Полис ОСАГО"] += policy_score

    # =============================================================================
    # ПУНКТ 3.7 — ПРАВИЛО СТС
    # =============================================================================
    def _apply_sts_structure_rule(
        self,
        full_text: str,
        header_text: str,
        lines: List[Dict],
        scores: Dict[str, float],
        evidence: List[Dict],
    ):
        sts_score = 0.0

        # ---------------------------------------------------------------------
        # 1. Настоящий заголовок СТС.
        # ---------------------------------------------------------------------
        has_sts_header = any(
            marker in header_text
            for marker in self.STS_HEADER_MARKERS
        )
        if has_sts_header:
            sts_score += self.STS_HEADER_BONUS
            evidence.append(
                {
                    "doc_type": "СТС",
                    "marker": "STS_HEADER",
                    "match_type": "structural_header",
                    "score": self.STS_HEADER_BONUS,
                }
            )

        # ---------------------------------------------------------------------
        # 2. Обычные текстовые структурные признаки СТС.
        # ---------------------------------------------------------------------
        structure_hits = []
        for marker in self.STS_STRUCTURE_MARKERS:
            if marker in full_text:
                structure_hits.append(marker)

        if len(structure_hits) >= 3:
            sts_score += self.STS_STRUCTURAL_BONUS
            evidence.append(
                {
                    "doc_type": "СТС",
                    "marker": "STS_STRUCTURE",
                    "match_type": "structural",
                    "matched_markers": structure_hits,
                    "score": self.STS_STRUCTURAL_BONUS,
                }
            )

        # ---------------------------------------------------------------------
        # 3. OCR-правило для фотографии СТС.
        # ---------------------------------------------------------------------
        # ============================================================
        # VIN — ищем по каждой OCR-строке отдельно
        # ============================================================
        # Нельзя удалять все переводы строк из full_text:
        # соседние поля документа могут склеиться в одну строку.
        #
        # Для VIN:
        # - разрешаем пробелы и дефисы внутри OCR-значения;
        # - проверяем каждую строку отдельно;
        # - сохраняем границы VIN.
        # ============================================================

        has_vin = False

        for item in lines:
            line_text = str(item["text"]).upper()

            vin_line = re.sub(
                r"[\s\-]",
                "",
                line_text,
            )

            if self.VIN_RE.search(vin_line):
                has_vin = True
                break

        has_plate = bool(
            self.PLATE_RE.search(
                full_text
            )
        )

        vehicle_hits = []
        normalized_full_text = normalize_ocr_for_search(
            full_text
        ).upper()
        for marker in self.STS_OCR_VEHICLE_MARKERS:
            if marker in normalized_full_text:
                vehicle_hits.append(marker)

        # ---------------------------------------------------------------------
        # OCR может распознать номер в латинице.
        # ---------------------------------------------------------------------
        has_latin_plate = bool(
            re.search(
                r"(?<![A-Z0-9])"
                r"[A-Z]\s*\d{3}\s*[A-Z]{2}\s*\d{2,3}"
                r"(?![A-Z0-9])",
                full_text,
                re.IGNORECASE,
            )
        )
        if has_latin_plate:
            has_plate = True

        # ---------------------------------------------------------------------
        # Для OCR-СTS достаточно двух автомобильных признаков.
        # ---------------------------------------------------------------------
        if (
            has_vin
            and has_plate
            and len(vehicle_hits) >= 2
        ):
            ocr_sts_score = 80.0
            sts_score += ocr_sts_score
            evidence.append(
                {
                    "doc_type": "СТС",
                    "marker": "STS_OCR_COMBINATION",
                    "match_type": "ocr_structural_combination",
                    "score": ocr_sts_score,
                    "signals": {
                        "vin": True,
                        "plate": True,
                        "vehicle_markers": vehicle_hits,
                    },
                    "reason": (
                        "Обнаружены независимые OCR-признаки "
                        "автомобильного регистрационного документа."
                    ),
                }
            )
        elif has_vin and has_plate:
            ocr_sts_score = 45.0
            sts_score += ocr_sts_score
            evidence.append(
                {
                    "doc_type": "СТС",
                    "marker": "STS_OCR_PARTIAL",
                    "match_type": "ocr_partial_combination",
                    "score": ocr_sts_score,
                    "signals": {
                        "vin": True,
                        "plate": True,
                        "vehicle_markers": vehicle_hits,
                    },
                    "reason": (
                        "Найдены VIN и госномер, но недостаточно "
                        "дополнительных признаков для уверенной "
                        "классификации СТС."
                    ),
                }
            )

        # ---------------------------------------------------------------------
        # 4. Если явно заявление — убираем OCR-бонус СТС.
        # ---------------------------------------------------------------------
        has_application = (
            "ПРОШУ ЗАКЛЮЧИТЬ" in full_text
            or "ЗАЯВЛЕНИЕ" in full_text
        )
        if has_application and not has_sts_header:
            sts_score = max(
                0.0,
                sts_score - 40.0,
            )
            evidence.append(
                {
                    "doc_type": "СТС",
                    "marker": "APPLICATION_CONTEXT",
                    "match_type": "negative_context",
                    "score": -40.0,
                    "reason": (
                        "Автомобильные признаки обнаружены внутри "
                        "документа с признаками заявления."
                    ),
                }
            )

        scores["СТС"] += sts_score

    # =============================================================================
    # ПУНКТ 3.8 — FUZZY ПОИСК
    # =============================================================================
    def _best_fuzzy_match(
        self,
        lines: List[Dict],
        marker: str,
    ) -> Optional[Tuple[float, str, int]]:
        best_similarity = 0.0
        best_line = ""
        best_page = 1

        marker_normalized = normalize_ocr_for_search(
            marker
        ).upper()
        if not marker_normalized:
            return None

        for item in lines:
            line = item["text"]
            line_normalized = normalize_ocr_for_search(
                line
            ).upper()
            if not line_normalized:
                continue

            similarity = self._line_similarity(
                line_normalized,
                marker_normalized,
            )
            if similarity > best_similarity:
                best_similarity = similarity
                best_line = line
                best_page = item["page"]

        if best_similarity <= 0:
            return None

        return (
            best_similarity,
            best_line,
            best_page,
        )

    # =============================================================================
    # ПУНКТ 3.8 — СРАВНЕНИЕ СТРОК
    # =============================================================================
    def _line_similarity(
        self,
        line: str,
        marker: str,
    ) -> float:
        if not line or not marker:
            return 0.0

        if marker in line:
            return 1.0

        if len(line) <= len(marker) + 20:
            return SequenceMatcher(
                None,
                line,
                marker,
            ).ratio()

        marker_length = len(marker)
        best = 0.0
        for start in range(
            0,
            max(
                1,
                len(line) - marker_length + 1,
            ),
        ):
            window = line[
                start:start + marker_length
            ]
            ratio = SequenceMatcher(
                None,
                window,
                marker,
            ).ratio()
            if ratio > best:
                best = ratio

        return best
