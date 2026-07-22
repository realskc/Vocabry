from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
from typing import Any

import pytest

from vocabry.credentials import get_deepseek_key
from vocabry.models import CardInput


def _send(process: subprocess.Popen[bytes], message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write((json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    process.stdin.flush()


def test_real_word_query_subprocess_emits_unicode_candidate() -> None:
    """Exercise the same subprocess and UTF-8 JSON Lines boundary used by the GUI."""
    key = get_deepseek_key()
    if not key:
        pytest.fail("No Vocabry DeepSeek credential is stored in Windows Credential Manager.")

    process = subprocess.Popen(
        [sys.executable, "-m", "vocabry.generators.word_query"],
        cwd=Path(__file__).parents[1],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output: queue.Queue[bytes] = queue.Queue()
    errors: list[bytes] = []

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output.put(line)

    def read_stderr() -> None:
        assert process.stderr is not None
        errors.extend(process.stderr.readlines())

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()

    def receive(timeout: float = 90) -> dict[str, Any]:
        try:
            line = output.get(timeout=timeout)
        except queue.Empty:
            diagnostic = b"".join(errors).decode("utf-8", errors="replace")[-2000:]
            pytest.fail(f"Word Query did not emit a protocol message in time. stderr: {diagnostic}")
        try:
            return json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            pytest.fail(f"Word Query stdout was not UTF-8 JSON Lines: {type(exc).__name__}")

    try:
        assert receive(10) == {"type": "hello", "id": "word-query", "protocol_version": 1, "layout": "chat-v1"}
        _send(process, {"type": "initialize", "credentials": {"deepseek": key}})
        assert receive(10)["type"] == "initialized"
        assert receive(10)["content"] == "请输入一个英语单词。"

        task_id = "live-unicode-candidate"
        _send(process, {"type": "user_input", "task_id": task_id, "content": "concise"})
        explanation = ""
        statuses: list[str] = []
        candidate: dict[str, Any] | None = None
        for _ in range(8):
            message = receive()
            assert message.get("task_id", task_id) == task_id
            if message["type"] == "status":
                statuses.append(message["content"])
            elif message["type"] == "message":
                explanation = message["content"]
            elif message["type"] == "candidate":
                candidate = message["card"]
                break
            elif message["type"] == "error":
                pytest.fail(f"Word Query reported {message.get('code')}")

        assert statuses == ["正在生成中文解释...", "正在生成卡片..."]
        assert any("\u4e00" <= character <= "\u9fff" for character in explanation)
        assert candidate is not None, "The generator never emitted the candidate message"
        card = CardInput.from_mapping({"card_type": candidate["card_type"], **candidate["fields"]})
        assert card.card_type == "word_only"
        assert card.word.casefold() == "concise"
        assert any(ord(character) > 127 for character in json.dumps(candidate, ensure_ascii=False))

        _send(process, {"type": "candidate_action", "task_id": task_id, "action": "discarded"})
        assert receive(10)["type"] == "ready_for_input"
    finally:
        if process.poll() is None:
            _send(process, {"type": "shutdown"})
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        assert process.returncode == 0
