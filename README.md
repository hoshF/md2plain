# md2plain

[![CI](https://github.com/hoshF/md2plain/actions/workflows/ci.yml/badge.svg)](https://github.com/hoshF/md2plain/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/md2plain.svg)](https://pypi.org/project/md2plain/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey)](pyproject.toml)

**Markdown in, plain-text email out.**

`md2plain` renders Markdown as a plain-text email and copies it to the macOS
clipboard as `text/plain`. Paste it into Gmail's **Plain text mode** and the
message is sent as a real `text/plain` message: hard-wrapped, with no HTML,
no fonts, and no client-side reflow.

## Demo

Input:

```markdown
# Quarterly Update

This is a **short** note with a [link](https://example.com).

* one
* two

> quoted
```

Output:

```text
Quarterly Update
================

This is a short note with a link (https://example.com).

* one
* two

> quoted
```

## Why

- Gmail's normal compose always sends HTML, even when you paste plain text.
- Rich text copied from Typora carries its own CSS, which mail clients mangle.
- Plain text has no automatic reflow, so the sender has to control line width.
- A 75-column limit leaves room for `> ` quote prefixes and stays within
  RFC 5322's recommended 78 characters.

## Requirements

- macOS (the clipboard is written through AppKit)
- Python 3.10 or newer

## Install

With [pipx](https://pipx.pypa.io/):

```bash
pipx install md2plain
```

Or with pip:

```bash
pip install md2plain
```

For development, install from a checkout:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```bash
md2plain note.md
```

Then in Gmail: open the compose window, click the three-dot menu, choose
**Plain text mode**, and press `Cmd+V`.

To verify, send a message to yourself and use **Show original**. The message
should contain only:

```text
Content-Type: text/plain; charset="UTF-8"
```

No `multipart/alternative`, no `text/html`.

## Options

| Option | Description |
|---|---|
| `--width N` | Line width in columns (default: 75) |
| `--watch` | Update the clipboard whenever the file is saved |
| `--print` | Write to stdout instead of the clipboard |
| `-o, --output FILE` | Also write the plain text to a file |
| `--soft-breaks` | Treat single newlines as spaces |
| `--version` | Print the version and exit |

## Output format

| Markdown | Output |
|---|---|
| `# Heading` | heading + `====` underline |
| `## Heading` | heading + `----` underline |
| `### Heading` | heading + `~~~~` underline |
| Paragraph | hard-wrapped at 75 columns (CJK counts as two) |
| `- item` | `* item`, with hanging indent |
| `1. item` | `1. item` |
| `> quote` | `> quote` |
| Code block | indented by four spaces |
| `[text](url)` | `text (url)` |
| Table | column-aligned plain text |
| Single newline | kept (signatures and dates stay on their own lines) |

## How it works

1. `markdown-it-py` parses CommonMark plus tables, strikethrough, and
   autolinks.
2. `src/md2plain/render.py` wraps text by display width (CJK counts as two
   columns), renders headings, lists, quotes, and tables.
3. `src/md2plain/cli.py` reads UTF-8 (BOM tolerant) and writes exactly one
   clipboard type: `text/plain`.

## Limitations

- macOS only; the clipboard backend is AppKit.
- Plain text has no bold, italics, or clickable links. Link URLs are kept as
  text, and links inside headings or table cells lose the URL.
- Images become alt text. YAML front matter, footnotes, math, and Mermaid
  diagrams are not converted.
- Tables are aligned with spaces, so proportional fonts break the alignment.
- Gmail may collapse `>` quote blocks behind a three-dot control; this is
  display only and the content stays intact.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/black --check src tests
```

The `./md2plain` script in the repository root is a development launcher; it
runs the package from `.venv`. Installed users get the `md2plain` command from
`pyproject.toml`.

## License

[MIT](LICENSE). See [CHANGELOG.md](CHANGELOG.md) for release history.
