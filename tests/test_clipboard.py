"""Clipboard backend tests; no test touches the user's desktop clipboard."""

from __future__ import annotations

import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from md2plain import clipboard


class MacClipboard(unittest.TestCase):
    def setUp(self):
        self.board = Mock()
        self.board.setString_forType_.return_value = True
        self.pasteboards = Mock()
        self.pasteboards.generalPasteboard.return_value = self.board
        self.pasteboards.pasteboardWithName_.return_value = self.board
        module = types.SimpleNamespace(
            NSPasteboard=self.pasteboards,
            NSPasteboardTypeString="public.utf8-plain-text",
        )
        for mocker in (
            patch.object(clipboard.sys, "platform", "darwin"),
            patch.dict(sys.modules, {"AppKit": module}),
            patch.dict(os.environ, {"MD2PLAIN_PASTEBOARD": "md2plain-unit-test"}),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)

    def test_named_board_contains_one_plain_text_type(self):
        clipboard.copy_text("正文\n-- \nAlice\n")
        self.pasteboards.pasteboardWithName_.assert_called_once_with(
            "md2plain-unit-test"
        )
        self.pasteboards.generalPasteboard.assert_not_called()
        self.board.declareTypes_owner_.assert_called_once_with(
            ["public.utf8-plain-text"], None
        )
        self.board.setString_forType_.assert_called_once_with(
            "正文\n-- \nAlice\n", "public.utf8-plain-text"
        )

    def test_general_board_selection_is_only_mocked(self):
        with patch.dict(os.environ, {"MD2PLAIN_PASTEBOARD": "general"}):
            clipboard.copy_text("hello")
        self.pasteboards.generalPasteboard.assert_called_once()

    def test_missing_board_is_reported(self):
        self.pasteboards.pasteboardWithName_.return_value = None
        with self.assertRaisesRegex(clipboard.ClipboardError, "access the clipboard"):
            clipboard.copy_text("hello")

    def test_rejected_text_is_reported(self):
        self.board.setString_forType_.return_value = False
        with self.assertRaisesRegex(clipboard.ClipboardError, "did not accept"):
            clipboard.copy_text("hello")

    def test_appkit_exception_is_actionable(self):
        self.board.clearContents.side_effect = RuntimeError("pasteboard unavailable")
        with self.assertRaisesRegex(clipboard.ClipboardError, "pasteboard unavailable"):
            clipboard.copy_text("hello")

    def test_missing_appkit_has_file_only_hint(self):
        with (
            patch.dict(sys.modules, {"AppKit": None}),
            self.assertRaisesRegex(clipboard.ClipboardError, "pyobjc.*-o FILE"),
        ):
            clipboard.copy_text("hello")


class WaylandClipboard(unittest.TestCase):
    def setUp(self):
        self.process = Mock(pid=99999999, returncode=0)
        self.process.communicate.return_value = (None, None)
        self.process.wait.return_value = 0
        for mocker in (
            patch.object(clipboard.sys, "platform", "linux"),
            patch.dict(os.environ),
            patch.object(clipboard.shutil, "which", return_value="/mock/wl-copy"),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)
        os.environ.pop("WAYLAND_SOCKET", None)
        mocker = patch.object(clipboard, "_USED_WAYLAND_SOCKETS", set())
        mocker.start()
        self.addCleanup(mocker.stop)
        self.popen = patch.object(
            clipboard.subprocess, "Popen", return_value=self.process
        )
        self.spawn = self.popen.start()
        self.addCleanup(self.popen.stop)

    def test_utf8_plain_text_without_shell_or_inherited_pipes(self):
        body = "中文 👨‍👩‍👧‍👦\n    a\tb  \n-- \nAlice\n"
        clipboard.copy_text(body)
        positional, kwargs = self.spawn.call_args
        self.assertEqual(
            positional[0], ["/mock/wl-copy", "--type", "text/plain;charset=utf-8"]
        )
        self.assertFalse(kwargs.get("shell", False))
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertNotEqual(kwargs["stderr"], subprocess.PIPE)
        self.assertTrue(hasattr(kwargs["stderr"], "fileno"))
        self.process.communicate.assert_called_once_with(
            input=body.encode("utf-8"), timeout=5
        )
        self.process.wait.assert_not_called()

    def test_session_type_does_not_prevent_a_real_connection_attempt(self):
        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}):
            clipboard.copy_text("hello")
        self.spawn.assert_called_once()

    def test_missing_tool_has_install_and_output_hints(self):
        with (
            patch.object(clipboard.shutil, "which", return_value=None),
            self.assertRaisesRegex(
                clipboard.ClipboardError, "wl-clipboard.*--print.*-o FILE"
            ),
        ):
            clipboard.copy_text("hello")
        self.spawn.assert_not_called()

    def test_launch_error_is_reported(self):
        self.spawn.side_effect = PermissionError("execution denied")
        with self.assertRaisesRegex(clipboard.ClipboardError, "execution denied"):
            clipboard.copy_text("hello")

    def test_nonzero_status_includes_stderr(self):
        self.process.returncode = 2

        def launch(*_args, **kwargs):
            kwargs["stderr"].write(b"Failed to connect to a Wayland server")
            return self.process

        self.spawn.side_effect = launch
        with (
            patch.object(clipboard.os, "killpg") as stop,
            self.assertRaisesRegex(
                clipboard.ClipboardError, "Failed to connect.*wl-clipboard"
            ),
        ):
            clipboard.copy_text("hello")
        stop.assert_called_once_with(self.process.pid, signal.SIGKILL)

    def test_timeout_terminates_only_the_invocation_process_group(self):
        self.process.communicate.side_effect = subprocess.TimeoutExpired("wl-copy", 5)
        with (
            patch.object(clipboard.os, "killpg") as stop,
            self.assertRaisesRegex(
                clipboard.ClipboardError, "timed out after 5 seconds"
            ),
        ):
            clipboard.copy_text("hello")
        stop.assert_called_once_with(self.process.pid, signal.SIGKILL)
        self.process.wait.assert_called_once_with(timeout=1)

    def test_interrupt_cleans_up_the_pending_invocation(self):
        self.process.communicate.side_effect = KeyboardInterrupt
        with (
            patch.object(clipboard.os, "killpg") as stop,
            self.assertRaises(KeyboardInterrupt),
        ):
            clipboard.copy_text("hello")
        stop.assert_called_once_with(self.process.pid, signal.SIGKILL)

    def test_inherited_socket_is_duplicated_forwarded_and_closed(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        forwarded = []

        def launch(*_args, **kwargs):
            duplicate = int(kwargs["env"]["WAYLAND_SOCKET"])
            self.assertNotEqual(duplicate, left.fileno())
            self.assertEqual(kwargs["pass_fds"], (duplicate,))
            self.assertTrue(stat.S_ISSOCK(os.fstat(duplicate).st_mode))
            forwarded.append(duplicate)
            return self.process

        self.spawn.side_effect = launch
        with patch.dict(os.environ, {"WAYLAND_SOCKET": str(left.fileno())}):
            clipboard.copy_text("hello")
            self.assertEqual(os.environ["WAYLAND_SOCKET"], str(left.fileno()))
        self.assertTrue(stat.S_ISSOCK(os.fstat(left.fileno()).st_mode))
        with self.assertRaises(OSError):
            os.fstat(forwarded[0])

    def test_repeated_inherited_copy_uses_a_fresh_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            address = str(Path(directory) / "wayland")
            with (
                socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener,
                socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as original,
            ):
                listener.bind(address)
                listener.listen(2)
                original.connect(address)
                initial, _ = listener.accept()
                self.addCleanup(initial.close)
                forwarded = []

                def launch(*_args, **kwargs):
                    descriptor = kwargs["pass_fds"][0]
                    forwarded.append(os.fstat(descriptor).st_ino)
                    return self.process

                self.spawn.side_effect = launch
                with patch.dict(os.environ, {"WAYLAND_SOCKET": str(original.fileno())}):
                    clipboard.copy_text("first")
                    clipboard.copy_text("second")
                    second, _ = listener.accept()
                    self.addCleanup(second.close)
                self.assertEqual(forwarded[0], os.fstat(original.fileno()).st_ino)
                self.assertNotEqual(forwarded[0], forwarded[1])
                self.assertEqual(self.spawn.call_count, 2)

    def test_anonymous_inherited_stream_is_never_reused(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        with patch.dict(os.environ, {"WAYLAND_SOCKET": str(left.fileno())}):
            clipboard.copy_text("first")
            with self.assertRaisesRegex(clipboard.ClipboardError, "reconnectable"):
                clipboard.copy_text("second")
        self.spawn.assert_called_once()

    def test_invalid_socket_environment_is_rejected_before_launch(self):
        for value in ("", "-1", "abc", "999999999999999999999999999"):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"WAYLAND_SOCKET": value}),
                self.assertRaisesRegex(
                    clipboard.ClipboardError, "Invalid WAYLAND_SOCKET"
                ),
            ):
                clipboard.copy_text("hello")
        self.spawn.assert_not_called()

    def test_regular_file_is_not_a_wayland_socket(self):
        with (
            tempfile.TemporaryFile() as file,
            patch.dict(os.environ, {"WAYLAND_SOCKET": str(file.fileno())}),
            self.assertRaisesRegex(clipboard.ClipboardError, "not a socket"),
        ):
            clipboard.copy_text("hello")
        self.spawn.assert_not_called()

    def test_invalid_unicode_never_starts_an_owner(self):
        with self.assertRaisesRegex(clipboard.ClipboardError, "valid UTF-8"):
            clipboard.copy_text("\ud800")
        self.spawn.assert_not_called()


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "fork"), "requires POSIX subprocesses"
)
class WaylandProcessLifecycle(unittest.TestCase):
    """Model wl-copy with a local process, without a compositor or clipboard."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tool = self.root / "wl-copy"
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("WAYLAND_SOCKET", None)
        for mocker in (
            patch.object(clipboard.sys, "platform", "linux"),
            patch.object(clipboard.shutil, "which", return_value=str(self.tool)),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)

    def script(self, source):
        self.tool.write_text(f"#!{sys.executable}\n" + textwrap.dedent(source))
        self.tool.chmod(0o700)

    def test_successful_parent_returns_while_daemon_keeps_stderr(self):
        pidfile = self.root / "owner.pid"
        self.script(f"""
            import os, time
            from pathlib import Path
            import sys
            sys.stdin.buffer.read()
            child = os.fork()
            if child == 0:
                os.close(0)
                os.close(1)
                time.sleep(30)
                os._exit(0)
            Path({str(pidfile)!r}).write_text(str(child))
        """)
        try:
            started = time.monotonic()
            with patch.object(clipboard, "COPY_TIMEOUT_SECONDS", 1):
                clipboard.copy_text("text\n")
            self.assertLess(time.monotonic() - started, 2)
        finally:
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def test_real_timeout_reaps_the_started_process(self):
        pidfile = self.root / "parent.pid"
        self.script(f"""
            import os, time
            from pathlib import Path
            Path({str(pidfile)!r}).write_text(str(os.getpid()))
            time.sleep(30)
        """)
        with (
            patch.object(clipboard, "COPY_TIMEOUT_SECONDS", 0.2),
            self.assertRaisesRegex(clipboard.ClipboardError, "timed out"),
        ):
            clipboard.copy_text("text\n")
        if pidfile.exists():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pidfile.read_text()), 0)


class UnsupportedClipboard(unittest.TestCase):
    def test_file_and_stdout_hint_on_unsupported_platform(self):
        with (
            patch.object(clipboard.sys, "platform", "win32"),
            self.assertRaisesRegex(
                clipboard.ClipboardError, "unsupported on win32.*-o FILE"
            ),
        ):
            clipboard.copy_text("hello")


if __name__ == "__main__":
    unittest.main()
