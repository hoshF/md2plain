# md2plain

[![CI](https://github.com/hoshF/md2plain/actions/workflows/ci.yml/badge.svg)](https://github.com/hoshF/md2plain/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/md2plain.svg)](https://pypi.org/project/md2plain/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Platform: macOS · Linux Wayland](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20Wayland-lightgrey)](pyproject.toml)

**Markdown in, plain-text email out.**

`md2plain` turns a Markdown letter into a plain-text email body, then copies
it to the macOS or Linux Wayland clipboard, or writes it to a file or stdout.
It preserves complete link targets, code whitespace, and email signature
separators while wrapping ordinary text to a target of 75 display columns.

Paste the result into your mail client's plain-text compose mode. The tool
produces the body text; your mail client controls the final MIME format,
encoding, and display.

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

- Write letters in Markdown without carrying rich-text styling into email.
- Keep the destination of every link, including its query and fragment.
- Keep greetings, addresses, and signatures on their own lines by default.
- Produce readable text with a consistent wrapping target. Complete URLs,
  email addresses, inline code, and code blocks may exceed that target to
  preserve their content.

The 75-column setting measures display width, not the character count or
encoded line length of a complete email. It does not guarantee compliance
with [RFC 5322's line-length rules](https://www.rfc-editor.org/rfc/rfc5322#section-2.1.1).

## Requirements

- Python 3.10 or newer.
- For clipboard output: macOS with AppKit, or Linux running a Wayland session
  with the system `wl-clipboard` package installed.

File and stdout output work without a clipboard backend, including on a
headless system. Clipboard output on X11 and Windows is not supported.

On Debian or Ubuntu, install the Wayland clipboard tools with:

```bash
sudo apt install wl-clipboard
```

On other Linux distributions, install `wl-clipboard` with your system package
manager. Run `md2plain` from an environment that can connect to your Wayland
session. If `wl-copy` is missing or the session is unavailable, the command
reports the error; use `-o FILE` or `--print` when you only need the text.
Wayland clipboard operations time out after five seconds if they cannot finish.
An inherited `WAYLAND_SOCKET` is validated and forwarded. Repeated copies
reconnect to the same socket endpoint. Anonymous inherited connections support
one copy only; clipboard watch mode rejects them before publishing. Use a
reconnectable `WAYLAND_DISPLAY` connection or file-only watching in that case.

## Install

With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install md2plain
```

Update an existing uv installation with `uv tool upgrade md2plain`.

Or with [pipx](https://pipx.pypa.io/):

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

In Gmail, enable **Plain text mode** in the compose window before pasting.
Other clients have their own plain-text compose setting. A plain-text
clipboard does not force the client to send a plain-text-only message.

To inspect a message you have sent, view its original source and check its
MIME content types. A plain-text body is identified by a header such as:

```text
Content-Type: text/plain; charset="UTF-8"
```

HTML alternatives, attachments, and other MIME structure depend on the mail
client. Display wrapping and quote collapsing also depend on the client.

Other output combinations:

```bash
# Print without changing the clipboard.
md2plain note.md --print

# Save without changing the clipboard; missing parent directories are created.
md2plain note.md -o ~/Documents/letters/note.txt

# Save and copy to the clipboard.
md2plain note.md -o note.txt --copy

# Explicitly request copying even when printing.
md2plain note.md --print --copy

# Print and save without changing the clipboard.
md2plain note.md --print -o note.txt

# Read Markdown from stdin; a UTF-8 BOM is accepted here too.
cat note.md | md2plain - --print

# Refresh the clipboard after stable file changes.
md2plain note.md --watch

# Refresh only the file; add --copy to update the clipboard too.
md2plain note.md --watch -o ~/Documents/letters/note.txt
```

**Upgrading from 0.1.x:** `-o FILE` now saves only to the file. To keep the
previous save-and-copy behavior, use `-o FILE --copy`.

See [examples/email.md](examples/email.md) and its rendered
[plain-text result](examples/email.txt) for a bilingual letter with links,
quotes, code, and signatures.

## Options

| Option | Description |
|---|---|
| `--width N` | Target display width (default: 75; minimum: 1) |
| `--watch` | Refresh selected outputs after a file change stays stable for 0.5 seconds; requires a file |
| `--print` | Write to stdout; do not copy unless `--copy` is specified |
| `-o, --output FILE` | Save UTF-8 text to this path; do not copy unless `--copy` is specified |
| `--copy` | Explicitly enable clipboard copying, including with `--print` or `-o` |
| `--no-copy` | Explicitly disable clipboard copying; mutually exclusive with `--copy` |
| `--soft-breaks` | Join ordinary paragraph soft newlines with spaces; code and signature separators stay intact |
| `--version` | Print the version and exit |

With no output option, the command copies to the clipboard. With `--print`
or `-o`, it uses only those selected outputs unless `--copy` is also given.
`--print -o FILE` both prints and saves without copying. `--no-copy` remains
available for explicitly disabling copying; use it with `--print` or `-o`.

Input and output paths accept standard `~` home-directory expansion, including
quoted paths such as `-o "~/Documents/My letters/note.txt"`. Absolute and
relative paths, spaces, and non-ASCII names are supported. Missing output
parent directories are created after the input has been read and converted
successfully. Any file suffix is accepted, but the content is always UTF-8
plain text: naming it `.pdf` or `.docx` does not convert it to that format.

Input must be valid UTF-8, with or without a BOM. Invalid encoding is an
error; it is never silently replaced with different characters. Failed
input does not change the output file or clipboard. Output cannot refer to
the input file, including through a symbolic or hard link. Files are saved
using an atomic replacement to avoid leaving a partially written result;
existing file permissions are preserved. If a file is saved but an explicitly
requested clipboard copy fails, the file remains saved. A one-shot command
reports the clipboard failure with a nonzero exit status.

Watch mode waits for a change to remain stable for 0.5 seconds before
converting it. Temporary empty files, unreadable files, and decoding errors
keep the last successful result; watching continues when the file is saved
again or recreated. Clipboard failures are reported as errors. With
`--watch -o FILE`, only the file is updated unless `--copy` is specified.
On Wayland, clipboard text remains available for repeated pastes after the
command finishes, including after exiting watch mode.

## Output format

| Markdown | Output |
|---|---|
| `# Heading` | heading + `====` underline |
| `## Heading` | heading + `----` underline |
| `### Heading` | heading + `~~~~` underline |
| Paragraph | wrapped to a target of 75 display columns |
| `- item` | `* item`, with hanging indent |
| `1. item` | `1. item` |
| `> quote` | `> quote` |
| Code block | indented by four spaces; parser-provided whitespace and line breaks kept; no wrapping |
| Inline code | parser-provided spaces kept; not split across lines |
| `[text](url)` | `text (url)`; full target retained in every context |
| `~~deleted~~` | `~~deleted~~` |
| `![alt](src)` | `[图片：alt] (src)`; empty alt uses `[图片] (src)` |
| Table | naturally aligned columns when they fit; otherwise one `header: value` line per column, with a blank line between records |
| Single newline | kept (signatures and dates stay on their own lines) |
| Exact `-- ` signature separator | kept, including the trailing space and inside blockquotes |

Links keep their full query strings, fragments, and relative paths. The
repeated target is omitted only when identical to the label. URLs and email
addresses move to the next line as a whole when needed; they may exceed the width.
Image references retain their source but do not attach or embed the image.
Tables containing tabs also use field records, preserving the tab characters
without depending on their position in a column.

Lists and blockquotes reserve room for their prefixes before wrapping.
Unicode text wraps at complete grapheme clusters, so a combining accent or
joined emoji is not split. Display width is estimated with `wcwidth` for
monospaced text; actual rendering varies with fonts and mail clients.

## How it works

1. `markdown-it-py` parses CommonMark plus tables, strikethrough, and
   autolinks.
2. The renderer retains protected content through wrapping, handles email
   signature separators before Markdown heading rules, and renders headings,
   lists, quotes, and tables.
3. The CLI strictly decodes UTF-8 (BOM tolerant), saves files atomically, and
   writes plain text to the selected outputs.

## Limitations

- Clipboard copying requires macOS and AppKit, or Linux Wayland with
  `wl-clipboard`; X11 and Windows clipboard backends are not included.
- Bold and italic styling is removed. Link destinations remain text; the
  mail client decides whether to make them clickable.
- Images are references, not attachments. YAML front matter, footnotes,
  math, and Mermaid diagrams do not have dedicated conversion support.
- Tables use spaces, so proportional fonts may break their alignment.
- The tool does not generate `.eml`, set MIME headers, or send mail. Pure
  `text/plain` delivery must be selected and checked in the mail client.
- Clients may reflow text or collapse quoted sections in their display.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/black --check src tests
```

The Wayland integration suite is opt-in and skipped during normal test runs.
On Linux with `sway`, `swaymsg`, and `wl-clipboard` installed, run:

```bash
MD2PLAIN_WAYLAND_TEST=1 .venv/bin/python -m unittest discover -s tests -p test_wayland_integration.py -v
```

These tests start a private headless Sway session with an isolated runtime
directory and do not use your desktop clipboard. A separate Ubuntu CI job
runs them to check UTF-8 fidelity, repeated pastes, and watch-mode persistence.

The `./md2plain` script in the repository root is a development launcher; it
runs the package from `.venv`. Installed users get the `md2plain` command from
`pyproject.toml`.

## Releasing

Releases are published by GitHub Actions through
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/), so no
API token is stored in the repository.

One-time setup on PyPI: open the `md2plain` project, go to
**Settings → Publishing**, and add a trusted publisher with:

| Field | Value |
|---|---|
| Owner | `hoshF` |
| Repository | `md2plain` |
| Workflow | `release.yml` |
| Environment | `pypi` |

To cut a release:

1. Confirm `__version__` in `src/md2plain/__init__.py` is the intended version.
2. Finalize its [CHANGELOG.md](CHANGELOG.md) entry and replace `Unreleased` with
   the release date.
3. Commit, tag, and push:

```bash
git tag v0.2.0
git push origin v0.2.0
```

The `Release` workflow then checks that the tag matches the package version,
runs the tests, builds the sdist and wheel, and publishes them to PyPI.

## License

[MIT](LICENSE). See [CHANGELOG.md](CHANGELOG.md) for release history.
