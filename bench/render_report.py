"""Render the headings, tables, lists, links and code used by our Markdown reports."""

import argparse
import html
import re
from pathlib import Path


def inline(text):
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)


def render(markdown):
    lines = markdown.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            i += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading:
            level = len(heading[1])
            blocks.append(f"<h{level}>" + inline(heading[2]) + f"</h{level}>")
            i += 1
            continue
        if (
            line.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|[\s:|\-]+\|\s*$", lines[i + 1])
        ):
            heads = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append("<tr>" + "".join("<td>" + inline(c) + "</td>" for c in cells) + "</tr>")
                i += 1
            blocks.append(
                '<div class="table-wrap"><table><thead><tr>'
                + "".join('<th scope="col">' + inline(c) + "</th>" for c in heads)
                + "</tr></thead><tbody>"
                + "".join(rows)
                + "</tbody></table></div>"
            )
            continue
        bullet = re.match(r"^[-*]\s+(.+)", line)
        ordered = re.match(r"^\d+\.\s+(.+)", line)
        if bullet or ordered:
            tag = "ul" if bullet else "ol"
            items = []
            while i < len(lines):
                m = re.match(r"^[-*]\s+(.+)" if tag == "ul" else r"^\d+\.\s+(.+)", lines[i])
                if not m:
                    break
                items.append("<li>" + inline(m[1]) + "</li>")
                i += 1
                if (
                    i < len(lines)
                    and not lines[i].strip()
                    and i + 1 < len(lines)
                    and re.match(r"^[-*]\s+" if tag == "ul" else r"^\d+\.\s+", lines[i + 1])
                ):
                    i += 1
            blocks.append("<" + tag + ">" + "".join(items) + "</" + tag + ">")
            continue
        paragraph = [line]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not re.match(r"^(?:#|\||```|[-*]\s|\d+\.\s)", lines[i])
        ):
            paragraph.append(lines[i])
            i += 1
        blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
    return "\n".join(blocks)


def write_html(source, target=None):
    source = Path(source)
    target = Path(target) if target else source.with_suffix(".html")
    markdown = source.read_text()
    title = next(
        (
            line.removeprefix("# ").strip()
            for line in markdown.splitlines()
            if line.startswith("# ")
        ),
        source.stem,
    )
    css = """
:root{color-scheme:light dark;--bg:#f4f6fa;--paper:#fff;--ink:#182338;--muted:#536177;--line:#dbe2ed;--accent:#1759b8;--head:#edf3fc}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:36px auto;padding:36px 44px;background:var(--paper);border:1px solid var(--line);border-radius:14px}
nav{font-size:.9rem;color:var(--muted);margin-bottom:24px}h1{font-size:2.1rem;line-height:1.2;letter-spacing:-.025em}h2{margin-top:2.1rem;font-size:1.35rem}p{max-width:90ch}
a{color:var(--accent);text-underline-offset:3px}code{font:.9em ui-monospace,Consolas,monospace;background:var(--head);padding:.1em .3em;border-radius:4px}pre{overflow:auto;padding:16px;background:var(--head)}pre code{padding:0}
.table-wrap{overflow-x:auto;margin:20px 0}table{border-collapse:collapse;width:100%;font-size:.94rem;font-variant-numeric:tabular-nums}th,td{padding:11px 14px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th{background:var(--head);font-weight:650}th:first-child,td:first-child{text-align:left}tbody tr:hover{background:var(--head)}footer{margin-top:30px;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:14px}
@media(max-width:700px){main{margin:0;border:0;border-radius:0;padding:22px 18px}h1{font-size:1.7rem}th,td{padding:9px}}
@media(prefers-color-scheme:dark){:root{--bg:#101722;--paper:#172130;--ink:#e1e8f2;--muted:#b1bfd3;--line:#35445a;--accent:#8dbbff;--head:#24344b}}
@media print{:root{color-scheme:light;--paper:#fff;--ink:#000;--line:#bbb;--head:#eee}body{background:#fff;font-size:11pt}main{max-width:none;margin:0;border:0;padding:0}nav{display:none}h2{break-after:avoid}table{break-inside:avoid}a{color:inherit}}
"""
    doc = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
        + html.escape(title)
        + "</title><style>"
        + css
        + '</style></head><body><main><nav>Codectx evaluation · <a href="'
        + html.escape(source.name, quote=True)
        + '">Markdown version</a></nav>'
        + render(markdown)
        + "<footer>Rendered from "
        + html.escape(source.name)
        + ". All measurements and qualifications are preserved from the Markdown report.</footer></main></body></html>\n"
    )
    target.write_text(doc)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(write_html(args.markdown, args.output))
