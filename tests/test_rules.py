from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from file_organizer.rules import FileInfo, RuleError, default_rules, load_rules, parse_size, rule_from_dict

NOW = datetime(2026, 1, 31)


def info(name: str, size: int = 100, modified: datetime = datetime(2025, 3, 9)) -> FileInfo:
    return FileInfo(Path("/x") / name, size, modified)


@pytest.mark.parametrize(
    ("text", "size"),
    [("500", 500), ("10KB", 10240), ("1.5 MB", 1572864), ("2gb", 2147483648), (" 7 B ", 7)],
)
def test_parse_size(text: str, size: int) -> None:
    assert parse_size(text) == size


@pytest.mark.parametrize("text", ["", "ten", "-5MB", "5TB", "MB"])
def test_parse_size_rejects(text: str) -> None:
    with pytest.raises(RuleError, match="invalid size"):
        parse_size(text)


def test_all_conditions_must_match() -> None:
    rule = rule_from_dict(
        {
            "name": "Big old videos",
            "extensions": ["MP4", ".mov"],
            "patterns": ["holiday*"],
            "min_size": "1KB",
            "older_than_days": 30,
            "destination": "Videos/old",
        },
        0,
    )
    assert rule.matches(info("Holiday-2025.mp4", size=2048), NOW)
    assert rule.matches(info("holiday.MOV", size=2048), NOW)
    assert not rule.matches(info("holiday.mkv", size=2048), NOW)  # extension
    assert not rule.matches(info("work.mp4", size=2048), NOW)  # pattern
    assert not rule.matches(info("holiday.mp4", size=10), NOW)  # size
    assert not rule.matches(info("holiday.mp4", size=2048, modified=datetime(2026, 1, 20)), NOW)  # age


def test_destination_placeholders() -> None:
    rule = rule_from_dict({"extensions": ["jpg"], "destination": "Images/{year}/{month}/{ext}"}, 0)
    assert rule.target_folder(info("a.JPG", modified=datetime(2025, 3, 9))) == Path("Images/2025/03/jpg")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"extensions": ["jpg"]}, "missing destination"),
        ({"extensions": ["jpg"], "destination": "/etc"}, "inside the organized folder"),
        ({"extensions": ["jpg"], "destination": "../elsewhere"}, "inside the organized folder"),
        ({"extensions": ["jpg"], "destination": "Images/{day}"}, "unknown placeholder {day}"),
        ({"destination": "Everything"}, "say what it matches"),
        ({"extensions": "jpg", "destination": "x", "colour": "red"}, "unknown setting 'colour'"),
        ({"extensions": [1], "destination": "x"}, "list of strings"),
        ({"older_than_days": -1, "destination": "x"}, "whole number of days"),
    ],
)
def test_invalid_rules_are_explained(data: dict[str, object], message: str) -> None:
    with pytest.raises(RuleError, match=message):
        rule_from_dict(data, 0)


def test_load_rules_file(tmp_path: Path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text(
        '[[rule]]\nname = "Notes"\nextensions = ["txt"]\ndestination = "Notes"\n', encoding="utf-8"
    )
    [rule] = load_rules(path)
    assert rule.name == "Notes"

    path.write_text("not = [valid", encoding="utf-8")
    with pytest.raises(RuleError):
        load_rules(path)
    path.write_text("title = 'no rules'\n", encoding="utf-8")
    with pytest.raises(RuleError, match="no \\[\\[rule\\]\\] entries"):
        load_rules(path)


def test_default_rules_put_screenshots_before_images() -> None:
    rules = default_rules()
    first = next(r for r in rules if r.matches(info("Screenshot 2025-03-09.png"), NOW))
    assert first.name == "Screenshots"
    first = next(r for r in rules if r.matches(info("beach.png"), NOW))
    assert first.name == "Images"
