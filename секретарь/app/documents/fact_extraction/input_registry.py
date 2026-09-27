# ============================================================
# ЭТАП 3
# ПУНКТ 3.2 — РЕЕСТР ВХОДНЫХ ДОКУМЕНТОВ
#
# Схема:
#
# PhysicalFolder
#       ↓
# Document
#       ↓
# файл / содержимое
#
# Этот модуль занимается ТОЛЬКО технической регистрацией.
#
# Он НЕ:
# - определяет владельца;
# - объединяет людей;
# - объединяет автомобили;
# - связывает Person / Vehicle / Policy;
# - разрешает конфликты;
# - переименовывает файлы;
# - перемещает файлы;
# - удаляет файлы;
# - создаёт CRM-связи.
# ============================================================

import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional


REGISTRY_SCHEMA_VERSION = "3.2"

REGISTRY_FILENAME = "document_registry.json"


class DocumentRegistry:

    def __init__(
        self,
        registry_dir: Path,
    ):
        self.registry_dir = Path(
            registry_dir
        )

        self.registry_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.registry_path = (
            self.registry_dir
            / REGISTRY_FILENAME
        )

        self.data = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "next_document_number": 1,
            "next_physical_folder_number": 1,
            "physical_folders": [],
            "documents": [],
        }

        self._load()

    # ========================================================
    # ЗАГРУЗКА РЕЕСТРА
    # ========================================================

    def _load(self):

        if not self.registry_path.exists():
            return

        try:

            with open(
                self.registry_path,
                "r",
                encoding="utf-8",
            ) as file:

                loaded = json.load(file)

            if not isinstance(
                loaded,
                dict,
            ):
                return

            self.data.update(
                loaded
            )

        except Exception:

            # Повреждённый технический реестр
            # НЕ должен останавливать обработку
            # оригинальных документов.
            #
            # В таком случае начинаем технический
            # реестр заново.

            self.data = {
                "schema_version":
                    REGISTRY_SCHEMA_VERSION,
                "next_document_number": 1,
                "next_physical_folder_number": 1,
                "physical_folders": [],
                "documents": [],
            }

    # ========================================================
    # СОХРАНЕНИЕ РЕЕСТРА
    # ========================================================

    def save(self):

        temporary_path = (
            self.registry_path
            .with_suffix(".tmp")
        )

        with open(
            temporary_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                self.data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        temporary_path.replace(
            self.registry_path
        )

    # ========================================================
    # HASH ФАЙЛА
    # ========================================================

    @staticmethod
    def calculate_content_hash(
        filepath: Path,
    ) -> str:

        sha256 = hashlib.sha256()

        with open(
            filepath,
            "rb",
        ) as file:

            while True:

                chunk = file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                sha256.update(
                    chunk
                )

        return sha256.hexdigest()

    # ========================================================
    # PHYSICAL FOLDER
    # ========================================================

    def get_or_create_physical_folder(
        self,
        folder_path: Path,
        incoming_root: Path,
    ) -> Dict[str, Any]:

        folder_path = folder_path.resolve()
        incoming_root = incoming_root.resolve()

        try:

            relative_path = (
                folder_path.relative_to(
                    incoming_root
                )
            )

            relative_path_string = (
                str(relative_path)
                if str(relative_path) != "."
                else ""
            )

        except ValueError:

            relative_path_string = str(
                folder_path
            )

        # Ищем уже зарегистрированную
        # физическую папку.

        for folder in self.data[
            "physical_folders"
        ]:

            if (
                folder.get(
                    "relative_path"
                )
                == relative_path_string
            ):

                return folder

        # Создаём новую PhysicalFolder.

        number = self.data[
            "next_physical_folder_number"
        ]

        physical_folder_id = (
            f"PF-{number:06d}"
        )

        self.data[
            "next_physical_folder_number"
        ] = number + 1

        folder = {
            "physical_folder_id":
                physical_folder_id,

            "relative_path":
                relative_path_string,

            "absolute_path":
                str(folder_path),

            "source":
                "PHYSICAL_ARCHIVE",
        }

        self.data[
            "physical_folders"
        ].append(
            folder
        )

        return folder

    # ========================================================
    # ПОИСК СУЩЕСТВУЮЩЕГО DOCUMENT
    # ========================================================

    def find_document_by_hash(
        self,
        content_hash: str,
    ) -> Optional[
        Dict[str, Any]
    ]:

        for document in self.data[
            "documents"
        ]:

            if (
                document.get(
                    "content_hash"
                )
                == content_hash
            ):

                return document

        return None

    # ========================================================
    # РЕГИСТРАЦИЯ DOCUMENT
    # ========================================================

    def register_document(
        self,
        filepath: Path,
        incoming_root: Path,
    ) -> Dict[str, Any]:

        filepath = filepath.resolve()
        incoming_root = incoming_root.resolve()

        content_hash = (
            self.calculate_content_hash(
                filepath
            )
        )

        physical_folder = (
            self.get_or_create_physical_folder(
                filepath.parent,
                incoming_root,
            )
        )

        # ----------------------------------------------------
        # Если такой файл уже был зарегистрирован
        # по содержимому — сохраняем его Document ID.
        # ----------------------------------------------------

        existing = (
            self.find_document_by_hash(
                content_hash
            )
        )

        if existing is not None:

            existing[
                "current_path"
            ] = str(filepath)

            existing[
                "file_name"
            ] = filepath.name

            existing[
                "physical_folder_id"
            ] = physical_folder[
                "physical_folder_id"
            ]

            self.save()

            return existing

        # ----------------------------------------------------
        # Новый документ
        # ----------------------------------------------------

        number = self.data[
            "next_document_number"
        ]

        document_id = (
            f"DOC-{number:06d}"
        )

        self.data[
            "next_document_number"
        ] = number + 1

        try:

            relative_file_path = str(
                filepath.relative_to(
                    incoming_root
                )
            )

        except ValueError:

            relative_file_path = (
                filepath.name
            )

        document = {

            # Технический ID документа
            "document_id":
                document_id,

            # Связь:
            # PhysicalFolder → Document
            "physical_folder_id":
                physical_folder[
                    "physical_folder_id"
                ],

            # Технические сведения
            "file_name":
                filepath.name,

            "current_path":
                str(filepath),

            "relative_path":
                relative_file_path,

            "extension":
                filepath.suffix.lower(),

            "size_bytes":
                filepath.stat().st_size,

            "content_hash":
                content_hash,

            # Источник
            "source":
                "PHYSICAL_ARCHIVE",

            "registration_status":
                "REGISTERED",
        }

        self.data[
            "documents"
        ].append(
            document
        )

        self.save()

        return document

    # ========================================================
    # СПИСКИ
    # ========================================================

    def get_documents(self):

        return list(
            self.data[
                "documents"
            ]
        )

    def get_physical_folders(self):

        return list(
            self.data[
                "physical_folders"
            ]
        )
