"""Rules decide where each file goes. The first rule that matches a file wins."""

from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath


class RuleError(ValueError):
    """A rules file is invalid."""


_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)?\s*$", re.IGNORECASE)
_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
PLACEHOLDERS = {"year", "month", "ext"}


def parse_size(text: str) -> int:
    """Parses sizes such as "500", "10KB" or "1.5 GB" into bytes (units are powers of 1024)."""
    match = _SIZE.match(text)
    if not match:
        raise RuleError(f"invalid size {text!r}; use a number with B, KB, MB or GB, like 10MB")
    number, unit = match.groups()
    return int(float(number) * _UNITS[(unit or "B").upper()])


@dataclass(frozen=True)
class FileInfo:
    path: Path
    size: int
    modified: datetime

    @property
    def extension(self) -> str:
        return self.path.suffix.lower().lstrip(".")


@dataclass(frozen=True)
class Rule:
    name: str
    destination: str
    extensions: frozenset[str] = field(default_factory=frozenset)
    patterns: tuple[str, ...] = ()
    min_size: int | None = None
    max_size: int | None = None
    older_than_days: int | None = None

    def matches(self, info: FileInfo, now: datetime) -> bool:
        if self.extensions and info.extension not in self.extensions:
            return False
        name = info.path.name.lower()
        if self.patterns and not any(fnmatch.fnmatchcase(name, p.lower()) for p in self.patterns):
            return False
        if self.min_size is not None and info.size < self.min_size:
            return False
        if self.max_size is not None and info.size > self.max_size:
            return False
        return not (self.older_than_days is not None and (now - info.modified).days < self.older_than_days)

    def target_folder(self, info: FileInfo) -> Path:
        values = {
            "year": f"{info.modified.year:04d}",
            "month": f"{info.modified.month:02d}",
            "ext": info.extension or "no-extension",
        }
        return Path(_PLACEHOLDER.sub(lambda m: values[m.group(1)], self.destination))


def _check_destination(name: str, destination: str) -> None:
    unknown = set(_PLACEHOLDER.findall(destination)) - PLACEHOLDERS
    if unknown:
        raise RuleError(f"rule {name!r}: unknown placeholder {{{sorted(unknown)[0]}}} in destination")
    # Destinations stay inside the folder being organized. They are checked by both Windows
    # and Unix rules, so a rules file means the same everywhere: "/etc" has no drive letter
    # but on Windows still points at the root of the current drive.
    escapes = any(
        p.anchor or ".." in p.parts for p in (PurePosixPath(destination), PureWindowsPath(destination))
    )
    if escapes or not destination.strip():
        raise RuleError(f"rule {name!r}: destination must be a folder inside the organized folder")


def rule_from_dict(data: dict[str, object], index: int) -> Rule:
    name = str(data.get("name") or f"rule {index + 1}")
    destination = data.get("destination")
    if not isinstance(destination, str):
        raise RuleError(f"rule {name!r}: missing destination")
    _check_destination(name, destination)

    def strings(key: str) -> list[str]:
        value = data.get(key, [])
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise RuleError(f"rule {name!r}: {key} must be a list of strings")
        return value

    def size(key: str) -> int | None:
        value = data.get(key)
        if value is None:
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            return parse_size(value)
        raise RuleError(f"rule {name!r}: {key} must be a size like 10MB")

    older = data.get("older_than_days")
    if older is not None and (not isinstance(older, int) or isinstance(older, bool) or older < 0):
        raise RuleError(f"rule {name!r}: older_than_days must be a whole number of days")

    allowed = {"name", "destination", "extensions", "patterns", "min_size", "max_size", "older_than_days"}
    unknown_keys = set(data) - allowed
    if unknown_keys:
        raise RuleError(f"rule {name!r}: unknown setting {sorted(unknown_keys)[0]!r}")

    extensions = frozenset(e.lower().lstrip(".") for e in strings("extensions"))
    patterns = tuple(strings("patterns"))
    if not extensions and not patterns and data.get("min_size") is None and older is None:
        raise RuleError(
            f"rule {name!r}: add extensions, patterns, min_size or older_than_days to say what it matches"
        )
    return Rule(name, destination, extensions, patterns, size("min_size"), size("max_size"), older)


def load_rules(path: Path) -> list[Rule]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise RuleError(f"{path}: {error}") from error
    entries = data.get("rule")
    if not isinstance(entries, list) or not entries:
        raise RuleError(f"{path}: no [[rule]] entries")
    return [rule_from_dict(entry, i) for i, entry in enumerate(entries)]


DEFAULT_RULES_TOML = """\
# Rules are checked in order; the first one that matches a file decides where it goes.
# Files that match no rule stay where they are.
#
# A rule can match on:
#   extensions      = ["jpg", "png"]        file extensions, without the dot
#   patterns        = ["Screenshot*"]       file name patterns (* and ? wildcards)
#   min_size        = "100MB"               at least this big (B, KB, MB, GB)
#   max_size        = "1MB"                 at most this big
#   older_than_days = 30                    last changed at least this many days ago
# All the conditions in a rule must match.
#
# destination is a folder inside the organized folder. It can use {year} and {month}
# (when the file was last changed) and {ext} (its extension).

[[rule]]
name = "Screenshots"
patterns = ["screenshot*", "screen shot*", "captura*"]
extensions = ["png", "jpg", "jpeg"]
destination = "Images/Screenshots"

[[rule]]
name = "Images"
extensions = ["jpg", "jpeg", "png", "gif", "webp", "heic", "bmp", "tiff", "svg"]
destination = "Images/{year}"

[[rule]]
name = "Videos"
extensions = ["mp4", "mov", "mkv", "avi", "webm", "m4v"]
destination = "Videos/{year}"

[[rule]]
name = "Audio"
extensions = ["mp3", "wav", "flac", "m4a", "ogg", "aac"]
destination = "Audio"

[[rule]]
name = "Documents"
extensions = ["pdf", "doc", "docx", "odt", "rtf", "txt", "md", "epub"]
destination = "Documents"

[[rule]]
name = "Spreadsheets"
extensions = ["xls", "xlsx", "ods", "csv"]
destination = "Documents/Spreadsheets"

[[rule]]
name = "Presentations"
extensions = ["ppt", "pptx", "odp", "key"]
destination = "Documents/Presentations"

[[rule]]
name = "Archives"
extensions = ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"]
destination = "Archives"

[[rule]]
name = "Installers"
extensions = ["exe", "msi", "dmg", "pkg", "deb", "rpm", "apk", "appimage"]
destination = "Installers"

[[rule]]
name = "Code"
extensions = ["py", "js", "ts", "html", "css", "json", "sh", "c", "cpp", "java", "go", "rs", "sql"]
destination = "Code"
"""


def default_rules() -> list[Rule]:
    data = tomllib.loads(DEFAULT_RULES_TOML)
    return [rule_from_dict(entry, i) for i, entry in enumerate(data["rule"])]
