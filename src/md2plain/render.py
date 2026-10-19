"""Render Markdown email bodies without losing links or literal content.

Ordinary prose targets 75 display columns. URLs, email addresses, inline
code, and code blocks remain intact even when they exceed that target.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.rules_block import lheading
from markdown_it.rules_block.state_block import StateBlock
from markdown_it.tree import SyntaxTreeNode
from wcwidth import iter_graphemes, wcswidth

UNDERLINE = {1: "=", 2: "-", 3: "~", 4: "^", 5: '"', 6: "'"}
NO_LINE_START = set("。，、；：！？）〕］｝》」』】’”…·%,.;:!?)]}'\"")


@dataclass(frozen=True)
class Span:
    text: str
    literal: bool = False


@dataclass(frozen=True)
class Line:
    text: str
    literal: bool = False


def disp_width(text: str) -> int:
    """Approximate monospace width without splitting Unicode graphemes."""
    return max(wcswidth(text.expandtabs(4)), 0)


def char_width(ch: str) -> int:
    return disp_width(ch)


def inline_spans(node: SyntaxTreeNode, with_urls: bool = True) -> list[Span]:
    kind = node.type
    if kind == "text":
        return [Span(node.content)]
    if kind == "code_inline":
        return [Span(node.content, True)]
    if kind == "softbreak":
        return [Span(" ")]
    if kind == "hardbreak":
        return [Span("\n")]
    if kind == "image":
        alt = "".join(inline_text(c, False) for c in node.children).strip()
        label = f"[图片：{alt}]" if alt else "[图片]"
        src = node.attrs.get("src") or ""
        return [Span(label)] + ([Span(" "), Span(f"({src})", True)] if src else [])
    if kind == "link":
        label = [s for c in node.children for s in inline_spans(c, False)]
        href = node.attrs.get("href") or ""
        label_text = "".join(s.text for s in label)
        if not with_urls or not href:
            return label
        if label_text == href:
            return [Span(href, True)]
        if node.markup in ("autolink", "linkify") or re.fullmatch(
            r"(?:[a-z][a-z0-9+.-]*://\S+|[^\s@]+@[^\s@]+\.[^\s@]+)",
            label_text,
            re.IGNORECASE,
        ):
            label = [Span(label_text, True)]
        # The link target is data: query strings, fragments and paths stay intact.
        return label + [Span(" "), Span(f"({href})", True)]
    if kind == "s":
        return (
            [Span("~~")]
            + [s for c in node.children for s in inline_spans(c, with_urls)]
            + [Span("~~")]
        )
    if kind == "html_inline":
        return []
    return [s for c in node.children for s in inline_spans(c, with_urls)]


def inline_text(node: SyntaxTreeNode, with_urls: bool = True) -> str:
    return "".join(s.text for s in inline_spans(node, with_urls))


def _units(spans: list[Span]) -> list[Span]:
    """Segment the final visible text, preserving literal spans as atomic units.

    A grapheme can cross a formatting or literal boundary (for example an
    emoji modifier after bold text). Expand literal boundaries to include
    the whole grapheme rather than segmenting each span independently.
    """
    text = "".join(span.text for span in spans)
    ranges: list[tuple[int, int]] = []
    position = 0
    for span in spans:
        end = position + len(span.text)
        if span.literal and end > position:
            ranges.append((position, end))
        position = end

    units: list[Span] = []
    literal: list[str] = []
    position = range_index = protected_until = 0
    for grapheme in iter_graphemes(text):
        end = position + len(grapheme)
        while range_index < len(ranges) and ranges[range_index][0] < end:
            protected_until = max(protected_until, ranges[range_index][1])
            range_index += 1
        if grapheme == "\n" or position >= protected_until:
            if literal:
                units.append(Span("".join(literal), True))
                literal = []
            units.append(Span(" " if grapheme == "\t" else grapheme))
        else:
            literal.append(grapheme)
        position = end
    if literal:
        units.append(Span("".join(literal), True))
    return units


def wrap_spans(spans: list[Span], width: int) -> list[Line]:
    width = max(width, 1)
    lines: list[Line] = []
    current: list[Span] = []
    used = 0

    def emit(parts: list[Span]) -> None:
        while parts and parts[-1] == Span(" "):
            parts.pop()
        lines.append(
            Line("".join(p.text for p in parts), any(p.literal for p in parts))
        )

    for unit in _units(spans):
        if unit.text == "\n":
            emit(current)
            current, used = [], 0
            continue
        if unit == Span(" "):
            if current and current[-1] != Span(" "):
                current.append(unit)
                used += 1
            continue

        size = disp_width(unit.text)
        while current and used + size > width:
            # Put a protected value on a fresh line; never split or normalize it.
            if unit.literal:
                emit(current)
                current, used = [], 0
                break
            spaces = [i for i, p in enumerate(current) if p == Span(" ")]
            if spaces:
                split = spaces[-1]
                emit(current[:split])
                current = current[split + 1 :]
            elif (
                unit.text in NO_LINE_START
                and len(current) > 1
                and not current[-1].literal
                and disp_width(current[-1].text) + size <= width
            ):
                # Move the preceding grapheme with punctuation, rather than
                # extending an already full line for an arbitrary punctuation run.
                emit(current[:-1])
                current = current[-1:]
            else:
                # Punctuation immediately following an overwide literal belongs
                # with it. This exception never grows ordinary prose without bound.
                if current[-1].literal and unit.text in NO_LINE_START:
                    break
                emit(current)
                current = []
            used = sum(disp_width(p.text) for p in current)
        current.append(unit)
        used += size
    if current or not lines:
        emit(current)
    return lines


def wrap_line(line: str, width: int) -> list[str]:
    return [line.text for line in wrap_spans([Span(line)], width)]


def wrap_text(text: str, width: int) -> list[str]:
    return wrap_line(text, width)


def _is_signature(state: StateBlock, line: int) -> bool:
    if state.is_code_block(line):
        return False
    start = state.bMarks[line] + state.tShift[line]
    return state.src[start : state.eMarks[line]] == "-- "


def _signature(state: StateBlock, start: int, end: int, silent: bool) -> bool:
    if not _is_signature(state, start):
        return False
    if not silent:
        token = state.push("mail_signature", "", 0)
        token.content = "-- "
        token.map = [start, start + 1]
        token.meta["blank_before"] = start == 0 or state.isEmpty(start - 1)
        token.meta["blank_after"] = start + 1 < end and state.isEmpty(start + 1)
        state.line = start + 1
    return True


def _email_lheading(state: StateBlock, start: int, end: int, silent: bool) -> bool:
    """Keep setext headings, except when their underline is a mail signature."""
    old_line, parent, count = state.line, state.parentType, len(state.tokens)
    matched = lheading(state, start, end, silent)
    if matched and _is_signature(state, state.line - 1):
        del state.tokens[count:]
        state.line, state.parentType = old_line, parent
        return False
    return matched


def parse(md_text: str, preserve_breaks: bool = True) -> SyntaxTreeNode:
    md = MarkdownIt(
        "commonmark", {"html": False, "linkify": True, "typographer": False}
    )
    md.enable(["table", "strikethrough", "linkify"])
    md.block.ruler.at("lheading", _email_lheading)
    md.block.ruler.before(
        "lheading",
        "mail_signature",
        _signature,
        {"alt": ["paragraph", "reference", "blockquote"]},
    )
    tokens = md.parse(md_text)
    # A signature lasts until its containing quote/list item ends. Soft-break
    # joining applies to body prose, never to the signature's address lines.
    signatures = [False]
    containers = {"blockquote_open", "list_item_open"}
    closes = {"blockquote_close", "list_item_close"}
    for token in tokens:
        if token.type in containers:
            signatures.append(False)
        elif token.type in closes:
            signatures.pop()
        elif token.type == "mail_signature":
            signatures[-1] = True
        if (
            token.type == "inline"
            and token.children
            and (preserve_breaks or any(signatures))
        ):
            for child in token.children:
                if child.type == "softbreak":
                    child.type = "hardbreak"
    return SyntaxTreeNode(tokens)


def _trim_separators(lines: list[Line]) -> list[Line]:
    while lines and lines[-1] == Line(""):
        lines.pop()
    return lines


def render_blocks(nodes: list[SyntaxTreeNode], width: int) -> list[Line]:
    out: list[Line] = []
    for node in nodes:
        kind = node.type
        if kind == "heading":
            spans = inline_spans(node.children[0])
            if not "".join(s.text for s in spans).strip():
                continue
            title = wrap_spans(spans, width)
            length = max(3, min(max(width, 1), max(disp_width(x.text) for x in title)))
            out += title + [Line(UNDERLINE[int(node.tag[1])] * length), Line("")]
        elif kind == "paragraph":
            out += wrap_spans(inline_spans(node.children[0]), width) + [Line("")]
        elif kind == "mail_signature":
            if not node.meta.get("blank_before"):
                _trim_separators(out)
            out.append(Line("-- ", True))
            if node.meta.get("blank_after"):
                out.append(Line(""))
        elif kind in ("bullet_list", "ordered_list"):
            out += render_list(node, width)
        elif kind == "blockquote":
            body = _trim_separators(render_blocks(node.children, max(width - 2, 1)))
            out += [Line(">" if not x.text else f"> {x.text}", x.literal) for x in body]
            out.append(Line(""))
        elif kind in ("fence", "code_block"):
            # Remove only the parser's final line terminator, not blank code lines.
            content = node.content.removesuffix("\n")
            if node.content:
                out += [Line("    " + text, True) for text in content.split("\n")]
            out.append(Line(""))
        elif kind == "hr":
            out += [Line("-" * max(1, min(width, 72))), Line("")]
        elif kind == "table":
            out += render_table(node, width) + [Line("")]
        elif kind == "html_block":
            continue
        elif node.children:
            out += render_blocks(node.children, width)
    return out


def render_list(node: SyntaxTreeNode, width: int) -> list[Line]:
    start = int(node.attrs.get("start", 1)) if node.type == "ordered_list" else None
    out: list[Line] = []
    for i, item in enumerate(node.children):
        marker = f"{start + i}. " if start is not None else "* "
        body = _trim_separators(
            render_blocks(item.children, max(width - len(marker), 1))
        )
        tight: list[Line] = []
        for k, line in enumerate(body):
            if line == Line(""):
                nxt = k + 1
                while nxt < len(body) and body[nxt] == Line(""):
                    nxt += 1
                if nxt < len(body) and re.match(r"^(\* |\d+\. )", body[nxt].text):
                    continue
            tight.append(line)
        out += [
            Line((marker if j == 0 else " " * len(marker)) + line.text, line.literal)
            for j, line in enumerate(tight)
        ]
    return out + [Line("")]


def render_table(node: SyntaxTreeNode, width: int) -> list[Line]:
    rows: list[list[list[Span]]] = []
    for section in node.children:
        for tr in section.children:
            cells = [
                [s for c in cell.children for s in inline_spans(c)]
                for cell in tr.children
            ]
            if cells:
                rows.append(cells)
    if not rows:
        return []
    ncols = max(map(len, rows))
    for row in rows:
        row.extend([[] for _ in range(ncols - len(row))])
    texts = [["".join(s.text for s in cell) for cell in row] for row in rows]
    widths = [max(disp_width(row[c]) for row in texts) for c in range(ncols)]
    if sum(widths) + 2 * (ncols - 1) <= width and all(
        "\n" not in cell and "\t" not in cell for row in texts for cell in row
    ):

        def fmt(index: int) -> Line:
            row = texts[index]
            padded = [
                cell + (" " * (widths[c] - disp_width(cell)) if c < ncols - 1 else "")
                for c, cell in enumerate(row)
            ]
            return Line(
                "  ".join(padded), any(s.literal for cell in rows[index] for s in cell)
            )

        return [fmt(0), Line("  ".join("-" * w for w in widths))] + [
            fmt(i) for i in range(1, len(rows))
        ]
    out: list[Line] = []
    # A header-only table still conveys column names.
    for row in rows[1:] or [[[] for _ in range(ncols)]]:
        for c, cell in enumerate(row):
            header = rows[0][c] or [Span(f"Column {c + 1}")]
            out += wrap_spans(header + [Span(": ")] + cell, width)
        out.append(Line(""))
    return _trim_separators(out)


def tidy(lines: list[Line]) -> list[Line]:
    out: list[Line] = []
    for line in lines:
        if not line.literal:
            line = Line(line.text.rstrip())
        if line == Line("") and (not out or out[-1] == Line("")):
            continue
        out.append(line)
    return _trim_separators(out)


def render_plain(md_text: str, width: int = 75, preserve_breaks: bool = True) -> str:
    if width < 1:
        raise ValueError("width must be at least 1")
    lines = tidy(render_blocks(parse(md_text, preserve_breaks).children, width))
    return "\n".join(line.text for line in lines) + "\n"
