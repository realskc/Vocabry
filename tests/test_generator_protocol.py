import io
import json
import threading

import pytest

from vocabry.generator_protocol import GeneratorManifest, JsonLineWriter, ProtocolError, decode_message
from vocabry.generators.word_query import DeepSeekClient, FrozenRequest, WordQueryGenerator


def test_manifest_and_json_lines() -> None:
    manifest = GeneratorManifest.from_mapping(
        {
            "id": "sample",
            "name": "Sample",
            "version": "1",
            "protocol_version": 1,
            "layout": "chat-v1",
            "module": "sample",
            "required_credentials": ["deepseek"],
        }
    )
    assert manifest.id == "sample"
    stream = io.StringIO()
    JsonLineWriter(stream).send({"type": "ready", "text": "你好"})
    assert decode_message(stream.getvalue())["text"] == "你好"
    with pytest.raises(ProtocolError):
        decode_message("plain output")


def test_frozen_request_is_stable() -> None:
    client = DeepSeekClient("sentinel")
    messages = [{"role": "user", "content": "word"}]
    first = client.freeze(messages)
    second = client.freeze(messages)
    assert isinstance(first, FrozenRequest)
    assert first.body == second.body


def test_invalid_business_input_does_not_start_task() -> None:
    stream = io.StringIO()
    generator = WordQueryGenerator(JsonLineWriter(stream))
    assert generator.handle({"type": "initialize", "credentials": {"deepseek": "sentinel"}})
    assert generator.handle({"type": "user_input", "task_id": "t1", "content": "word!"})
    messages = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert any(item.get("content") == "请输入一个英语单词或词组。" for item in messages)
    assert messages[-1]["type"] == "ready_for_input"
    assert generator.task_id is None


def test_word_query_accepts_an_english_phrase(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    generator = WordQueryGenerator(JsonLineWriter(stream))
    generator.handle({"type": "initialize", "credentials": {"deepseek": "sentinel"}})
    started = threading.Event()
    received: list[tuple[str, str]] = []

    def capture(task_id: str, query: str) -> None:
        received.append((task_id, query))
        started.set()

    monkeypatch.setattr(generator, "_run_explanation", capture)
    generator.handle({"type": "user_input", "task_id": "phrase-1", "content": "take off"})

    assert started.wait(1)
    assert received == [("phrase-1", "take off")]
    assert generator.task_id == "phrase-1"


@pytest.mark.parametrize("query", ["the more ... the more", "the more … the more"])
def test_word_query_accepts_ellipsis_in_a_phrase(monkeypatch: pytest.MonkeyPatch, query: str) -> None:
    stream = io.StringIO()
    generator = WordQueryGenerator(JsonLineWriter(stream))
    generator.handle({"type": "initialize", "credentials": {"deepseek": "sentinel"}})
    started = threading.Event()
    received: list[str] = []

    def capture(_task_id: str, value: str) -> None:
        received.append(value)
        started.set()

    monkeypatch.setattr(generator, "_run_explanation", capture)
    generator.handle({"type": "user_input", "task_id": "ellipsis-1", "content": query})

    assert started.wait(1)
    assert received == [query]
