"""Tests for md2plain: renderer, CLI, clipboard and output invariants."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from md2plain.render import disp_width, render_plain

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "-m", "md2plain"]
MACOS = sys.platform == "darwin"

SAMPLE_MD = """\
# Format Test

Dear Tester,

This is a sample letter with **bold text**, *italics* and `inline code`.
It also has a [link](https://example.com) and a bare URL https://example.org.

## A List

* first item
* second item, long enough to wrap onto another line when the width is small
* third item

1. one
2. two

## A Quote

> quoted line one
> quoted line two

## A Table

| name | count |
| --- | --- |
| apple | 3 |
| pear | 12 |

## Code

```python
print("hello")
```

---

Best regards,
Test User
2026-01-01
"""


def r(md: str, width: int = 75, preserve: bool = True) -> str:
    return render_plain(md, width, preserve)


def run_cli(
    *args: str, stdin: str | None = None, cwd: Path = ROOT
) -> subprocess.CompletedProcess:
    return subprocess.run(
        CLI + list(args),
        input=stdin,
        text=True,
        capture_output=True,
        cwd=cwd,
        check=False,
    )


class SampleCase(unittest.TestCase):
    """Provide a temporary Markdown file for CLI tests."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sample = Path(self.tmp.name) / "sample.md"
        self.sample.write_text(SAMPLE_MD, encoding="utf-8")


class Headings(unittest.TestCase):
    def test_levels_use_underline(self):
        out = r(
            "# One\n\n## Two\n\n### Three\n\n#### Four\n\n##### Five\n\n###### Six\n"
        )
        self.assertIn("One\n===", out)
        self.assertIn("Two\n---", out)
        self.assertIn("Three\n~~~~~", out)
        self.assertIn("Four\n^^^^", out)
        self.assertIn('Five\n""""', out)
        self.assertIn("Six\n'''", out)

    def test_underline_matches_cjk_width(self):
        self.assertEqual(r("# 标题\n"), "标题\n====\n")

    def test_empty_heading_skipped(self):
        self.assertEqual(r("#\n\ntext\n"), "text\n")


class Paragraphs(unittest.TestCase):
    def test_wrap_respects_width(self):
        out = r("word " * 60, 75)
        for line in out.splitlines():
            self.assertLessEqual(disp_width(line), 75)

    def test_cjk_wraps_by_display_width(self):
        out = r("这是一段很长的中文文字，用于测试按两列宽度换行。" * 5, 40)
        for line in out.splitlines():
            self.assertLessEqual(disp_width(line), 40)

    def test_no_closing_punctuation_at_line_start(self):
        out = r("字" * 74 + "。下一句。", 75)
        for line in out.splitlines():
            self.assertFalse(line.startswith("。"))

    def test_single_newline_is_kept(self):
        self.assertEqual(r("Dear A,\nBest regards\n"), "Dear A,\nBest regards\n")

    def test_soft_breaks_join_lines(self):
        self.assertEqual(r("a\nb\n", 75, preserve=False), "a b\n")

    def test_hard_break_two_spaces(self):
        self.assertEqual(r("a  \nb\n"), "a\nb\n")

    def test_hard_break_backslash(self):
        self.assertEqual(r("a\\\nb\n"), "a\nb\n")

    def test_tabs_collapse(self):
        self.assertEqual(r("a\tb\n"), "a b\n")

    def test_long_token_is_split(self):
        out = r("x" * 120, 40)
        self.assertEqual([len(line) for line in out.splitlines()], [40, 40, 40])


class Lists(unittest.TestCase):
    def test_bullets(self):
        self.assertEqual(r("- a\n- b\n"), "* a\n* b\n")

    def test_ordered(self):
        self.assertEqual(r("1. a\n2. b\n"), "1. a\n2. b\n")

    def test_ordered_start(self):
        self.assertEqual(r("3. c\n4. d\n"), "3. c\n4. d\n")

    def test_nested_is_tight(self):
        self.assertEqual(r("- a\n  - b\n  - c\n- d\n"), "* a\n  * b\n  * c\n* d\n")

    def test_hanging_indent(self):
        out = r("- " + "word " * 30 + "\n", 40)
        self.assertTrue(out.startswith("* word"))
        self.assertTrue(out.splitlines()[1].startswith("  "))


class Quotes(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(r("> a\n> b\n"), "> a\n> b\n")

    def test_blank_line(self):
        self.assertEqual(r("> a\n>\n> b\n"), "> a\n>\n> b\n")

    def test_nested(self):
        self.assertEqual(r("> a\n> > b\n"), "> a\n>\n> > b\n")

    def test_respects_width(self):
        out = r("> " + "word " * 40, 40)
        for line in out.splitlines():
            self.assertLessEqual(disp_width(line), 40)


class Code(unittest.TestCase):
    def test_fence_indented(self):
        self.assertEqual(r("```\nx = 1\n```\n"), "    x = 1\n")

    def test_fence_not_wrapped(self):
        long_line = "x" * 100
        self.assertIn("    " + long_line, r(f"```\n{long_line}\n```\n"))

    def test_inline_code(self):
        self.assertEqual(r("use `x` here\n"), "use x here\n")


class Tables(unittest.TestCase):
    def test_alignment(self):
        out = r("| a | b |\n| --- | --- |\n| 1 | 2 |\n")
        self.assertEqual(out, "a  b\n-  -\n1  2\n")

    def test_cjk_columns(self):
        out = r("| 名称 | n |\n| --- | --- |\n| 苹果 | 3 |\n")
        lines = out.splitlines()
        self.assertEqual(lines[0], "名称  n")
        self.assertEqual(lines[1], "----  -")


class Inline(unittest.TestCase):
    def test_markdown_link(self):
        self.assertEqual(r("[x](https://e.com)\n"), "x (https://e.com)\n")

    def test_url_label_with_tracking_param(self):
        self.assertEqual(
            r("[https://e.com](https://e.com?utm_source=x)\n"),
            "https://e.com (https://e.com?utm_source=x)\n",
        )

    def test_bare_url_not_duplicated(self):
        self.assertEqual(r("https://e.com\n"), "https://e.com\n")

    def test_mailto_target_kept(self):
        self.assertEqual(r("<a@b.com>\n"), "a@b.com (mailto:a@b.com)\n")

    def test_unsafe_scheme_not_linked(self):
        self.assertEqual(r("[x](javascript:alert(1))\n"), "[x](javascript:alert(1))\n")

    def test_image_alt(self):
        self.assertEqual(r("![alt text](i.png)\n"), "[图片：alt text] (i.png)\n")

    def test_emphasis_stripped(self):
        self.assertEqual(r("**bold** *it* ~~gone~~\n"), "bold it ~~gone~~\n")

    def test_html_is_literal(self):
        self.assertEqual(r("<b>x</b>\n"), "<b>x</b>\n")


class Blocks(unittest.TestCase):
    def test_hr(self):
        self.assertEqual(r("---\n"), "-" * 72 + "\n")

    def test_empty_input(self):
        self.assertEqual(r(""), "\n")


class Widths(unittest.TestCase):
    def test_no_wrap_when_width_is_large(self):
        out = r("word " * 40, 1000)
        self.assertEqual(len(out.splitlines()), 1)

    def test_width_one_has_no_blank_lines(self):
        out = r("a b c\n", 1)
        self.assertEqual([line for line in out.splitlines() if not line], [])


class Cli(SampleCase):
    def test_print_matches_renderer(self):
        proc = run_cli(str(self.sample), "--print", "--no-copy")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, render_plain(SAMPLE_MD))

    def test_output_file(self):
        out = Path(self.tmp.name) / "out.txt"
        proc = run_cli(str(self.sample), "-o", str(out))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out.read_text(encoding="utf-8"), render_plain(SAMPLE_MD))

    def test_relative_input_and_output_paths(self):
        proc = run_cli("sample.md", "-o", "new/信件.custom", cwd=Path(self.tmp.name))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "")
        self.assertEqual(
            (Path(self.tmp.name) / "new/信件.custom").read_text(encoding="utf-8"),
            render_plain(SAMPLE_MD),
        )

    def test_stdin(self):
        proc = run_cli("-", "--print", "--no-copy", stdin="# Hi\n")
        self.assertEqual(proc.stdout, "Hi\n===\n")

    def test_missing_file(self):
        proc = run_cli("nope.md", "--no-copy")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("File not found", proc.stderr)

    def test_empty_input(self):
        proc = run_cli("-", "--no-copy", stdin="")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Input is empty", proc.stderr)

    def test_invalid_width(self):
        proc = run_cli(str(self.sample), "--width", "0", "--no-copy")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("at least 1", proc.stderr)

    def test_watch_requires_file(self):
        proc = run_cli("-", "--watch", stdin="x")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("requires a file", proc.stderr)

    def test_bom_stripped(self):
        path = Path(self.tmp.name) / "bom.md"
        path.write_bytes(b"\xef\xbb\xbf# Title\n\nBody\n")
        proc = run_cli(str(path), "--print", "--no-copy")
        self.assertFalse(proc.stdout.startswith("\ufeff"))
        self.assertTrue(proc.stdout.startswith("Title"))

    def test_crlf(self):
        path = Path(self.tmp.name) / "crlf.md"
        path.write_bytes(b"a\r\nb\r\n")
        proc = run_cli(str(path), "--print", "--no-copy")
        self.assertEqual(proc.stdout, "a\nb\n")

    def test_invalid_utf8(self):
        path = Path(self.tmp.name) / "bad.md"
        path.write_bytes(b"hello \xff world\n")
        proc = run_cli(str(path), "--print", "--no-copy")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertIn("invalid UTF-8", proc.stderr)

    def test_directory_input(self):
        proc = run_cli(self.tmp.name, "--no-copy")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Cannot read", proc.stderr)

    def test_path_with_spaces(self):
        path = Path(self.tmp.name) / "a b.md"
        path.write_text("# Hi\n", encoding="utf-8")
        proc = run_cli(str(path), "--print", "--no-copy")
        self.assertEqual(proc.stdout, "Hi\n===\n")

    def test_cli_width_matches_renderer(self):
        proc = run_cli(str(self.sample), "--print", "--no-copy", "--width", "60")
        self.assertEqual(proc.stdout, render_plain(SAMPLE_MD, 60))

    def test_output_path_with_spaces(self):
        out = Path(self.tmp.name) / "out file.txt"
        proc = run_cli(str(self.sample), "-o", str(out))
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(out.exists())


class Invariants(unittest.TestCase):
    def check(self, out: str) -> None:
        self.assertTrue(out.endswith("\n"))
        self.assertFalse(out.endswith("\n\n"))
        self.assertNotIn("\x00", out)
        self.assertNotIn("\r", out)
        for line in out.splitlines():
            self.assertEqual(line, line.rstrip())
            self.assertLessEqual(disp_width(line), 76)
            self.assertFalse(line[:1] in set("。，、；：！？"))

    def test_sample(self):
        self.check(r(SAMPLE_MD))

    def test_cjk(self):
        self.check(r("中文段落。" * 40))

    def test_deterministic(self):
        self.assertEqual(r(SAMPLE_MD), r(SAMPLE_MD))


class Performance(unittest.TestCase):
    def test_large_document(self):
        md = ("word " * 20000 + "\n\n") + ("中文段落。" * 5000)
        start = time.perf_counter()
        out = r(md)
        elapsed = time.perf_counter() - start
        self.assertGreater(len(out), 10000)
        self.assertLess(elapsed, 2.0)


class Fuzz(unittest.TestCase):
    def test_random_markdown_never_crashes(self):
        import random

        random.seed(7)
        parts = [
            "# Title",
            "## Sub",
            "text",
            "中文段落",
            "- item",
            "1. one",
            "> quote",
            "```",
            "code()",
            "| a | b |",
            "| --- | --- |",
            "**bold**",
            "[link](https://e.com)",
            "https://e.com",
            "---",
            "",
            "  ",
            "\t",
            "😀",
            "a" * 90,
        ]
        for _ in range(200):
            md = "\n".join(random.choice(parts) for _ in range(random.randint(1, 25)))
            out = r(md + "\n", random.choice([1, 10, 40, 75, 200]))
            self.assertTrue(out.endswith("\n"))
            self.assertNotIn("\x00", out)
            self.assertNotIn("\r", out)


@unittest.skipUnless(MACOS, "clipboard tests need macOS")
class Clipboard(SampleCase):
    def test_text_only_and_content(self):
        from AppKit import NSPasteboard, NSPasteboardTypeHTML, NSPasteboardTypeString

        name = f"md2plain-test-{os.getpid()}"
        env = dict(os.environ, MD2PLAIN_PASTEBOARD=name)
        proc = subprocess.run(
            CLI + [str(self.sample)],
            env=env,
            text=True,
            capture_output=True,
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        board = NSPasteboard.pasteboardWithName_(name)
        self.assertIsNone(board.dataForType_(NSPasteboardTypeHTML))
        self.assertEqual(
            board.stringForType_(NSPasteboardTypeString), render_plain(SAMPLE_MD)
        )


@unittest.skipUnless(MACOS, "clipboard tests need macOS")
class Watch(unittest.TestCase):
    def test_watch_updates_clipboard(self):
        from AppKit import NSPasteboard, NSPasteboardTypeString

        name = f"md2plain-watch-{os.getpid()}"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("# A\n\nfirst\n")
            path = f.name
        env = dict(os.environ, MD2PLAIN_PASTEBOARD=name)
        proc = subprocess.Popen(
            CLI + [path, "--watch"],
            env=env,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        board = NSPasteboard.pasteboardWithName_(name)
        try:
            deadline = time.time() + 6
            while time.time() < deadline:
                if "A" in (board.stringForType_(NSPasteboardTypeString) or ""):
                    break
                time.sleep(0.2)
            Path(path).write_text("# B\n\nsecond\n", encoding="utf-8")
            deadline = time.time() + 6
            text = ""
            while time.time() < deadline:
                text = board.stringForType_(NSPasteboardTypeString) or ""
                if "B" in text:
                    break
                time.sleep(0.2)
            self.assertIn("B", text)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
