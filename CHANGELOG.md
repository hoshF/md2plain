# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-20

### Added

- Linux Wayland clipboard via `wl-clipboard`, with a five-second timeout and
  background ownership for repeated pastes after command or watch exit.
- `--copy` to enable clipboard output explicitly; conflicts with `--no-copy`.
- `~` expansion and automatic creation of output directories.
- Directory output derives `name.txt` from the input filename. New directories
  require a trailing `/`; stdin requires an explicit output filename.
- Isolated headless Sway integration tests in a separate Ubuntu CI job.

### Changed

- `-o` now saves without copying, including in watch mode. Use `-o PATH --copy`
  to retain 0.1.x behavior; `--print` also accepts `--copy`.
- Source archives include only project sources, tests, examples, and
  documentation; local drafts and conversion results are excluded.

## [0.1.1] - 2026-10-19

### Changed

- Preserve full link targets, including queries, fragments, relative paths,
  and links in headings and tables. Keep image sources as text references
  and retain strikethrough markers.
- Wrap ordinary text by Unicode grapheme and display width without splitting
  URLs, email addresses, or inline code. Code blocks retain parser-provided
  whitespace and line breaks and may exceed the requested width.
- Preserve exact email signature separators (`-- `), including in quoted
  text, without treating them as Markdown heading underlines. Keep multiline
  signatures separate even with `--soft-breaks`.
- Keep aligned tables at their natural widths when they fit; render wider
  tables as ordered `header: value` records instead of truncating columns.
- Make `--print` disable clipboard copying, including when combined with
  `-o`. Document `--no-copy` and all output combinations.
- Require valid UTF-8 for both files and stdin, accepting an optional BOM.
  Reject input/output aliases and save output files atomically.
- Debounce watch changes for 0.5 seconds, retain the last successful result
  through temporary input errors or empty files, and report clipboard
  failures.
- Clarify that output is an email body with a display-width target; MIME
  format, transport compliance, and final display depend on the mail client.

### Added

- Regression tests for content preservation, Unicode wrapping, CLI output
  behavior, encoding errors, safe file output, and watch recovery.
- A bilingual example letter and its plain-text rendering.

## [0.1.0] - 2026-10-18

### Added

- Markdown to plain-text email rendering: `=` / `-` / `~` headings, `*` lists,
  `>` quotes, four-space code blocks, and 75-column hard wrapping with CJK
  width support.
- Clipboard output as `text/plain` only, for Gmail's Plain text mode.
- CLI options: `--width`, `--watch`, `--print`, `-o/--output`,
  `--soft-breaks`, and `--version`.
- Test suite covering the renderer, CLI, clipboard, edge cases, fuzzing, and
  performance.
