from pathlib import Path

from fastapi.testclient import TestClient

from vocabry.api import create_app
from vocabry.config import Settings


def test_authenticated_card_lifecycle(tmp_path: Path) -> None:
    settings = Settings.load(tmp_path)
    app = create_app(settings)
    token = settings.token_path.read_text(encoding="utf-8").strip()
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "create-clear"}
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        unauthorized = client.get("/api/v1/cards")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"]["code"] == "unauthorized"
        assert client.get("/docs").status_code == 404
        assert client.get("/api/v1/openapi.json").status_code == 401
        assert client.get("/api/v1/openapi.json", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        created = client.post(
            "/api/v1/cards",
            headers=headers,
            json={"card_type": "word_only", "word": "clear", "definition": "easy"},
        )
        assert created.status_code == 201
        card = created.json()
        replayed = client.post(
            "/api/v1/cards",
            headers=headers,
            json={"card_type": "word_only", "word": "clear", "definition": "easy"},
        )
        assert replayed.json()["card_id"] == card["card_id"]
        reused = client.post(
            "/api/v1/cards",
            headers=headers,
            json={"card_type": "word_only", "word": "different", "definition": "value"},
        )
        assert reused.status_code == 409
        assert reused.json()["error"]["code"] == "idempotency_conflict"
        updated = client.patch(
            f"/api/v1/cards/{card['card_id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"expected_revision": 1, "notes": "plain"},
        )
        assert updated.status_code == 200
        assert updated.json()["revision"] == 2
        conflict = client.patch(
            f"/api/v1/cards/{card['card_id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"expected_revision": 1, "notes": "stale"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "revision_conflict"


def test_pairing_and_preview(tmp_path: Path) -> None:
    settings = Settings.load(tmp_path)
    app = create_app(settings)
    token = settings.token_path.read_text(encoding="utf-8").strip()
    auth = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        code = client.post("/api/v1/pairing/codes", headers=auth).json()["code"]
        paired = client.post("/api/v1/pairing/exchange", json={"code": code}).json()
        assert paired["token"]
        assert client.post("/api/v1/pairing/exchange", json={"code": code}).status_code == 404

        card = client.post(
            "/api/v1/cards",
            headers={**auth, "Idempotency-Key": "preview-card"},
            json={"card_type": "word_only", "word": "safe", "definition": "not dangerous"},
        ).json()
        session = client.post("/api/v1/preview/sessions", headers=auth, json={"card_id": card["card_id"]}).json()
        page = client.get(session["path"])
        assert page.status_code == 200
        assert "<iframe sandbox" in page.text


def test_candidate_preview_search_and_shutdown_permissions(tmp_path: Path) -> None:
    settings = Settings.load(tmp_path)
    app = create_app(settings)
    token = settings.token_path.read_text(encoding="utf-8").strip()
    auth = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        health = client.get("/api/v1/health").json()
        assert health | {"database_id": "ignored"} == {
            "status": "ok", "service": "vocabry", "version": "0.2.1", "api_version": 1,
            "database_id": "ignored",
        }
        assert health["database_id"]

        body = {"card_type": "standard_definition", "word": "Safe", "definition": "not dangerous"}
        preview = client.post("/api/v1/preview/candidate", headers=auth, json=body)
        assert preview.status_code == 200
        assert "Safe" in preview.json()["front_html"]
        assert client.get("/api/v1/cards", headers=auth).json()["items"] == []

        created = client.post(
            "/api/v1/cards",
            headers={**auth, "Idempotency-Key": "word-search"},
            json=body,
        )
        assert created.status_code == 201
        matches = client.get("/api/v1/cards?word=%20safe%20", headers=auth).json()["items"]
        assert [item["card_id"] for item in matches] == [created.json()["card_id"]]

        code = client.post("/api/v1/pairing/codes", headers=auth).json()["code"]
        anki = client.post("/api/v1/pairing/exchange", json={"code": code}).json()["token"]
        assert client.post("/api/v1/admin/shutdown", headers={"Authorization": f"Bearer {anki}"}).status_code == 403
        assert client.post("/api/v1/admin/shutdown", headers=auth).status_code == 202


def test_websocket_event_ack_advances_cursor(tmp_path: Path) -> None:
    settings = Settings.load(tmp_path)
    app = create_app(settings)
    token = settings.token_path.read_text(encoding="utf-8").strip()
    auth = {"Authorization": f"Bearer {token}", "Idempotency-Key": "event-card"}
    with TestClient(app) as client:
        card = client.post(
            "/api/v1/cards",
            headers=auth,
            json={"card_type": "word_only", "word": "event", "definition": "something that happens"},
        ).json()
        with client.websocket_connect("/api/v1/events?cursor=0", headers={"Authorization": f"Bearer {token}"}) as socket:
            event = socket.receive_json()
            assert event["type"] == "card.created"
            assert event["card_id"] == card["card_id"]
            assert event["database_id"]
            socket.send_json({"type": "ack", "event_id": event["event_id"]})
            assert socket.receive_json()["type"] == "idle"
        status = client.get("/api/v1/sync/status", headers={"Authorization": f"Bearer {token}"}).json()
        assert status["cursor"] == 1


def test_full_anki_reconciliation_is_scanned_then_explicitly_approved(tmp_path: Path) -> None:
    settings = Settings.load(tmp_path)
    app = create_app(settings)
    token = settings.token_path.read_text(encoding="utf-8").strip()
    admin = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        database_id = client.get("/api/v1/health").json()["database_id"]
        active = client.post(
            "/api/v1/cards",
            headers={**admin, "Idempotency-Key": "reconcile-active"},
            json={"card_type": "word_only", "word": "active", "definition": "kept"},
        ).json()
        removed = client.post(
            "/api/v1/cards",
            headers={**admin, "Idempotency-Key": "reconcile-deleted"},
            json={"card_type": "word_only", "word": "removed", "definition": "deleted"},
        ).json()
        client.request(
            "DELETE", f"/api/v1/cards/{removed['card_id']}", headers=admin,
            json={"expected_revision": removed["revision"]},
        )
        code = client.post("/api/v1/pairing/codes", headers=admin).json()["code"]
        pairing = client.post("/api/v1/pairing/exchange", json={"code": code}).json()
        assert pairing["database_id"] == database_id
        anki = {"Authorization": f"Bearer {pairing['token']}"}

        request_id = client.post("/api/v1/sync/reconcile", headers=admin).json()["request_id"]
        command = client.get("/api/v1/anki/reconcile/pending", headers=anki).json()
        assert command == {"command": "inventory", "request_id": request_id, "database_id": database_id}
        inventory = {
            "notes": [
                {"note_id": 10, "database_id": "", "card_id": active["card_id"]},
                {"note_id": 20, "database_id": database_id, "card_id": active["card_id"]},
                {"note_id": 30, "database_id": database_id, "card_id": removed["card_id"]},
                {"note_id": 40, "database_id": database_id, "card_id": "unknown-card"},
                {"note_id": 50, "database_id": "another-database", "card_id": "foreign-card"},
            ]
        }
        scanned = client.post(
            f"/api/v1/anki/reconcile/{request_id}/inventory", headers=anki, json=inventory
        ).json()
        assert scanned["status"] == "ready"
        assert scanned["report"] == {
            "anki_notes": 5,
            "active_cards": 1,
            "missing": 0,
            "legacy_adoptions": 1,
            "duplicates": 1,
            "deleted_card_notes": 1,
            "orphans": 1,
            "foreign_database_notes": 1,
            "delete_count": 4,
        }
        assert client.get("/api/v1/anki/reconcile/pending", headers=anki).json() == {"command": None}

        approved = client.post(f"/api/v1/sync/reconcile/{request_id}/execute", headers=admin).json()
        assert approved["status"] == "approved"
        execution = client.get("/api/v1/anki/reconcile/pending", headers=anki).json()
        assert execution["command"] == "execute"
        assert execution["plan"]["upserts"][0]["note_id"] == 10
        assert {item["note_id"] for item in execution["plan"]["deletions"]} == {20, 30, 40, 50}
        completed = client.post(
            f"/api/v1/anki/reconcile/{request_id}/complete",
            headers=anki,
            json={
                "deleted_note_ids": [20, 30, 40, 50],
                "mappings": [{"card_id": active["card_id"], "note_id": 10, "revision": 1}],
            },
        ).json()
        assert completed["status"] == "completed"
