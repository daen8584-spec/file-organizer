"""Command-line interface: fileorg plan | run | undo | rules."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .journal import JournalError, run_plan, undo_last
from .planner import Plan, PlanError, make_plan
from .rules import DEFAULT_RULES_TOML, Rule, RuleError, default_rules, load_rules

RULES_FILE = ".fileorg.toml"


def _files(count: int) -> str:
    return f"{count} file" if count == 1 else f"{count} files"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fileorg",
        description="Sort a messy folder into tidy subfolders. "
        "Start with 'fileorg plan', which changes nothing.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "folder", type=Path, nargs="?", default=Path.cwd(), help="folder to organize (default: here)"
        )
        sub.add_argument(
            "--rules", type=Path, help=f"rules file (default: {RULES_FILE} in the folder, else built-in)"
        )
        sub.add_argument("-r", "--recursive", action="store_true", help="include files in subfolders")

    plan = commands.add_parser("plan", help="show what would move, without moving anything")
    add_common(plan)
    plan.add_argument("--json", action="store_true", help="print the plan as JSON")

    run = commands.add_parser("run", help="move the files")
    add_common(run)
    run.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")

    undo = commands.add_parser("undo", help="move the files of the last run back")
    undo.add_argument("folder", type=Path, nargs="?", default=Path.cwd(), help="folder that was organized")

    rules = commands.add_parser("rules", help="print the built-in rules, to start a rules file")
    rules.add_argument(
        "--write", action="store_true", help=f"save them as {RULES_FILE} in the current folder"
    )
    return parser


def _load_rules(folder: Path, rules_path: Path | None) -> tuple[list[Rule], str]:
    if rules_path is not None:
        return load_rules(rules_path), str(rules_path)
    local = folder / RULES_FILE
    if local.exists():
        return load_rules(local), str(local)
    return default_rules(), "built-in rules"


def _show_plan(plan: Plan, source: str) -> None:
    if not plan.moves:
        print(f"Nothing to move in {plan.root} ({source}).")
        return
    print(f"{_files(len(plan.moves))} to move in {plan.root} ({source}):\n")
    width = max(len(m.source.relative_to(plan.root).as_posix()) for m in plan.moves)
    for move in plan.moves:
        source_name = move.source.relative_to(plan.root).as_posix()
        print(f"  {source_name:<{width}}  ->  {move.destination.relative_to(plan.root).as_posix()}")
    counts = Counter(m.rule for m in plan.moves)
    print("\n" + ", ".join(f"{rule}: {n}" for rule, n in counts.most_common()))
    if plan.unmatched:
        if len(plan.unmatched) == 1:
            print("1 file matches no rule and stays where it is.")
        else:
            print(f"{len(plan.unmatched)} files match no rule and stay where they are.")


def _check_folder(folder: Path) -> Path:
    if not folder.is_dir():
        raise SystemExit(f"fileorg: {folder} is not a folder")
    return folder


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "rules":
            if args.write:
                target = Path.cwd() / RULES_FILE
                if target.exists():
                    print(f"fileorg: {target} already exists", file=sys.stderr)
                    return 1
                target.write_text(DEFAULT_RULES_TOML, encoding="utf-8")
                print(f"Wrote {target}. Edit it, then run 'fileorg plan'.")
            else:
                print(DEFAULT_RULES_TOML, end="")
            return 0

        folder = _check_folder(args.folder)

        if args.command == "undo":
            undone = undo_last(folder)
            print(f"Moved {_files(undone.restored)} back.")
            for path in undone.renamed:
                print(f"  Restored as {path.name}, because the original name is taken now.")
            for path in undone.missing:
                print(f"  Not found, so not restored: {path}")
            return 0

        rules, source = _load_rules(folder, args.rules)
        plan = make_plan(folder, rules, recursive=args.recursive)

        if args.command == "plan":
            if args.json:
                print(
                    json.dumps(
                        [
                            {"from": str(m.source), "to": str(m.destination), "rule": m.rule}
                            for m in plan.moves
                        ],
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                _show_plan(plan, source)
            return 0

        _show_plan(plan, source)
        if not plan.moves:
            return 0
        if not args.yes:
            if not sys.stdin.isatty():
                print("\nfileorg: not moving anything without confirmation; add --yes", file=sys.stderr)
                return 1
            if input("\nMove these files? [y/N] ").strip().lower() not in ("y", "yes"):
                print("Nothing moved.")
                return 0
        result = run_plan(plan)
        print(f"\nMoved {_files(result.moved)}. Undo with: fileorg undo {folder}")
        for path, error in result.failed:
            print(f"  Could not move {path.name}: {error}", file=sys.stderr)
        return 1 if result.failed else 0
    except (RuleError, JournalError, PlanError) as error:
        print(f"fileorg: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
