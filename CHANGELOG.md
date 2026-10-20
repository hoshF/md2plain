# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - Unreleased

### Added

- Linux Wayland clipboard support through the system `wl-clipboard` package,
  with UTF-8 plain-text output, actionable connection errors, and a five-second
  timeout. Clipboard contents remain available for repeated pastes after the
  command or watch mode exits.
- `--copy` to explicitly request clipboard output alongside a file or stdout;
  `--copy` and `--no-copy` are mutually exclusive.
- Standard `~` expansion for input and output paths, including quoted paths,
  and automatic creation of missing output directories after valid conversion.
- Regression coverage for output combinations, paths, and Wayland clipboard
  failures, plus a separate private headless Sway integration test job.

### Changed

- `-o FILE` now saves only to the file by default. Users upgrading from 0.1.x
  who want both outputs must use `-o FILE --copy`. This applies to watch mode
  too. `--print -o FILE` prints and saves without copying unless `--copy` is set.
- Document macOS and Linux Wayland requirements, clipboard-free file/stdout
  usage, and that arbitrary output suffixes still contain UTF-8 plain text.
- Prepare package version 0.2.0; no new Python dependencies are required.

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
