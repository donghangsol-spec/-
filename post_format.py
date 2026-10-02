"""글 파일의 간단한 서식 표기를 네이버 에디터에 붙여 넣을 HTML 조각과 이미지 순서로 바꾼다.

지원하는 표기 (한 줄 단위):
    ## 소제목          큰 소제목
    ### 작은 제목       작은 소제목
    > 문장             인용 상자
    - 항목 / 1. 항목   목록
    | 칸 | 칸 |        표 (첫 줄은 머리글, |---| 줄은 무시)
    ![설명](경로.png)  그 자리에 사진 업로드 (설명이 "≡ "로 시작하면 바로 다음 목록은 사진으로 대신한다)
    ※ 문장             작은 회색 안내문
    **굵게**           줄 안의 강조
빈 줄은 문단 구분이다. 표기가 없는 글도 그대로 일반 문단으로 처리된다.
"""

import html
import re
from pathlib import Path

NAVY = "#1f3a68"
ORANGE = "#d9822b"
TEXT = "#333333"
GRAY = "#888888"

# 네이버 에디터 글자 크기 단계(11·13·15·16·19·24·28…)에 맞춘다.
BODY = f"font-size:16px;line-height:1.9;color:{TEXT};"
H2 = f"font-size:24px;font-weight:bold;color:{NAVY};"
H3 = f"font-size:19px;font-weight:bold;color:{ORANGE};"
NOTE = f"font-size:13px;color:{GRAY};"

IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")
LIST_RE = re.compile(r"^(?:[-·•]|\d+\.)\s+(.*)$")


def inline(text):
    """**굵게** 를 <b> 로 바꾸고 나머지는 HTML 이스케이프한다."""
    parts = re.split(r"(\*\*.+?\*\*)", text)
    out = []
    for p in parts:
        if p.startswith("**") and p.endswith("**") and len(p) > 4:
            out.append(f'<b style="color:{NAVY};">{html.escape(p[2:-2])}</b>')
        else:
            out.append(html.escape(p))
    return "".join(out)


def strip_marks(text):
    return text.replace("**", "")


def parse(body):
    """본문을 블록 목록 [(종류, 값)] 으로 나눈다."""
    blocks, para, table, items = [], [], [], []

    def flush():
        nonlocal para, table, items
        if para:
            blocks.append(("p", " ".join(para)))
        if table:
            blocks.append(("table", table))
        if items:
            blocks.append(("list", items))
        para, table, items = [], [], []

    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("|"):
            if para or items:
                flush()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                table.append(cells)
            continue
        m = LIST_RE.match(line)
        if m and not line.startswith("**"):
            if para or table:
                flush()
            items.append(m.group(1))
            continue
        flush()
        if line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("> "):
            blocks.append(("quote", line[2:].strip()))
        elif line.startswith("※"):
            blocks.append(("note", line))
        elif IMAGE_RE.match(line):
            alt, path = IMAGE_RE.match(line).groups()
            blocks.append(("image", (alt, path)))
        else:
            para.append(line)
            flush()  # 원고의 한 줄은 한 문단으로 둔다
    flush()
    return blocks


def block_html(kind, value):
    if kind == "p":
        return f'<p style="{BODY}">{inline(value)}</p>'
    if kind == "h2":
        return f'<p><br></p><p style="{H2}">{inline(value)}</p>'
    if kind == "h3":
        return f'<p style="{H3}">{inline(value)}</p>'
    if kind == "note":
        return f'<p style="{NOTE}">{inline(value)}</p>'
    if kind == "quote":
        return (f'<blockquote style="border-left:4px solid {ORANGE};padding:6px 14px;margin:12px 0;">'
                f'<p style="{BODY}font-weight:bold;">{inline(value)}</p></blockquote>')
    if kind == "list":
        lis = "".join(f'<li style="{BODY}">{inline(i)}</li>' for i in value)
        return f"<ul>{lis}</ul>"
    if kind == "table":
        head, *rows = value
        th = "".join(f'<td style="background:{NAVY};color:#fff;font-weight:bold;padding:8px;'
                     f'border:1px solid #c9d3e3;">{inline(c)}</td>' for c in head)
        trs = "".join(
            "<tr>" + "".join(f'<td style="padding:8px;border:1px solid #c9d3e3;">{inline(c)}</td>'
                             for c in r) + "</tr>" for r in rows)
        return (f'<table style="border-collapse:collapse;width:100%;font-size:15px;">'
                f"<tr>{th}</tr>{trs}</table><p><br></p>")
    raise ValueError(kind)


def block_text(kind, value):
    if kind in ("p", "h2", "h3", "note", "quote"):
        return strip_marks(value)
    if kind == "list":
        return "\n".join("- " + strip_marks(i) for i in value)
    if kind == "table":
        head, *rows = value
        return "\n".join(" / ".join(f"{h}: {c}" for h, c in zip(head, r)) for r in rows)
    return ""


def visible_blocks(blocks):
    """카드 사진과 내용이 겹치는 블록을 뺀다.

    - 소제목 바로 뒤에 같은 이름의 사진이 오면 소제목 글자는 생략한다 (장면 카드 등).
    - 설명이 "≡ "로 시작하는 사진 바로 뒤의 목록은 사진이 대신한다 (멘토의 세 가지 등).
    """
    out, skip_list = [], False
    for n, (kind, value) in enumerate(blocks):
        nxt = blocks[n + 1] if n + 1 < len(blocks) else (None, None)
        if kind == "h2" and nxt[0] == "image" and nxt[1][0].lstrip("≡ ").strip() == value.strip():
            continue
        if kind == "list" and skip_list:
            skip_list = False
            continue
        skip_list = kind == "image" and value[0].startswith("≡")
        out.append((kind, value))
    return out


def segments(body, base_dir):
    """[("rich", html, 일반텍스트) 또는 ("image", 경로, 설명)] 순서 목록."""
    out, chunk_html, chunk_text = [], [], []
    prev = None
    for kind, value in visible_blocks(parse(body)):
        if kind == "p" and prev == "p":  # 문단 사이 한 줄 띄우기
            chunk_html.append("<p><br></p>")
        prev = kind
        if kind == "image":
            if chunk_html:
                out.append(("rich", "".join(chunk_html), "\n\n".join(chunk_text)))
                chunk_html, chunk_text = [], []
            alt, rel = value
            out.append(("image", str((Path(base_dir) / rel).resolve()), alt.lstrip("≡ ")))
        else:
            chunk_html.append(block_html(kind, value))
            chunk_text.append(block_text(kind, value))
    if chunk_html:
        out.append(("rich", "".join(chunk_html), "\n\n".join(chunk_text)))
    return out


def plain_text(body):
    """서식 없이 입력할 때 쓰는 일반 텍스트."""
    return "\n\n".join(block_text(k, v) for k, v in parse(body) if k != "image")
