import urllib.error

from anki_addon import apply_new_pairing, connection_status_text, should_report_reconciliation_error


def test_new_pairing_does_not_reuse_another_database_cursor_or_mappings() -> None:
    previous = {
        "base_url": "http://127.0.0.1:8765",
        "token": "old-token",
        "client_id": "old-client",
        "cursor": 8,
        "managed_cards": {"old-card": {"note_id": 42, "revision": 3}},
    }
    updated = apply_new_pairing(
        previous,
        {"token": "new-token", "client_id": "new-client", "database_id": "new-database"},
    )
    assert updated["token"] == "new-token"
    assert updated["client_id"] == "new-client"
    assert updated["database_id"] == "new-database"
    assert updated["cursor"] == 0
    assert updated["managed_cards"] == {}
    assert previous["cursor"] == 8


def test_reconciliation_poll_does_not_report_service_shutdown_as_failure() -> None:
    refused = urllib.error.URLError(ConnectionRefusedError(10061, "connection refused"))
    unauthorized = urllib.error.HTTPError("http://127.0.0.1", 401, "unauthorized", {}, None)

    assert not should_report_reconciliation_error(refused)
    assert should_report_reconciliation_error(unauthorized)
    assert should_report_reconciliation_error(ValueError("invalid reconciliation payload"))


def test_anki_connection_status_has_user_facing_labels() -> None:
    assert connection_status_text("unpaired") == "Vocabry：未配对"
    assert connection_status_text("connecting") == "Vocabry：正在连接"
    assert connection_status_text("connected") == "Vocabry：已连接"
    assert connection_status_text("offline") == "Vocabry：未运行"
    assert connection_status_text("error") == "Vocabry：连接失败"
