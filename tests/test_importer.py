import os
from pathlib import Path

import pytest

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


def test_crash_before_database_commit_retries_without_partial_cards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, importer, exchange = setup_importer(tmp_path)
    job_id = create_job(exchange)
    original = database._insert_card
    calls = 0

    def crash_on_second_card(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated crash before commit")
        return original(*args, **kwargs)

    monkeypatch.setattr(database, "_insert_card", crash_on_second_card)
    with pytest.raises(RuntimeError, match="before commit"):
        importer.process(job_id)
    assert database.list_cards() == []
    assert (exchange / "processing" / job_id).is_dir()

    monkeypatch.setattr(database, "_insert_card", original)
    results = importer.recover()
    assert results[0]["status"] == "succeeded"
    assert len(database.list_cards()) == 2
    assert (exchange / "succeeded" / job_id / "result.json").exists()
    database.close()


def test_crash_after_commit_recovers_result_and_does_not_duplicate_cards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, importer, exchange = setup_importer(tmp_path)
    job_id = create_job(exchange)

    def crash_before_archive(*_args, **_kwargs):
        raise RuntimeError("simulated crash after commit")

    monkeypatch.setattr(importer, "_archive", crash_before_archive)
    with pytest.raises(RuntimeError, match="after commit"):
        importer.process(job_id)

    job = database.get_job(job_id)
    assert job["status"] == "succeeded"
    assert job["result"]["accepted"] == 2
    assert len(database.list_cards()) == 2

    monkeypatch.undo()
    recovered = importer.recover()
    assert recovered == [job["result"]]
    assert importer.recover() == []
    assert len(database.list_cards()) == 2
    assert (exchange / "succeeded" / job_id / "result.json").exists()
    database.close()


def test_recovery_rebuilds_legacy_missing_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database, importer, exchange = setup_importer(tmp_path)
    job_id = create_job(exchange)

    monkeypatch.setattr(
        importer,
        "_archive",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated legacy window")),
    )
    with pytest.raises(RuntimeError, match="legacy window"):
        importer.process(job_id)
    database.connection.execute("UPDATE import_jobs SET result_json=NULL WHERE job_id=?", (job_id,))
    assert database.get_job(job_id)["result"] is None

    monkeypatch.undo()
    result = importer.recover()[0]
    assert result["status"] == "succeeded"
    assert result["accepted"] == 2
    assert len(result["card_ids"]) == 2
    assert database.get_job(job_id)["result"] == result
    assert len(database.list_cards()) == 2
    database.close()


def test_crash_after_result_file_write_finishes_archive_on_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, importer, exchange = setup_importer(tmp_path)
    job_id = create_job(exchange)
    original_replace = os.replace
    processing = exchange / "processing" / job_id
    destination = exchange / "succeeded" / job_id

    def fail_final_move(source, target):
        if Path(source) == processing and Path(target) == destination:
            raise RuntimeError("simulated crash before final move")
        return original_replace(source, target)

    monkeypatch.setattr("vocabry.importer.os.replace", fail_final_move)
    with pytest.raises(RuntimeError, match="final move"):
        importer.process(job_id)
    assert (processing / "result.json").exists()
    assert len(database.list_cards()) == 2

    monkeypatch.undo()
    result = importer.recover()[0]
    assert result["status"] == "succeeded"
    assert (destination / "result.json").exists()
    assert len(database.list_cards()) == 2
    database.close()
