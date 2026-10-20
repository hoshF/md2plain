"""Regression tests for safe outputs, decoding, and stable file watching."""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            "copy": None,
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

    def test_output_option_combinations(self):
        for show in (False, True):
            for save in (False, True):
                for choice in (None, "--copy", "--no-copy"):
                    with self.subTest(show=show, save=save, choice=choice):
                        arguments = [str(self.source)]
                        if show:
                            arguments.append("--print")
                        if save:
                            arguments.extend(["-o", str(self.output)])
                        if choice is not None:
                            arguments.append(choice)
                        result, out, err, copy = self.run_main(*arguments)
                        expected = "Dear A,\nHello.\n"
                        self.assertEqual(result, 0)
                        self.assertEqual(out, expected if show else "")
                        if save:
                            self.assertEqual(self.output.read_text(), expected)
                        should_copy = choice == "--copy" or (
                            choice is None and not (show or save)
                        )
                        if should_copy:
                            copy.assert_called_once_with(expected)
                            self.assertIn("Copied", err)
                        else:
                            copy.assert_not_called()
                            self.assertEqual(err, "")

    def test_conflicting_clipboard_flags_are_rejected(self):
        stderr = io.StringIO()
        with (
            patch.object(
                sys, "argv", ["md2plain", str(self.source), "--copy", "--no-copy"]
            ),
            patch.object(sys, "stderr", stderr),
            self.assertRaises(SystemExit) as error,
            patch.object(cli, "copy_text") as copy,
        ):
            cli.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("not allowed with argument", stderr.getvalue())
        copy.assert_not_called()

    def test_output_creates_parents_and_supports_unicode_and_any_extension(self):
        target = self.root / "信件 草稿" / "nested" / "letter.custom"
        result, out, err, copy = self.run_main(self.source, "-o", target)
        self.assertEqual(result, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), "Dear A,\nHello.\n")
        self.assertEqual((out, err), ("", ""))
        copy.assert_not_called()

    def test_quoted_tilde_paths_are_expanded(self):
        target = self.root / "Documents" / "信件.txt"
        with patch.dict(os.environ, {"HOME": str(self.root)}):
            result, out, err, copy = self.run_main(
                "~/letter.md", "-o", "~/Documents/信件.txt"
            )
        self.assertEqual(result, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), "Dear A,\nHello.\n")
        self.assertEqual((out, err), ("", ""))
        copy.assert_not_called()

    def test_expanded_alias_is_rejected(self):
        with patch.dict(os.environ, {"HOME": str(self.root)}):
            result, out, err, copy = self.run_main(self.source, "-o", "~/letter.md")
        self.assertEqual(result, 1)
        self.assertEqual(out, "")
        self.assertIn("different files", err)
        copy.assert_not_called()

    def test_failed_input_never_creates_output_directory(self):
        target = self.root / "uncreated" / "result.txt"
        cases = [
            (self.root / "missing.md", None),
            (self.source, b"\xff"),
            (self.source, b""),
        ]
        for input_path, content in cases:
            with self.subTest(input_path=input_path, content=content):
                if content is not None:
                    self.source.write_bytes(content)
                result, out, _, copy = self.run_main(input_path, "-o", target)
                self.assertEqual(result, 1)
                self.assertEqual(out, "")
                self.assertFalse(target.parent.exists())
                copy.assert_not_called()

    def test_failed_conversion_never_creates_output_directory(self):
        target = self.root / "uncreated" / "result.txt"
        with patch.object(
            cli, "render_plain", side_effect=cli.CliError("conversion failed")
        ):
            result, out, err, copy = self.run_main(self.source, "-o", target)
        self.assertEqual(result, 1)
        self.assertEqual(out, "")
        self.assertIn("conversion failed", err)
        self.assertFalse(target.parent.exists())
        copy.assert_not_called()

    def test_stdin_can_save_into_new_directory(self):
        target = self.root / "new" / "letter.txt"
        result, out, _, copy = self.run_main(
            "-", "-o", target, stdin=io.StringIO("# Hello\n")
        )
        self.assertEqual(result, 0)
        self.assertEqual(target.read_text(), "Hello\n=====\n")
        self.assertEqual(out, "")
        copy.assert_not_called()

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
        blocked_parent = self.root / "not-a-directory"
        blocked_parent.write_text("occupied", encoding="utf-8")
        result, out, err, copy = self.run_main(
            self.source, "-o", blocked_parent / "out.txt", "--copy"
        )
        self.assertEqual(result, 1)
        self.assertEqual(out, "")
        self.assertIn(str(blocked_parent / "out.txt"), err)
        self.assertIn("Not a directory", err)
        self.assertNotIn("Traceback", err)
        copy.assert_not_called()

    def test_clipboard_failure_never_reports_success(self):
        stderr = io.StringIO()
        for error in (
            cli.ClipboardError("rejected"),
            RuntimeError("unavailable"),
            ImportError("missing backend"),
        ):
            with (
                self.subTest(error=error),
                patch.object(cli, "copy_text", side_effect=error),
                patch.object(sys, "stderr", stderr),
                self.assertRaises(cli.CliError),
            ):
                cli.finish("hello\n", self.args())
        self.assertNotIn("Copied", stderr.getvalue())

    def test_parent_permission_failure_is_reported_before_copy(self):
        with patch.object(
            Path, "mkdir", side_effect=PermissionError("permission denied")
        ):
            result, out, err, copy = self.run_main(
                self.source, "-o", self.root / "protected" / "out.txt", "--copy"
            )
        self.assertEqual(result, 1)
        self.assertEqual(out, "")
        self.assertIn("Cannot write", err)
        self.assertIn("permission denied", err)
        self.assertFalse((self.root / "protected").exists())
        copy.assert_not_called()

    def test_saved_file_is_retained_and_named_when_copy_fails(self):
        stderr = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                ["md2plain", str(self.source), "-o", str(self.output), "--copy"],
            ),
            patch.object(sys, "stderr", stderr),
            patch.object(
                cli, "copy_text", side_effect=cli.ClipboardError("Wayland unavailable")
            ),
        ):
            result = cli.main()
        self.assertEqual(result, 1)
        self.assertEqual(self.output.read_text(), "Dear A,\nHello.\n")
        self.assertIn(f"Saved {self.output}", stderr.getvalue())
        self.assertIn("clipboard copy failed", stderr.getvalue())
        self.assertIn("Wayland unavailable", stderr.getvalue())
        self.assertNotIn("Copied", stderr.getvalue())

    def test_unknown_home_user_is_an_actionable_error(self):
        with patch.object(
            Path, "expanduser", side_effect=RuntimeError("home unavailable")
        ):
            result, out, err, copy = self.run_main(self.source, "-o", self.output)
        self.assertEqual(result, 1)
        self.assertEqual(out, "")
        self.assertIn("Cannot expand file path", err)
        copy.assert_not_called()


class WatchReliability(CliFixture):
    """Use real file changes and a virtual clock, without touching the clipboard."""

    def run_watch(self, events=(), until=2.0, convert=None, args=None):
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
            cli.watch_input(args or self.args(), publish)
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

    def test_watch_file_output_does_not_copy_by_default(self):
        args = self.args(output=str(self.root / "new" / "letter.txt"))
        with patch.object(cli, "copy_text") as copy:
            published, _ = self.run_watch(
                [(0.7, lambda: self.write("Updated\n"))],
                until=1.5,
                convert=lambda text: cli.finish(cli.render_plain(text), args),
                args=args,
            )
        self.assertEqual(
            [text for _, text in published], ["Dear A,\nHello.\n", "Updated\n"]
        )
        self.assertEqual(Path(args.output).read_text(), "Updated\n")
        copy.assert_not_called()

    def test_watch_file_output_can_explicitly_copy(self):
        args = self.args(output=str(self.output), copy=True)
        with patch.object(cli, "copy_text") as copy:
            published, _ = self.run_watch(
                until=0.8,
                convert=lambda text: cli.finish(cli.render_plain(text), args),
                args=args,
            )
        self.assertEqual(len(published), 1)
        copy.assert_called_once_with(self.output.read_text())

    def test_watch_uses_expanded_input_and_output_paths(self):
        observed = []

        def watch(args, convert):
            observed.extend([args.input, args.output])
            convert(cli.read_input(args.input))
            raise KeyboardInterrupt

        with (
            patch.dict(os.environ, {"HOME": str(self.root)}),
            patch.object(cli, "watch_input", side_effect=watch),
        ):
            result, _, _, copy = self.run_main(
                "~/letter.md", "-o", "~/nested/letter.txt", "--watch"
            )
        self.assertEqual(result, 0)
        self.assertEqual(
            observed, [str(self.source), str(self.root / "nested/letter.txt")]
        )
        self.assertEqual(
            (self.root / "nested/letter.txt").read_text(), "Dear A,\nHello.\n"
        )
        copy.assert_not_called()

    def test_ctrl_c_is_clean(self):
        with patch.object(cli, "watch_input", side_effect=KeyboardInterrupt):
            result, out, err, copy = self.run_main(self.source, "--watch")
        self.assertEqual(result, 0)
        self.assertEqual(out, "")
        self.assertIn("Stopped watching", err)
        copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
