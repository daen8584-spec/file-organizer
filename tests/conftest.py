from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

MakeFile = Callable[..., Path]


@pytest.fixture
def make_file(tmp_path: Path) -> MakeFile:
    """Creates a file under tmp_path with the given size and modification time."""

    def make(name: str, size: int = 10, modified: datetime = datetime(2025, 6, 15, 12, 0)) -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        stamp = modified.timestamp()
        os.utime(path, (stamp, stamp))
        return path

    return make


def tree(root: Path) -> dict[str, bytes]:
    """Every file under root (except the state folder) with its content, by relative path."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".fileorg" not in p.parts
    }
