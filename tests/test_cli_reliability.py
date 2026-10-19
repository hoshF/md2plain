"""Regression tests for safe outputs, decoding, and stable file watching."""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from md2plain import cli


class CliFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "letter.md"
        self.source.write_text("Dear A,\nHello.\n", encoding="utf-8")
        self.output = self.root / "letter.txt"

    def args(self, **overrides):
        values = {
            "input": str(self.source),
            "output": None,
            "show": False,
            "no_copy": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def run_main(self, *arguments, stdin=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["md2plain", *map(str, arguments)]),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
            patch.object(sys, "stdin", stdin or io.StringIO()),
            patch.object(cli, "copy_text") as copy,
        ):
            result = cli.main()
        return result, stdout.getvalue(), stderr.getvalue(), copy


class CliReliability(CliFixture):
    def test_print_does_not_copy(self):
        result, out, err, copy = self.run_main(self.source, "--print")
        self.assertEqual(result, 0)
        self.assertEqual(out, "Dear A,\nHello.\n")
        self.assertEqual(err, "")
        copy.assert_not_called()

    def test_print_and_output_save_without_copy(self):
        result, out, _, copy = self.run_main(self.source, "--print", "-o", self.output)
        self.assertEqual(result, 0)
        self.assertEqual(self.output.read_text(), out)
        copy.assert_not_called()

    def test_output_alone_still_copies(self):
        result, out, err, copy = self.run_main(self.source, "-o", self.output)
        self.assertEqual(result, 0)
        self.assertEqual(out, "")
        copy.assert_called_once_with(self.output.read_text())
        self.assertIn("Copied", err)

    def test_file_and_stdin_bom_and_newlines(self):
        raw = b"\xef\xbb\xbfHello\r\nA\rB\n"
        self.source.write_bytes(raw)
        self.assertEqual(cli.read_input(str(self.source)), "Hello\nA\nB\n")
        stream = io.TextIOWrapper(io.BytesIO(raw))
        self.addCleanup(stream.close)
        with patch.object(sys, "stdin", stream):
            self.assertEqual(cli.read_input("-"), "Hello\nA\nB\n")

    def test_invalid_utf8_file_has_path_and_original_byte_offset(self):
        self.source.write_bytes(b"\xef\xbb\xbfHello\xff")
        self.output.write_text("old result", encoding="utf-8")
        result, out, err, copy = self.run_main(
            self.source, "--print", "-o", self.output
        )
        self.assertEqual(result, 1)
        self.assertEqual(out, "")
        self.assertIn(str(self.source), err)
        self.assertIn("UTF-8 at byte 9", err)
        self.assertEqual(self.output.read_text(), "old result")
        copy.assert_not_called()

    def test_invalid_utf8_stdin_is_rejected(self):
        stream = io.TextIOWrapper(io.BytesIO(b"a\xff"))
        self.addCleanup(stream.close)
        result, out, err, copy = self.run_main("-", "--print", stdin=stream)
        self.assertEqual(result, 1)
        self.assertEqual(out, "")
        self.assertIn("stdin", err)
        self.assertIn("UTF-8 at byte 2", err)
        copy.assert_not_called()

    def test_same_file_and_aliases_are_rejected(self):
        symlink = self.root / "symlink.txt"
        symlink.symlink_to(self.source)
        hardlink = self.root / "hardlink.txt"
        os.link(self.source, hardlink)
        original = self.source.read_bytes()
        for target in (self.source, symlink, hardlink):
            with self.subTest(target=target):
                result, out, err, copy = self.run_main(
                    self.source, "-o", target, "--print"
                )
                self.assertEqual(result, 1)
                self.assertEqual(out, "")
                self.assertIn("different files", err)
                copy.assert_not_called()
                self.assertEqual(self.source.read_bytes(), original)

    def test_save_rechecks_alias_after_writing_temporary_file(self):
        self.output.write_text("old result", encoding="utf-8")
        original = self.source.read_bytes()

        def change_target(_descriptor):
            self.output.unlink()
            os.link(self.source, self.output)

        with (
            patch.object(cli.os, "fsync", side_effect=change_target),
            self.assertRaisesRegex(cli.CliError, "different files"),
        ):
            cli.save_output("new result", self.args(output=str(self.output)))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(list(self.root.glob(".md2plain-*")), [])

    def test_atomic_save_keeps_old_result_until_replace(self):
        self.output.write_text("old result", encoding="utf-8")
        self.output.chmod(0o640)
        replace = os.replace

        def inspect_then_replace(source, target):
            self.assertEqual(self.output.read_text(), "old result")
            self.assertEqual(Path(source).read_text(), "new result\n")
            self.assertEqual(Path(source).parent, self.output.parent)
            replace(source, target)

        with patch.object(cli.os, "replace", side_effect=inspect_then_replace):
            cli.save_output("new result\n", self.args(output=str(self.output)))
        self.assertEqual(self.output.read_text(), "new result\n")
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.root.glob(".md2plain-*")), [])

    def test_failed_replace_keeps_previous_file_and_cleans_temporary_file(self):
        self.output.write_text("old result", encoding="utf-8")
        with (
            patch.object(cli.os, "replace", side_effect=OSError("disk unavailable")),
            self.assertRaisesRegex(cli.CliError, "Cannot write.*disk unavailable"),
        ):
            cli.save_output("new result", self.args(output=str(self.output)))
        self.assertEqual(self.output.read_text(), "old result")
        self.assertEqual(list(self.root.glob(".md2plain-*")), [])

    def test_output_failure_has_no_traceback_or_clipboard_change(self):
        result, out, err, copy = self.run_main(
            self.source, "-o", self.root / "missing" / "out.txt"
        )
        self.assertEqual(result, 1)
        self.assertEqual(out, "")
        self.assertIn("Cannot write", err)
        self.assertNotIn("Traceback", err)
        copy.assert_not_called()

    def test_clipboard_failure_never_reports_success(self):
        stderr = io.StringIO()
        for error in (
            cli.CliError("rejected"),
            RuntimeError("unavailable"),
            ImportError(),
        ):
            with (
                self.subTest(error=error),
                patch.object(cli, "copy_text", side_effect=error),
                patch.object(sys, "stderr", stderr),
                self.assertRaises(cli.CliError),
            ):
                cli.finish("hello\n", self.args())
        self.assertNotIn("Copied", stderr.getvalue())

    def test_clipboard_board_and_acceptance_are_checked(self):
        pasteboard = Mock()
        module = types.SimpleNamespace(
            NSPasteboard=pasteboard, NSPasteboardTypeString="public.utf8-plain-text"
        )
        with (
            patch.dict(sys.modules, {"AppKit": module}),
            patch.dict(os.environ, {"MD2PLAIN_PASTEBOARD": "md2plain-unit-test"}),
        ):
            pasteboard.pasteboardWithName_.return_value = None
            with self.assertRaisesRegex(cli.CliError, "access the clipboard"):
                cli.copy_text("hello")
            board = Mock()
            pasteboard.pasteboardWithName_.return_value = board
            board.setString_forType_.return_value = False
            with self.assertRaisesRegex(cli.CliError, "did not accept"):
                cli.copy_text("hello")
            board.setString_forType_.return_value = True
            cli.copy_text("hello")
            board.setString_forType_.assert_called_with(
                "hello", "public.utf8-plain-text"
            )
            pasteboard.generalPasteboard.assert_not_called()


class WatchReliability(CliFixture):
    """Use real file changes and a virtual clock, without touching the clipboard."""

    def run_watch(self, events=(), until=2.0, convert=None):
        now = 0.0
        remaining = list(events)
        published = []
        stderr = io.StringIO()

        def sleep(_seconds):
            nonlocal now
            now = round(now + cli.WATCH_POLL_SECONDS, 8)
            while remaining and remaining[0][0] <= now:
                _, action = remaining.pop(0)
                action()
            if now >= until:
                raise KeyboardInterrupt

        def publish(source):
            if convert is not None:
                convert(source)
            published.append((now, source))

        with (
            patch.object(cli.time, "monotonic", side_effect=lambda: now),
            patch.object(cli.time, "sleep", side_effect=sleep),
            patch.object(sys, "stderr", stderr),
            self.assertRaises(KeyboardInterrupt),
        ):
            cli.watch_input(self.args(), publish)
        return published, stderr.getvalue()

    def write(self, content):
        self.source.write_text(content, encoding="utf-8")

    def test_initial_content_must_be_stable(self):
        published, _ = self.run_watch(until=0.4)
        self.assertEqual(published, [])

    def test_partial_writes_only_publish_completed_stable_content(self):
        published, _ = self.run_watch(
            [
                (0.2, lambda: self.write("Dear")),
                (0.4, lambda: self.write("Dear B,\nDone.\n")),
            ],
            until=1.2,
        )
        self.assertEqual([text for _, text in published], ["Dear B,\nDone.\n"])
        self.assertGreaterEqual(published[0][0], 0.9)

    def test_empty_and_invalid_save_keep_previous_success_and_recover(self):
        published, err = self.run_watch(
            [
                (0.7, lambda: self.write("")),
                (1.0, lambda: self.source.write_bytes(b"\xff")),
                (1.3, lambda: self.write("Recovered\n")),
            ],
            until=2.1,
        )
        self.assertEqual(
            [text for _, text in published], ["Dear A,\nHello.\n", "Recovered\n"]
        )
        self.assertIn("Input is empty", err)
        self.assertIn("invalid UTF-8", err)
        self.assertGreaterEqual(published[1][0], 1.8)

    def test_delete_and_recreate_recovers(self):
        published, err = self.run_watch(
            [(0.7, self.source.unlink), (1.0, lambda: self.write("Recreated\n"))],
            until=1.8,
        )
        self.assertEqual(
            [text for _, text in published], ["Dear A,\nHello.\n", "Recreated\n"]
        )
        self.assertEqual(err.count("File not found"), 1)

    def test_watch_can_start_before_input_exists(self):
        self.source.unlink()
        published, _ = self.run_watch(
            [(0.3, lambda: self.write("Created later\n"))], until=1.1
        )
        self.assertEqual([text for _, text in published], ["Created later\n"])
        self.assertGreaterEqual(published[0][0], 0.8)

    def test_atomic_editor_save_is_observed(self):
        replacement = self.root / "editor-save.md"
        replacement.write_text("Atomic save\n", encoding="utf-8")
        published, _ = self.run_watch(
            [(0.7, lambda: os.replace(replacement, self.source))], until=1.5
        )
        self.assertEqual(
            [text for _, text in published], ["Dear A,\nHello.\n", "Atomic save\n"]
        )
        self.assertGreaterEqual(published[1][0], 1.2)

    def test_repeated_identical_save_does_not_republish(self):
        published, _ = self.run_watch(
            [(0.7, lambda: self.write("Dear A,\nHello.\n"))], until=1.6
        )
        self.assertEqual(len(published), 1)

    def test_copy_failure_is_retried_and_success_is_retained(self):
        attempts = 0

        def flaky_convert(_source):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise cli.CliError("clipboard unavailable")

        published, err = self.run_watch(until=1.5, convert=flaky_convert)
        self.assertEqual(attempts, 2)
        self.assertEqual(len(published), 1)
        self.assertEqual(err.count("clipboard unavailable"), 1)

    def test_permission_failure_recovers(self):
        real_read = cli.read_input
        attempts = 0

        def interrupted_read(path):
            nonlocal attempts
            attempts += 1
            if attempts <= 3:
                raise cli.CliError("Cannot read: permission denied")
            return real_read(path)

        with patch.object(cli, "read_input", side_effect=interrupted_read):
            published, err = self.run_watch(until=1.2)
        self.assertEqual(len(published), 1)
        self.assertEqual(err.count("permission denied"), 1)
        self.assertGreaterEqual(published[0][0], 0.8)

    def test_changed_revision_during_read_is_never_published(self):
        real_read = cli.read_input
        first = True

        def changing_read(path):
            nonlocal first
            text = real_read(path)
            if first:
                first = False
                self.write("New content\n")
            return text

        with patch.object(cli, "read_input", side_effect=changing_read):
            published, _ = self.run_watch(until=1.0)
        self.assertEqual([text for _, text in published], ["New content\n"])

    def test_ctrl_c_is_clean(self):
        with patch.object(cli, "watch_input", side_effect=KeyboardInterrupt):
            result, out, err, copy = self.run_main(self.source, "--watch")
        self.assertEqual(result, 0)
        self.assertEqual(out, "")
        self.assertIn("Stopped watching", err)
        copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
