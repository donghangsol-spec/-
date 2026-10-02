"""posts/ 의 글마다 내용에 맞는 카드 이미지를 7장 이상 만들고, 글 속 알맞은 자리에 넣는다.

    python post_images.py                 # posts/*.md 전체
    python post_images.py posts/a.md ...  # 지정한 글만

이미지는 posts/images/<글 파일 이름>/NN.png 로 저장되고, 글에는 ![설명](images/...) 줄이 들어간다.
다시 실행하면 이전에 넣은 이미지 줄과 파일을 지우고 새로 만든다.
"""

import re
import shutil
import sys
from pathlib import Path

import card_renderer as c

POSTS_DIR = Path(__file__).resolve().parent / "posts"
MIN_IMAGES = 7
IMAGE_LINE = re.compile(r"^!\[.*\]\(images/.*\)\s*$")  # 다시 만들 때 지우는 줄
DIALOGUE = re.compile(r"^[“\"](.+?)[”\"]$")


def clean(text):
    return re.sub(r"\*\*", "", text).strip()


def first_sentence(text, limit=70):
    text = clean(text)
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    s = m.group(1) if m else text
    return s if len(s) <= limit else s[:limit].rstrip() + "…"


def section_ranges(lines):
    """[(제목줄 번호, 제목, 본문 줄 목록)] — '## ' 소제목 기준."""
    heads = [i for i, l in enumerate(lines) if l.startswith("## ")]
    out = []
    for k, i in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        out.append((i, lines[i][3:].strip(), lines[i + 1:end]))
    return out


def list_items(body):
    return [re.sub(r"^(?:-|\d+\.)\s+", "", l.strip()) for l in body if re.match(r"^\s*(?:-|\d+\.)\s+", l)]


def paragraphs(body):
    return [l.strip() for l in body if l.strip() and not re.match(r"^(#|-|\d+\.|\||!\[|※)", l.strip())]


# ── 평가바이블365 연재 ───────────────────────────────────────────────
def book_cards(title, lines):
    """[(이 줄 다음에 넣을 줄 번호, 카드 HTML, 설명)]"""
    m = re.match(r"\[(.+?)\]\s*(.+)", title)
    kicker, name = (m.group(1), m.group(2)) if m else ("평가바이블365 연재", title)
    indicator = next((l.lstrip("# ").strip() for l in lines if re.match(r"^### (연결 )?(지표|주제)", l)), "")
    cards = [(-1, c.cover(kicker, name, indicator), f"{kicker} 표지")]

    sections = section_ranges(lines)
    for i, head, body in sections:
        sm = re.match(r"(장면 \d+)\s*·\s*(.+)", head)
        if sm:
            cards.append((i, c.scene(sm.group(1), sm.group(2)), head))
        elif head.startswith("멘토의 세 가지"):
            items = [clean(x).strip("“”\"") for x in list_items(body)][:3]
            if items:
                cards.append((i, c.numbered("멘토의 세 가지", "오늘 가져갈 것", items), "≡ 멘토의 세 가지"))
        elif head.startswith("콕"):
            text = next((clean(p) for p in paragraphs(body) if "콕!" in p or p.startswith("**콕의 지표 연결")), "")
            text = re.sub(r"^콕의 지표 연결:\s*", "", text)
            text = re.sub(r"^“?여기 하나만 콕!\s*", "", text).strip("“”")
            if text:
                cards.append((i, c.boxed("콕의 지표 설명", indicator or head, text), "콕의 지표 설명"))
        elif head.startswith("이번 화 작성 실습"):
            p_title = head.split("—", 1)[-1].strip()
            rows = []
            for item in list_items(body):
                label = item.split(":", 1)[0].strip()
                if label and "_" in item:
                    rows.append([clean(label), "____________________"])
            if rows:
                cards.append((i, c.table("이번 화 작성 실습", p_title, ["항목", "직접 작성"], rows),
                              f"작성 실습 활동지 — {p_title}"))
            ex = next((clean(l) for l in body if l.startswith("**작성 예시")), "")
            ex_note = next(((n, clean(l)) for n, l in enumerate(lines) if l.startswith("**해설")), None)
            if ex and ex_note:
                rows2 = [["작성 예시", re.sub(r"^작성 예시:\s*", "", ex)],
                         ["해설", re.sub(r"^해설:\s*", "", ex_note[1])]]
                cards.append((ex_note[0], c.table("작성 예시와 해설", p_title, ["구분", "내용"], rows2),
                              "작성 예시와 해설"))

    # 제목이 나오는 대사(없으면 두 번째 장면의 첫 대사)를 인용 카드로
    core = re.sub(r"[^가-힣a-zA-Z0-9]", "", name)[:4]
    dialogues = [(n, DIALOGUE.match(l.strip()).group(1)) for n, l in enumerate(lines) if DIALOGUE.match(l.strip())]
    pick = next(((n, d) for n, d in dialogues if core and core in re.sub(r"[^가-힣a-zA-Z0-9]", "", d)), None)
    scene_heads = [i for i, h, _ in sections if h.startswith("장면")]
    if not pick and len(scene_heads) > 1:
        pick = next(((n, d) for n, d in dialogues if n > scene_heads[1]), None)
    if pick:
        cards.append((pick[0], c.quote(f"“{pick[1]}”"), "이번 화의 한마디"))

    if len(cards) < MIN_IMAGES:  # 장면이 적은 화는 장면 요약표를 더한다
        rows = [[h.split("·", 1)[0].strip(), h.split("·", 1)[-1].strip()] for _, h, _ in sections if h.startswith("장면")]
        mentor = next((i for i, h, _ in sections if h.startswith("멘토")), len(lines) - 1)
        if rows:
            cards.append((mentor - 1, c.table("이번 화 한눈에 보기", name, ["장면", "장소·시간"], rows), "장면 한눈에 보기"))
    return cards


# ── 음식·의료기기·정책 글 ─────────────────────────────────────────────
def article_cards(category, title, lines):
    cards = [(-1, c.cover(category or "동행솔루션 블로그", title), f"{title} 표지")]
    intro = next((l for l in lines if l.strip() and not l.startswith(("#", "!", "-", "※"))), "")
    sections = section_ranges(lines)

    summary, checks = [], []
    for i, head, body in sections:
        items = [clean(x) for x in list_items(body)]
        paras = paragraphs(body)
        if items:
            short = [first_sentence(x, 60) for x in items][:5]
            card = (c.numbered if re.match(r"^\d+\.", body[0].strip() if body else "") else c.checklist)
            cards.append((i, card(category or "", head, short), head))
            checks += short[:2]
            summary.append([re.sub(r"^\d+\.\s*", "", head), short[0]])
        elif paras:
            cards.append((i, c.boxed(category or "", head, first_sentence(paras[0], 120)), head))
            summary.append([re.sub(r"^\d+\.\s*", "", head), first_sentence(paras[0], 60)])

    end = next((n for n, l in enumerate(lines) if l.startswith("※")), len(lines)) - 1
    # 마무리 문장(없으면 첫 문장)을 '기억해 두세요' 카드로
    tail = [p for p in paragraphs(lines[:end + 1]) if p != intro and "http" not in p and not p.startswith("출처")]
    key = tail[-1] if tail else ("" if "http" in intro else intro)
    if key:
        cards.append((end, c.quote(first_sentence(key, 90), "기억해 두세요"), "기억해 두세요"))
    if summary:
        cards.append((end, c.table("한눈에 보기", title, ["항목", "핵심"], summary), "한눈에 보기 요약표"))
    if len(cards) < MIN_IMAGES and checks:
        cards.append((end, c.checklist("체크리스트", "오늘 확인할 것", checks[:6]), "체크리스트"))
    return cards


def process(path, renderer):
    text = path.read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if not IMAGE_LINE.match(l.strip())]
    category = lines[0].split(":", 1)[1].strip() if lines and lines[0].startswith("카테고리:") else ""
    head_n = 2 if category else 1
    title, body = lines[head_n - 1].strip(), lines[head_n:]

    cards = book_cards(title, body) if "_book_" in path.name else article_cards(category, title, body)

    img_dir = POSTS_DIR / "images" / path.stem
    shutil.rmtree(img_dir, ignore_errors=True)
    inserts = {}
    for k, (after, card_html, alt) in enumerate(sorted(cards, key=lambda x: x[0]), 1):
        rel = f"images/{path.stem}/{k:02d}.png"
        renderer.save(card_html, POSTS_DIR / rel)
        inserts.setdefault(after, []).append(f"![{alt}]({rel})")

    out = lines[:head_n] + [x for img in inserts.get(-1, []) for x in (img, "")]
    for n, l in enumerate(body):
        out.append(l)
        for img in inserts.get(n, []):
            out += ["", img, ""]
    path.write_text(re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n", encoding="utf-8")
    return len(cards)


if __name__ == "__main__":
    files = [Path(a) for a in sys.argv[1:]] or sorted(POSTS_DIR.glob("*.md"))
    with c.Renderer() as r:
        for f in files:
            n = process(f, r)
            flag = "" if n >= MIN_IMAGES else f"  ← {MIN_IMAGES}장 미만"
            print(f"[INFO] {f.name}: 이미지 {n}장{flag}")
