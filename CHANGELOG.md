# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
