"""Opt-in real Wayland tests, isolated from the desktop's compositor and clipboard.

Run on Linux with sway and wl-clipboard installed:
MD2PLAIN_WAYLAND_TEST=1 python -m unittest discover -s tests \
    -p test_wayland_integration.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from md2plain.render import render_plain

MIME = "text/plain;charset=utf-8"
ENABLED = (
    sys.platform.startswith("linux") and os.environ.get("MD2PLAIN_WAYLAND_TEST") == "1"
)


def stop_process(process: subprocess.Popen) -> None:
    """Stop only a process group that this test started in a new session."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except ProcessLookupError:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


@unittest.skipUnless(ENABLED, "set MD2PLAIN_WAYLAND_TEST=1 on Linux to run")
class WaylandIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for executable in ("sway", "swaymsg", "wl-copy", "wl-paste"):
            if shutil.which(executable) is None:
                raise RuntimeError(f"Wayland integration requires {executable}")

        cls.temporary = tempfile.TemporaryDirectory(prefix="md2plain-wayland-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.runtime = cls.root / "runtime"
        cls.runtime.mkdir(mode=0o700)
        cls.env = os.environ.copy()
        for variable in (
            "WAYLAND_SOCKET",
            "WAYLAND_DISPLAY",
            "WAYLAND_DEBUG",
            "SWAYSOCK",
            "DISPLAY",
            "DBUS_SESSION_BUS_ADDRESS",
        ):
            cls.env.pop(variable, None)
        cls.env.update(
            XDG_RUNTIME_DIR=str(cls.runtime),
            XDG_SESSION_TYPE="wayland",
            WLR_BACKENDS="headless",
            WLR_RENDERER="pixman",
            WLR_HEADLESS_OUTPUTS="1",
            WLR_LIBINPUT_NO_DEVICES="1",
        )
        config = cls.root / "sway.conf"
        config.write_text(
            "xwayland disable\nseat seat0 fallback true\n", encoding="utf-8"
        )
        cls.log_path = cls.root / "sway.log"
        log = cls.log_path.open("wb")
        cls.addClassCleanup(log.close)
        cls.compositor = subprocess.Popen(
            ["sway", "--config", str(config)],
            env=cls.env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        cls.addClassCleanup(cls.stop_compositor)
        cls.wait_for_compositor()

    @classmethod
    def wait_for_compositor(cls):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if cls.compositor.poll() is not None:
                break
            displays = [p for p in cls.runtime.glob("wayland-*") if p.is_socket()]
            controls = [p for p in cls.runtime.glob("sway-ipc.*.sock") if p.is_socket()]
            if displays and controls:
                try:
                    result = subprocess.run(
                        ["swaymsg", "--socket", str(controls[0]), "-t", "get_seats"],
                        env=cls.env,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        timeout=1,
                        check=False,
                    )
                    seats = json.loads(result.stdout) if result.returncode == 0 else []
                    if any(seat.get("name") == "seat0" for seat in seats):
                        cls.env["WAYLAND_DISPLAY"] = displays[0].name
                        return
                except (subprocess.TimeoutExpired, ValueError):
                    pass
            time.sleep(0.05)
        raise RuntimeError(
            "Private headless Sway did not become ready within 10 seconds:\n"
            + cls.log_path.read_text(encoding="utf-8", errors="replace")
        )

    @classmethod
    def stop_compositor(cls):
        """Clear our selection and clean up only owners using our private runtime."""
        try:
            subprocess.run(
                ["wl-copy", "--clear"],
                env=cls.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        stop_process(cls.compositor)

        # wl-copy deliberately outlives the CLI and starts a separate session.
        # A unique runtime path restricts this cleanup to owners from this fixture.
        marker = f"XDG_RUNTIME_DIR={cls.runtime}".encode()
        owners = []
        for entry in Path("/proc").glob("[0-9]*"):
            try:
                variables = (entry / "environ").read_bytes().split(b"\0")
                command = (entry / "cmdline").read_bytes().split(b"\0")[0]
                if marker in variables and Path(os.fsdecode(command)).name == "wl-copy":
                    owners.append(int(entry.name))
            except (OSError, ValueError):
                continue
        for number in owners:
            try:
                os.kill(number, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.source = self.work / "letter.md"

    def cli(self, *arguments, env=None, pass_fds=()):
        result = subprocess.run(
            [sys.executable, "-m", "md2plain", str(self.source), *arguments],
            env=self.env if env is None else env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=20,
            pass_fds=pass_fds,
            check=False,
        )
        self.assertEqual(
            result.returncode, 0, result.stderr.decode("utf-8", errors="replace")
        )
        return result

    def paste(self):
        return subprocess.run(
            ["wl-paste", "--no-newline", "--type", MIME],
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=2,
            check=False,
        )

    def assert_pastes(self, expected):
        for _ in range(3):
            result = self.paste()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)

    def wait_for_clipboard(self, expected, process):
        deadline = time.monotonic() + 10
        last = None
        while time.monotonic() < deadline:
            self.assertIsNone(process.poll(), "watch exited before copying the update")
            try:
                last = self.paste()
                if last.returncode == 0 and last.stdout == expected:
                    return
            except subprocess.TimeoutExpired:
                pass
            time.sleep(0.05)
        detail = None if last is None else (last.returncode, last.stderr)
        self.fail(f"Clipboard did not receive the expected watch update: {detail!r}")

    def test_cli_exit_preserves_unicode_whitespace_and_plain_mime(self):
        source = (
            "Dear 李华 👩‍💻,\n\n"
            "中文邮件、组合重音 e\u0301、家庭 emoji 👨‍👩‍👧‍👦。\n\n"
            "[报告](https://example.com/report?token=abc#结论)\n\n"
            "> 引用正文\n\n"
            "```text\n"
            "alpha\tbeta  \n\n"
            "gamma\t末尾\t\n"
            "```\n\n"
            "-- \n张三\n某某公司\n"
        )
        expected = render_plain(source).encode("utf-8")
        self.assertIn(b"-- \n", expected)
        self.assertIn(b"alpha\tbeta  \n", expected)
        self.assertTrue(expected.endswith(b"\n"))
        self.source.write_text(source, encoding="utf-8")
        self.cli()
        self.assert_pastes(expected)
        types = subprocess.run(
            ["wl-paste", "--list-types"],
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=2,
            check=False,
        )
        self.assertEqual(types.returncode, 0, types.stderr)
        offered = types.stdout.decode("utf-8").splitlines()
        self.assertIn(MIME, offered)
        self.assertFalse(any(value.startswith("text/html") for value in offered))

    def test_large_body_and_actual_connection_without_wayland_session_label(self):
        source = (
            "中文与 emoji 🙂 / repeated clipboard line with trailing words.\n" * 4096
        )
        expected = render_plain(source).encode("utf-8")
        self.assertGreater(len(expected), 128 * 1024)
        self.source.write_text(source, encoding="utf-8")
        self.cli(env={**self.env, "XDG_SESSION_TYPE": "tty"})
        self.assert_pastes(expected)

    def test_inherited_wayland_socket_remains_usable_after_cli_exit(self):
        source = "通过 WAYLAND_SOCKET 复制 👋\n\n-- \n张三\n"
        self.source.write_text(source, encoding="utf-8")
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(2)
            connection.connect(str(self.runtime / self.env["WAYLAND_DISPLAY"]))
            connection.settimeout(None)
            environment = {
                **self.env,
                "WAYLAND_DISPLAY": "invalid-display-for-inherited-socket",
                "WAYLAND_SOCKET": str(connection.fileno()),
            }
            self.cli(env=environment, pass_fds=(connection.fileno(),))
        self.assert_pastes(render_plain(source).encode("utf-8"))

    def test_inherited_wayland_socket_watch_updates_and_survives_ctrl_c(self):
        initial = "继承连接的初始正文 👋\n\n-- \n张三\n"
        updated = "继承连接的更新正文 🌍\n\n```text\na\tb  \n```\n\n-- \n李四\n"
        self.source.write_text(initial, encoding="utf-8")
        with (
            socket.socket(socket.AF_UNIX) as connection,
            tempfile.TemporaryFile() as errors,
        ):
            connection.settimeout(2)
            connection.connect(str(self.runtime / self.env["WAYLAND_DISPLAY"]))
            connection.settimeout(None)
            environment = {
                **self.env,
                "WAYLAND_DISPLAY": "invalid-display-for-inherited-socket",
                "WAYLAND_SOCKET": str(connection.fileno()),
            }
            watcher = subprocess.Popen(
                [sys.executable, "-m", "md2plain", str(self.source), "--watch"],
                env=environment,
                pass_fds=(connection.fileno(),),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                start_new_session=True,
            )
            try:
                expected = render_plain(initial).encode("utf-8")
                self.wait_for_clipboard(expected, watcher)
                replacement = self.work / "inherited-editor-save.md"
                replacement.write_text(updated, encoding="utf-8")
                replacement.replace(self.source)
                expected = render_plain(updated).encode("utf-8")
                self.wait_for_clipboard(expected, watcher)
                os.killpg(watcher.pid, signal.SIGINT)
                self.assertEqual(watcher.wait(timeout=5), 0)
                errors.seek(0)
                self.assertIn(b"Stopped watching", errors.read())
            finally:
                stop_process(watcher)
        self.assert_pastes(expected)

    def test_watch_updates_file_and_clipboard_survives_ctrl_c(self):
        initial = "初始正文 👋\n\n-- \n张三\n"
        updated = "更新正文 🌍\n\n```text\na\tb  \n```\n\n-- \n李四\n"
        self.source.write_text(initial, encoding="utf-8")
        output = self.work / "saved" / "letter.txt"
        with tempfile.TemporaryFile() as errors:
            watcher = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "md2plain",
                    str(self.source),
                    "--watch",
                    "-o",
                    str(output),
                    "--copy",
                ],
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                start_new_session=True,
            )
            try:
                expected = render_plain(initial).encode("utf-8")
                self.wait_for_clipboard(expected, watcher)
                self.assertEqual(output.read_bytes(), expected)
                replacement = self.work / "editor-save.md"
                replacement.write_text(updated, encoding="utf-8")
                replacement.replace(self.source)
                expected = render_plain(updated).encode("utf-8")
                self.wait_for_clipboard(expected, watcher)
                self.assertEqual(output.read_bytes(), expected)
                # Match terminal Ctrl-C: signal the CLI's whole process group.
                os.killpg(watcher.pid, signal.SIGINT)
                self.assertEqual(watcher.wait(timeout=5), 0)
                errors.seek(0)
                self.assertIn(b"Stopped watching", errors.read())
                self.assert_pastes(expected)
            finally:
                stop_process(watcher)


if __name__ == "__main__":
    unittest.main()
