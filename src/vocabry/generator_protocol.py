from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, TextIO

PROTOCOL_VERSION = 1
LAYOUT_CHAT_V1 = "chat-v1"
MAX_INPUT_LENGTH = 500


class ProtocolError(ValueError):
    pass


def decode_message(line: str) -> dict[str, Any]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ProtocolError("Protocol message must be an object with a string 'type'")
    return value


def encode_message(message: dict[str, Any]) -> str:
    if not isinstance(message.get("type"), str):
        raise ProtocolError("Protocol message requires a string 'type'")
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


class JsonLineWriter:
    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self._lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        line = encode_message(message)
        with self._lock:
            self.stream.write(line + "\n")
            self.stream.flush()


@dataclass(frozen=True, slots=True)
class GeneratorManifest:
    id: str
    name: str
    version: str
    protocol_version: int
    layout: str
    module: str
    required_credentials: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "GeneratorManifest":
        required = {"id", "name", "version", "protocol_version", "layout", "module"}
        missing = required - set(value)
        if missing:
            raise ProtocolError(f"Manifest missing: {', '.join(sorted(missing))}")
        credentials = value.get("required_credentials", [])
        if not isinstance(credentials, list) or not all(isinstance(item, str) for item in credentials):
            raise ProtocolError("required_credentials must be a list of strings")
        manifest = cls(
            id=str(value["id"]),
            name=str(value["name"]),
            version=str(value["version"]),
            protocol_version=int(value["protocol_version"]),
            layout=str(value["layout"]),
            module=str(value["module"]),
            required_credentials=tuple(credentials),
        )
        if manifest.protocol_version != PROTOCOL_VERSION or manifest.layout != LAYOUT_CHAT_V1:
            raise ProtocolError("Unsupported generator protocol or layout")
        return manifest
