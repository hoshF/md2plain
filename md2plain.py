#!/usr/bin/env python3
"""Convert Markdown to a plain-text email and copy it to the macOS clipboard.

Only text/plain is placed on the clipboard, so pasting into Gmail's
"Plain text mode" produces a real text/plain message.

Usage:
    ./md2plain note.md
    ./md2plain note.md --width 72
    ./md2plain note.md --watch
    ./md2plain note.md --print
    ./md2plain note.md -o out.txt
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from plaintext import render_plain


def positive_width(value: str) -> int:
    width = int(value)
    if width < 1:
        raise argparse.ArgumentTypeError("width must be at least 1")
    return width


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        sys.exit(f"File not found: {path}")
    except OSError as exc:
        sys.exit(f"Cannot read {path}: {exc}")


def copy_text(text: str) -> None:
    """Write plain text only, so Gmail's plain-text mode gets it verbatim."""
    from AppKit import NSPasteboard, NSPasteboardTypeString

    name = os.environ.get("MD2PLAIN_PASTEBOARD", "general")
    board = (
        NSPasteboard.generalPasteboard()
        if name == "general"
        else NSPasteboard.pasteboardWithName_(name)
    )
    board.clearContents()
    board.declareTypes_owner_([NSPasteboardTypeString], None)
    board.setString_forType_(text, NSPasteboardTypeString)


def finish(text: str, args: argparse.Namespace) -> None:
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    if args.show:
        sys.stdout.write(text)
    if args.no_copy:
        return

    try:
        copy_text(text)
    except ImportError:
        sys.exit("pyobjc is not installed; use --print or -o instead")

    print(
        f"Copied {len(text.splitlines())} lines / {len(text)} chars of plain text. "
        "Enable Gmail's Plain text mode, then press Cmd+V.",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Markdown to plain-text email and copy it to the clipboard."
    )
    parser.add_argument("input", help="Markdown file, or - for stdin")
    parser.add_argument("-o", "--output", help="also write the plain text to a file")
    parser.add_argument(
        "--print", dest="show", action="store_true", help="write to stdout"
    )
    parser.add_argument(
        "--no-copy", action="store_true", help="do not touch the clipboard"
    )
    parser.add_argument(
        "--watch", action="store_true", help="update the clipboard on save"
    )
    parser.add_argument(
        "--width", type=positive_width, default=75, help="line width (default: 75)"
    )
    parser.add_argument(
        "--soft-breaks",
        action="store_true",
        help="treat a single newline as a space (default: keep line breaks)",
    )
    args = parser.parse_args()

    if args.watch and args.input == "-":
        parser.error("--watch requires a file, not stdin")

    text = read_input(args.input)
    if not text.strip():
        sys.exit("Input is empty.")

    preserve_breaks = not args.soft_breaks

    def convert(src: str) -> None:
        finish(render_plain(src, args.width, preserve_breaks), args)

    if not args.watch:
        convert(text)
        return 0

    last_mtime: float | None = None
    try:
        while True:
            try:
                mtime = os.stat(args.input).st_mtime
            except FileNotFoundError:
                time.sleep(1)
                continue
            if mtime != last_mtime:
                convert(read_input(args.input))
                last_mtime = mtime
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped watching.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
