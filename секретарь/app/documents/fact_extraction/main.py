"""
============================================================
ЭТАП 3 — ДОКУМЕНТЫ → ФАКТЫ
Главный исполнитель этапа.
============================================================
ПУНКТЫ:
3.1  Граница этапа
3.2  Входные документы
3.3  Очередь
3.4  PDF text layer → OCR
3.5  Оригиналы не изменяются
3.6  Сохранение результата
3.7  Типы документов
3.8  Уверенность классификации
3.9  Извлечение фактов
3.10 Источник каждого факта
3.11 Evidence
...
3.29 Никаких entity resolution / CRM /
rename / move / delete
============================================================
"""
import json
import os
from datetime import datetime
from typing import List
from .config import (
    INCOMING_DIR,
    EXTRACTED_DIR,
    SUPPORTED_EXTENSIONS,
    CLASSIFICATION_THRESHOLD,
)
from .text_extractor import TextExtractor
from .classifier import DocumentClassifier
from .validators import validate_fact
from pathlib import Path
from .extractors.osago import OsagoExtractor
from .extractors.sts import StsExtractor
from .extractors.passport import PassportExtractor
from .extractors.vnz import VnzExtractor
from .extractors.application import ApplicationExtractor
from .extractors.addendum import AddendumExtractor
from .extractors.generic import GenericExtractor
from .input_registry import DocumentRegistry


# =============================================================================
# ПУНКТ 0 — ГРАНИЦА ЭТАПА 3
# =============================================================================

STAGE_3_ALLOWED_ACTIONS = {
    "READ_DOCUMENT",
    "EXTRACT_TEXT",
    "RUN_OCR",
    "CLASSIFY_DOCUMENT",
    "EXTRACT_FACTS",
    "VALIDATE_FACTS",
    "SAVE_RESULTS",
}

STAGE_3_FORBIDDEN_ACTIONS = {
    "RESOLVE_PERSON",
    "RESOLVE_VEHICLE",
    "RESOLVE_POLICY",
    "RESOLVE_ENTITY",
    "RESOLVE_CONFLICT",
    "CREATE_CRM_RECORD",
    "CREATE_TASK",
    "SEND_MESSAGE",
    "RENAME_FILE",
    "MOVE_FILE",
    "DELETE_FILE",
}


def check_stage_3_action(
    action: str,
):
    """
    Контроль границы Этапа 3.
    Если когда-либо код Этапа 3 попытается
    выполнить действие следующего этапа —
    получаем явную ошибку.
    """
    if action in STAGE_3_FORBIDDEN_ACTIONS:
        raise RuntimeError(
            "НАРУШЕНИЕ ГРАНИЦЫ ЭТАПА 3: "
            f"{action}"
        )
    if action not in STAGE_3_ALLOWED_ACTIONS:
        raise RuntimeError(
            "НЕРАЗРЕШЁННОЕ ДЕЙСТВИЕ ЭТАПА 3: "
            f"{action}"
        )


"""
============================================================
ПУНКТ 3.7 — EXTRACTOR'Ы
============================================================
"""
EXTRACTOR_BY_TYPE = {
    "Полис ОСАГО": OsagoExtractor(),
    "СТС": StsExtractor(),
    "Паспорт РФ": PassportExtractor(),
    "ВНЖ": VnzExtractor(),
    "Заявление": ApplicationExtractor(),
    "АДДЕНДУМ": AddendumExtractor(),
}


# =============================================================================
# ПУНКТ 3.3 — СОСТОЯНИЯ ОЧЕРЕДИ
# =============================================================================

QUEUE_NEW = "NEW"
QUEUE_TEXT_EXTRACTION = "TEXT_EXTRACTION"
QUEUE_OCR = "OCR"
QUEUE_DOCUMENT_CLASSIFICATION = "DOCUMENT_CLASSIFICATION"
QUEUE_FACT_EXTRACTION = "FACT_EXTRACTION"
QUEUE_QUALITY_CHECK = "QUALITY_CHECK"
QUEUE_DONE = "DONE"
QUEUE_REVIEW = "REQUIRES_REVIEW"
QUEUE_PROBLEM = "PROBLEM"


class Stage3Processor:
    def __init__(self):
        self.text_extractor = TextExtractor()
        self.classifier = DocumentClassifier()
        os.makedirs(
            INCOMING_DIR,
            exist_ok=True,
        )
        os.makedirs(
            EXTRACTED_DIR,
            exist_ok=True,
        )
        # ----------------------------------------------------
        # ПУНКТ 3.2
        #
        # Реестр:
        #
        # PhysicalFolder → Document
        # ----------------------------------------------------
        registry_dir = os.path.join(
            EXTRACTED_DIR,
            "registry",
        )
        self.document_registry = (
            DocumentRegistry(
                registry_dir
            )
        )

    # ========================================================
    # ПУНКТ 3.3 — ПОИСК ДОКУМЕНТОВ
    # ========================================================
    def find_documents(
        self,
    ) -> List[str]:
        files = []
        # rglob позволяет видеть документы
        # внутри физических подпапок.
        #
        # Это необходимо для:
        #
        # PhysicalFolder
        #       ↓
        # Document
        for root, directories, filenames in os.walk(
            INCOMING_DIR
        ):
            for filename in sorted(
                filenames
            ):
                filepath = os.path.join(
                    root,
                    filename,
                )
                extension = os.path.splitext(
                    filename
                )[1].lower()
                if (
                    extension
                    in SUPPORTED_EXTENSIONS
                ):
                    files.append(
                        filepath
                    )
        return sorted(files)

    # ========================================================
    # ПУНКТ 3.6 — СОХРАНЕНИЕ JSON
    # ========================================================
    def save_json(
        self,
        filename: str,
        data: dict,
    ):
        path = os.path.join(
            EXTRACTED_DIR,
            filename,
        )
        with open(
            path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

    # ========================================================
    # ПУНКТ 3.5 — ОТДЕЛЬНОЕ ХРАНЕНИЕ РЕЗУЛЬТАТОВ
    # ========================================================

    def save_json_to_directory(
        self,
        directory: str,
        filename: str,
        data: dict,
    ):
        path = os.path.join(
            directory,
            filename,
        )

        with open(
            path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

    def save_document_reading_result(
        self,
        document_id: str,
        filepath: str,
        extraction_result,
        processed_at: str,
    ):
        """
        Оригинальный файл НЕ изменяется.

        Сохраняются отдельно:
        - сведения об оригинале;
        - извлечённый текст;
        - OCR-результат;
        - технические метаданные чтения.
        """

        document_dir = os.path.join(
            EXTRACTED_DIR,
            document_id,
        )

        os.makedirs(
            document_dir,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # ORIGINAL FILE
        # ----------------------------------------------------

        original_metadata = {
            "document_id": document_id,
            "original_file": {
                "filename": os.path.basename(filepath),
                "path": os.path.abspath(filepath),
                "extension": os.path.splitext(filepath)[1].lower(),
                "size_bytes": os.path.getsize(filepath),
            },
            "original_modified": False,
        }

        self.save_json_to_directory(
            document_dir,
            "original_file.json",
            original_metadata,
        )

        # ----------------------------------------------------
        # EXTRACTED TEXT
        # ----------------------------------------------------

        text_path = os.path.join(
            document_dir,
            "extracted_text.txt",
        )

        with open(
            text_path,
            "w",
            encoding="utf-8",
        ) as file:

            file.write(
                extraction_result.extracted_text
            )

        # ----------------------------------------------------
        # OCR RESULT
        # ----------------------------------------------------

        self.save_json_to_directory(
            document_dir,
            "ocr_result.json",
            {
                "document_id": document_id,
                "ocr_used": (
                    "OCR"
                    in extraction_result.extraction_method.upper()
                    or extraction_result.extraction_method == "MIXED"
                ),
                "ocr_version": extraction_result.ocr_version,
                "result": extraction_result.ocr_result,
            },
        )

        # ----------------------------------------------------
        # ANALYSIS METADATA
        # ----------------------------------------------------

        self.save_json_to_directory(
            document_dir,
            "analysis_metadata.json",
            {
                "document_id": document_id,
                "processed_at": processed_at,
                "extraction_method":
                    extraction_result.extraction_method,
                "pages_total":
                    extraction_result.pages_total,
                "pages_read":
                    extraction_result.pages_read,
                "pages_failed":
                    extraction_result.pages_failed,
                "technical_quality":
                    extraction_result.technical_quality,
                "handwriting_detected":
                    extraction_result.handwriting_detected,
                "unreadable":
                    extraction_result.unreadable,
                "error":
                    extraction_result.error,
                "ocr_version":
                    extraction_result.ocr_version,
            },
        )

    # ========================================================
    # ПУНКТ 3.9–3.20 — ФАКТЫ
    # ========================================================
    def extract_facts(
        self,
        lines,
        doc_type,
        doc_id,
    ):
        extractor = EXTRACTOR_BY_TYPE.get(
            doc_type
        )
        if extractor is None:
            extractor = GenericExtractor()
        return extractor.extract_facts(
            lines=lines,
            doc_type=doc_type,
            doc_id=doc_id,
        )

    # ========================================================
    # ПУНКТ 3.21 — QUALITY CHECK
    # ========================================================
    def quality_check(
        self,
        facts: list,
        extraction_result,
        classification,
    ):
        warnings = []
        if extraction_result.unreadable:
            warnings.append(
                "DOCUMENT_UNREADABLE"
            )
        if extraction_result.pages_failed > 0:
            warnings.append(
                "Не все страницы удалось прочитать."
            )
        if (
            classification.confidence
            < CLASSIFICATION_THRESHOLD
        ):
            warnings.append(
                "Низкая уверенность классификации."
            )
        for fact in facts:
            validation = validate_fact(
                fact
            )
            if (
                validation["status"]
                != "VALID"
            ):
                warnings.extend(
                    validation["warnings"]
                )
        return warnings

    # ========================================================
    # ОБРАБОТКА ОДНОГО ДОКУМЕНТА
    # ========================================================
    def process_document(
        self,
        filepath: str,
    ) -> dict:
        filename = os.path.basename(
            filepath
        )
        # ----------------------------------------------------
        # ПУНКТ 3.2
        #
        # Регистрируем:
        #
        # PhysicalFolder
        #       ↓
        # Document
        #
        # ID теперь НЕ зависит от имени файла.
        # ----------------------------------------------------
        document = (
            self.document_registry.register_document(
                filepath=Path(filepath).resolve(),
                incoming_root=Path(INCOMING_DIR).resolve(),
            )
        )
        doc_id = document[
            "document_id"
        ]
        physical_folder_id = document[
            "physical_folder_id"
        ]
        print()
        print(
            f"## 📄 [{doc_id}] ОБРАБОТКА: "
            f"{filename}"
        )
        print(
            f"📁 PhysicalFolder: "
            f"{physical_folder_id}"
        )
        result = {
            "schema_version": "3.0",
            "analysis_version": "3.0",
            # ------------------------------------------------
            # ПУНКТ 3.2
            # ------------------------------------------------
            "document": document,
            "document_id": doc_id,
            "filename": filename,
            "source_path": os.path.abspath(
                filepath
            ),
            "processed_at":
                datetime.now().isoformat(),
            # ------------------------------------------------
            # ПУНКТ 3.3
            # ------------------------------------------------
            "queue": {
                "initial": QUEUE_NEW,
                "current": QUEUE_NEW,
                "history": [],
            },
            "classification": {},
            "extraction": {},
            "facts": [],
            "quality": {},
            "error": None,
            # ------------------------------------------------
            # ПУНКТ 3.1
            #
            # Явная граница этапа.
            # ------------------------------------------------
            "stage_3_boundary": {
                "entity_resolution":
                    False,
                "person_resolution":
                    False,
                "vehicle_resolution":
                    False,
                "policy_resolution":
                    False,
                "conflict_resolution":
                    False,
                "crm_links_created":
                    False,
                "work_tasks_created":
                    False,
                "messages_sent":
                    False,
                "folders_renamed":
                    False,
                "folders_moved":
                    False,
                "documents_deleted":
                    False,
                "originals_modified":
                    False,
            },
        }
        try:
            # ================================================
            # 3.1 — READ DOCUMENT
            # ================================================
            check_stage_3_action(
                "READ_DOCUMENT"
            )
            # ================================================
            # 3.3 — TEXT EXTRACTION
            # ================================================
            check_stage_3_action(
                "EXTRACT_TEXT"
            )
            result[
                "queue"
            ][
                "history"
            ].append(
                QUEUE_TEXT_EXTRACTION
            )
            result[
                "queue"
            ][
                "current"
            ] = QUEUE_TEXT_EXTRACTION
            extraction_result = (
                self.text_extractor.extract(
                    filepath
                )
            )

            # ========================================================
            # ПУНКТ 3.5 — СОХРАНЯЕМ РЕЗУЛЬТАТ ЧТЕНИЯ ОТДЕЛЬНО
            # ========================================================

            self.save_document_reading_result(
                document_id=doc_id,
                filepath=filepath,
                extraction_result=extraction_result,
                processed_at=result["processed_at"],
            )

            # ================================================
            # 3.4 — OCR
            # ================================================
            if (
                "OCR"
                in extraction_result.extraction_method.upper()
            ):
                check_stage_3_action(
                    "RUN_OCR"
                )
                result[
                    "queue"
                ][
                    "history"
                ].append(
                    QUEUE_OCR
                )
            result[
                "extraction"
            ] = {
                "method":
                    extraction_result.extraction_method,
                "ocr_version":
                    extraction_result.ocr_version,
                "pages_total":
                    extraction_result.pages_total,
                "pages_read":
                    extraction_result.pages_read,
                "pages_failed":
                    extraction_result.pages_failed,
                "technical_quality":
                    extraction_result.technical_quality,
                "handwriting_detected":
                    extraction_result.handwriting_detected,
                "unreadable":
                    extraction_result.unreadable,
                "error":
                    extraction_result.error,
                "lines_count":
                    len(
                        extraction_result.lines
                    ),
            }
            # ================================================
            # 3.7–3.8 — CLASSIFICATION
            # ================================================
            check_stage_3_action(
                "CLASSIFY_DOCUMENT"
            )
            result[
                "queue"
            ][
                "history"
            ].append(
                QUEUE_DOCUMENT_CLASSIFICATION
            )
            result[
                "queue"
            ][
                "current"
            ] = QUEUE_DOCUMENT_CLASSIFICATION
            classification = (
                self.classifier.classify(
                    extraction_result.lines
                )
            )
            result[
                "classification"
            ] = {
                "doc_type":
                    classification.doc_type,
                "confidence":
                    classification.confidence,
                "requires_review":
                    classification.requires_review,
                "all_scores":
                    classification.all_scores,
                "evidence":
                    classification.evidence,
                "reason":
                    classification.reason,
            }
            print(
                f"🏷️ ТИП: "
                f"{classification.doc_type} "
                f"(Уверенность: "
                f"{classification.confidence:.1f}%)"
            )
            print(
                f"ℹ️ Причина: "
                f"{classification.reason}"
            )

            # ========================================================
            # ДОПОЛНИТЕЛЬНЫЙ OCR ДЛЯ ВИЗУАЛЬНЫХ ПОЛЕЙ
            # ========================================================

            if (
                classification.doc_type == "Полис ОСАГО"
                and filepath.lower().endswith(".pdf")
            ):
                check_stage_3_action("RUN_OCR")

                visual_ocr = self.text_extractor.extract_pdf_ocr_pages(
                    filepath
                )

                # Сохраняем отдельно: оригинальный text layer
                # не заменяется.
                result["visual_ocr"] = visual_ocr

                result["extraction"]["visual_ocr"] = True

                visual_lines = []

                for page_data in visual_ocr["pages"]:
                    for item in page_data.get("items", []):
                        visual_lines.append(
                            (
                                item["text"],
                                item["confidence"],
                                item["page"],
                            )
                        )

                # Text layer + OCR.
                # Дубликаты позже отсекаются extractor'ом.
                extraction_result.lines.extend(
                    visual_lines
                )

            # ================================================
            # 3.9 — FACT EXTRACTION
            # ================================================
            check_stage_3_action(
                "EXTRACT_FACTS"
            )
            result[
                "queue"
            ][
                "history"
            ].append(
                QUEUE_FACT_EXTRACTION
            )
            result[
                "queue"
            ][
                "current"
            ] = QUEUE_FACT_EXTRACTION
            facts = self.extract_facts(
                extraction_result.lines,
                classification.doc_type,
                doc_id,
            )
            # ================================================
            # 3.20 — VALIDATION
            # ================================================
            check_stage_3_action(
                "VALIDATE_FACTS"
            )
            result[
                "queue"
            ][
                "history"
            ].append(
                QUEUE_QUALITY_CHECK
            )
            result[
                "queue"
            ][
                "current"
            ] = QUEUE_QUALITY_CHECK
            quality_warnings = (
                self.quality_check(
                    facts,
                    extraction_result,
                    classification,
                )
            )
            result[
                "facts"
            ] = facts
            # ================================================
            # ФИНАЛЬНЫЙ СТАТУС
            # ================================================
            if extraction_result.unreadable:
                status = QUEUE_REVIEW
            elif quality_warnings:
                status = QUEUE_REVIEW
            elif classification.requires_review:
                status = QUEUE_REVIEW
            else:
                status = QUEUE_DONE
            result[
                "queue"
            ][
                "current"
            ] = status
            result[
                "quality"
            ] = {
                "status":
                    (
                        "GOOD"
                        if not quality_warnings
                        else "REQUIRES_REVIEW"
                    ),
                "warnings":
                    quality_warnings,
                "facts_count":
                    len(facts),
            }
            result[
                "queue"
            ][
                "history"
            ].append(
                status
            )
            print(
                f"📊 Извлечено фактов: "
                f"{len(facts)}"
            )
            print(
                f"🎯 Техническое качество: "
                f"{result['extraction']['technical_quality']}"
            )
            print(
                f"📌 Статус: {status}"
            )
            # ================================================
            # 3.6 — СОХРАНЕНИЕ
            # ================================================
            check_stage_3_action(
                "SAVE_RESULTS"
            )
            self.save_json(
                f"{doc_id}.json",
                result,
            )
            return result
        except Exception as exc:
            result[
                "queue"
            ][
                "current"
            ] = QUEUE_PROBLEM
            result[
                "queue"
            ][
                "history"
            ].append(
                QUEUE_PROBLEM
            )
            result[
                "error"
            ] = {
                "type":
                    type(exc).__name__,
                "message":
                    str(exc),
            }
            result[
                "quality"
            ] = {
                "status":
                    "PROBLEM",
                "warnings": [
                    "Ошибка обработки документа."
                ],
                "facts_count":
                    0,
            }
            self.save_json(
                f"{doc_id}.json",
                result,
            )
            print(
                f"❌ Ошибка: "
                f"{type(exc).__name__}: {exc}"
            )
            return result

    # ========================================================
    # ПОЛНЫЙ ЗАПУСК
    # ========================================================
    def run(self):
        print(
            "🔍 ПОЛНАЯ РЕАЛИЗАЦИЯ ЭТАПА 3: "
            "ДОКУМЕНТЫ → ФАКТЫ"
        )
        print(
            "=" * 47
        )
        print()
        print(
            "🛡️ ГРАНИЦА ЭТАПА 3:"
        )
        print(
            "   Document → Text/OCR → Type → Facts → Evidence"
        )
        print(
            "   Person/Vehicle/Policy resolution: НЕТ"
        )
        print(
            "   Conflict resolution: НЕТ"
        )
        print(
            "   CRM: НЕТ"
        )
        print(
            "   Tasks/Messages: НЕТ"
        )
        print(
            "   Rename/Move/Delete: НЕТ"
        )
        print()
        print(
            "🔄 Инициализация компонентов..."
        )
        if self.text_extractor.ocr is not None:
            print(
                "✅ OCR-движок инициализирован."
            )
        else:
            print(
                "⚠️ OCR-движок недоступен."
            )
        documents = self.find_documents()
        print()
        print(
            f"📋 Найдено файлов для анализа: "
            f"{len(documents)}"
        )
        print(
            f"📋 СОЗДАНА ОЧЕРЕДЬ: "
            f"{len(documents)} документов"
        )
        all_results = []
        for filepath in documents:
            result = (
                self.process_document(
                    filepath
                )
            )
            all_results.append(
                result
            )
            print(
                "-" * 27
            )
        # ====================================================
        # ALL FACTS
        # ====================================================
        all_facts = []
        for result in all_results:
            all_facts.extend(
                result.get(
                    "facts",
                    [],
                )
            )
        self.save_json(
            "all_facts.json",
            {
                "schema_version":
                    "3.0",
                "analysis_version":
                    "3.0",
                "generated_at":
                    datetime.now().isoformat(),
                "facts_count":
                    len(all_facts),
                "facts":
                    all_facts,
            },
        )
        # ====================================================
        # RUN REPORT
        # ====================================================
        done_count = sum(
            1
            for result in all_results
            if result[
                "queue"
            ][
                "current"
            ] == QUEUE_DONE
        )
        review_count = sum(
            1
            for result in all_results
            if result[
                "queue"
            ][
                "current"
            ] == QUEUE_REVIEW
        )
        problem_count = sum(
            1
            for result in all_results
            if result[
                "queue"
            ][
                "current"
            ] == QUEUE_PROBLEM
        )
        physical_folders = (
            self.document_registry
            .get_physical_folders()
        )
        registered_documents = (
            self.document_registry
            .get_documents()
        )
        report = {
            "schema_version":
                "3.0",
            "analysis_version":
                "3.0",
            "generated_at":
                datetime.now().isoformat(),
            # ------------------------------------------------
            # 3.2
            # ------------------------------------------------
            "physical_folders_count":
                len(
                    physical_folders
                ),
            "documents_registered":
                len(
                    registered_documents
                ),
            "documents_total":
                len(
                    all_results
                ),
            # ------------------------------------------------
            # 3.36
            # ------------------------------------------------
            "done":
                done_count,
            "requires_review":
                review_count,
            "problem":
                problem_count,
            "facts_total":
                len(all_facts),
            # ------------------------------------------------
            # 3.1 / 3.5 / 3.29
            # ------------------------------------------------
            "originals_modified":
                0,
            "folders_renamed":
                False,
            "folders_moved":
                False,
            "documents_deleted":
                False,
            "entity_resolution":
                False,
            "conflict_resolution":
                False,
            "crm_links_created":
                False,
            "work_tasks_created":
                False,
            "messages_sent":
                False,
            # ------------------------------------------------
            # DOCUMENTS
            # ------------------------------------------------
            "documents": [
                {
                    "document_id":
                        r["document_id"],
                    "physical_folder_id":
                        r["document"].get(
                            "physical_folder_id"
                        ),
                    "filename":
                        r["filename"],
                    "status":
                        r["queue"][
                            "current"
                        ],
                    "doc_type":
                        r[
                            "classification"
                        ].get(
                            "doc_type",
                            "НЕ ОПРЕДЕЛЕНО",
                        ),
                    "classification_confidence":
                        r[
                            "classification"
                        ].get(
                            "confidence",
                            0,
                        ),
                    "extraction_method":
                        r[
                            "extraction"
                        ].get(
                            "method"
                        ),
                    "pages_total":
                        r[
                            "extraction"
                        ].get(
                            "pages_total",
                            0,
                        ),
                    "pages_read":
                        r[
                            "extraction"
                        ].get(
                            "pages_read",
                            0,
                        ),
                    "technical_quality":
                        r[
                            "extraction"
                        ].get(
                            "technical_quality"
                        ),
                    "facts":
                        len(
                            r.get(
                                "facts",
                                [],
                            )
                        ),
                    "error":
                        r.get(
                            "error"
                        ),
                }
                for r in all_results
            ],
        }
        self.save_json(
            "run_report.json",
            report,
        )
        # ====================================================
        # ФИНАЛЬНЫЙ ВЫВОД
        # ====================================================
        print()
        print(
            "💾 Результаты сохранены в: "
            f"{os.path.abspath(EXTRACTED_DIR)}"
        )
        print()
        print(
            "=" * 70
        )
        print(
            "📊 ФИНАЛЬНЫЙ ОТЧЁТ ПО ЭТАПУ 3"
        )
        print(
            "=" * 70
        )
        print(
            f"📁 PHYSICAL FOLDERS: "
            f"{len(physical_folders)}"
        )
        print(
            f"📄 DOCUMENTS: "
            f"{len(all_results)}"
        )
        print(
            f"✅ ОБРАБОТАНО УСПЕШНО: "
            f"{done_count}"
        )
        print(
            f"⚠️ ТРЕБУЕТ ПРОВЕРКИ: "
            f"{review_count}"
        )
        print(
            f"❌ ПРОБЛЕМЫ: "
            f"{problem_count}"
        )
        print(
            f"📄 ВСЕГО ФАКТОВ ИЗВЛЕЧЕНО: "
            f"{len(all_facts)}"
        )
        print(
            "🛡️ ИЗМЕНЕНИЙ ОРИГИНАЛОВ: 0"
        )
        print()
        print(
            "🔒 ГРАНИЦА ЭТАПА 3 СОБЛЮДЕНА:"
        )
        print(
            "   Entity Resolution: НЕТ"
        )
        print(
            "   Conflict Resolution: НЕТ"
        )
        print(
            "   CRM: НЕТ"
        )
        print(
            "   Tasks/Messages: НЕТ"
        )
        print(
            "   Rename/Move/Delete: НЕТ"
        )
        print(
            "=" * 70
        )


def main():
    processor = Stage3Processor()
    processor.run()


if __name__ == "__main__":
    main()
