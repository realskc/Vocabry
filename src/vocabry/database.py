from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Sequence

from .errors import DuplicateJobError, NotFoundError, RevisionConflictError
from .models import CardInput
from .renderer import RENDERER_VERSION, input_hash, render


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS cards (
    card_id TEXT PRIMARY KEY,
    card_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    structured_fields TEXT NOT NULL,
    front_html TEXT NOT NULL,
    back_html TEXT NOT NULL,
    html_origin TEXT NOT NULL CHECK (html_origin IN ('renderer', 'anki_manual')),
    renderer_version INTEGER NOT NULL,
    render_input_hash TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS card_revisions (
    card_id TEXT NOT NULL REFERENCES cards(card_id),
    revision INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    PRIMARY KEY (card_id, revision)
);
CREATE TABLE IF NOT EXISTS card_sources (
    card_id TEXT PRIMARY KEY REFERENCES cards(card_id),
    job_id TEXT,
    line_number INTEGER,
    generator_name TEXT,
    generator_version TEXT,
    source_json TEXT
);
CREATE TABLE IF NOT EXISTS import_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    card_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(card_id, revision)
);
CREATE TABLE IF NOT EXISTS client_cursors (
    client_id TEXT PRIMARY KEY,
    cursor INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_clients (
    client_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pairing_codes (
    code_hash TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE IF NOT EXISTS preview_sessions (
    session_hash TEXT PRIMARY KEY,
    card_id TEXT,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
    client_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(client_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS anki_note_mappings (
    card_id TEXT PRIMARY KEY REFERENCES cards(card_id),
    note_id INTEGER UNIQUE,
    pushed_revision INTEGER NOT NULL DEFAULT 0,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except BaseException:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    @staticmethod
    def _snapshot(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        value = dict(row)
        value["structured_fields"] = json.loads(value["structured_fields"])
        return value

    def _insert_card(
        self,
        connection: sqlite3.Connection,
        card: CardInput,
        *,
        source: str,
        reason: str,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        card_id = str(uuid.uuid4())
        now = utc_now()
        rendered = render(card)
        fields_json = json.dumps(card.structured_fields(), ensure_ascii=False, sort_keys=True)
        connection.execute(
            """INSERT INTO cards VALUES (?, ?, 1, ?, ?, ?, 'renderer', ?, ?, 1, ?, ?, NULL)""",
            (card_id, card.card_type, fields_json, rendered.front_html, rendered.back_html,
             rendered.renderer_version, input_hash(card), now, now),
        )
        row = connection.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
        assert row is not None
        self._record_change(connection, row, source=source, reason=reason, event_type="card.created")
        if provenance is not None:
            connection.execute(
                """INSERT INTO card_sources
                   (card_id, job_id, line_number, generator_name, generator_version, source_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (card_id, provenance.get("job_id"), provenance.get("line_number"),
                 provenance.get("generator_name"), provenance.get("generator_version"),
                 json.dumps(provenance.get("source"), ensure_ascii=False)),
            )
        return self._snapshot(row)

    def _record_change(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        source: str,
        reason: str,
        event_type: str,
    ) -> None:
        snapshot = self._snapshot(row)
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        connection.execute(
            "INSERT INTO card_revisions VALUES (?, ?, ?, ?, ?, ?)",
            (row["card_id"], row["revision"], encoded, source, reason, utc_now()),
        )
        connection.execute(
            """INSERT INTO outbox_events(event_type, card_id, revision, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (event_type, row["card_id"], row["revision"], encoded, utc_now()),
        )

    def create_card(self, card: CardInput, *, source: str = "api") -> dict[str, Any]:
        with self.transaction() as connection:
            return self._insert_card(connection, card, source=source, reason="create")

    def create_cards_for_job(
        self, job_id: str, manifest: dict[str, Any], cards: Sequence[tuple[int, CardInput]]
    ) -> list[dict[str, Any]]:
        generator = manifest.get("generator") or {}
        with self.transaction() as connection:
            exists = connection.execute("SELECT 1 FROM import_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if exists:
                raise DuplicateJobError(f"Job '{job_id}' has already been processed")
            connection.execute(
                "INSERT INTO import_jobs(job_id,status,manifest_json,created_at) VALUES (?, 'processing', ?, ?)",
                (job_id, json.dumps(manifest, ensure_ascii=False), utc_now()),
            )
            created = []
            for line_number, card in cards:
                created.append(self._insert_card(
                    connection,
                    card,
                    source="import",
                    reason=f"import:{job_id}",
                    provenance={
                        "job_id": job_id,
                        "line_number": line_number,
                        "generator_name": generator.get("name"),
                        "generator_version": generator.get("version"),
                        "source": manifest.get("source"),
                    },
                ))
            connection.execute(
                "UPDATE import_jobs SET status='succeeded', accepted=?, finished_at=? WHERE job_id=?",
                (len(created), utc_now(), job_id),
            )
            return created

    def record_failed_job(self, job_id: str, manifest: dict[str, Any], result: dict[str, Any]) -> None:
        with self.transaction() as connection:
            exists = connection.execute("SELECT 1 FROM import_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if exists:
                raise DuplicateJobError(f"Job '{job_id}' has already been processed")
            connection.execute(
                """INSERT INTO import_jobs(job_id,status,manifest_json,result_json,created_at,finished_at)
                   VALUES (?, 'failed', ?, ?, ?, ?)""",
                (job_id, json.dumps(manifest, ensure_ascii=False),
                 json.dumps(result, ensure_ascii=False), utc_now(), utc_now()),
            )

    def set_job_result(self, job_id: str, result: dict[str, Any]) -> None:
        self.connection.execute(
            "UPDATE import_jobs SET result_json=? WHERE job_id=?",
            (json.dumps(result, ensure_ascii=False), job_id),
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM import_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Job '{job_id}' was not found")
        result = dict(row)
        result["manifest"] = json.loads(result.pop("manifest_json"))
        raw_result = result.pop("result_json")
        result["result"] = json.loads(raw_result) if raw_result else None
        return result

    def get_card(self, card_id: str, *, include_deleted: bool = True) -> dict[str, Any]:
        query = "SELECT * FROM cards WHERE card_id=?"
        params: tuple[Any, ...] = (card_id,)
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        row = self.connection.execute(query, params).fetchone()
        if row is None:
            raise NotFoundError(f"Card '{card_id}' was not found")
        return self._snapshot(row)

    def list_cards(self, *, include_deleted: bool = False, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        rows = self.connection.execute(
            f"SELECT * FROM cards {where} ORDER BY created_at, card_id LIMIT ? OFFSET ?",
            (min(max(limit, 1), 500), max(offset, 0)),
        ).fetchall()
        return [self._snapshot(row) for row in rows]

    def update_card(self, card_id: str, expected_revision: int, changes: dict[str, Any], *, source: str = "api") -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Card '{card_id}' was not found")
            if row["revision"] != expected_revision:
                raise RevisionConflictError(
                    f"Card has changed since revision {expected_revision}",
                    details={"expected": expected_revision, "actual": row["revision"]},
                )
            current = self._snapshot(row)
            fields = dict(current["structured_fields"])
            card_type = changes.get("card_type", current["card_type"])
            for name in fields:
                if name in changes:
                    fields[name] = changes[name]
            candidate = CardInput.from_mapping({"card_type": card_type, **fields})
            if candidate.card_type == current["card_type"] and candidate.structured_fields() == fields == current["structured_fields"]:
                return current
            rendered = render(candidate)
            now = utc_now()
            connection.execute(
                """UPDATE cards SET card_type=?, structured_fields=?, front_html=?, back_html=?,
                   html_origin='renderer', renderer_version=?, render_input_hash=?, revision=revision+1,
                   updated_at=? WHERE card_id=?""",
                (candidate.card_type, json.dumps(candidate.structured_fields(), ensure_ascii=False, sort_keys=True),
                 rendered.front_html, rendered.back_html, rendered.renderer_version,
                 input_hash(candidate), now, card_id),
            )
            updated = connection.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
            assert updated is not None
            self._record_change(connection, updated, source=source, reason="structured_edit", event_type="card.updated")
            return self._snapshot(updated)

    def update_html_from_anki(self, card_id: str, expected_revision: int, front_html: str, back_html: str) -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Card '{card_id}' was not found")
            if row["revision"] != expected_revision:
                raise RevisionConflictError(
                    "Card changed before the Anki edit was accepted",
                    details={"expected": expected_revision, "actual": row["revision"]},
                )
            if row["front_html"] == front_html and row["back_html"] == back_html:
                return self._snapshot(row)
            connection.execute(
                """UPDATE cards SET front_html=?, back_html=?, html_origin='anki_manual',
                   revision=revision+1, updated_at=? WHERE card_id=?""",
                (front_html, back_html, utc_now(), card_id),
            )
            updated = connection.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
            assert updated is not None
            self._record_change(connection, updated, source="anki", reason="html_edit", event_type="card.updated")
            return self._snapshot(updated)

    def delete_card(self, card_id: str, expected_revision: int, *, source: str = "api") -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Card '{card_id}' was not found")
            if row["revision"] != expected_revision:
                raise RevisionConflictError(
                    "Card revision does not match",
                    details={"expected": expected_revision, "actual": row["revision"]},
                )
            if row["deleted_at"] is not None:
                return self._snapshot(row)
            now = utc_now()
            connection.execute(
                "UPDATE cards SET deleted_at=?, updated_at=?, revision=revision+1 WHERE card_id=?",
                (now, now, card_id),
            )
            updated = connection.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
            assert updated is not None
            self._record_change(connection, updated, source=source, reason="delete", event_type="card.deleted")
            return self._snapshot(updated)

    def history(self, card_id: str) -> list[dict[str, Any]]:
        self.get_card(card_id)
        rows = self.connection.execute(
            "SELECT * FROM card_revisions WHERE card_id=? ORDER BY revision", (card_id,)
        ).fetchall()
        return [{**dict(row), "snapshot": json.loads(row["snapshot"])} for row in rows]

    def rerender_stale_cards(self) -> list[dict[str, Any]]:
        card_ids = [row["card_id"] for row in self.connection.execute(
            """SELECT card_id FROM cards
               WHERE deleted_at IS NULL AND html_origin='renderer' AND renderer_version<?
               ORDER BY card_id""",
            (RENDERER_VERSION,),
        ).fetchall()]
        updated: list[dict[str, Any]] = []
        for card_id in card_ids:
            with self.transaction() as connection:
                row = connection.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
                if row is None or row["html_origin"] != "renderer" or row["renderer_version"] >= RENDERER_VERSION:
                    continue
                snapshot = self._snapshot(row)
                card = CardInput.from_mapping({"card_type": snapshot["card_type"], **snapshot["structured_fields"]})
                rendered = render(card)
                connection.execute(
                    """UPDATE cards SET front_html=?,back_html=?,renderer_version=?,render_input_hash=?,
                       revision=revision+1,updated_at=? WHERE card_id=?""",
                    (rendered.front_html, rendered.back_html, rendered.renderer_version,
                     input_hash(card), utc_now(), card_id),
                )
                changed = connection.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
                assert changed is not None
                self._record_change(connection, changed, source="maintenance", reason="renderer_upgrade", event_type="card.updated")
                updated.append(self._snapshot(changed))
        return updated

    def events_after(self, cursor: int, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM outbox_events WHERE event_id>? ORDER BY event_id LIMIT ?",
            (max(cursor, 0), min(max(limit, 1), 500)),
        ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def acknowledge(self, client_id: str, event_id: int) -> int:
        with self.transaction() as connection:
            current = connection.execute("SELECT cursor FROM client_cursors WHERE client_id=?", (client_id,)).fetchone()
            cursor = current["cursor"] if current else 0
            if event_id <= cursor:
                return cursor
            if event_id != cursor + 1:
                raise RevisionConflictError("Ack must advance the continuous event prefix", details={"cursor": cursor})
            connection.execute(
                """INSERT INTO client_cursors(client_id,cursor,updated_at) VALUES(?,?,?)
                   ON CONFLICT(client_id) DO UPDATE SET cursor=excluded.cursor,updated_at=excluded.updated_at""",
                (client_id, event_id, utc_now()),
            )
            return event_id

    def record_anki_application(self, card_id: str, revision: int, note_id: int | None, status: str = "synced") -> None:
        self.connection.execute(
            """INSERT INTO anki_note_mappings(card_id,note_id,pushed_revision,sync_status,updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(card_id) DO UPDATE SET
               note_id=COALESCE(excluded.note_id,anki_note_mappings.note_id),
               pushed_revision=MAX(excluded.pushed_revision,anki_note_mappings.pushed_revision),
               sync_status=excluded.sync_status,updated_at=excluded.updated_at""",
            (card_id, note_id, revision, status, utc_now()),
        )

    def mark_anki_missing(self, card_id: str) -> None:
        self.get_card(card_id)
        self.connection.execute(
            """INSERT INTO anki_note_mappings(card_id,note_id,pushed_revision,sync_status,updated_at)
               VALUES (?, NULL, 0, 'missing', ?)
               ON CONFLICT(card_id) DO UPDATE SET sync_status='missing',updated_at=excluded.updated_at""",
            (card_id, utc_now()),
        )

    def sync_mappings(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM anki_note_mappings ORDER BY updated_at DESC"
        ).fetchall()]

    def create_client(self, name: str, kind: str) -> tuple[str, str]:
        client_id, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        self.connection.execute(
            "INSERT INTO api_clients VALUES (?, ?, ?, ?, NULL, ?)",
            (client_id, name, token_hash(token), kind, utc_now()),
        )
        return client_id, token

    def ensure_client_token(self, client_id: str, name: str, kind: str, token: str) -> None:
        self.connection.execute(
            """INSERT INTO api_clients(client_id,name,token_hash,kind,revoked_at,created_at)
               VALUES (?, ?, ?, ?, NULL, ?)
               ON CONFLICT(client_id) DO UPDATE SET name=excluded.name,
               token_hash=excluded.token_hash,kind=excluded.kind,revoked_at=NULL""",
            (client_id, name, token_hash(token), kind, utc_now()),
        )

    def authenticate(self, token: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM api_clients WHERE token_hash=? AND revoked_at IS NULL", (token_hash(token),)
        ).fetchone()
        return dict(row) if row else None

    def revoke_client(self, client_id: str) -> None:
        if client_id == "admin":
            raise ValueError("The local administrator client cannot be revoked through the API")
        cursor = self.connection.execute(
            "UPDATE api_clients SET revoked_at=? WHERE client_id=? AND revoked_at IS NULL",
            (utc_now(), client_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"Client '{client_id}' was not found or is already revoked")

    def create_pairing_code(self) -> str:
        code = "-".join((f"{secrets.randbelow(10000):04d}", f"{secrets.randbelow(10000):04d}"))
        expires = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        self.connection.execute("INSERT INTO pairing_codes VALUES (?, ?, NULL)", (token_hash(code), expires))
        return code

    def exchange_pairing_code(self, code: str, name: str) -> tuple[str, str]:
        now = utc_now()
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM pairing_codes WHERE code_hash=?", (token_hash(code),)).fetchone()
            if row is None or row["used_at"] is not None or row["expires_at"] < now:
                raise NotFoundError("Pairing code is invalid or expired")
            connection.execute("UPDATE pairing_codes SET used_at=? WHERE code_hash=?", (now, token_hash(code)))
            return self.create_client(name, "anki")

    def create_preview_session(self, card_id: str | None) -> str:
        if card_id:
            self.get_card(card_id)
        token = secrets.token_urlsafe(24)
        expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
        self.connection.execute("INSERT INTO preview_sessions VALUES (?, ?, ?)", (token_hash(token), card_id, expires))
        return token

    def validate_preview_session(self, token: str, card_id: str) -> bool:
        row = self.connection.execute(
            "SELECT * FROM preview_sessions WHERE session_hash=?", (token_hash(token),)
        ).fetchone()
        return bool(row and row["expires_at"] >= utc_now() and (row["card_id"] is None or row["card_id"] == card_id))

    def idempotent_result(self, client_id: str, key: str) -> tuple[str, int, dict[str, Any]] | None:
        row = self.connection.execute(
            "SELECT request_hash,status_code,response_json FROM idempotency_keys WHERE client_id=? AND idempotency_key=?",
            (client_id, key),
        ).fetchone()
        return (row["request_hash"], row["status_code"], json.loads(row["response_json"])) if row else None

    def store_idempotent_result(self, client_id: str, key: str, request_hash: str, status: int, response: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO idempotency_keys VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, key, request_hash, status, json.dumps(response, ensure_ascii=False), utc_now()),
        )
