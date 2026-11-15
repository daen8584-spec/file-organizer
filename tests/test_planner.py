from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from file_organizer.planner import make_plan
from file_organizer.rules import default_rules, rule_from_dict

from .conftest import MakeFile


def plan_pairs(root: Path, recursive: bool = False) -> list[tuple[str, str]]:
    plan = make_plan(root, default_rules(), recursive=recursive)
    return [
        (m.source.relative_to(plan.root).as_posix(), m.destination.relative_to(plan.root).as_posix())
        for m in plan.moves
    ]


def test_plans_moves_by_type_and_year(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("beach.jpg", modified=datetime(2024, 8, 1))
    make_file("report.pdf")
    make_file("song.mp3")
    make_file("Screenshot 1.png")
    make_file("notes.unknown")

    assert plan_pairs(tmp_path) == [
        ("Screenshot 1.png", "Images/Screenshots/Screenshot 1.png"),
        ("beach.jpg", "Images/2024/beach.jpg"),
        ("report.pdf", "Documents/report.pdf"),
        ("song.mp3", "Audio/song.mp3"),
    ]
    assert [p.name for p in make_plan(tmp_path, default_rules()).unmatched] == ["notes.unknown"]


def test_never_plans_over_an_existing_or_planned_name(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("Documents/report.pdf")
    make_file("report.pdf")
    make_file("Report.PDF")  # same name on case-insensitive file systems
    if len([p for p in tmp_path.iterdir() if p.is_file()]) < 2:
        pytest.skip("the file system ignores case, so both names are the same file")
    destinations = [to for _, to in plan_pairs(tmp_path)]
    assert sorted(destinations) == ["Documents/Report (2).PDF", "Documents/report (3).pdf"]


def test_leaves_hidden_files_symlinks_and_subfolders_alone(tmp_path: Path, make_file: MakeFile) -> None:
    make_file(".hidden.jpg")
    make_file("inside/photo.jpg")
    target = make_file("real.txt")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are not available")
    assert plan_pairs(tmp_path) == [("real.txt", "Documents/real.txt")]


def test_recursive_skips_destination_folders(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("inside/deeper/photo.jpg", modified=datetime(2023, 1, 1))
    make_file("Images/2023/already.jpg", modified=datetime(2023, 1, 1))
    make_file("Images/stray.mp3")
    assert plan_pairs(tmp_path, recursive=True) == [("inside/deeper/photo.jpg", "Images/2023/photo.jpg")]


def test_files_already_in_place_are_not_moved(tmp_path: Path, make_file: MakeFile) -> None:
    rule = rule_from_dict({"extensions": ["txt"], "destination": "."}, 0)
    make_file("a.txt")
    assert make_plan(tmp_path, [rule]).moves == []


def test_plan_does_not_change_anything(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("a.jpg")
    before = sorted(p.name for p in tmp_path.iterdir())
    make_plan(tmp_path, default_rules())
    assert sorted(p.name for p in tmp_path.iterdir()) == before
