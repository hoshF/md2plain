"""Plain-text clipboard adapters for macOS and Linux Wayland."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile

PLAIN_TEXT_MIME = "text/plain;charset=utf-8"
COPY_TIMEOUT_SECONDS = 5
# A daemon keeps the inherited Wayland stream after the first publication.
# A later independent client must connect afresh, never share that stream.
_USED_WAYLAND_SOCKETS: set[tuple[int, int]] = set()
_WAYLAND_HINT = (
    "Install wl-clipboard and use a working Wayland session, "
    "or use --print / -o FILE without --copy."
)


class ClipboardError(RuntimeError):
    """The selected clipboard backend could not accept the text."""


def copy_text(text: str) -> None:
    """Copy plain text using the current platform's supported backend."""
    if sys.platform == "darwin":
        _copy_macos(text)
    elif sys.platform.startswith("linux"):
        _copy_wayland(text)
    else:
        raise ClipboardError(
            f"Clipboard copying is unsupported on {sys.platform}; "
            "use --print or -o FILE without --copy."
        )


def _copy_macos(text: str) -> None:
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
    except ImportError as exc:
        raise ClipboardError(
            "The macOS clipboard needs pyobjc-framework-Cocoa; "
            "reinstall md2plain, or use --print / -o FILE without --copy."
        ) from exc

    try:
        name = os.environ.get("MD2PLAIN_PASTEBOARD", "general")
        board = (
            NSPasteboard.generalPasteboard()
            if name == "general"
            else NSPasteboard.pasteboardWithName_(name)
        )
        if board is None:
            raise ClipboardError("Cannot access the clipboard.")
        board.clearContents()
        board.declareTypes_owner_([NSPasteboardTypeString], None)
        if not board.setString_forType_(text, NSPasteboardTypeString):
            raise ClipboardError("The clipboard did not accept the plain text.")
    except ClipboardError:
        raise
    except Exception as exc:
        raise ClipboardError(f"Cannot copy to the macOS clipboard: {exc}") from exc


def _wayland_socket() -> tuple[dict[str, str] | None, int | None]:
    """Forward an inherited connection once; reconnect for later publications."""
    value = os.environ.get("WAYLAND_SOCKET")
    if value is None:
        return None, None
    try:
        if not value.isascii() or not value.isdigit():
            raise ValueError("expected an open socket descriptor")
        original = int(value)
        info = os.fstat(original)
        if not stat.S_ISSOCK(info.st_mode):
            raise ValueError("descriptor is not a socket")
        # This import is POSIX-only; file/stdout output must still import on Windows.
        import fcntl

        descriptor = fcntl.fcntl(original, fcntl.F_DUPFD_CLOEXEC, 3)
        identity = (info.st_dev, info.st_ino)
        if identity in _USED_WAYLAND_SOCKETS:
            with socket.socket(fileno=descriptor) as previous:
                address = previous.getpeername()
                if previous.family != socket.AF_UNIX or not address:
                    raise ValueError(
                        "repeated copying needs a reconnectable Wayland socket; "
                        "use WAYLAND_DISPLAY for watching"
                    )
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(COPY_TIMEOUT_SECONDS)
                connection.connect(address)
                connection.settimeout(None)
                descriptor = fcntl.fcntl(connection.fileno(), fcntl.F_DUPFD_CLOEXEC, 3)
        _USED_WAYLAND_SOCKETS.add(identity)
    except (OSError, ValueError, OverflowError) as exc:
        raise ClipboardError(f"Invalid WAYLAND_SOCKET: {exc}. {_WAYLAND_HINT}") from exc
    environment = dict(os.environ, WAYLAND_SOCKET=str(descriptor))
    return environment, descriptor


def _stop_process_group(process: subprocess.Popen) -> None:
    """Stop only the clipboard invocation's own session on failure or timeout."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    # Reap the direct child. Successful background owners are deliberately kept
    # alive, and this cleanup is never called for a successful publication.
    process.wait(timeout=1)


def _copy_wayland(text: str) -> None:
    executable = shutil.which("wl-copy")
    if executable is None:
        raise ClipboardError(f"wl-copy was not found. {_WAYLAND_HINT}")
    try:
        data = text.encode("utf-8")
    except UnicodeError as exc:
        raise ClipboardError("Clipboard text must be valid UTF-8.") from exc
    environment, descriptor = _wayland_socket()
    try:
        # wl-copy's background owner retains stderr. A PIPE here could make
        # communicate() wait for its EOF until a later clipboard replacement.
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                [executable, "--type", PLAIN_TEXT_MIME],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                env=environment,
                pass_fds=() if descriptor is None else (descriptor,),
                start_new_session=True,
            )
            try:
                process.communicate(input=data, timeout=COPY_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                _stop_process_group(process)
                raise ClipboardError(
                    f"Wayland clipboard timed out after {COPY_TIMEOUT_SECONDS} seconds. "
                    f"{_WAYLAND_HINT}"
                ) from exc
            except BaseException:
                _stop_process_group(process)
                raise
            if process.returncode:
                _stop_process_group(process)
                errors.seek(0)
                detail = errors.read(4096).decode("utf-8", errors="replace").strip()
                reason = detail or f"wl-copy exited with status {process.returncode}"
                raise ClipboardError(
                    f"Cannot copy to the Wayland clipboard: {reason}. {_WAYLAND_HINT}"
                )
    except ClipboardError:
        raise
    except OSError as exc:
        raise ClipboardError(f"Cannot run wl-copy: {exc}. {_WAYLAND_HINT}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
