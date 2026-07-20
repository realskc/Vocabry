from pathlib import Path

import pytest

from vocabry.database import Database
from vocabry.errors import RevisionConflictError
from vocabry.models import CardInput


@pytest.fixture
def database(tmp_path: Path):
    value = Database(tmp_path / "test.sqlite3")
    yield value
    value.close()


def test_card_revision_and_outbox_are_committed_together(database: Database) -> None:
    card = database.create_card(CardInput("single_definition_word", "clear", "easy to understand"))
    updated = database.update_card(card["card_id"], 1, {"notes": "plain"})
    assert updated["revision"] == 2
    assert len(database.history(card["card_id"])) == 2
    assert [event["revision"] for event in database.events_after(0)] == [1, 2]


def test_stale_revision_is_rejected(database: Database) -> None:
    card = database.create_card(CardInput("single_definition_word", "clear", "easy to understand"))
    database.update_card(card["card_id"], 1, {"notes": "plain"})
    with pytest.raises(RevisionConflictError):
        database.update_card(card["card_id"], 1, {"notes": "stale"})


def test_anki_html_is_preserved_until_structured_edit(database: Database) -> None:
    card = database.create_card(CardInput("single_definition_word", "clear", "easy"))
    manual = database.update_html_from_anki(card["card_id"], 1, "<b>front</b>", "<b>back</b>")
    assert manual["html_origin"] == "anki_manual"
    rendered = database.update_card(card["card_id"], 2, {"notes": "changed"})
    assert rendered["html_origin"] == "renderer"
    assert rendered["front_html"] != "<b>front</b>"


def test_rerender_only_updates_stale_renderer_html(database: Database) -> None:
    card = database.create_card(CardInput("standard_definition", "clear", "easy", example="Very clear."))
    database.connection.execute("UPDATE cards SET renderer_version=1 WHERE card_id=?", (card["card_id"],))
    updated = database.rerender_stale_cards()
    assert len(updated) == 1
    assert updated[0]["revision"] == 2
    assert updated[0]["renderer_version"] == 2
    assert '<div class="label">Example</div>' in updated[0]["front_html"]
    assert database.rerender_stale_cards() == []
