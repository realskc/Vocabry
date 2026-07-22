from __future__ import annotations

import hashlib
import html
import json

from .models import CardInput, RenderedCard

RENDERER_VERSION = 3


def _text(value: str) -> str:
    escaped = html.escape(value, quote=True)
    return "<br>".join(escaped.splitlines())


def _section(css_class: str, value: str) -> str:
    if not value:
        return ""
    return f'<section class="{css_class}"><div class="value">{_text(value)}</div></section>'


def render(card: CardInput) -> RenderedCard:
    word = f'<div class="word">{_text(card.word)}</div>'
    example = _section("example", card.example)
    if card.card_type == "standard_definition":
        front = f'<article class="vocabry-card front">{word}{example}</article>'
    else:
        front = f'<article class="vocabry-card front">{word}</article>'
    back = "".join(
        (
            '<article class="vocabry-card back">',
            word,
            _section("phonetic", card.phonetic),
            _section("definition", card.definition),
            example,
            _section("notes", card.notes),
            "</article>",
        )
    )
    return RenderedCard(front, back, RENDERER_VERSION)


def input_hash(card: CardInput) -> str:
    payload = {"card_type": card.card_type, **card.structured_fields()}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
