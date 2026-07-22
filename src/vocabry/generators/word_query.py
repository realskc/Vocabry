from __future__ import annotations

import json
import logging
import re
import sys
import threading
from dataclasses import dataclass
from typing import Any

import httpx

from vocabry.generator_protocol import JsonLineWriter, PROTOCOL_VERSION, decode_message
from vocabry.models import CardInput

GENERATOR_ID = "word-query"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
QUERY_PATTERN = re.compile(r"(?=[A-Za-z.'… -]*[A-Za-z])[A-Za-z.'… -]+\Z")

EXPLANATION_PROMPT = """请用中文清晰解释英语单词或词组 {word!r}。如果其可以拆分，请对其进行拆分并简要讲解组成部分（无论是否来自英语）。仅介绍它最常见的本质含义，如果这一本质含义有多种相似、派生、抽象含义（例如 shift 的移动、改变、变化、轮班），均进行介绍。同时介绍其重要的用法细节，并给出一个英文例句。只输出纯文本，不要使用 Markdown，也不要输出 JSON。"""
CARD_PROMPT = """请把上文的解释作为权威上下文，生成且只生成一张 word_only 词汇卡。只返回一个 JSON 对象，且只能包含以下字符串字段：word、phonetic、definition、example、notes。word 保留输入的英语单词或词组，phonetic 使用标准音标，definition 和 notes 使用中文，example 使用自然的英文例句。不要输出 Markdown 代码围栏或任何额外文字。"""


class NetworkTimeout(Exception):
    pass


@dataclass(slots=True)
class FrozenRequest:
    body: bytes


class DeepSeekClient:
    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def freeze(self, messages: list[dict[str, str]]) -> FrozenRequest:
        payload = {
            "model": MODEL,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "stream": False,
        }
        return FrozenRequest(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def send(self, request: FrozenRequest) -> str:
        try:
            response = httpx.post(
                DEEPSEEK_URL,
                content=request.body,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise NetworkTimeout("DeepSeek request timed out") from exc
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()


class WordQueryGenerator:
    def __init__(self, writer: JsonLineWriter) -> None:
        self.writer = writer
        self.client: DeepSeekClient | None = None
        self.task_id: str | None = None
        self.cancelled: set[str] = set()
        self.pending_retry: tuple[str, str, FrozenRequest, list[dict[str, str]]] | None = None
        self._lock = threading.Lock()

    def handle(self, message: dict[str, Any]) -> bool:
        kind = message["type"]
        if kind == "initialize":
            credentials = message.get("credentials", {})
            key = credentials.get("deepseek") if isinstance(credentials, dict) else None
            if not isinstance(key, str) or not key:
                raise ValueError("DeepSeek credential is required")
            self.client = DeepSeekClient(key)
            self.writer.send({"type": "initialized"})
            self.writer.send({"type": "message", "role": "assistant", "content_type": "text", "content": "请输入一个英语单词或词组。"})
            return True
        if kind == "user_input":
            self._start(str(message.get("task_id", "")), message.get("content"))
            return True
        if kind == "retry":
            self._retry(str(message.get("task_id", "")))
            return True
        if kind == "cancel":
            task_id = str(message.get("task_id", ""))
            self.cancelled.add(task_id)
            if self.task_id == task_id:
                self.task_id = None
                self.pending_retry = None
                self.writer.send({"type": "cancelled", "task_id": task_id})
            return True
        if kind == "candidate_action":
            if str(message.get("task_id", "")) == self.task_id:
                self.task_id = None
                self.pending_retry = None
                self.writer.send({"type": "ready_for_input"})
            return True
        if kind == "shutdown":
            return False
        raise ValueError(f"Unsupported message type: {kind}")

    def _start(self, task_id: str, content: Any) -> None:
        if self.client is None:
            raise ValueError("Generator is not initialized")
        if self.task_id is not None:
            raise ValueError("Another task is active")
        if not isinstance(content, str) or not QUERY_PATTERN.fullmatch(content.strip()):
            self.writer.send({"type": "message", "role": "assistant", "content_type": "text", "content": "请输入一个英语单词或词组。"})
            self.writer.send({"type": "ready_for_input"})
            return
        self.task_id = task_id
        self.cancelled.discard(task_id)
        word = content.strip()
        threading.Thread(target=self._run_explanation, args=(task_id, word), daemon=True).start()

    def _run_explanation(self, task_id: str, word: str) -> None:
        assert self.client is not None
        messages = [{"role": "user", "content": EXPLANATION_PROMPT.format(word=word)}]
        request = self.client.freeze(messages)
        self.writer.send({"type": "status", "task_id": task_id, "content": "正在生成中文解释..."})
        self._perform(task_id, "explanation", request, messages)

    def _perform(self, task_id: str, stage: str, request: FrozenRequest, messages: list[dict[str, str]]) -> None:
        assert self.client is not None
        try:
            content = self.client.send(request)
        except NetworkTimeout:
            if task_id not in self.cancelled:
                self.pending_retry = (task_id, stage, request, messages)
                self.writer.send({"type": "network_timeout", "task_id": task_id, "stage": stage})
            return
        except Exception as exc:
            logging.exception("DeepSeek %s request failed for task %s", stage, task_id)
            if task_id not in self.cancelled:
                self.writer.send({"type": "error", "task_id": task_id, "code": "deepseek_error", "message": type(exc).__name__})
            return
        if task_id in self.cancelled:
            return
        self.pending_retry = None
        if stage == "explanation":
            self.writer.send({"type": "message", "task_id": task_id, "role": "assistant", "content_type": "text", "content": content})
            continued = [*messages, {"role": "assistant", "content": content}, {"role": "user", "content": CARD_PROMPT}]
            card_request = self.client.freeze(continued)
            self.writer.send({"type": "status", "task_id": task_id, "content": "正在生成卡片..."})
            self._perform(task_id, "card", card_request, continued)
            return
        try:
            raw = content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
            value = json.loads(raw)
            card = CardInput.from_mapping({"card_type": "word_only", **value})
            if card.card_type != "word_only":
                raise ValueError("Word Query only produces word_only")
        except Exception as exc:
            logging.exception("Invalid card response for task %s", task_id)
            self.writer.send({"type": "error", "task_id": task_id, "code": "invalid_card", "message": type(exc).__name__})
            return
        self.writer.send({"type": "candidate", "task_id": task_id, "card": {"card_type": card.card_type, "fields": card.structured_fields()}})

    def _retry(self, task_id: str) -> None:
        pending = self.pending_retry
        if pending is None or pending[0] != task_id:
            raise ValueError("No timed-out request is available")
        self.pending_retry = None
        threading.Thread(target=self._perform, args=pending, daemon=True).start()


def main() -> None:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    writer = JsonLineWriter(sys.stdout)
    generator = WordQueryGenerator(writer)
    writer.send({"type": "hello", "id": GENERATOR_ID, "protocol_version": PROTOCOL_VERSION, "layout": "chat-v1"})
    for line in sys.stdin:
        try:
            message = decode_message(line)
            if not generator.handle(message):
                return
        except Exception as exc:
            logging.exception("Protocol command failed")
            writer.send({"type": "error", "code": "protocol_error", "message": type(exc).__name__})


if __name__ == "__main__":
    main()
