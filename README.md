# md2plain

Turn Markdown from Typora into a true plain-text email (`text/plain`) and
put it on the macOS clipboard.

## Usage

```bash
./md2plain note.md
```

Then in Gmail: open the compose window, click the three-dot menu, choose
**Plain text mode**, and press `Cmd+V`.

To verify, send a message to yourself and use **Show original**. The
message should contain only:

```text
Content-Type: text/plain; charset="UTF-8"
```

No `multipart/alternative`, no `text/html`.

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
| Single newline | **kept** (signatures and dates stay on their own lines) |

## Options

```bash
./md2plain note.md --width 72      # line width (default: 75)
./md2plain note.md --watch         # update the clipboard whenever the file is saved
./md2plain note.md --print         # print only, do not touch the clipboard
./md2plain note.md -o out.txt      # also write the plain text to a file
./md2plain note.md --soft-breaks   # treat single newlines as spaces
```

Keep the width at 75: each quote level adds `> `, so a 75-column body
quoted once is 77 columns, still within RFC 5322's recommended 78.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Tests

```bash
.venv/bin/python -m unittest test_md2plain -v
```

59 tests cover the renderer, CLI, clipboard, edge cases and performance.

## Notes

- The clipboard holds `text/plain` only; no HTML is added.
- Gmail's plain-text mode is per message; there is no global default.
- Quotes use `>`, the standard plain-text marker. Gmail may collapse them
  behind a three-dot control; this is display only and the content stays
  intact.
- Plain text has no bold, italics, or clickable links; local images, math,
  and Mermaid diagrams are not converted.
