from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CARD_TYPES = {"standard_definition", "single_definition_word"}
FIELD_NAMES = ("word", "phonetic", "definition", "example", "notes")


@dataclass(frozen=True, slots=True)
class CardInput:
    card_type: str
    word: str
    definition: str
    phonetic: str = ""
    example: str = ""
    notes: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "CardInput":
        unknown = set(value) - {"type", "card_type", *FIELD_NAMES}
        if unknown:
            raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}")
        card_type = value.get("card_type", value.get("type"))
        if card_type not in CARD_TYPES:
            raise ValueError("Unsupported card type")
        fields: dict[str, str] = {}
        for name in FIELD_NAMES:
            item = value.get(name, "")
            if not isinstance(item, str):
                raise ValueError(f"Field '{name}' must be a string")
            fields[name] = item
        if not fields["word"].strip():
            raise ValueError("Field 'word' is required")
        if not fields["definition"].strip():
            raise ValueError("Field 'definition' is required")
        return cls(card_type=card_type, **fields)

    def structured_fields(self) -> dict[str, str]:
        result = asdict(self)
        result.pop("card_type")
        return result


@dataclass(frozen=True, slots=True)
class RenderedCard:
    front_html: str
    back_html: str
    renderer_version: int = 1
