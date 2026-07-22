import json

from vocabry.generators.word_query import DeepSeekClient


def test_word_query_uses_v4_flash_with_thinking_explicitly_disabled() -> None:
    messages = [{"role": "user", "content": "test"}]
    request = DeepSeekClient("unused").freeze(messages)
    payload = json.loads(request.body)

    assert payload["model"] == "deepseek-v4-flash"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["messages"] == messages
