"""Minimal loader for a local ``.env`` file.

Only ``KEY=value`` lines are supported, with optional ``export`` prefix and
matching single or double quotes around the value. Variables already set in
the environment are never overwritten, so an explicit shell value wins.

Error messages never contain the file content, because the file may hold the
card-ID salt.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path


def parse_env_text(text: str) -> dict[str, str]:
    """Parse ``.env`` content into a mapping.

    Args:
        text: File content.

    Returns:
        Mapping of variable names to values.

    Raises:
        ValueError: If a non-empty, non-comment line has no ``=``. The message
            names the line number only, never the content.
    """
    values: dict[str, str] = {}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"invalid .env syntax on line {number}")
        values[key.strip()] = _unquote(value.strip())
    return values


def load_env_file(path: Path, environ: MutableMapping[str, str]) -> None:
    """Load variables from ``path`` into ``environ`` without overriding them.

    A missing file is not an error: the shell environment stays authoritative.

    Args:
        path: Location of the ``.env`` file.
        environ: Target mapping, normally ``os.environ``.

    Raises:
        ValueError: If the file has invalid syntax (line number only).
    """
    if not path.is_file():
        return
    for key, value in parse_env_text(path.read_text(encoding="utf-8")).items():
        environ.setdefault(key, value)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


__all__ = ["load_env_file", "parse_env_text"]
