"""Render Markdown as plain-text email in reStructuredText style.

Headings use = / - / ~ underlines, paragraphs are hard-wrapped at 75
columns (CJK counts as two), lists use "*", quotes use ">", and code is
indented by four spaces.
"""

from __future__ import annotations

import re
import unicodedata

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

UNDERLINE = {1: "=", 2: "-", 3: "~", 4: "^", 5: '"', 6: "'"}
QUOTE = ">"

# Punctuation that must not start a line (CJK line-breaking rule).
NO_LINE_START = set("。，、；：！？）〕］｝》」』】’”…·%,.;:!?)]}'\"")
# Link schemes that are safe to keep.
SAFE_LINK = re.compile(r"^(https?://|mailto:|#)", re.IGNORECASE)


def char_width(ch: str) -> int:
    """Display width of one character: 2 for wide (CJK) characters."""
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def disp_width(text: str) -> int:
    return sum(char_width(c) for c in text)


# --------------------------------------------------------------------- inline


def inline_text(node: SyntaxTreeNode, with_urls: bool = True) -> str:
    """Flatten an inline node to text; links become "label (url)"."""
    kind = node.type

    if kind in ("text", "code_inline"):
        return node.content
    if kind == "softbreak":
        return " "
    if kind == "hardbreak":
        return "\n"
    if kind == "image":
        return node.content or (node.attrs.get("src") or "")
    if kind == "html_inline":
        return ""
    if kind == "link":
        label = "".join(inline_text(c, False) for c in node.children)
        href = node.attrs.get("href") or ""
        if not with_urls or not href or not SAFE_LINK.match(href):
            return label
        # Do not repeat a bare address: mailto:a@b.com with label a@b.com.
        if href.lower().startswith("mailto:") and href[7:] == label:
            return label
        # A URL used as its own label needs no "(url)" suffix, even when the
        # target only differs by tracking parameters.
        if label.startswith(("http://", "https://")):
            base = href.split("?", 1)[0].split("#", 1)[0].rstrip("/")
            if base == label.rstrip("/"):
                return label
        if href != label:
            return f"{label} ({href})"
        return label

    return "".join(inline_text(c, with_urls) for c in node.children)


def plain_of(node: SyntaxTreeNode) -> str:
    return inline_text(node, with_urls=False)


# ----------------------------------------------------------------------- wrap


def wrap_line(line: str, width: int) -> list[str]:
    """Wrap one line at spaces, breaking CJK text between characters."""
    line = re.sub(r"[ \t]+", " ", line).strip()
    if not line:
        return [""]

    out: list[str] = []
    current: list[str] = []
    current_width = 0
    last_space = -1

    for ch in line:
        w = char_width(ch)
        if current and current_width + w > width:
            if ch in NO_LINE_START:
                current.append(ch)
                current_width += w
                continue

            if last_space > 0:
                out.append("".join(current[:last_space]).rstrip())
                current = current[last_space + 1 :]
            else:
                out.append("".join(current).rstrip())
                current = []

            current_width = sum(char_width(c) for c in current)
            last_space = -1
            for i, c in enumerate(current):
                if c == " ":
                    last_space = i

        current.append(ch)
        current_width += w
        if ch == " ":
            last_space = len(current) - 1

    if current:
        out.append("".join(current).rstrip())
    # Very small widths can produce blank lines; keep the result non-empty.
    return [line for line in out if line] or [""]


def wrap_text(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for part in text.split("\n"):
        lines.extend(wrap_line(part, width))
    return lines


# --------------------------------------------------------------------- blocks


def render_blocks(nodes: list[SyntaxTreeNode], width: int) -> list[str]:
    out: list[str] = []

    for node in nodes:
        kind = node.type

        if kind == "heading":
            level = int(node.tag[1])
            text = plain_of(node.children[0]).strip()
            if not text:
                continue
            mark = UNDERLINE.get(level, "-")
            out += [text, mark * max(disp_width(text), 3), ""]

        elif kind == "paragraph":
            out += wrap_text(inline_text(node.children[0]), width)
            out.append("")

        elif kind in ("bullet_list", "ordered_list"):
            out += render_list(node, width)

        elif kind == "blockquote":
            body = render_blocks(node.children, width - 2)
            while body and not body[-1]:
                body.pop()
            out += [QUOTE if not line else f"{QUOTE} {line}" for line in body]
            out.append("")

        elif kind in ("fence", "code_block"):
            code = (node.content or "").rstrip("\n").split("\n")
            out += ["    " + line for line in code]
            out.append("")

        elif kind == "hr":
            out += ["-" * min(width, 72), ""]

        elif kind == "table":
            out += render_table(node, width)
            out.append("")

        elif kind == "html_block":
            continue

        elif node.children:
            out += render_blocks(node.children, width)

    return out


def render_list(node: SyntaxTreeNode, width: int) -> list[str]:
    ordered = node.type == "ordered_list"
    start = int(node.attrs.get("start", 1)) if ordered else None
    out: list[str] = []

    for i, item in enumerate(node.children):
        marker = f"{start + i}. " if start is not None else "* "
        body = render_blocks(item.children, width - len(marker))
        while body and not body[-1]:
            body.pop()

        # Keep nested lists tight: drop the blank line before them.
        tight: list[str] = []
        for k, line in enumerate(body):
            if not line:
                nxt = k + 1
                while nxt < len(body) and not body[nxt]:
                    nxt += 1
                if nxt < len(body) and re.match(r"^(\* |\d+\. )", body[nxt]):
                    continue
            tight.append(line)

        for j, line in enumerate(tight):
            out.append((marker if j == 0 else " " * len(marker)) + line)

    out.append("")
    return out


def render_table(node: SyntaxTreeNode, width: int) -> list[str]:
    rows: list[list[str]] = []
    for section in node.children:
        for tr in section.children:
            cells = [
                "".join(plain_of(c) for c in cell.children).strip()
                for cell in tr.children
            ]
            if cells:
                rows.append(cells)
    if not rows:
        return []

    ncols = max(len(row) for row in rows)
    for row in rows:
        row.extend([""] * (ncols - len(row)))

    widths = [max(disp_width(row[c]) for row in rows) for c in range(ncols)]
    while sum(widths) + 2 * (ncols - 1) > width and max(widths) > 4:
        widths[widths.index(max(widths))] -= 1

    def fmt(row: list[str]) -> str:
        padded = []
        for c, cell in enumerate(row):
            padded.append(cell + " " * max(widths[c] - disp_width(cell), 0))
        return "  ".join(padded).rstrip()

    lines = [fmt(rows[0]), "  ".join("-" * w for w in widths)]
    lines += [fmt(row) for row in rows[1:]]
    return lines


# --------------------------------------------------------------------- output


def parse(md_text: str, preserve_breaks: bool = True) -> SyntaxTreeNode:
    md = MarkdownIt(
        "commonmark", {"html": False, "linkify": True, "typographer": False}
    )
    md.enable(["table", "strikethrough", "linkify"])
    tokens = md.parse(md_text)

    if preserve_breaks:
        # A single newline usually means a real line break here (signatures,
        # dates), unlike CommonMark's default of joining it with a space.
        for token in tokens:
            if token.type == "inline" and token.children:
                for child in token.children:
                    if child.type == "softbreak":
                        child.type = "hardbreak"

    return SyntaxTreeNode(tokens)


def tidy(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        line = line.rstrip()
        if not line and out and not out[-1]:
            continue
        out.append(line)
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return out


def render_plain(md_text: str, width: int = 75, preserve_breaks: bool = True) -> str:
    lines = tidy(render_blocks(parse(md_text, preserve_breaks).children, width))
    return "\n".join(lines) + "\n"
