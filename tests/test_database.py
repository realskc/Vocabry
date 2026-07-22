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
    card = database.create_card(CardInput("word_only", "clear", "easy to understand"))
    updated = database.update_card(card["card_id"], 1, {"notes": "plain"})
    assert updated["revision"] == 2
    assert len(database.history(card["card_id"])) == 2
    assert [event["revision"] for event in database.events_after(0)] == [1, 2]


def test_stale_revision_is_rejected(database: Database) -> None:
    card = database.create_card(CardInput("word_only", "clear", "easy to understand"))
    database.update_card(card["card_id"], 1, {"notes": "plain"})
    with pytest.raises(RevisionConflictError):
        database.update_card(card["card_id"], 1, {"notes": "stale"})


def test_anki_html_is_preserved_until_structured_edit(database: Database) -> None:
    card = database.create_card(CardInput("word_only", "clear", "easy"))
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
    assert updated[0]["renderer_version"] == 3
    assert '<section class="example"><div class="value">Very clear.</div></section>' in updated[0]["front_html"]
    assert 'class="label"' not in updated[0]["front_html"]
    assert database.rerender_stale_cards() == []


def test_legacy_single_definition_word_is_migrated_with_a_revision(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    database = Database(path)
    card = database.create_card(CardInput("word_only", "legacy", "old name"))
    database.connection.execute(
        "UPDATE cards SET card_type='single_definition_word', front_html='<b>manual</b>', "
        "back_html='<i>manual</i>', html_origin='anki_manual' WHERE card_id=?",
        (card["card_id"],),
    )
    database.close()

    migrated = Database(path)
    current = migrated.get_card(card["card_id"])
    assert current["card_type"] == "word_only"
    assert current["revision"] == 2
    assert current["html_origin"] == "anki_manual"
    assert current["front_html"] == "<b>manual</b>"
    assert current["back_html"] == "<i>manual</i>"
    assert migrated.history(card["card_id"])[-1]["source"] == "migration"
    assert migrated.events_after(0)[-1]["event_type"] == "card.updated"
    migrated.close()


def test_database_id_is_created_once_and_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "identity.sqlite3"
    database = Database(path)
    first = database.database_id
    database.close()
    reopened = Database(path)
    assert reopened.database_id == first
    reopened.close()
