from pathlib import Path

from vocabry.config import Settings
from vocabry.database import Database
from vocabry.demo_generator import create_job
from vocabry.importer import JobImporter


def setup_importer(tmp_path: Path) -> tuple[Database, JobImporter, Path]:
    settings = Settings.load(tmp_path)
    settings.ensure_directories()
    database = Database(settings.database_path)
    return database, JobImporter(database, settings.exchange_dir), settings.exchange_dir


def test_valid_job_is_imported_atomically(tmp_path: Path) -> None:
    database, importer, exchange = setup_importer(tmp_path)
    job_id = create_job(exchange)
    result = importer.process(job_id)
    assert result["status"] == "succeeded"
    assert result["accepted"] == 2
    assert len(database.list_cards()) == 2
    assert (exchange / "succeeded" / job_id / "result.json").exists()
    database.close()


def test_invalid_job_adds_no_cards(tmp_path: Path) -> None:
    database, importer, exchange = setup_importer(tmp_path)
    job_id = create_job(exchange, invalid=True)
    result = importer.process(job_id)
    assert result["status"] == "failed"
    assert database.list_cards() == []
    assert result["errors"][0]["line"] == 2
    database.close()
