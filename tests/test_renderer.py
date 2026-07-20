from vocabry.models import CardInput
from vocabry.renderer import input_hash, render


def test_renderer_escapes_external_text() -> None:
    card = CardInput("standard_definition", "<script>x</script>", "one & two", example="a\nb")
    result = render(card)
    assert "<script>" not in result.front_html
    assert "&lt;script&gt;" in result.front_html
    assert "one &amp; two" in result.back_html
    assert "a<br>b" in result.front_html
    assert '<div class="label">Example</div><div class="value">a<br>b</div>' in result.front_html


def test_renderer_is_deterministic() -> None:
    card = CardInput("single_definition_word", "concise", "brief")
    assert render(card) == render(card)
    assert input_hash(card) == input_hash(card)
