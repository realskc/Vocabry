import json

import pytest

from vocabry.credentials import get_deepseek_key
from vocabry.generators.word_query import CARD_PROMPT, EXPLANATION_PROMPT, DeepSeekClient
from vocabry.models import CardInput


def test_real_deepseek_word_query() -> None:
    key = get_deepseek_key()
    if not key:
        pytest.fail(
            "No Vocabry DeepSeek credential is stored in Windows Credential Manager. "
            "Open vocabry-gui, enter the key in Settings, click Save, and confirm the saved message."
        )
    client = DeepSeekClient(key, timeout=60)
    first_messages = [{"role": "user", "content": EXPLANATION_PROMPT.format(word="concise")}]
    explanation = client.send(client.freeze(first_messages))
    assert explanation.strip()
    second_messages = [*first_messages, {"role": "assistant", "content": explanation}, {"role": "user", "content": CARD_PROMPT}]
    raw = client.send(client.freeze(second_messages)).strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    value = json.loads(raw)
    card = CardInput.from_mapping({"card_type": "word_only", **value})
    assert card.card_type == "word_only"
    assert card.word.casefold() == "concise"
    assert card.definition.strip()
