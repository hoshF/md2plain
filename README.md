# md2plain

[![CI](https://github.com/hoshF/md2plain/actions/workflows/ci.yml/badge.svg)](https://github.com/hoshF/md2plain/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/md2plain.svg)](https://pypi.org/project/md2plain/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Convert Markdown letters to plain-text email bodies.
Copy to the macOS or Linux Wayland clipboard, save a UTF-8 file, or write to stdout.

## Install

Python 3.10+.

```sh
uv tool install md2plain
uv tool upgrade md2plain
```

Linux clipboard support requires `wl-clipboard` and a working Wayland session.
On Debian/Ubuntu:

```sh
sudo apt install wl-clipboard
```

File and stdout output need no clipboard backend. X11 and Windows clipboard
backends are not supported.

## Usage

```sh
md2plain letter.md                           # copy
md2plain letter.md --print                   # stdout
md2plain letter.md -o letter.txt             # save
md2plain letter.md -o ~/Documents/letters/   # save as letter.txt
md2plain letter.md -o letter.txt --copy      # save and copy
md2plain letter.md --watch -o letter.txt     # update file on save
cat letter.md | md2plain - --print           # stdin
```

`-o` and `--print` disable default copying. Add `--copy` to copy as well.
`--print -o FILE` prints and saves.

**0.2.0:** replace the old save-and-copy usage with `-o FILE --copy`.

## Options

| Option | Description |
|---|---|
| `-o, --output FILE_OR_DIR` | Save to a file or directory |
| `--print` | Write to stdout |
| `--copy` | Enable copying with other outputs |
| `--no-copy` | Disable copying; mutually exclusive with `--copy` |
| `--watch` | Update after the input stays stable for 0.5 seconds |
| `--width N` | Target display width; default 75, minimum 1 |
| `--soft-breaks` | Join paragraph soft line breaks |
| `--version` | Show version |

## Files

- Input and output use UTF-8; an input BOM is accepted. Paths support `~`.
- Existing output directories produce `INPUT_STEM.txt`. New directories require
  a trailing `/`; otherwise a nonexistent path is a filename.
- Missing parent directories are created after successful conversion.
  `letter.draft.md` becomes `letter.draft.txt`. For stdin, `-o` requires a filename.
- Any suffix is accepted; output remains plain text.
- Saves are atomic and preserve existing permissions. Input/output aliases are
  rejected. A copy failure leaves the saved file intact and reports an error.

## Rendering

- Wrap ordinary text at 75 display columns by default; URLs, email addresses,
  and code may exceed the target.
- Preserve link targets, code whitespace, `~~strikethrough~~`, and exact `-- `
  signature separators. Keep source line breaks unless `--soft-breaks` is set.
- Keep aligned tables that fit; render wider tables as `header: value` records.
  Images become text references to their source.

Use your mail client's plain-text compose mode. The client controls MIME and
sending; display columns are not email transport line limits.

[Example Markdown](examples/email.md) · [Plain-text output](examples/email.txt)

## Watching

Watch mode requires a file. Temporary empty or invalid input keeps the last
successful output. Wayland clipboard contents survive command and watch exit.
Wayland copying times out after five seconds.

Inherited `WAYLAND_SOCKET` connections are supported. Anonymous connections
allow one-shot copying only; watching requires a reconnectable endpoint.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/black --check src tests
```

Real Wayland tests require Sway and `wl-clipboard`. They start a private headless
session and run separately in Ubuntu CI:

```sh
MD2PLAIN_WAYLAND_TEST=1 .venv/bin/python -m unittest discover \
  -s tests -p test_wayland_integration.py -v
```

[MIT](LICENSE) · [Changelog](CHANGELOG.md)
