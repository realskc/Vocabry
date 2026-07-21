from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .database import Database
from .errors import DuplicateJobError
from .models import CardInput

JOB_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
MAX_JOB_BYTES = 10 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_CARDS = 10_000


@dataclass(slots=True)
class ImportIssue:
    code: str
    file: str
    message: str
    line: int | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class JobImporter:
    def __init__(self, database: Database, exchange_dir: str | Path) -> None:
        self.database = database
        self.exchange_dir = Path(exchange_dir).resolve()

    def ingest(self) -> list[dict[str, Any]]:
        inbox = self.exchange_dir / "inbox"
        results = []
        for path in sorted(inbox.iterdir(), key=lambda value: value.name):
            if path.is_dir():
                results.append(self.process(path.name))
        return results

    def process(self, job_id: str) -> dict[str, Any]:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            return self._reject_unclaimed(job_id, "invalid_job_id", "Directory name is not a valid job ID")
        source = self.exchange_dir / "inbox" / job_id
        processing = self.exchange_dir / "processing" / job_id
        if not source.is_dir():
            return {"job_id": job_id, "status": "skipped", "reason": "not_found"}
        try:
            os.replace(source, processing)
        except FileExistsError:
            return {"job_id": job_id, "status": "skipped", "reason": "already_processing"}

        manifest, cards, issues = self._validate(processing, job_id)
        if issues:
            result = {
                "protocol_version": 1,
                "job_id": job_id,
                "status": "failed",
                "accepted": 0,
                "errors": [issue.to_dict() for issue in issues],
            }
            try:
                self.database.record_failed_job(job_id, manifest, result)
            except DuplicateJobError:
                result["errors"] = [{"code": "duplicate_job", "message": "Job ID was already processed"}]
            return self._archive(processing, "failed", result)

        try:
            result = self.database.create_cards_for_job(job_id, manifest, cards)
            return self._archive(processing, "succeeded", result)
        except DuplicateJobError:
            result = {
                "protocol_version": 1,
                "job_id": job_id,
                "status": "failed",
                "accepted": 0,
                "errors": [{"code": "duplicate_job", "message": "Job ID was already processed"}],
            }
            return self._archive(processing, "failed", result)

    def recover(self) -> list[dict[str, Any]]:
        results = []
        for path in sorted((self.exchange_dir / "processing").iterdir()):
            if not path.is_dir():
                continue
            try:
                job = self.database.get_job(path.name)
            except Exception:
                target = self.exchange_dir / "inbox" / path.name
                if not target.exists():
                    os.replace(path, target)
                    results.append(self.process(path.name))
                continue
            result = job.get("result") or self.database.recover_job_result(path.name)
            if result:
                results.append(self._archive(path, job["status"], result))
        return results

    def _validate(self, root: Path, job_id: str) -> tuple[dict[str, Any], list[tuple[int, CardInput]], list[ImportIssue]]:
        issues: list[ImportIssue] = []
        manifest_path, cards_path = root / "manifest.json", root / "cards.jsonl"
        allowed = {"manifest.json", "cards.jsonl"}
        extra = [path.name for path in root.iterdir() if path.name not in allowed]
        if extra:
            issues.append(ImportIssue("unexpected_file", extra[0], "Only manifest.json and cards.jsonl are allowed"))
        total_size = sum(path.stat().st_size for path in root.iterdir() if path.is_file())
        if total_size > MAX_JOB_BYTES:
            issues.append(ImportIssue("job_too_large", "", f"Job exceeds {MAX_JOB_BYTES} bytes"))
        manifest: dict[str, Any] = {}
        try:
            raw = manifest_path.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                raise UnicodeError("UTF-8 BOM is not allowed")
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("Manifest must be an object")
            manifest = parsed
        except FileNotFoundError:
            issues.append(ImportIssue("missing_file", "manifest.json", "manifest.json is required"))
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            issues.append(ImportIssue("invalid_manifest", "manifest.json", str(exc)))
        if manifest:
            if manifest.get("protocol_version") != 1:
                issues.append(ImportIssue("unsupported_protocol_version", "manifest.json", "protocol_version must be 1", field="protocol_version"))
            if manifest.get("job_id") != job_id:
                issues.append(ImportIssue("job_id_mismatch", "manifest.json", "manifest job_id must match directory", field="job_id"))
            generator = manifest.get("generator")
            if not isinstance(generator, dict) or not isinstance(generator.get("name"), str):
                issues.append(ImportIssue("missing_required_field", "manifest.json", "generator.name is required", field="generator.name"))
            payload = manifest.get("payload")
            if payload != {"format": "jsonl", "file": "cards.jsonl"}:
                issues.append(ImportIssue("invalid_payload", "manifest.json", "payload must select cards.jsonl", field="payload"))

        cards: list[tuple[int, CardInput]] = []
        try:
            with cards_path.open("rb") as stream:
                for line_number, raw_line in enumerate(stream, 1):
                    if len(raw_line) > MAX_LINE_BYTES:
                        issues.append(ImportIssue("line_too_large", "cards.jsonl", "Line exceeds size limit", line_number))
                        continue
                    if raw_line.startswith(b"\xef\xbb\xbf"):
                        issues.append(ImportIssue("invalid_encoding", "cards.jsonl", "UTF-8 BOM is not allowed", line_number))
                        continue
                    if not raw_line.strip():
                        continue
                    if len(cards) >= MAX_CARDS:
                        issues.append(ImportIssue("too_many_cards", "cards.jsonl", f"Job exceeds {MAX_CARDS} cards", line_number))
                        break
                    try:
                        value = json.loads(raw_line.decode("utf-8"))
                        if not isinstance(value, dict):
                            raise ValueError("Line must contain a JSON object")
                        cards.append((line_number, CardInput.from_mapping(value)))
                    except UnicodeDecodeError:
                        issues.append(ImportIssue("invalid_encoding", "cards.jsonl", "Line is not valid UTF-8", line_number))
                    except json.JSONDecodeError as exc:
                        issues.append(ImportIssue("invalid_json", "cards.jsonl", exc.msg, line_number))
                    except ValueError as exc:
                        message = str(exc)
                        field_match = re.search(r"Field '([^']+)'", message)
                        issues.append(ImportIssue("invalid_card", "cards.jsonl", message, line_number, field_match.group(1) if field_match else None))
        except FileNotFoundError:
            issues.append(ImportIssue("missing_file", "cards.jsonl", "cards.jsonl is required"))
        if not cards and not any(issue.file == "cards.jsonl" for issue in issues):
            issues.append(ImportIssue("empty_job", "cards.jsonl", "At least one card is required"))
        return manifest, cards, issues

    def _archive(self, processing: Path, status: str, result: dict[str, Any]) -> dict[str, Any]:
        result_path = processing / "result.json"
        temporary = processing / "result.json.tmp"
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, result_path)
        destination = self.exchange_dir / status / processing.name
        if destination.exists():
            shutil.rmtree(processing)
        else:
            os.replace(processing, destination)
        return result

    @staticmethod
    def _reject_unclaimed(job_id: str, code: str, message: str) -> dict[str, Any]:
        return {"job_id": job_id, "status": "failed", "accepted": 0, "errors": [{"code": code, "message": message}]}
