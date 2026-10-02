"""보건복지부·국민건강보험공단(노인장기요양보험) 게시판 새 글을 수집해 posts/ 대기열에 블로그 글로 만든다.

sources.json 의 게시판 목록 첫 페이지(들)를 읽고, 제목에 키워드가 들어간 새 글만
본문·첨부파일 목록과 원문 링크를 붙여 posts/00_news_*.md 로 저장한다.
이미 수집한 글은 data/seen.json 에 기록해 다시 만들지 않는다.

    python notice_collector.py            # 수집해서 posts/ 에 저장
    python notice_collector.py --dry-run  # 찾은 글 목록만 출력 (저장 안 함)
"""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SOURCES_FILE = BASE_DIR / "sources.json"
SEEN_FILE = BASE_DIR / "data" / "seen.json"
POSTS_DIR = BASE_DIR / "posts"

DATE_RE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
FILE_RE = re.compile(r"\.(hwpx?|pdf|xlsx?|docx?|pptx?|zip)\b", re.I)

# 게시판 목록에서 글 링크와 그 행(row)의 텍스트를 뽑는다.
LIST_JS = """
els => els.map(a => {
  const row = a.closest('tr, li');
  return {
    href: a.href,
    title: (a.getAttribute('title') || a.innerText || '').trim(),
    row: row ? row.innerText : ''
  };
})
"""

# 상세 페이지 본문 후보. 처음으로 충분한 텍스트가 있는 요소를 쓴다.
CONTENT_SELECTORS = [
    ".view_con", ".view_cont", ".board_view .cont", ".bbs_view_con",
    ".view_content", ".board_view", ".bbs_view", ".view", "#content",
]


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def post_id(url, param):
    q = parse_qs(urlparse(url).query)
    return q.get(param, [url])[0]


def clean_title(title):
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"\s*(새글|NEW|new|첨부파일|파일첨부)\s*$", "", title)
    return title.strip()


def find_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def list_items(page, board, pages):
    items, seen_urls = [], set()
    for n in range(1, pages + 1):
        page.goto(f"{board['url']}&{board['page_param']}={n}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        for it in page.eval_on_selector_all(board["link_selector"], LIST_JS):
            title = clean_title(it["title"])
            if not title or it["href"] in seen_urls:
                continue
            seen_urls.add(it["href"])
            items.append({"url": it["href"], "title": title, "date": find_date(it["row"])})
    return items


def read_detail(page, url, max_chars):
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    content = ""
    for sel in CONTENT_SELECTORS:
        loc = page.locator(sel).first
        if loc.count() and len(loc.inner_text().strip()) > 30:
            content = loc.inner_text()
            break

    files = []
    for a in page.locator("a").all():
        text = (a.inner_text() or "").strip()
        if FILE_RE.search(text) and text not in files:
            files.append(re.sub(r"\s+", " ", text))

    lines = [ln.strip() for ln in content.splitlines()]
    lines = [ln for ln in lines if ln and not FILE_RE.search(ln)]
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[:max_chars].rsplit("\n", 1)[0] + "\n(이하 생략 — 전체 내용은 원문에서 확인하세요.)"
    return body, files, find_date(page.inner_text("body"))


def pick_category(cfg, board, title):
    """category_rules 중 제목 키워드가 처음 맞는 규칙의 카테고리, 없으면 게시판·기본 카테고리."""
    for rule in cfg.get("category_rules", []):
        if any(k in title for k in rule["keywords"]):
            return rule["category"]
    return board.get("category", cfg.get("category"))


def render_post(board, item, body, files, footer, category):
    out = [f"카테고리: {category}"] if category else []
    out += [f"[{board['org']} {board['label']}] {item['title']}", ""]
    out.append(f"게시일: {item['date'] or '원문 참조'}")
    out.append(f"출처: {board['org']} {board['name']}")
    out.append(f"원문: {item['url']}")
    out.append("")
    if body:
        out += ["주요 내용", body, ""]
    if files:
        out.append("첨부파일 (원문 링크에서 내려받을 수 있습니다)")
        out += [f"- {f}" for f in files]
        out.append("")
    out.append(f"※ 이 글은 {board['org']} 누리집에 게시된 공식 자료를 안내하기 위한 글입니다. "
               "정확한 내용과 시행일은 반드시 원문을 확인해 주세요.")
    if footer:
        out += ["", footer]
    return "\n".join(out) + "\n"


def collect(dry_run=False):
    cfg = load_json(SOURCES_FILE, None)
    if cfg is None:
        raise SystemExit(f"[ERROR] {SOURCES_FILE.name} 이 없습니다.")
    seen = set(load_json(SEEN_FILE, []))
    created = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="ko-KR")
        for board in cfg["boards"]:
            try:
                items = list_items(page, board, cfg.get("pages", 1))
            except Exception as e:
                print(f"[ERROR] {board['org']} {board['name']} 목록을 읽지 못했습니다: {e}")
                continue
            if not items:
                print(f"[WARN] {board['org']} {board['name']}: 글 목록을 찾지 못했습니다. 게시판 주소나 구조가 바뀌었는지 확인하세요.")
                continue

            keywords = board.get("keywords") or []
            matched = [it for it in items if not keywords or any(k in it["title"] for k in keywords)]
            new = [it for it in matched if f"{board['key']}:{post_id(it['url'], board['id_param'])}" not in seen]
            print(f"[INFO] {board['org']} {board['name']}: 목록 {len(items)}건, 키워드 일치 {len(matched)}건, 새 글 {len(new)}건")

            for it in reversed(new):  # 오래된 글부터 대기열에 넣는다
                print(f"       - {it['date'] or '날짜?'} {it['title']}")
                if dry_run:
                    continue
                try:
                    body, files, page_date = read_detail(page, it["url"], cfg.get("max_content_chars", 2500))
                except Exception as e:
                    print(f"[ERROR]   본문을 읽지 못했습니다: {e}")
                    continue
                it["date"] = it["date"] or page_date
                pid = post_id(it["url"], board["id_param"])
                date_tag = (it["date"] or "0000-00-00").replace("-", "")
                path = POSTS_DIR / f"00_news_{date_tag}_{board['key']}_{pid}.md"
                path.write_text(render_post(board, it, body, files, cfg.get("footer", ""), pick_category(cfg, board, it["title"])), encoding="utf-8")
                seen.add(f"{board['key']}:{pid}")
                created += 1
        browser.close()

    if not dry_run:
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[INFO] 새 글 {created}건을 posts/ 대기열에 추가했습니다.")
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="보건복지부·건강보험공단 게시판 새 글 수집")
    parser.add_argument("--dry-run", action="store_true", help="찾은 글 목록만 출력")
    collect(parser.parse_args().dry_run)
