import pytest

from vocabry.models import CardInput
from vocabry.renderer import input_hash, render


def test_renderer_escapes_external_text() -> None:
    card = CardInput("standard_definition", "<script>x</script>", "one & two", example="a\nb")
    result = render(card)
    assert "<script>" not in result.front_html
    assert "&lt;script&gt;" in result.front_html
    assert "one &amp; two" in result.back_html
    assert "a<br>b" in result.front_html
    assert '<section class="example"><div class="value">a<br>b</div></section>' in result.front_html
    assert 'class="label"' not in result.front_html + result.back_html
    assert "Example" not in result.front_html + result.back_html
    assert "Pronunciation" not in result.back_html
    assert "Definition" not in result.back_html
    assert "Notes" not in result.back_html


def test_renderer_is_deterministic() -> None:
    card = CardInput("word_only", "concise", "brief")
    assert render(card) == render(card)
    assert input_hash(card) == input_hash(card)


def test_legacy_card_type_is_rejected_for_new_input() -> None:
    with pytest.raises(ValueError, match="Unsupported card type"):
        CardInput.from_mapping(
            {
                "card_type": "single_definition_word",
                "word": "legacy",
                "definition": "old name",
            }
        )
