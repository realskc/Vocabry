from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    exchange_dir: Path
    database_path: Path
    token_path: Path
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def load(cls, data_dir: str | Path | None = None) -> "Settings":
        if data_dir is None:
            configured = os.environ.get("VOCABRY_DATA_DIR")
            if configured:
                root = Path(configured)
            else:
                local = os.environ.get("LOCALAPPDATA")
                root = Path(local) / "Vocabry" if local else Path.cwd() / ".vocabry"
        else:
            root = Path(data_dir)
        root = root.expanduser().resolve()
        return cls(
            data_dir=root,
            exchange_dir=root / "exchange",
            database_path=root / "vocabry.sqlite3",
            token_path=root / "admin.token",
            port=int(os.environ.get("VOCABRY_PORT", "8765")),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for name in ("staging", "inbox", "processing", "succeeded", "failed"):
            (self.exchange_dir / name).mkdir(parents=True, exist_ok=True)
