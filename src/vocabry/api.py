from __future__ import annotations

import asyncio
import hashlib
import html
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .errors import IdempotencyConflictError, ValidationError, VocabryError
from .models import CardInput
from .renderer import render
from .service import VocabryService
from . import __version__


class CardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_type: str
    word: str
    definition: str
    phonetic: str = ""
    example: str = ""
    notes: str = ""


class CardPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    card_type: str | None = None
    word: str | None = None
    definition: str | None = None
    phonetic: str | None = None
    example: str | None = None
    notes: str | None = None


class CardDelete(BaseModel):
    expected_revision: int = Field(ge=1)


class PreviewSessionRequest(BaseModel):
    card_id: str


class CandidatePreviewRequest(CardCreate):
    pass


class PairingExchange(BaseModel):
    code: str
    name: str = "Anki Add-on"


class AnkiChange(BaseModel):
    card_id: str
    expected_revision: int
    kind: str
    front_html: str | None = None
    back_html: str | None = None


class ReconciliationNote(BaseModel):
    note_id: int
    database_id: str = ""
    card_id: str


class ReconciliationInventory(BaseModel):
    notes: list[ReconciliationNote]


class ReconciliationResult(BaseModel):
    deleted_note_ids: list[int] = Field(default_factory=list)
    mappings: list[dict[str, Any]] = Field(default_factory=list)


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.load()
    service = VocabryService.open(configured)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        service.close()

    app = FastAPI(title="Vocabry", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.state.service = service

    @app.exception_handler(VocabryError)
    async def vocabry_error(_: Request, exc: VocabryError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details, "request_id": str(uuid.uuid4())}},
        )

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        error = ValidationError(str(exc))
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message, "details": {}, "request_id": str(uuid.uuid4())}},
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = "unauthorized" if exc.status_code == 401 else "forbidden" if exc.status_code == 403 else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": str(exc.detail), "details": {}, "request_id": str(uuid.uuid4())}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "request_validation", "message": "Request does not match the API schema", "details": {"issues": exc.errors()}, "request_id": str(uuid.uuid4())}},
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/preview"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; frame-src 'self'"
        return response

    def current_client(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        client = service.database.authenticate(authorization[7:])
        if client is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return client

    def admin_client(client: dict[str, Any] = Depends(current_client)) -> dict[str, Any]:
        if client["kind"] != "admin":
            raise HTTPException(status_code=403, detail="Administrator token required")
        return client

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok", "service": "vocabry", "version": __version__, "api_version": 1,
            "database_id": service.database.database_id,
        }

    @app.get("/api/v1/openapi.json", include_in_schema=False)
    def openapi_schema(_: dict[str, Any] = Depends(admin_client)) -> dict[str, Any]:
        return app.openapi()

    @app.post("/api/v1/ingest")
    def ingest(_=Depends(admin_client)) -> dict[str, Any]:
        results = service.importer.ingest()
        return {"jobs": results}

    @app.post("/api/v1/maintenance/rerender")
    def rerender(_: dict[str, Any] = Depends(admin_client)) -> dict[str, Any]:
        cards = service.database.rerender_stale_cards()
        return {"updated": len(cards), "card_ids": [card["card_id"] for card in cards]}

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str, _=Depends(current_client)) -> dict[str, Any]:
        return service.database.get_job(job_id)

    @app.get("/api/v1/cards")
    def list_cards(
        _=Depends(current_client),
        include_deleted: bool = False,
        word: str | None = Query(default=None, max_length=500),
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        cards = (
            service.database.find_cards_by_word(word, limit=limit)
            if word is not None and not include_deleted
            else service.database.list_cards(include_deleted=include_deleted, limit=limit, offset=offset)
        )
        return {"items": cards, "limit": limit, "offset": offset}

    @app.post("/api/v1/cards", status_code=201)
    def create_card(
        body: CardCreate,
        client: dict[str, Any] = Depends(current_client),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="Idempotency-Key header required")
        request_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        cached = service.database.idempotent_result(client["client_id"], idempotency_key)
        if cached:
            if cached[0] != request_hash:
                raise IdempotencyConflictError("Idempotency-Key was already used for another request")
            return cached[2]
        card = CardInput.from_mapping(body.model_dump())
        result = service.database.create_card(card)
        service.database.store_idempotent_result(client["client_id"], idempotency_key, request_hash, 201, result)
        return result

    @app.get("/api/v1/cards/{card_id}")
    def get_card(card_id: str, _=Depends(current_client)) -> dict[str, Any]:
        return service.database.get_card(card_id)

    @app.patch("/api/v1/cards/{card_id}")
    def patch_card(card_id: str, body: CardPatch, _=Depends(current_client)) -> dict[str, Any]:
        changes = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
        return service.database.update_card(card_id, body.expected_revision, changes)

    @app.delete("/api/v1/cards/{card_id}")
    def delete_card(card_id: str, body: CardDelete, _=Depends(current_client)) -> dict[str, Any]:
        return service.database.delete_card(card_id, body.expected_revision)

    @app.get("/api/v1/cards/{card_id}/history")
    def history(card_id: str, _=Depends(current_client)) -> dict[str, Any]:
        return {"items": service.database.history(card_id)}

    @app.post("/api/v1/preview/sessions")
    def preview_session(body: PreviewSessionRequest, _=Depends(current_client)) -> dict[str, Any]:
        token = service.database.create_preview_session(body.card_id)
        path = f"/preview/{body.card_id or 'cards'}?session={token}"
        return {"path": path, "expires_in": 600}

    @app.post("/api/v1/preview/candidate")
    def preview_candidate(body: CandidatePreviewRequest, _: dict[str, Any] = Depends(admin_client)) -> dict[str, Any]:
        card = CardInput.from_mapping(body.model_dump())
        rendered = render(card)
        return {
            "card_type": card.card_type,
            "structured_fields": card.structured_fields(),
            "front_html": rendered.front_html,
            "back_html": rendered.back_html,
            "renderer_version": rendered.renderer_version,
        }

    @app.post("/api/v1/admin/shutdown", status_code=202)
    async def shutdown(request: Request, _: dict[str, Any] = Depends(admin_client)) -> dict[str, str]:
        callback = getattr(request.app.state, "shutdown_callback", None)
        if callback is None:
            return {"status": "accepted"}
        asyncio.get_running_loop().call_later(0.1, callback)
        return {"status": "accepted"}

    @app.get("/preview/{card_id}", response_class=HTMLResponse)
    def preview(card_id: str, session: str) -> HTMLResponse:
        if not service.database.validate_preview_session(session, card_id):
            raise HTTPException(status_code=401, detail="Invalid preview session")
        card = service.database.get_card(card_id)
        front = html.escape(card["front_html"], quote=True)
        back = html.escape(card["back_html"], quote=True)
        page = f"""<!doctype html><meta charset=utf-8><title>Vocabry Preview</title>
<style>body{{font:16px system-ui;margin:2rem;max-width:50rem}}iframe{{width:100%;min-height:12rem;border:1px solid #ccc}}small{{color:#666}}</style>
<h1>{html.escape(card['structured_fields']['word'])}</h1><small>revision {card['revision']} · {card['html_origin']}</small>
<h2>Front</h2><iframe sandbox srcdoc="{front}"></iframe><h2>Back</h2><iframe sandbox srcdoc="{back}"></iframe>"""
        return HTMLResponse(page)

    @app.get("/api/v1/sync/status")
    def sync_status(client: dict[str, Any] = Depends(current_client)) -> dict[str, Any]:
        row = service.database.connection.execute("SELECT cursor FROM client_cursors WHERE client_id=?", (client["client_id"],)).fetchone()
        return {"client_id": client["client_id"], "cursor": row["cursor"] if row else 0, "mappings": service.database.sync_mappings()}

    @app.post("/api/v1/sync/reconcile")
    def reconcile(_=Depends(admin_client)) -> dict[str, Any]:
        return service.database.create_reconciliation()

    @app.get("/api/v1/sync/reconcile/{request_id}")
    def reconciliation_status(request_id: str, _=Depends(admin_client)) -> dict[str, Any]:
        return service.database.get_reconciliation(request_id)

    @app.post("/api/v1/sync/reconcile/{request_id}/execute")
    def execute_reconciliation(request_id: str, _=Depends(admin_client)) -> dict[str, Any]:
        return service.database.approve_reconciliation(request_id)

    @app.post("/api/v1/sync/reconcile/{request_id}/cancel")
    def cancel_reconciliation(request_id: str, _=Depends(admin_client)) -> dict[str, Any]:
        return service.database.cancel_reconciliation(request_id)

    @app.get("/api/v1/anki/reconcile/pending")
    def pending_reconciliation(client: dict[str, Any] = Depends(current_client)) -> dict[str, Any]:
        if client["kind"] != "anki":
            raise HTTPException(status_code=403, detail="Anki client required")
        return service.database.pending_reconciliation(client["client_id"]) or {"command": None}

    @app.post("/api/v1/anki/reconcile/{request_id}/inventory")
    def reconciliation_inventory(
        request_id: str, body: ReconciliationInventory, client: dict[str, Any] = Depends(current_client)
    ) -> dict[str, Any]:
        if client["kind"] != "anki":
            raise HTTPException(status_code=403, detail="Anki client required")
        return service.database.submit_reconciliation_inventory(
            request_id, client["client_id"], [item.model_dump() for item in body.notes]
        )

    @app.post("/api/v1/anki/reconcile/{request_id}/complete")
    def reconciliation_complete(
        request_id: str, body: ReconciliationResult, client: dict[str, Any] = Depends(current_client)
    ) -> dict[str, Any]:
        if client["kind"] != "anki":
            raise HTTPException(status_code=403, detail="Anki client required")
        return service.database.complete_reconciliation(request_id, client["client_id"], body.model_dump())

    @app.post("/api/v1/anki/changes")
    def anki_change(body: AnkiChange, client: dict[str, Any] = Depends(current_client)) -> dict[str, Any]:
        if client["kind"] != "anki":
            raise HTTPException(status_code=403, detail="Anki client required")
        if body.kind == "html_updated" and body.front_html is not None and body.back_html is not None:
            return service.database.update_html_from_anki(body.card_id, body.expected_revision, body.front_html, body.back_html)
        if body.kind == "deleted":
            return service.database.delete_card(body.card_id, body.expected_revision, source="anki")
        if body.kind == "missing":
            service.database.mark_anki_missing(body.card_id)
            return {"card_id": body.card_id, "sync_status": "missing"}
        raise HTTPException(status_code=422, detail="Unsupported or incomplete Anki change")

    @app.post("/api/v1/pairing/codes")
    def pairing_code(_=Depends(admin_client)) -> dict[str, Any]:
        return {"code": service.database.create_pairing_code(), "expires_in": 300}

    @app.post("/api/v1/pairing/exchange")
    def pairing_exchange(body: PairingExchange) -> dict[str, Any]:
        client_id, token = service.database.exchange_pairing_code(body.code, body.name)
        return {"client_id": client_id, "token": token, "database_id": service.database.database_id}

    @app.delete("/api/v1/clients/{client_id}")
    def revoke_client(client_id: str, _: dict[str, Any] = Depends(admin_client)) -> dict[str, str]:
        service.database.revoke_client(client_id)
        return {"client_id": client_id, "status": "revoked"}

    @app.websocket("/api/v1/events")
    async def events(websocket: WebSocket) -> None:
        authorization = websocket.headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        client = service.database.authenticate(token)
        if client is None:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        cursor = int(websocket.query_params.get("cursor", "0"))
        try:
            while True:
                for event in service.database.events_after(cursor):
                    message = {key: value for key, value in event.items() if key not in {"payload_json", "event_type"}}
                    message["type"] = event["event_type"]
                    message["database_id"] = service.database.database_id
                    await websocket.send_json(message)
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=30)
                    if message.get("type") != "ack" or message.get("event_id") != event["event_id"]:
                        await websocket.close(code=4400)
                        return
                    if client["kind"] == "anki":
                        service.database.record_anki_application(
                            event["card_id"], event["revision"], message.get("note_id"), message.get("status", "synced")
                        )
                    cursor = service.database.acknowledge(client["client_id"], event["event_id"])
                await websocket.send_json({"type": "idle", "cursor": cursor})
                message = await asyncio.wait_for(websocket.receive_json(), timeout=30)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
        except (WebSocketDisconnect, TimeoutError):
            return

    return app
