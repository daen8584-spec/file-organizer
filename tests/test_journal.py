from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from file_organizer.journal import JournalError, journal_path, last_run, run_plan, undo_last
from file_organizer.planner import make_plan
from file_organizer.rules import default_rules

from .conftest import MakeFile, tree


def populate(make_file: MakeFile) -> None:
    make_file("beach.jpg")
    make_file("report.pdf", size=20)
    make_file("song.mp3", size=30)
    make_file("archive.zip", size=40)
    make_file("keep.unknown")


def test_run_then_undo_restores_the_folder_exactly(tmp_path: Path, make_file: MakeFile) -> None:
    populate(make_file)
    before = tree(tmp_path)

    result = run_plan(make_plan(tmp_path, default_rules()))
    assert result.moved == 4 and result.failed == []
    assert sorted(tree(tmp_path)) == [
        "Archives/archive.zip",
        "Audio/song.mp3",
        "Documents/report.pdf",
        "Images/2025/beach.jpg",
        "keep.unknown",
    ]

    undone = undo_last(tmp_path)
    assert undone.restored == 4
    assert tree(tmp_path) == before
    # The folders the run created are gone again.
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        ".fileorg",
        "archive.zip",
        "beach.jpg",
        "keep.unknown",
        "report.pdf",
        "song.mp3",
    ]


def test_undo_takes_back_one_run_at_a_time(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("a.jpg")
    run_plan(make_plan(tmp_path, default_rules()))
    make_file("b.pdf")
    run_plan(make_plan(tmp_path, default_rules()))

    undo_last(tmp_path)
    assert sorted(tree(tmp_path)) == ["Images/2025/a.jpg", "b.pdf"]
    undo_last(tmp_path)
    assert sorted(tree(tmp_path)) == ["a.jpg", "b.pdf"]
    assert last_run(tmp_path) is None
    with pytest.raises(JournalError, match="no run to undo"):
        undo_last(tmp_path)


def test_interrupted_run_can_be_undone(tmp_path: Path, make_file: MakeFile) -> None:
    populate(make_file)
    before = tree(tmp_path)
    calls = 0

    def crash_after_second_move(source: str, destination: str) -> None:
        nonlocal calls
        calls += 1
        shutil.move(source, destination)
        if calls == 2:
            # The file has moved but the confirmation is never written, as if the
            # process were killed at this moment.
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_plan(make_plan(tmp_path, default_rules()), move=crash_after_second_move)

    assert undo_last(tmp_path).restored == 2
    assert tree(tmp_path) == before


def test_undo_does_not_replace_a_file_that_took_the_old_name(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("report.pdf", size=5)
    run_plan(make_plan(tmp_path, default_rules()))
    newer = make_file("report.pdf", size=99)

    undone = undo_last(tmp_path)
    assert [p.name for p in undone.renamed] == ["report (2).pdf"]
    assert newer.stat().st_size == 99
    assert (tmp_path / "report (2).pdf").stat().st_size == 5


def test_undo_reports_files_deleted_since_the_run(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("a.pdf")
    make_file("b.pdf")
    run_plan(make_plan(tmp_path, default_rules()))
    (tmp_path / "Documents" / "a.pdf").unlink()

    undone = undo_last(tmp_path)
    assert undone.restored == 1
    assert [p.name for p in undone.missing] == ["a.pdf"]


def test_a_failed_move_is_reported_and_the_rest_continue(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("a.pdf")
    make_file("b.pdf")

    def refuse_a(source: str, destination: str) -> None:
        if source.endswith("a.pdf"):
            raise PermissionError("in use by another program")
        shutil.move(source, destination)

    result = run_plan(make_plan(tmp_path, default_rules()), move=refuse_a)
    assert result.moved == 1
    assert [(p.name, error) for p, error in result.failed] == [("a.pdf", "in use by another program")]
    assert sorted(tree(tmp_path)) == ["Documents/b.pdf", "a.pdf"]


def test_a_cut_off_journal_line_is_ignored(tmp_path: Path, make_file: MakeFile) -> None:
    make_file("a.pdf")
    run_plan(make_plan(tmp_path, default_rules()))
    with journal_path(tmp_path).open("a", encoding="utf-8") as journal:
        journal.write('{"type": "intent", "run": "x", "fr')
    assert undo_last(tmp_path).restored == 1
