from __future__ import annotations

import ctypes
import os
from pathlib import Path
import re
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _windows_user_name() -> str:
    size = ctypes.c_ulong(0)
    ctypes.windll.advapi32.GetUserNameW(None, ctypes.byref(size))
    buffer = ctypes.create_unicode_buffer(size.value)
    if not ctypes.windll.advapi32.GetUserNameW(buffer, ctypes.byref(size)):
        return "unknown"
    return buffer.value


def pytest_configure(config) -> None:
    if config.option.basetemp is not None:
        return
    identity = re.sub(r"[^A-Za-z0-9_.-]", "_", _windows_user_name())
    base = Path.cwd() / ".test-tmp" / f"{identity}-{os.getpid()}"
    base.parent.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(base)
    config._vocabry_basetemp = base


def pytest_sessionfinish(session, exitstatus) -> None:
    base = getattr(session.config, "_vocabry_basetemp", None)
    if base is not None and base.is_dir():
        shutil.rmtree(base, ignore_errors=True)
