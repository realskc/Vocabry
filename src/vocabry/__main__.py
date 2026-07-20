from __future__ import annotations

import argparse

import uvicorn

from .api import create_app
from .config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="vocabd")
    parser.add_argument("command", nargs="?", default="start", choices=("start", "status"))
    parser.add_argument("--data-dir")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    settings = Settings.load(args.data_dir)
    if args.port:
        settings = Settings(settings.data_dir, settings.exchange_dir, settings.database_path, settings.token_path, settings.host, args.port)
    if args.command == "status":
        print(f"data_dir={settings.data_dir}")
        print(f"database={'present' if settings.database_path.exists() else 'missing'}")
        print(f"token={'present' if settings.token_path.exists() else 'missing'}")
        return
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
