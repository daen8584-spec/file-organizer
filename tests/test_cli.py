from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_organizer.cli import main

from .conftest import MakeFile, tree


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_plan_shows_moves_and_changes_nothing(
    tmp_path: Path, make_file: MakeFile, capsys: pytest.CaptureFixture[str]
) -> None:
    make_file("report.pdf")
    make_file("song.mp3")
    make_file("x.unknown")
    code, out, _ = run(capsys, "plan", str(tmp_path))
    assert code == 0
    assert "2 files to move" in out
    assert "report.pdf  ->  Documents/report.pdf" in out
    assert "1 file matches no rule and stays where it is." in out
    assert sorted(tree(tmp_path)) == ["report.pdf", "song.mp3", "x.unknown"]


def test_plan_as_json(tmp_path: Path, make_file: MakeFile, capsys: pytest.CaptureFixture[str]) -> None:
    make_file("song.mp3")
    code, out, _ = run(capsys, "plan", str(tmp_path), "--json")
    assert code == 0
    [entry] = json.loads(out)
    assert entry["rule"] == "Audio"
    assert Path(entry["to"]).parts[-2:] == ("Audio", "song.mp3")


def test_run_needs_confirmation_when_not_interactive(
    tmp_path: Path, make_file: MakeFile, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    make_file("report.pdf")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code, _, err = run(capsys, "run", str(tmp_path))
    assert code == 1
    assert "add --yes" in err
    assert sorted(tree(tmp_path)) == ["report.pdf"]


def test_run_and_undo(tmp_path: Path, make_file: MakeFile, capsys: pytest.CaptureFixture[str]) -> None:
    make_file("report.pdf")
    code, out, _ = run(capsys, "run", str(tmp_path), "--yes")
    assert code == 0
    assert "Moved 1 file." in out
    assert sorted(tree(tmp_path)) == ["Documents/report.pdf"]

    code, out, _ = run(capsys, "undo", str(tmp_path))
    assert code == 0
    assert "Moved 1 file back." in out
    assert sorted(tree(tmp_path)) == ["report.pdf"]

    code, _, err = run(capsys, "undo", str(tmp_path))
    assert code == 1
    assert "no run to undo" in err


def test_rules_file_in_the_folder_is_used(
    tmp_path: Path, make_file: MakeFile, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".fileorg.toml").write_text(
        '[[rule]]\nname = "Big"\nmin_size = "1KB"\ndestination = "Big files"\n', encoding="utf-8"
    )
    make_file("small.pdf", size=10)
    make_file("large.pdf", size=4096)
    code, out, _ = run(capsys, "plan", str(tmp_path))
    assert code == 0
    assert "large.pdf  ->  Big files/large.pdf" in out
    assert "small.pdf" not in out.split("files match no rule")[0].split("\n\n")[1]


def test_invalid_rules_file_is_explained(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rules = tmp_path / "rules.toml"
    rules.write_text('[[rule]]\nextensions = ["txt"]\ndestination = "../out"\n', encoding="utf-8")
    code, _, err = run(capsys, "plan", str(tmp_path), "--rules", str(rules))
    assert code == 1
    assert "destination must be a folder inside the organized folder" in err


def test_rules_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    code, _, _ = run(capsys, "rules", "--write")
    assert code == 0 and (tmp_path / ".fileorg.toml").exists()
    code, _, err = run(capsys, "rules", "--write")
    assert code == 1 and "already exists" in err


def test_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="is not a folder"):
        main(["plan", str(tmp_path / "nope")])
