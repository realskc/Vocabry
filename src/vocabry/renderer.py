from __future__ import annotations

import hashlib
import html
import json

from .models import CardInput, RenderedCard

RENDERER_VERSION = 2


def _text(value: str) -> str:
    escaped = html.escape(value, quote=True)
    return "<br>".join(escaped.splitlines())


def _section(css_class: str, label: str, value: str) -> str:
    if not value:
        return ""
    return (
        f'<section class="{css_class}"><div class="label">{label}</div>'
        f'<div class="value">{_text(value)}</div></section>'
    )


def render(card: CardInput) -> RenderedCard:
    word = f'<div class="word">{_text(card.word)}</div>'
    example = _section("example", "Example", card.example)
    if card.card_type == "standard_definition":
        front = f'<article class="vocabry-card front">{word}{example}</article>'
    else:
        front = f'<article class="vocabry-card front">{word}</article>'
    back = "".join(
        (
            '<article class="vocabry-card back">',
            word,
            _section("phonetic", "Pronunciation", card.phonetic),
            _section("definition", "Definition", card.definition),
            example,
            _section("notes", "Notes", card.notes),
            "</article>",
        )
    )
    return RenderedCard(front, back, RENDERER_VERSION)


def input_hash(card: CardInput) -> str:
    payload = {"card_type": card.card_type, **card.structured_fields()}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
