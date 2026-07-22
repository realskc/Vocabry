from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path


def create_job(exchange: Path, *, invalid: bool = False) -> str:
    job_id = f"demo-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    staging = exchange.resolve() / "staging" / f"tmp-{job_id}"
    inbox = exchange.resolve() / "inbox" / job_id
    staging.mkdir(parents=True)
    manifest = {
        "protocol_version": 1,
        "job_id": job_id,
        "created_at": datetime.now(UTC).isoformat(),
        "generator": {"name": "vocabry-demo", "version": "0.2.0"},
        "payload": {"format": "jsonl", "file": "cards.jsonl"},
        "source": {"description": "built-in protocol demonstration"},
    }
    cards = [
        {"type": "standard_definition", "word": "run", "phonetic": "/rʌn/", "definition": "经营；管理", "example": "She runs a small restaurant.", "notes": ""},
        {"type": "word_only", "word": "concise", "phonetic": "/kənˈsaɪs/", "definition": "简明的", "example": "Keep the answer concise.", "notes": ""},
    ]
    if invalid:
        cards[1].pop("definition")
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (staging / "cards.jsonl").write_text("".join(json.dumps(card, ensure_ascii=False) + "\n" for card in cards), encoding="utf-8")
    inbox.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, inbox)
    return job_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an independent Vocabry import job")
    parser.add_argument("exchange", type=Path)
    parser.add_argument("--invalid", action="store_true")
    args = parser.parse_args()
    print(create_job(args.exchange, invalid=args.invalid))


if __name__ == "__main__":
    main()
