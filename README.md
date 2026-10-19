# md2plain

[![CI](https://github.com/hoshF/md2plain/actions/workflows/ci.yml/badge.svg)](https://github.com/hoshF/md2plain/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/md2plain.svg)](https://pypi.org/project/md2plain/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey)](pyproject.toml)

**Markdown in, plain-text email out.**

`md2plain` turns a Markdown letter into a plain-text email body, then copies
it to the macOS clipboard or writes it to a file or stdout. It preserves
complete link targets, code whitespace, and email signature separators while
wrapping ordinary text to a target of 75 display columns.

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

- macOS (the clipboard is written through AppKit)
- Python 3.10 or newer

Rendering to stdout or a file with copying disabled also works without the
macOS clipboard backend.

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

# Save and copy to the clipboard.
md2plain note.md -o note.txt

# Save without changing the clipboard.
md2plain note.md -o note.txt --no-copy

# Print and save without changing the clipboard.
md2plain note.md --print -o note.txt

# Read Markdown from stdin; a UTF-8 BOM is accepted here too.
cat note.md | md2plain - --print

# Refresh the selected outputs after stable file changes.
md2plain note.md --watch
```

See [examples/email.md](examples/email.md) and its rendered
[plain-text result](examples/email.txt) for a bilingual letter with links,
quotes, code, and signatures.

## Options

| Option | Description |
|---|---|
| `--width N` | Target display width (default: 75; minimum: 1) |
| `--watch` | Refresh selected outputs after a file change stays stable for 0.5 seconds; requires a file |
| `--print` | Write to stdout and disable clipboard copying |
| `-o, --output FILE` | Also save to a UTF-8 text file; copying remains enabled unless disabled |
| `--no-copy` | Disable clipboard copying; use with `--print` or `-o` |
| `--soft-breaks` | Join ordinary paragraph soft newlines with spaces; code and signature separators stay intact |
| `--version` | Print the version and exit |

Input must be valid UTF-8, with or without a BOM. Invalid encoding is an
error; it is never silently replaced with different characters. Failed
input does not change the output file or clipboard. Output cannot refer to
the input file, including through a symbolic or hard link. Files are saved
using an atomic replacement to avoid leaving a partially written result.

Watch mode waits for a change to remain stable for 0.5 seconds before
converting it. Temporary empty files, unreadable files, and decoding errors
keep the last successful result; watching continues when the file is saved
again or recreated. Clipboard failures are reported as errors.

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

- Clipboard copying requires macOS and AppKit.
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

1. Bump `__version__` in `src/md2plain/__init__.py`.
2. Add an entry to [CHANGELOG.md](CHANGELOG.md).
3. Commit, tag, and push:

```bash
git tag v0.1.2
git push origin v0.1.2
```

The `Release` workflow then checks that the tag matches the package version,
runs the tests, builds the sdist and wheel, and publishes them to PyPI.

## License

[MIT](LICENSE). See [CHANGELOG.md](CHANGELOG.md) for release history.
