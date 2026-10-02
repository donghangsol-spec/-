"""네이버 블로그 1일 3회 자동 발행 스케줄러.

사용법:
    1) 최초 1회 로그인 (브라우저 창에서 직접 로그인 → 세션 저장)
         python naver_blog_auto_post.py --login
    2) 즉시 1건 발행 테스트
         python naver_blog_auto_post.py --once
    3) 스케줄러 실행 (09:00 / 14:00 / 20:00 발행, 08:00 새 글 수집)
         python naver_blog_auto_post.py
    4) 보건복지부·건강보험공단 게시판 새 글 수집만 실행
         python naver_blog_auto_post.py --collect

posts/ 폴더의 *.md 파일을 이름순으로 하나씩 발행하고, 발행된 파일은
posts/published/ 로 옮긴다. 파일 첫 줄은 제목, 나머지는 본문.
첫 줄을 "카테고리: 이름" 으로 쓰면 그 카테고리에 발행한다(제목은 다음 줄).
"""

import argparse
import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import schedule
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from notice_collector import collect
from post_format import plain_text, segments

NAVER_ID = os.environ.get("NAVER_ID", "donghangsol")
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
RICH = os.environ.get("RICH", "1") != "0"  # 0 이면 예전처럼 글자만 입력

BASE_DIR = Path(__file__).resolve().parent
AUTH_FILE = BASE_DIR / "auth" / "naver_state.json"
POSTS_DIR = BASE_DIR / "posts"
PUBLISHED_DIR = POSTS_DIR / "published"  # 예전 방식: 발행한 글을 이 폴더로 옮겼다
PUBLISHED_LOG = BASE_DIR / "data" / "published.json"  # 지금 방식: 발행한 글 이름을 기록한다

SCHEDULE_TIMES = ["09:00", "14:00", "20:00"]
COLLECT_TIME = "08:00"
VIEWPORT = {"width": 1280, "height": 1024}


def pause(lo=1.0, hi=2.0):
    time.sleep(random.uniform(lo, hi))


def login_once():
    """브라우저를 띄워 사용자가 직접 로그인하고, 세션(쿠키)을 저장한다.

    아이디/비밀번호를 코드에 저장하지 않고, 캡차·2단계 인증도 사람이 처리한다.
    """
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()
        page.goto("https://nid.naver.com/nidlogin.login")
        print("[INFO] 열린 브라우저에서 네이버 로그인을 완료하세요. ('로그인 상태 유지' 체크 권장)")
        input("[INFO] 로그인 완료 후 Enter를 누르세요... ")
        context.storage_state(path=str(AUTH_FILE))
        browser.close()
    print(f"[INFO] 세션 저장 완료: {AUTH_FILE}")


def parse_post(path):
    """(카테고리 또는 None, 제목, 본문) 을 돌려준다."""
    lines = path.read_text(encoding="utf-8").splitlines()
    category = None
    if lines and lines[0].startswith("카테고리:"):
        category = lines.pop(0).split(":", 1)[1].strip() or None
    title = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip()
    return category, title, body


def published_names():
    names = set(json.loads(PUBLISHED_LOG.read_text(encoding="utf-8"))) if PUBLISHED_LOG.exists() else set()
    if PUBLISHED_DIR.exists():
        names |= {f.name for f in PUBLISHED_DIR.glob("*.md")}
    return names


def mark_published(path, url):
    names = published_names() | {path.name}
    PUBLISHED_LOG.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_LOG.write_text(json.dumps(sorted(names), ensure_ascii=False, indent=1), encoding="utf-8")


def queue():
    done = published_names()
    return sorted(f for f in POSTS_DIR.glob("*.md") if f.is_file() and f.name not in done)


def next_post():
    files = queue()
    if not files:
        return None
    category, title, body = parse_post(files[0])
    if not title:
        raise ValueError(f"{files[0].name}: 제목 줄이 비어 있습니다.")
    return files[0], category, title, body


def dismiss_if_present(frame, selector, timeout=3000):
    try:
        frame.locator(selector).first.click(timeout=timeout)
        pause(0.5, 1.0)
    except PlaywrightTimeout:
        pass


def select_category(editor, category):
    """발행 설정 창에서 카테고리를 고른다. 블로그에 같은 이름의 카테고리가 있어야 한다."""
    editor.locator("button[class*='selectbox_button']").first.click()
    pause(0.5, 1.0)
    option = editor.get_by_text(category, exact=True).last
    try:
        option.click(timeout=5000)
    except PlaywrightTimeout:
        raise RuntimeError(f"카테고리 '{category}' 를 찾지 못했습니다. 블로그 관리에서 같은 이름으로 만들어 주세요.")
    pause(0.5, 1.0)


COMPONENTS = ".se-component"
TEXT_PARAGRAPH = ".se-component.se-text .se-text-paragraph"
IMAGE_COMPONENT = ".se-component.se-image"
IMAGE_BUTTON = "button[data-name='image'], button.se-image-toolbar-button"

CLIPBOARD_JS = """([h, t]) => navigator.clipboard.write([new ClipboardItem({
    'text/html': new Blob([h], {type: 'text/html'}),
    'text/plain': new Blob([t], {type: 'text/plain'})})])"""
# 빈 문단 안내 문구(placeholder)를 뺀 본문 글자 수
TEXT_LENGTH_JS = """el => { const c = el.cloneNode(true);
    c.querySelectorAll('.se-placeholder').forEach(x => x.remove()); return c.innerText.length; }"""
PASTE_EVENT_JS = """([h, t]) => {
    const dt = new DataTransfer();
    dt.setData('text/html', h);
    dt.setData('text/plain', t);
    const target = document.activeElement || document.body;
    target.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
}"""


def wait_for_more(locator, before, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if locator.count() > before:
            return True
        time.sleep(0.3)
    return False


def type_plain(page, text):
    for i, line in enumerate(text.splitlines()):
        if i:
            page.keyboard.press("Enter")
        if line:
            page.keyboard.type(line, delay=random.randint(10, 25))


def caret_to_end(page, editor):
    """본문 맨 끝 글 문단에 커서를 둔다. 마지막이 사진이면 그 아래에 새 문단을 만든다."""
    last = editor.locator(COMPONENTS).last
    if "se-text" not in (last.get_attribute("class") or ""):
        last.click()
        page.keyboard.press("Enter")
        pause(0.4, 0.8)
    if "se-text" not in (editor.locator(COMPONENTS).last.get_attribute("class") or ""):
        print("[WARN] 사진 아래에 새 문단을 만들지 못했습니다. 미리보기 화면을 확인해 주세요.")
    editor.locator(TEXT_PARAGRAPH).last.click()
    page.keyboard.press("End")


def paste_rich(page, frame, editor, html_text, plain):
    """서식 있는 HTML 을 붙여 넣는다. 붙지 않으면 글자로 입력한다."""
    content = editor.locator(".se-content").first
    before = content.evaluate(TEXT_LENGTH_JS)
    try:
        frame.evaluate(CLIPBOARD_JS, [html_text, plain])
        page.keyboard.press("ControlOrMeta+V")
    except Exception:
        frame.evaluate(PASTE_EVENT_JS, [html_text, plain])
    pause(1.0, 1.5)
    if content.evaluate(TEXT_LENGTH_JS) > before:
        return
    print("[WARN] 서식 붙여넣기가 되지 않아 글자로 입력합니다.")
    type_plain(page, plain)


def upload_image(page, editor, path):
    before = editor.locator(IMAGE_COMPONENT).count()
    try:
        with page.expect_file_chooser(timeout=8000) as chooser:
            editor.locator(IMAGE_BUTTON).first.click()
        chooser.value.set_files(path)
    except PlaywrightTimeout:
        editor.locator("input[type='file']").first.set_input_files(path)
    if not wait_for_more(editor.locator(IMAGE_COMPONENT), before, timeout=40):
        raise RuntimeError(f"사진 업로드가 끝나지 않았습니다: {Path(path).name}")
    pause(0.8, 1.2)


def write_body(page, editor, body):
    frame = page.frame(name="mainFrame")
    editor.locator(TEXT_PARAGRAPH).first.click()
    for kind, value, extra in segments(body, POSTS_DIR):
        if kind == "image":
            if not Path(value).exists():
                print(f"[WARN] 사진 파일이 없어 건너뜁니다: {value}")
                continue
            upload_image(page, editor, value)
        else:
            paste_rich(page, frame, editor, value, extra)
        caret_to_end(page, editor)


def write_and_publish(page, title, body, category=None, dry_run=False):
    page.goto(f"https://blog.naver.com/{NAVER_ID}?Redirect=Write")
    page.wait_for_load_state("domcontentloaded")

    if "nidlogin" in page.url:
        raise RuntimeError("세션이 만료되었습니다. --login 으로 다시 로그인하세요.")

    # 스마트에디터 ONE 은 mainFrame iframe 안에 로드된다.
    editor = page.frame_locator("#mainFrame")
    editor.locator(".se-documentTitle").first.wait_for(timeout=20000)
    pause(1.5, 2.5)

    # "작성 중인 글이 있습니다" 팝업 → 취소(새 글 작성), 도움말 패널 닫기
    dismiss_if_present(editor, ".se-popup-button-cancel")
    dismiss_if_present(editor, ".se-help-panel-close-button")

    # 제목
    editor.locator(".se-documentTitle .se-text-paragraph").first.click()
    page.keyboard.type(title, delay=random.randint(30, 70))
    pause()

    # 본문: 서식 있는 글 + 사진 (RICH=0 이면 글자만)
    if RICH:
        write_body(page, editor, body)
    else:
        editor.locator(TEXT_PARAGRAPH).first.click()
        type_plain(page, plain_text(body))
    pause(1.5, 2.5)
    if dry_run:  # 본문 전체 모습을 따로 저장
        stamp = time.strftime('%Y%m%d_%H%M%S')
        editor.locator(".se-content").first.screenshot(path=str(BASE_DIR / f"preview_{stamp}_body.png"))

    # 발행 설정 창 열기 → (카테고리 선택) → 발행 확인
    editor.locator("button[class*='publish_btn']").first.click()
    pause()
    if category:
        select_category(editor, category)

    if dry_run:  # 발행 확인은 누르지 않고 화면만 저장
        shot = BASE_DIR / f"preview_{time.strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=str(shot), full_page=True)
        return shot.name

    editor.locator("button[class*='confirm_btn']").first.click()

    # 발행되면 글 주소로 이동한다: blog.naver.com/아이디/글번호 또는 예전 형식 PostView
    post_url = re.compile(rf"/{re.escape(NAVER_ID)}/\d+|PostView")
    page.wait_for_url(post_url, timeout=30000)
    return page.url


def run_auto_post(dry_run=False):
    mode = "미리보기(발행 안 함)" if dry_run else "자동 포스팅"
    print(f"[INFO] {time.strftime('%Y-%m-%d %H:%M')} 네이버 블로그 {mode} 시작...")
    if not AUTH_FILE.exists():
        print("[ERROR] 저장된 세션이 없습니다. 먼저 --login 을 실행하세요.")
        return

    try:
        post = next_post()
    except ValueError as e:
        print(f"[ERROR] {e}")
        return
    if post is None:
        print("[INFO] posts/ 폴더에 발행할 글이 없습니다. 건너뜁니다.")
        return
    path, category, title, body = post

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(viewport=VIEWPORT, storage_state=str(AUTH_FILE))
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://blog.naver.com")
        page = context.new_page()
        try:
            url = write_and_publish(page, title, body, category, dry_run)
            # 갱신된 쿠키 저장 (세션 수명 연장)
            context.storage_state(path=str(AUTH_FILE))
        except Exception as e:
            shot = BASE_DIR / f"error_{time.strftime('%Y%m%d_%H%M%S')}.png"
            page.screenshot(path=str(shot), full_page=True)
            print(f"[ERROR] 발행 실패: {e} (스크린샷: {shot.name})")
            return
        finally:
            browser.close()

    if dry_run:
        print(f"[INFO] 미리보기 완료: '{title}' → {url} (글은 발행되지 않았고 대기열에 그대로 남아 있습니다)")
        return

    mark_published(path, url)
    print(f"[INFO] 발행 완료: '{title}' → {url}")


def safe_collect():
    try:
        collect()
    except Exception as e:
        print(f"[ERROR] 게시판 글 수집 실패: {e}")


def show_status():
    """대기 중인 글 목록과 각 글의 예상 발행 시각을 보여준다."""
    pending = queue()
    published = published_names()
    print(f"블로그: https://blog.naver.com/{NAVER_ID}")
    print(f"세션: {'저장됨' if AUTH_FILE.exists() else '없음 (--login 필요)'}")
    print(f"발행 완료 {len(published)}건 / 대기 {len(pending)}건\n")

    now = datetime.now()
    slots = []
    day = now.date()
    while len(slots) < len(pending):
        for t in SCHEDULE_TIMES:
            h, m = map(int, t.split(":"))
            slot = datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)
            if slot > now and len(slots) < len(pending):
                slots.append(slot)
        day += timedelta(days=1)

    weekdays = "월화수목금토일"
    for f, slot in zip(pending, slots):
        category, title, _ = parse_post(f)
        tag = f"<{category}> " if category else ""
        print(f"  {slot:%m/%d}({weekdays[slot.weekday()]}) {slot:%H:%M}  {tag}{title or '(제목 없음)'}")

    if pending:
        print(f"\n대기열은 {slots[-1]:%m/%d %H:%M} 발행분까지입니다.")
    else:
        print("대기 중인 글이 없습니다. posts/ 폴더에 .md 파일을 추가하세요.")


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 발행")
    parser.add_argument("--login", action="store_true", help="직접 로그인하여 세션 저장")
    parser.add_argument("--once", action="store_true", help="즉시 1건 발행 후 종료")
    parser.add_argument("--dry-run", action="store_true", help="글을 에디터에 입력하고 스크린샷만 저장 (발행 안 함)")
    parser.add_argument("--collect", action="store_true", help="보건복지부·건강보험공단 새 글을 posts/ 에 수집")
    parser.add_argument("--status", action="store_true", help="대기열과 예상 발행 일정 표시")
    args = parser.parse_args()

    if args.collect:
        collect(dry_run=args.dry_run)
        return
    if args.status:
        show_status()
        return
    if args.dry_run:
        run_auto_post(dry_run=True)
        return

    if args.login:
        login_once()
        return
    if args.once:
        run_auto_post()
        return

    safe_collect()
    schedule.every().day.at(COLLECT_TIME).do(safe_collect)
    for t in SCHEDULE_TIMES:
        schedule.every().day.at(t).do(run_auto_post)
    print(f"[INFO] 네이버 블로그 1일 {len(SCHEDULE_TIMES)}회 자동 발행 스케줄러 활성화: {', '.join(SCHEDULE_TIMES)}")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
