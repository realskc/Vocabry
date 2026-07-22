"""Thin Vocabry adapter for Anki.

The module remains importable outside Anki for packaging checks. Hook registration is
performed only when Anki's runtime is present.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse


def api_request(base_url: str, token: str, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def exchange_pairing_code(base_url: str, code: str) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/v1/pairing/exchange",
        data=json.dumps({"code": code, "name": "Anki Add-on"}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def apply_new_pairing(config: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Replace server identity without carrying cursors or mappings across databases."""
    updated = dict(config)
    updated.update(result)
    updated["cursor"] = 0
    updated["managed_cards"] = {}
    return updated


def should_report_reconciliation_error(exc: BaseException) -> bool:
    """Treat the local service being offline as normal background-polling state."""
    if isinstance(exc, urllib.error.HTTPError):
        return True
    return not isinstance(exc, urllib.error.URLError)


def connection_status_text(status: str) -> str:
    labels = {
        "unpaired": "Vocabry：未配对",
        "connecting": "Vocabry：正在连接",
        "connected": "Vocabry：已连接",
        "offline": "Vocabry：未运行",
        "error": "Vocabry：连接失败",
    }
    return labels[status]


def ensure_note_type(collection: Any) -> Any:
    """Create the managed note type using only Anki collection APIs."""
    models = collection.models
    model = models.by_name("Vocabry")
    if model is not None:
        names = {field["name"] for field in model["flds"]}
        legacy = {"ExternalCardId", "Front", "Back"}
        expected = legacy | {"VocabryDatabaseId"}
        if names == legacy:
            models.add_field(model, models.new_field("VocabryDatabaseId"))
            models.save(model)
            return model
        if names != expected:
            raise RuntimeError("Existing Vocabry note type has incompatible fields")
        return model
    model = models.new("Vocabry")
    for name in ("VocabryDatabaseId", "ExternalCardId", "Front", "Back"):
        models.add_field(model, models.new_field(name))
    template = models.new_template("Vocabry Card")
    template["qfmt"] = "{{Front}}"
    template["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}"
    models.add_template(model, template)
    models.add(model)
    return model


try:
    from aqt import gui_hooks, mw  # type: ignore
    from PyQt6.QtCore import QTimer, QUrl  # type: ignore
    from PyQt6.QtGui import QAction  # type: ignore
    from PyQt6.QtNetwork import QAbstractSocket, QNetworkRequest  # type: ignore
    from PyQt6.QtWebSockets import QWebSocket  # type: ignore
    from PyQt6.QtWidgets import QInputDialog, QMessageBox  # type: ignore

    _socket = None
    _heartbeat = None
    _reconcile_timer = None
    _reconcile_busy = False
    _status_action = None
    _applying: set[str] = set()

    def _config() -> dict[str, Any]:
        return mw.addonManager.getConfig(__name__) or {}

    def _save_config(value: dict[str, Any]) -> None:
        mw.addonManager.writeConfig(__name__, value)

    def _set_connection_status(status: str) -> None:
        if _status_action is not None:
            _status_action.setText(connection_status_text(status))

    def _find_notes(database_id: str, card_id: str, *, include_legacy: bool = True) -> list[Any]:
        note_ids = mw.col.find_notes(f'"ExternalCardId:{card_id}"')
        notes = [mw.col.get_note(note_id) for note_id in note_ids]
        exact = [note for note in notes if note["VocabryDatabaseId"] == database_id]
        if exact or not include_legacy:
            return exact
        return [note for note in notes if not note["VocabryDatabaseId"]]

    def _apply_event(event: dict[str, Any]) -> int | None:
        payload = event["payload"]
        card_id = event["card_id"]
        database_id = event["database_id"]
        notes = _find_notes(database_id, card_id)
        note = notes[0] if notes else None
        config = _config()
        managed = config.setdefault("managed_cards", {})
        if event["type"] == "card.deleted":
            managed.pop(card_id, None)
            _save_config(config)
            if notes:
                note_ids = [item.id for item in notes]
                mw.col.remove_notes(note_ids)
                return note_ids[0]
            return None
        _applying.add(card_id)
        try:
            if note is None:
                model = ensure_note_type(mw.col)
                note = mw.col.new_note(model)
                note["VocabryDatabaseId"] = database_id
                note["ExternalCardId"] = card_id
                note["Front"] = payload["front_html"]
                note["Back"] = payload["back_html"]
                deck_id = mw.col.decks.id("Vocabry")
                mw.col.add_note(note, deck_id)
            else:
                note["VocabryDatabaseId"] = database_id
                note["Front"] = payload["front_html"]
                note["Back"] = payload["back_html"]
                note.flush()
        finally:
            _applying.discard(card_id)
        managed[card_id] = {"note_id": note.id, "revision": event["revision"]}
        _save_config(config)
        return note.id

    def _submit_user_change(note: Any) -> None:
        if "ExternalCardId" not in note or "Front" not in note or "Back" not in note:
            return
        card_id = note["ExternalCardId"]
        if not card_id or card_id in _applying:
            return
        config = _config()
        state = config.get("managed_cards", {}).get(card_id)
        if not state or not config.get("token"):
            return
        body = {
            "card_id": card_id,
            "expected_revision": state["revision"],
            "kind": "html_updated",
            "front_html": note["Front"],
            "back_html": note["Back"],
        }

        def work() -> dict[str, Any]:
            return api_request(config["base_url"], config["token"], "/api/v1/anki/changes", method="POST", body=body)

        def done(future: Any) -> None:
            try:
                result = future.result()
            except Exception as exc:
                QMessageBox.warning(mw, "Vocabry", f"Could not upload Anki edit: {exc}")
                return
            latest = _config()
            latest.setdefault("managed_cards", {}).setdefault(card_id, {})["revision"] = result["revision"]
            _save_config(latest)

        mw.taskman.run_in_background(work, done)

    def _detect_deleted_notes() -> None:
        config = _config()
        managed = dict(config.get("managed_cards", {}))
        for card_id, state in managed.items():
            try:
                mw.col.get_note(state["note_id"])
                continue
            except Exception:
                pass
            body = {"card_id": card_id, "expected_revision": state["revision"], "kind": "deleted"}
            try:
                result = api_request(config["base_url"], config["token"], "/api/v1/anki/changes", method="POST", body=body)
            except Exception:
                continue
            state["revision"] = result["revision"]
            managed.pop(card_id, None)
        config["managed_cards"] = managed
        _save_config(config)

    def _inventory() -> list[dict[str, Any]]:
        ensure_note_type(mw.col)
        result = []
        for note_id in mw.col.find_notes("note:Vocabry"):
            note = mw.col.get_note(note_id)
            card_id = note["ExternalCardId"].strip()
            if card_id:
                result.append({
                    "note_id": note.id,
                    "database_id": note["VocabryDatabaseId"].strip(),
                    "card_id": card_id,
                })
        return result

    def _apply_reconciliation(plan: dict[str, Any]) -> dict[str, Any]:
        deletion_ids = sorted({int(item["note_id"]) for item in plan.get("deletions", [])})
        if deletion_ids:
            mw.col.remove_notes(deletion_ids)
        mappings = []
        managed: dict[str, dict[str, int]] = {}
        for item in plan.get("upserts", []):
            note = None
            note_id = item.get("note_id")
            if note_id is not None:
                try:
                    note = mw.col.get_note(int(note_id))
                except Exception:
                    note = None
            if note is None:
                matches = _find_notes(item["database_id"], item["card_id"])
                note = matches[0] if matches else None
            if note is None:
                model = ensure_note_type(mw.col)
                note = mw.col.new_note(model)
                note["VocabryDatabaseId"] = item["database_id"]
                note["ExternalCardId"] = item["card_id"]
                note["Front"] = item["front_html"]
                note["Back"] = item["back_html"]
                mw.col.add_note(note, mw.col.decks.id("Vocabry"))
            else:
                note["VocabryDatabaseId"] = item["database_id"]
                note["ExternalCardId"] = item["card_id"]
                note["Front"] = item["front_html"]
                note["Back"] = item["back_html"]
                note.flush()
            managed[item["card_id"]] = {"note_id": note.id, "revision": item["revision"]}
            mappings.append({"card_id": item["card_id"], "note_id": note.id, "revision": item["revision"]})
        config = _config()
        config["managed_cards"] = managed
        _save_config(config)
        mw.reset()
        return {"deleted_note_ids": deletion_ids, "mappings": mappings}

    def _poll_reconciliation() -> None:
        global _reconcile_busy
        config = _config()
        if _reconcile_busy or not config.get("token") or mw.col is None:
            return
        _reconcile_busy = True

        def work() -> dict[str, Any]:
            return api_request(config["base_url"], config["token"], "/api/v1/anki/reconcile/pending")

        def done(future: Any) -> None:
            global _reconcile_busy
            try:
                command = future.result()
                if command.get("command") == "inventory":
                    body = {"notes": _inventory()}
                    path = f"/api/v1/anki/reconcile/{command['request_id']}/inventory"
                    mw.taskman.run_in_background(
                        lambda: api_request(config["base_url"], config["token"], path, method="POST", body=body),
                        lambda _future: _finish_reconcile_poll(_future),
                    )
                    return
                if command.get("command") == "execute":
                    result = _apply_reconciliation(command["plan"])
                    path = f"/api/v1/anki/reconcile/{command['request_id']}/complete"
                    mw.taskman.run_in_background(
                        lambda: api_request(config["base_url"], config["token"], path, method="POST", body=result),
                        lambda _future: _finish_reconcile_poll(_future),
                    )
                    return
            except Exception as exc:
                if should_report_reconciliation_error(exc):
                    QMessageBox.warning(mw, "Vocabry", f"全量对账失败：{exc}")
            _reconcile_busy = False

        mw.taskman.run_in_background(work, done)

    def _finish_reconcile_poll(future: Any) -> None:
        global _reconcile_busy
        try:
            future.result()
        except Exception as exc:
            if should_report_reconciliation_error(exc):
                QMessageBox.warning(mw, "Vocabry", f"全量对账失败：{exc}")
        _reconcile_busy = False

    def _connect() -> None:
        global _heartbeat, _socket
        config = _config()
        token = config.get("token")
        if not token:
            _set_connection_status("unpaired")
            return
        _set_connection_status("connecting")
        if config.get("cursor", 0) and not config.get("managed_cards"):
            config["cursor"] = 0
            _save_config(config)
        if _heartbeat is not None:
            _heartbeat.stop()
        parsed = urlparse(config.get("base_url", "http://127.0.0.1:8765"))
        query = urlencode({"cursor": int(config.get("cursor", 0))})
        target = urlunparse(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, "/api/v1/events", "", query, ""))
        socket = QWebSocket()
        disconnect_status = {"value": "offline"}

        def on_connected() -> None:
            disconnect_status["value"] = "offline"
            _set_connection_status("connected")

        def on_error(error: QAbstractSocket.SocketError) -> None:
            offline_errors = {
                QAbstractSocket.SocketError.ConnectionRefusedError,
                QAbstractSocket.SocketError.RemoteHostClosedError,
                QAbstractSocket.SocketError.SocketTimeoutError,
            }
            disconnect_status["value"] = "offline" if error in offline_errors else "error"
            _set_connection_status(disconnect_status["value"])

        def on_disconnected() -> None:
            _set_connection_status(disconnect_status["value"])
            QTimer.singleShot(3_000, _connect)

        def on_message(raw: str) -> None:
            event = json.loads(raw)
            if event.get("type") in {"idle", "pong"}:
                return
            try:
                note_id = _apply_event(event)
                socket.sendTextMessage(json.dumps({"type": "ack", "event_id": event["event_id"], "note_id": note_id, "status": "synced"}))
                latest = _config()
                latest["cursor"] = event["event_id"]
                _save_config(latest)
                mw.reset()
            except Exception as exc:
                QMessageBox.warning(mw, "Vocabry", f"Could not apply sync event: {exc}")

        socket.textMessageReceived.connect(on_message)
        socket.connected.connect(on_connected)
        socket.errorOccurred.connect(on_error)
        socket.disconnected.connect(on_disconnected)
        request = QNetworkRequest(QUrl(target))
        request.setRawHeader(b"Authorization", f"Bearer {token}".encode("ascii"))
        socket.open(request)
        _socket = socket
        timer = QTimer(mw)
        timer.setInterval(10_000)
        timer.timeout.connect(lambda: socket.sendTextMessage(json.dumps({"type": "ping"})))
        timer.start()
        _heartbeat = timer

    def _pair() -> None:
        code, accepted = QInputDialog.getText(mw, "配对 Vocabry", "一次性配对码：")
        if not accepted or not code:
            return
        config = _config()
        try:
            result = exchange_pairing_code(config.get("base_url", "http://127.0.0.1:8765"), code)
        except Exception as exc:
            QMessageBox.warning(mw, "Vocabry", f"配对失败：{exc}")
            return
        config = apply_new_pairing(config, result)
        _save_config(config)
        _connect()
        QMessageBox.information(mw, "Vocabry", "配对成功，已重置旧服务的同步游标和映射。")

    def _on_profile_open() -> None:
        global _reconcile_timer, _status_action
        if mw.col is not None:
            ensure_note_type(mw.col)
            status = QAction(connection_status_text("unpaired"), mw)
            status.setEnabled(False)
            mw.form.menuTools.addAction(status)
            _status_action = status
            action = QAction("配对 Vocabry...", mw)
            action.triggered.connect(_pair)
            mw.form.menuTools.addAction(action)
            _connect()
            timer = QTimer(mw)
            timer.setInterval(2_000)
            timer.timeout.connect(_poll_reconciliation)
            timer.start()
            _reconcile_timer = timer

    gui_hooks.profile_did_open.append(_on_profile_open)
    try:
        from anki.hooks import note_will_flush  # type: ignore

        note_will_flush.append(_submit_user_change)
    except (ImportError, AttributeError):
        pass

    def _after_operation(*_args: Any) -> None:
        QTimer.singleShot(0, _detect_deleted_notes)

    gui_hooks.operation_did_execute.append(_after_operation)
except ImportError as exc:
    if exc.name not in {"aqt", "anki"} and not (exc.name or "").startswith(("aqt.", "anki.")):
        raise
