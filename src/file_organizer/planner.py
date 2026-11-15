"""Builds the list of moves without touching anything, so a plan can be shown first."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .rules import FileInfo, Rule

STATE_DIR = ".fileorg"


@dataclass(frozen=True)
class Move:
    source: Path
    destination: Path
    rule: str


@dataclass(frozen=True)
class Plan:
    root: Path
    moves: list[Move]
    unmatched: list[Path]


def _free_name(target: Path, taken: set[str]) -> Path:
    """The target, or "name (2).ext", "name (3).ext"... if that name is used or planned.

    Names are compared case-insensitively, as macOS and Windows do, both with files already
    in the folder and with other planned moves. A plan made on Linux then never puts two
    names that differ only in case side by side.
    """
    existing = _names_in(target.parent)
    candidate = target
    number = 2
    while candidate.name.casefold() in existing or str(candidate).casefold() in taken:
        candidate = target.with_name(f"{target.stem} ({number}){target.suffix}")
        number += 1
    return candidate


def _names_in(folder: Path) -> set[str]:
    try:
        return {entry.name.casefold() for entry in folder.iterdir()}
    except FileNotFoundError:
        return set()


def _files(root: Path, recursive: bool, skip_top: set[str]) -> list[Path]:
    """Regular files to consider: hidden files, symlinks and the state folder are left alone.

    With recursive, subfolders are searched too, except hidden ones and the top-level
    folders that rules move files into, so organized files are not organized again.
    """
    found: list[Path] = []
    pending = [root]
    while pending:
        folder = pending.pop()
        for entry in sorted(folder.iterdir(), key=lambda p: p.name):
            if entry.name.startswith(".") or entry.is_symlink():
                continue
            if entry.is_dir():
                if recursive and not (folder == root and entry.name in skip_top):
                    pending.append(entry)
            elif entry.is_file():
                found.append(entry)
    return sorted(found)


def make_plan(root: Path, rules: list[Rule], recursive: bool = False, now: datetime | None = None) -> Plan:
    root = root.resolve()
    now = now or datetime.now()
    # Top-level folders that rules move files into ("." moves nothing into a subfolder).
    skip_top = {Path(rule.destination).parts[0] for rule in rules if Path(rule.destination).parts}
    moves: list[Move] = []
    unmatched: list[Path] = []
    taken: set[str] = set()

    for path in _files(root, recursive, skip_top):
        stat = path.stat()
        info = FileInfo(path, stat.st_size, datetime.fromtimestamp(stat.st_mtime))
        rule = next((r for r in rules if r.matches(info, now)), None)
        if rule is None:
            unmatched.append(path)
            continue
        folder = root / rule.target_folder(info)
        if path.parent == folder:
            continue  # already in place
        destination = _free_name(folder / path.name, taken)
        taken.add(str(destination).casefold())
        moves.append(Move(path, destination, rule.name))
    return Plan(root, moves, unmatched)
