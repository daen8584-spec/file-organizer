# file-organizer

[![CI](https://github.com/daen8584-spec/file-organizer/actions/workflows/ci.yml/badge.svg)](https://github.com/daen8584-spec/file-organizer/actions/workflows/ci.yml)

A command-line tool that tidies a messy folder, like Downloads, by sorting files into subfolders. It shows you the plan first, never overwrites anything, and can undo a run.

```
$ fileorg plan ~/Downloads
12 files to move in /home/me/Downloads (built-in rules):

  IMG_2041.jpg               ->  Images/2025/IMG_2041.jpg
  IMG_2042.jpg               ->  Images/2026/IMG_2042.jpg
  Invoice-March.PDF          ->  Documents/Invoice-March.PDF
  Screenshot 2026-03-02.png  ->  Images/Screenshots/Screenshot 2026-03-02.png
  budget.xlsx                ->  Documents/Spreadsheets/budget.xlsx
  invoice-march.pdf          ->  Documents/invoice-march (2).pdf
  notes.txt                  ->  Documents/notes.txt
  photos.zip                 ->  Archives/photos.zip
  script.py                  ->  Code/script.py
  setup.exe                  ->  Installers/setup.exe
  slides.pptx                ->  Documents/Presentations/slides.pptx
  song.mp3                   ->  Audio/song.mp3

Documents: 3, Images: 2, Screenshots: 1, Spreadsheets: 1, Archives: 1, Code: 1, Installers: 1, Presentations: 1, Audio: 1
1 file matches no rule and stays where it is.

$ fileorg run ~/Downloads
...
Moved 12 files. Undo with: fileorg undo /home/me/Downloads

$ fileorg undo ~/Downloads
Moved 12 files back.
```

## Install

Requires Python 3.11 or later. No other dependencies.

```bash
pip install git+https://github.com/daen8584-spec/file-organizer
```

## Commands

| Command | What it does |
| --- | --- |
| `fileorg plan [folder]` | Shows what would move. Changes nothing. `--json` for scripts. |
| `fileorg run [folder]` | Moves the files after asking. `--yes` skips the question. |
| `fileorg undo [folder]` | Moves the files of the last run back. Run it again to undo earlier runs. |
| `fileorg rules` | Prints the built-in rules. `--write` saves them as `.fileorg.toml` to edit. |

`plan` and `run` take `--rules FILE` and `--recursive` (include subfolders). Without `--rules`, a `.fileorg.toml` in the folder is used if there is one, and the built-in rules otherwise.

## Rules

Rules are a TOML file. The first rule that matches a file decides where it goes; files that match nothing stay put.

```toml
[[rule]]
name = "Screenshots"
patterns = ["screenshot*", "captura*"]   # file name patterns, * and ? wildcards
extensions = ["png", "jpg"]
destination = "Images/Screenshots"

[[rule]]
name = "Old big videos"
extensions = ["mp4", "mov"]
min_size = "500MB"                       # also max_size; B, KB, MB, GB
older_than_days = 90
destination = "Videos/Archive/{year}"    # {year}, {month}, {ext}
```

All the conditions in a rule must match. Mistakes are explained instead of guessed at: a misspelled setting, an unknown placeholder, or a destination outside the folder (`../elsewhere`) are errors.

## Safety

- **Plan first.** `plan` reads the folder and changes nothing.
- **No overwriting.** If a name is taken, the file becomes `name (2).ext`. Names are compared ignoring case, as macOS and Windows do, so a folder organized on Linux stays valid when synced to those systems.
- **Left alone:** hidden files, symbolic links and, unless `--recursive` is given, subfolders. With `--recursive`, folders the rules sort into are skipped, so organized files aren't organized again.
- **Undo, even after a crash.** Every move is recorded in `.fileorg/journal.jsonl` before it happens and confirmed after. If a run is interrupted, undo finds the files that moved from where they are now. If another file has taken an original name in the meantime, the moved file comes back as `name (2).ext` instead of replacing it.
- **Errors don't stop the run.** A file that can't be moved (for example, open in another program) is reported, and the rest continue.

## Development

```bash
pip install -e ".[dev]"
pytest          # 43 tests
ruff check .
mypy            # strict
```

CI runs the tests on Linux, macOS and Windows with Python 3.11 and 3.13, then runs the installed `fileorg` command on a real folder.

The tests found two bugs before release: a rule with `destination = "."` crashed the planner, and on Linux a file could be planned next to an existing one whose name differed only in case. Both are fixed and covered by tests.

## License

MIT
