"""Carries out a plan and records every move, so a run can be undone.

Each move is recorded in the journal before it happens and confirmed after. If a run is
interrupted, undo still knows which files moved: those whose intent was written and
which are no longer where they were.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .planner import STATE_DIR, Plan

JOURNAL = "journal.jsonl"


class JournalError(RuntimeError):
    """Nothing to undo, or the journal cannot be read."""


@dataclass
class RunResult:
    run_id: str
    moved: int
    failed: list[tuple[Path, str]]


def journal_path(root: Path) -> Path:
    return root / STATE_DIR / JOURNAL


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(record, ensure_ascii=False) + "\n")
        journal.flush()
        os.fsync(journal.fileno())


def _records(root: Path) -> Iterator[dict[str, object]]:
    path = journal_path(root)
    if not path.exists():
        return
    with path.open(encoding="utf-8") as journal:
        for line in journal:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # a line cut off by a crash


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def run_plan(plan: Plan, move: Callable[[str, str], object] = shutil.move) -> RunResult:
    """Moves the files in the plan. A file that cannot be moved is reported and skipped."""
    root = plan.root
    run_id = uuid.uuid4().hex[:12]
    journal = journal_path(root)
    _append(journal, {"type": "run", "run": run_id, "at": datetime.now(UTC).isoformat()})
    moved = 0
    failed: list[tuple[Path, str]] = []
    for item in plan.moves:
        record = {
            "run": run_id,
            "from": _relative(root, item.source),
            "to": _relative(root, item.destination),
        }
        _append(journal, {"type": "intent", **record})
        try:
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            # Checked again right before moving, in case the file appeared since planning.
            if item.destination.exists():
                raise FileExistsError(f"{item.destination.name} already exists")
            move(str(item.source), str(item.destination))
        except OSError as error:
            failed.append((item.source, str(error)))
            continue
        _append(journal, {"type": "done", **record})
        moved += 1
    return RunResult(run_id, moved, failed)


@dataclass
class UndoResult:
    run_id: str
    restored: int
    renamed: list[Path]
    missing: list[Path]


def last_run(root: Path) -> str | None:
    runs = [r["run"] for r in _records(root) if r.get("type") == "run"]
    undone = {r["run"] for r in _records(root) if r.get("type") == "undone"}
    remaining = [str(run) for run in runs if run not in undone]
    return remaining[-1] if remaining else None


def undo_last(root: Path, move: Callable[[str, str], object] = shutil.move) -> UndoResult:
    """Moves the files of the most recent run that has not been undone back where they were.

    A file is moved back if its move was confirmed, or if it was recorded as about to
    move and is now at its destination and not at its source (the run was interrupted
    between the move and its confirmation). If something else now has the original name,
    the file comes back as "name (2).ext" rather than replacing it.
    """
    root = root.resolve()
    run_id = last_run(root)
    if run_id is None:
        raise JournalError("there is no run to undo in this folder")

    moves: dict[tuple[str, str], bool] = {}
    for record in _records(root):
        if record.get("run") != run_id or record.get("type") not in ("intent", "done"):
            continue
        key = (str(record["from"]), str(record["to"]))
        moves[key] = moves.get(key, False) or record["type"] == "done"

    restored = 0
    renamed: list[Path] = []
    missing: list[Path] = []
    created_folders: set[Path] = set()
    for (source_text, destination_text), confirmed in reversed(list(moves.items())):
        source = root / source_text
        destination = root / destination_text
        if not destination.exists():
            if confirmed:
                missing.append(destination)
            continue
        if not confirmed and source.exists():
            continue  # the move never happened
        target = source
        number = 2
        while target.exists():
            target = source.with_name(f"{source.stem} ({number}){source.suffix}")
            number += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        move(str(destination), str(target))
        if target != source:
            renamed.append(target)
        created_folders.add(destination.parent)
        restored += 1

    # Remove folders the run created and left empty, deepest first, never above the root.
    for folder in sorted(created_folders, key=lambda p: len(p.parts), reverse=True):
        current = folder
        while current != root and current.is_dir() and not any(current.iterdir()):
            current.rmdir()
            current = current.parent

    _append(journal_path(root), {"type": "undone", "run": run_id, "at": datetime.now(UTC).isoformat()})
    return UndoResult(run_id, restored, renamed, missing)
