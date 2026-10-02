"""『평가바이블365 [방문요양] 1. 행동편』 원고(.md)를 장별 블로그 연재 글로 나눈다.

    python book_to_posts.py 원고.md

각 장(## 1 ~ ## 20)에 부록의 같은 번호 실습(### 실습 NN)을 붙여 서식 표기(post_format.py)로
posts/10_SSS_book_NN.md 로 저장한다. SSS 는 발행 순서 번호로, 연재 2화마다
다른 카테고리 글(10_SSS_food/med/policy_KK.md, SSS = 3의 배수) 1편이
음식 → 의료기기 → 정책·청구 순으로 돌아가며 끼도록 비워 둔다.
카드 이미지는 post_images.py 로 따로 만든다.
"""

import re
import sys
from pathlib import Path

POSTS_DIR = Path(__file__).resolve().parent / "posts"
SERIES = "평가바이블365 [방문요양] 1. 행동편"
CATEGORY = "평가바이블365 연재"
FOOTER = "장기요양기관 평가·청구 실무 문의: 동행솔루션 042-673-3338 / donghangsol@naver.com"

CHAPTER_RE = re.compile(r"^## (\d+) (.+)$")
PRACTICE_RE = re.compile(r"^### 실습 (\d+) — (.+)$")


def split_sections(lines, pattern):
    """pattern 에 맞는 줄부터 다음 같은 수준 제목 전까지를 {번호: (제목, 본문줄)} 로 모은다."""
    level = "### " if pattern is PRACTICE_RE else "## "
    out, cur = {}, None
    for line in lines:
        m = pattern.match(line)
        if m:
            cur = int(m.group(1))
            out[cur] = (m.group(2).strip(), [])
            continue
        if cur is not None and (line.startswith(level) or line.startswith("## ")):
            cur = None
        if cur is not None:
            out[cur][1].append(line)
    return out


def styled(lines, heading="## "):
    """원고 마크다운을 글 서식 표기(post_format.py)에 맞게 다듬는다.

    한 줄 전체가 **굵게** 인 줄(장면·멘토·콕 등)은 소제목으로, ### 은 작은 제목으로 바꾸고
    줄 안의 **굵게**, 목록, 표는 그대로 둔다.
    """
    out = []
    for line in lines:
        s = line.rstrip()
        m = re.fullmatch(r"\*\*(.+?)\*\*", s.strip())
        if m:
            s = heading + m.group(1).rstrip(":")
        elif s.startswith("#"):
            s = "### " + s.lstrip("#").strip()
        out.append(s)
    text = "\n".join(out).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def build(manuscript):
    lines = Path(manuscript).read_text(encoding="utf-8").splitlines()
    chapters = split_sections(lines, CHAPTER_RE)
    practices = split_sections(lines, PRACTICE_RE)
    chapters = {n: v for n, v in chapters.items() if 1 <= n <= 20}
    if not chapters:
        raise SystemExit("[ERROR] '## 1 제목' 형식의 장을 찾지 못했습니다.")

    posts = {}
    total = len(chapters)
    for n, (title, body) in sorted(chapters.items()):
        parts = [
            f"카테고리: {CATEGORY}",
            f"[평가바이블365 연재 {n}화] {title}",
            "",
            f"장기요양기관의 실무지침서 **『{SERIES}』** 연재 {n}/{total}화입니다.",
            "",
            "※ 이야기에 등장하는 인물·기관·사건은 모두 가상입니다.",
            "",
            styled(body),
        ]
        if n in practices:
            p_title, p_body = practices[n]
            parts += ["", f"## 이번 화 작성 실습 — {p_title}", "", styled(p_body, heading="### ")]
        parts += ["", "※ 공식 평가기준은 국민건강보험공단의 최신 평가매뉴얼과 공지를 함께 확인해 주세요.", "", f"※ {FOOTER}"]
        posts[n] = "\n".join(parts).strip() + "\n"
    return posts


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용법: python book_to_posts.py 원고.md")
    for n, text in build(sys.argv[1]).items():
        slot = n + (n - 1) // 2  # 연재 2화 → 다른 카테고리 글 1편 순서
        path = POSTS_DIR / f"10_{slot:03d}_book_{n:02d}.md"
        path.write_text(text, encoding="utf-8")
        print(f"[INFO] {path.name} ({len(text):,}자)")
