"""Regression tests for preserving a letter's meaning in plain-text output."""

from __future__ import annotations

import unittest

from wcwidth import wcswidth

from md2plain.render import disp_width, render_plain


class LinkFidelity(unittest.TestCase):
    def test_destinations_survive_in_every_supported_block(self):
        destinations = (
            "https://example.com/apply?token=abc#section",
            "report.pdf?version=2#totals",
            "../documents/report.pdf",
            "ftp://example.com/report.pdf",
            "#details",
        )
        contexts = {
            "paragraph": "Please read {link}.\n",
            "heading": "# {link}\n",
            "list": "- {link}\n",
            "quote": "> {link}\n",
            "table value": "| document |\n| --- |\n| {link} |\n",
            "table heading": "| {link} |\n| --- |\n| ready |\n",
        }
        for destination in destinations:
            link = f"[Report]({destination})"
            for context, template in contexts.items():
                with self.subTest(destination=destination, context=context):
                    out = render_plain(template.format(link=link), width=200)
                    self.assertIn(f"Report ({destination})", out)

    def test_similar_url_labels_do_not_hide_different_targets(self):
        for destination in (
            "https://example.com?token=abc",
            "https://example.com#details",
            "https://example.com/",
        ):
            with self.subTest(destination=destination):
                out = render_plain(f"[https://example.com]({destination})\n", width=200)
                self.assertIn(f"https://example.com ({destination})", out)

    def test_only_an_exact_destination_label_is_not_duplicated(self):
        self.assertEqual(
            render_plain("[https://example.com](https://example.com)\n"),
            "https://example.com\n",
        )
        self.assertEqual(
            render_plain("[alice@example.com](mailto:alice@example.com)\n"),
            "alice@example.com (mailto:alice@example.com)\n",
        )

    def test_long_addresses_remain_copyable_in_narrow_contexts(self):
        url = "https://example.com/download/" + "a" * 90 + "?token=abc#part"
        email = "a" * 70 + "@example.com"
        for address in (url, email):
            for prefix in ("", "- ", "> ", "> > "):
                with self.subTest(address=address, prefix=prefix):
                    markdown = f"{prefix}Please use <{address}> now.\n"
                    out = render_plain(markdown, width=20)
                    self.assertIn(address, out)
                    self.assertTrue(any(address in line for line in out.splitlines()))

    def test_linkified_www_label_is_not_split(self):
        out = render_plain("Please visit www.example.com today.\n", width=10)
        self.assertIn("www.example.com\n", out)
        self.assertIn("(http://www.example.com)", out)


class ImageAndDeletionFidelity(unittest.TestCase):
    def test_image_description_and_source_are_both_kept(self):
        self.assertEqual(
            render_plain("![付款二维码](https://example.com/qr.png)\n", width=100),
            "[图片：付款二维码] (https://example.com/qr.png)\n",
        )

    def test_image_without_alt_keeps_its_source(self):
        self.assertEqual(
            render_plain("![](images/qr.png)\n"),
            "[图片] (images/qr.png)\n",
        )

    def test_deletion_is_not_presented_as_current_text(self):
        self.assertEqual(render_plain("~~周一~~ 周二\n"), "~~周一~~ 周二\n")
        out = render_plain("- ~~旧地址~~ 新地址\n")
        self.assertIn("~~旧地址~~", out)


class CodeFidelity(unittest.TestCase):
    def test_inline_code_keeps_parser_content_and_internal_whitespace(self):
        self.assertEqual(render_plain("Use `a  b` here.\n"), "Use a  b here.\n")
        self.assertEqual(render_plain("`a\tb`\n"), "a\tb\n")
        # CommonMark removes one enclosing space and changes a code newline to
        # a space; the renderer must preserve that parsed content thereafter.
        self.assertEqual(render_plain("` a  b `\n"), "a  b\n")
        self.assertEqual(render_plain("`a\nb`\n"), "a b\n")

    def test_inline_code_is_not_split_to_meet_the_wrap_width(self):
        code = "command  --token=" + "x" * 50
        for prefix in ("", "- ", "> "):
            with self.subTest(prefix=prefix):
                out = render_plain(f"{prefix}Run `{code}` now.\n", width=12)
                self.assertIn(code, out)

    def test_fenced_code_retains_blank_lines_and_trailing_whitespace(self):
        source = "```\nfirst\n\n\nlast  \t\n```\n"
        self.assertEqual(
            render_plain(source),
            "    first\n    \n    \n    last  \t\n",
        )

    def test_final_blank_code_lines_survive_end_of_document(self):
        self.assertEqual(
            render_plain("```\nfirst\n\n\n```\n"),
            "    first\n    \n    \n",
        )

    def test_code_content_is_preserved_inside_a_quote(self):
        self.assertEqual(
            render_plain("> ```\n> a  \n> \n> \n> b\n> ```\n"),
            ">     a  \n>     \n>     \n>     b\n",
        )


class SignatureFidelity(unittest.TestCase):
    def test_exact_signature_delimiter_survives_in_both_break_modes(self):
        for preserve_breaks in (True, False):
            for separator in ("\n", "\n\n"):
                with self.subTest(preserve_breaks=preserve_breaks, separator=separator):
                    source = f"Hello{separator}-- \nAlice\n"
                    self.assertEqual(
                        render_plain(source, preserve_breaks=preserve_breaks),
                        source,
                    )

    def test_signature_retains_nested_quote_depth(self):
        for depth in (1, 2, 3):
            prefix = "> " * depth
            source = f"{prefix}Hello\n{prefix}-- \n{prefix}Alice\n"
            for preserve_breaks in (True, False):
                with self.subTest(depth=depth, preserve_breaks=preserve_breaks):
                    out = render_plain(source, preserve_breaks=preserve_breaks)
                    self.assertEqual(out, source)

    def test_signature_delimiter_at_end_is_not_trimmed(self):
        self.assertEqual(render_plain("Hello\n-- \n"), "Hello\n-- \n")

    def test_soft_breaks_preserve_multiline_signature(self):
        source = "Body line one\nbody line two\n-- \nAlice\nExample Inc.\nLondon\n"
        for preserve in (True, False):
            with self.subTest(preserve=preserve):
                out = render_plain(source, preserve_breaks=preserve)
                self.assertIn("-- \nAlice\nExample Inc.\nLondon\n", out)
                self.assertIn(
                    (
                        "Body line one\nbody line two"
                        if preserve
                        else "Body line one body line two"
                    ),
                    out,
                )

    def test_quoted_signature_does_not_change_surrounding_soft_breaks(self):
        source = "> -- \n> Alice\n> Example Inc.\n\nBody one\nbody two\n"
        out = render_plain(source, preserve_breaks=False)
        self.assertEqual(out, "> -- \n> Alice\n> Example Inc.\n\nBody one body two\n")

    def test_signature_blank_line_after_delimiter_is_kept(self):
        self.assertEqual(render_plain("A\n-- \n\nB\n"), "A\n-- \n\nB\n")

    def test_ordinary_setext_headings_are_unchanged(self):
        self.assertEqual(render_plain("Hello\n--\n"), "Hello\n-----\n")
        self.assertEqual(render_plain("Hello\n---\n"), "Hello\n-----\n")
        self.assertEqual(render_plain("Hello\n===\n"), "Hello\n=====\n")

    def test_ordinary_horizontal_rule_is_unchanged(self):
        self.assertEqual(render_plain("---\n"), "-" * 72 + "\n")

    def test_signature_text_inside_fence_remains_code(self):
        self.assertEqual(
            render_plain("```\nHello\n-- \nAlice\n```\n"),
            "    Hello\n    -- \n    Alice\n",
        )


class UnicodeAndWrapping(unittest.TestCase):
    def assert_lines_fit(self, output: str, width: int):
        for line in output.splitlines():
            self.assertLessEqual(wcswidth(line), width, repr(line))

    def test_combining_mark_has_one_display_column(self):
        self.assertEqual(disp_width("e\u0301"), 1)
        self.assertEqual(render_plain("Ae\u0301B\n", width=1), "A\ne\u0301\nB\n")

    def test_family_emoji_is_one_indivisible_display_grapheme(self):
        family = "👨‍👩‍👧‍👦"
        self.assertEqual(disp_width(family), 2)
        self.assertEqual(render_plain(f"A{family}B\n", width=2), f"A\n{family}\nB\n")
        # A single grapheme may exceed the available width, but must not split.
        self.assertEqual(render_plain(f"{family}A\n", width=1), f"{family}\nA\n")

    def test_graphemes_survive_removed_formatting_boundaries(self):
        for source, visible in (
            ("**👍**🏽", "👍🏽"),
            ("**🇨**🇳", "🇨🇳"),
            ("**👩‍**💻", "👩‍💻"),
            ("`👍`🏽", "👍🏽"),
        ):
            with self.subTest(source=source):
                self.assertEqual(render_plain(source, width=2), visible + "\n")

    def test_ordinary_prose_stays_within_available_width(self):
        prose = "English words 中文内容，继续下一句。 " * 12
        for width in (8, 20, 40):
            for prefix in ("", "- ", "> ", "> > "):
                with self.subTest(width=width, prefix=prefix):
                    self.assert_lines_fit(render_plain(prefix + prose, width), width)

    def test_long_plain_word_still_wraps(self):
        out = render_plain("x" * 100, width=12)
        self.assert_lines_fit(out, 12)
        self.assertEqual("".join(out.splitlines()), "x" * 100)

    def test_punctuation_run_cannot_grow_an_unbounded_line(self):
        source = "文字" + "。！？" * 100
        out = render_plain(source, width=10)
        self.assert_lines_fit(out, 10)
        self.assertEqual("".join(out.splitlines()), source)


class TableFidelity(unittest.TestCase):
    def test_tabs_use_records_without_changing_code_content(self):
        source = "| A | code | C |\n| --- | --- | --- |\n| x | `a\tb` | z |\n"
        out = render_plain(source, width=75)
        self.assertEqual(out, "A: x\ncode: a\tb\nC: z\n")

    def test_small_table_retains_natural_column_layout(self):
        self.assertEqual(
            render_plain("| item | qty |\n| --- | --- |\n| pear | 2 |\n"),
            "item  qty\n----  ---\npear  2\n",
        )

    def test_wide_table_becomes_fields_in_source_row_and_column_order(self):
        source = (
            "| 项目 | 负责人 | 状态 |\n"
            "| --- | --- | --- |\n"
            "| 阶段一 | 张三 | 已完成 |\n"
            "| 阶段二 | 李四 | 待安排 |\n"
        )
        self.assertEqual(
            render_plain(source, width=20),
            "项目: 阶段一\n负责人: 张三\n状态: 已完成\n"
            "\n项目: 阶段二\n负责人: 李四\n状态: 待安排\n",
        )

    def test_fallback_table_retains_links_code_and_deletion(self):
        destination = "https://example.com/apply?token=abc#section"
        source = (
            "| document | command | schedule |\n"
            "| --- | --- | --- |\n"
            f"| [Apply]({destination}) | `a  b` | ~~周一~~ 周二 |\n"
        )
        out = render_plain(source, width=20)
        self.assertIn(destination, out)
        self.assertIn("a  b", out)
        self.assertIn("~~周一~~", out)
        positions = [
            out.index(label) for label in ("document:", "command:", "schedule:")
        ]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
