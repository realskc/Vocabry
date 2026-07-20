from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

from .config import Settings
from .database import Database
from .importer import JobImporter


@dataclass(slots=True)
class VocabryService:
    settings: Settings
    database: Database
    importer: JobImporter

    @classmethod
    def open(cls, settings: Settings) -> "VocabryService":
        settings.ensure_directories()
        database = Database(settings.database_path)
        if settings.token_path.exists():
            token = settings.token_path.read_text(encoding="utf-8").strip()
        else:
            token = secrets.token_urlsafe(32)
            settings.token_path.write_text(token + "\n", encoding="utf-8")
            try:
                os.chmod(settings.token_path, 0o600)
            except OSError:
                pass
        database.ensure_client_token("admin", "Local administrator", "admin", token)
        importer = JobImporter(database, settings.exchange_dir)
        importer.recover()
        return cls(settings, database, importer)

    def close(self) -> None:
        self.database.close()
