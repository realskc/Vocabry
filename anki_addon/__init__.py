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


def ensure_note_type(collection: Any) -> Any:
    """Create the managed note type using only Anki collection APIs."""
    models = collection.models
    model = models.by_name("Vocabry")
    if model is not None:
        names = {field["name"] for field in model["flds"]}
        if names != {"ExternalCardId", "Front", "Back"}:
            raise RuntimeError("Existing Vocabry note type has incompatible fields")
        return model
    model = models.new("Vocabry")
    for name in ("ExternalCardId", "Front", "Back"):
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
    from PyQt6.QtNetwork import QNetworkRequest  # type: ignore
    from PyQt6.QtWebSockets import QWebSocket  # type: ignore
    from PyQt6.QtWidgets import QInputDialog, QMessageBox  # type: ignore

    _socket = None
    _heartbeat = None
    _applying: set[str] = set()

    def _config() -> dict[str, Any]:
        return mw.addonManager.getConfig(__name__) or {}

    def _save_config(value: dict[str, Any]) -> None:
        mw.addonManager.writeConfig(__name__, value)

    def _find_note(card_id: str) -> Any | None:
        note_ids = mw.col.find_notes(f'"ExternalCardId:{card_id}"')
        return mw.col.get_note(note_ids[0]) if note_ids else None

    def _apply_event(event: dict[str, Any]) -> int | None:
        payload = event["payload"]
        card_id = event["card_id"]
        note = _find_note(card_id)
        config = _config()
        managed = config.setdefault("managed_cards", {})
        if event["type"] == "card.deleted":
            managed.pop(card_id, None)
            _save_config(config)
            if note is not None:
                note_id = note.id
                mw.col.remove_notes([note_id])
                return note_id
            return None
        _applying.add(card_id)
        try:
            if note is None:
                model = ensure_note_type(mw.col)
                note = mw.col.new_note(model)
                note["ExternalCardId"] = card_id
                note["Front"] = payload["front_html"]
                note["Back"] = payload["back_html"]
                deck_id = mw.col.decks.id("Vocabry")
                mw.col.add_note(note, deck_id)
            else:
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

    def _connect() -> None:
        global _heartbeat, _socket
        config = _config()
        token = config.get("token")
        if not token:
            return
        if config.get("cursor", 0) and not config.get("managed_cards"):
            config["cursor"] = 0
            _save_config(config)
        if _heartbeat is not None:
            _heartbeat.stop()
        parsed = urlparse(config.get("base_url", "http://127.0.0.1:8765"))
        query = urlencode({"cursor": int(config.get("cursor", 0))})
        target = urlunparse(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, "/api/v1/events", "", query, ""))
        socket = QWebSocket()

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
        socket.disconnected.connect(lambda: QTimer.singleShot(3_000, _connect))
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
        code, accepted = QInputDialog.getText(mw, "Pair Vocabry", "One-time pairing code:")
        if not accepted or not code:
            return
        config = _config()
        try:
            result = exchange_pairing_code(config.get("base_url", "http://127.0.0.1:8765"), code)
        except Exception as exc:
            QMessageBox.warning(mw, "Vocabry", f"Pairing failed: {exc}")
            return
        config.update(result)
        _save_config(config)
        _connect()
        QMessageBox.information(mw, "Vocabry", "Pairing succeeded.")

    def _on_profile_open() -> None:
        if mw.col is not None:
            ensure_note_type(mw.col)
            action = QAction("Pair Vocabry…", mw)
            action.triggered.connect(_pair)
            mw.form.menuTools.addAction(action)
            _connect()

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
