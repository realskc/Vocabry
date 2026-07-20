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
            json={"card_type": "single_definition_word", "word": "clear", "definition": "easy"},
        )
        assert created.status_code == 201
        card = created.json()
        replayed = client.post(
            "/api/v1/cards",
            headers=headers,
            json={"card_type": "single_definition_word", "word": "clear", "definition": "easy"},
        )
        assert replayed.json()["card_id"] == card["card_id"]
        reused = client.post(
            "/api/v1/cards",
            headers=headers,
            json={"card_type": "single_definition_word", "word": "different", "definition": "value"},
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
            json={"card_type": "single_definition_word", "word": "safe", "definition": "not dangerous"},
        ).json()
        session = client.post("/api/v1/preview/sessions", headers=auth, json={"card_id": card["card_id"]}).json()
        page = client.get(session["path"])
        assert page.status_code == 200
        assert "<iframe sandbox" in page.text


def test_websocket_event_ack_advances_cursor(tmp_path: Path) -> None:
    settings = Settings.load(tmp_path)
    app = create_app(settings)
    token = settings.token_path.read_text(encoding="utf-8").strip()
    auth = {"Authorization": f"Bearer {token}", "Idempotency-Key": "event-card"}
    with TestClient(app) as client:
        card = client.post(
            "/api/v1/cards",
            headers=auth,
            json={"card_type": "single_definition_word", "word": "event", "definition": "something that happens"},
        ).json()
        with client.websocket_connect("/api/v1/events?cursor=0", headers={"Authorization": f"Bearer {token}"}) as socket:
            event = socket.receive_json()
            assert event["type"] == "card.created"
            assert event["card_id"] == card["card_id"]
            socket.send_json({"type": "ack", "event_id": event["event_id"]})
            assert socket.receive_json()["type"] == "idle"
        status = client.get("/api/v1/sync/status", headers={"Authorization": f"Bearer {token}"}).json()
        assert status["cursor"] == 1
