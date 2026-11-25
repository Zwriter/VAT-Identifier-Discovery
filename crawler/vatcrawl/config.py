"""
Minimal .env loader (no extra dependency). Looks for a .env file in the current folder and its
parents, and sets any variables that aren't already set in the environment.
Real environment variables always win over the file.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_env(filename: str = ".env") -> Path | None:
    here = Path.cwd().resolve()
    for folder in [here, *here.parents]:
        f = folder / filename
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.split(" #", 1)[0].strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            return f
    return None


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default
