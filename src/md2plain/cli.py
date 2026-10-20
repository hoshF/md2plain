#!/usr/bin/env python3
"""Convert Markdown to a plain-text email body for pasting or saving.

The clipboard contains plain text. The mail client still controls the final
message format, so enable its plain-text mode before pasting.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from . import __version__
from .clipboard import ClipboardError, copy_text
from .render import render_plain

WATCH_POLL_SECONDS = 0.1
WATCH_STABLE_SECONDS = 0.5


class CliError(Exception):
    """An actionable input, output, or clipboard failure."""


def positive_width(value: str) -> int:
    width = int(value)
    if width < 1:
        raise argparse.ArgumentTypeError("width must be at least 1")
    return width


def read_input(path: str) -> str:
    """Decode UTF-8 strictly, accepting a BOM for files and standard input."""
    label = "stdin" if path == "-" else path
    try:
        if path == "-":
            stream = getattr(sys.stdin, "buffer", sys.stdin)
            raw = stream.read()
        else:
            raw = Path(path).read_bytes()
    except FileNotFoundError as exc:
        raise CliError(f"File not found: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise CliError(f"Cannot read {label}: {exc}") from exc

    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CliError(
                f"Cannot decode {label}: invalid UTF-8 at byte {exc.start + 1} "
                f"({exc.reason})."
            ) from exc
    else:
        # StringIO and other already decoded streams have no binary buffer.
        text = raw
    text = text.removeprefix("\ufeff")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def validate_output(input_path: str, output_path: str | None) -> None:
    """Protect the source even when either path is a link or changes in watch."""
    if input_path == "-" or not output_path:
        return
    source, target = Path(input_path), Path(output_path)
    try:
        same = source.resolve() == target.resolve()
        if not same:
            try:
                same = source.samefile(target)
            except FileNotFoundError:
                pass
    except (OSError, RuntimeError) as exc:
        raise CliError(f"Cannot check output path {output_path}: {exc}") from exc
    if same:
        raise CliError("Input and output must be different files.")


def save_output(text: str, args: argparse.Namespace) -> None:
    """Replace a completed temporary file, leaving previous output on failure."""
    validate_output(args.input, args.output)
    target = Path(args.output)
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            mode = stat.S_IMODE(target.stat().st_mode)
        except FileNotFoundError:
            mode = None
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=".md2plain-",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            temporary.chmod(mode)
        validate_output(args.input, args.output)
        os.replace(temporary, target)
    except OSError as exc:
        raise CliError(f"Cannot write {args.output}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                # Keep the actionable save error if cleanup also fails.
                pass


def finish(text: str, args: argparse.Namespace) -> None:
    if args.output:
        save_output(text, args)
    if args.show:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except (OSError, UnicodeError) as exc:
            raise CliError(f"Cannot write stdout: {exc}") from exc

    should_copy = args.copy
    if should_copy is None:
        should_copy = not (args.output or args.show)
    if not should_copy:
        return

    try:
        copy_text(text)
    except ClipboardError as exc:
        message = str(exc)
        if args.output:
            message = f"Saved {args.output}, but clipboard copy failed: {message}"
        raise CliError(message) from exc
    except Exception as exc:
        message = f"Cannot copy to the clipboard: {exc}"
        if args.output:
            message = f"Saved {args.output}, but clipboard copy failed: {exc}"
        raise CliError(message) from exc

    print(
        f"Copied {len(text.splitlines())} lines / {len(text)} chars of plain text. "
        "Enable your mail client's plain-text mode, then paste.",
        file=sys.stderr,
    )


def file_revision(path: str) -> tuple[int, int, int, int, int]:
    try:
        info = Path(path).stat()
    except FileNotFoundError as exc:
        raise CliError(f"File not found: {path}") from exc
    except OSError as exc:
        raise CliError(f"Cannot read {path}: {exc}") from exc
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def watch_input(args: argparse.Namespace, convert: Callable[[str], None]) -> None:
    """Publish only stable nonempty input, retrying failures without losing output."""
    pending: tuple[str, tuple[int, int, int, int, int]] | None = None
    stable_since = 0.0
    last_success: str | None = None
    last_error: str | None = None
    while True:
        try:
            validate_output(args.input, args.output)
            before = file_revision(args.input)
            source = read_input(args.input)
            after = file_revision(args.input)
            if before != after:
                pending = None
            elif not source.strip():
                raise CliError("Input is empty; waiting for a nonempty save.")
            else:
                now = time.monotonic()
                observed = (source, after)
                if observed != pending:
                    pending = observed
                    stable_since = now
                elif now - stable_since >= WATCH_STABLE_SECONDS:
                    if source != last_success:
                        convert(source)
                        last_success = source
                    last_error = None
        except CliError as exc:
            pending = None
            message = str(exc)
            if message != last_error:
                print(
                    f"{message} Watching for valid input and retrying failed outputs.",
                    file=sys.stderr,
                )
                last_error = message
        time.sleep(WATCH_POLL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="md2plain",
        description="Convert Markdown to plain-text email and copy it to the clipboard.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("input", help="Markdown file, or - for stdin")
    parser.add_argument(
        "-o", "--output", help="save UTF-8 plain text to a file (without copying)"
    )
    parser.add_argument(
        "--print",
        dest="show",
        action="store_true",
        help="write to stdout (without copying unless --copy is set)",
    )
    clipboard = parser.add_mutually_exclusive_group()
    clipboard.add_argument(
        "--copy",
        dest="copy",
        action="store_const",
        const=True,
        default=None,
        help="copy to the clipboard, including with --output or --print",
    )
    clipboard.add_argument(
        "--no-copy",
        dest="copy",
        action="store_const",
        const=False,
        help="do not touch the clipboard",
    )
    parser.add_argument(
        "--watch", action="store_true", help="update after a stable save"
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

    def convert(source: str) -> None:
        finish(render_plain(source, args.width, not args.soft_breaks), args)

    try:
        try:
            if args.input != "-":
                args.input = str(Path(args.input).expanduser())
            if args.output:
                args.output = str(Path(args.output).expanduser())
        except (OSError, RuntimeError) as exc:
            raise CliError(f"Cannot expand file path: {exc}") from exc
        validate_output(args.input, args.output)
        if args.watch:
            try:
                watch_input(args, convert)
            except KeyboardInterrupt:
                print("\nStopped watching.", file=sys.stderr)
        else:
            source = read_input(args.input)
            if not source.strip():
                raise CliError("Input is empty.")
            convert(source)
    except CliError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
