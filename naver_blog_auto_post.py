"""네이버 블로그 1일 3회 자동 발행 스케줄러.

사용법:
    1) 최초 1회 로그인 (브라우저 창에서 직접 로그인 → 세션 저장)
         python naver_blog_auto_post.py --login
    2) 즉시 1건 발행 테스트
         python naver_blog_auto_post.py --once
    3) 스케줄러 실행 (09:00 / 14:00 / 20:00 발행, 08:00 보건복지부 새 글 수집)
         python naver_blog_auto_post.py
    4) 보건복지부 고시·공지·자료실 새 글 수집만 실행
         python naver_blog_auto_post.py --collect

posts/ 폴더의 *.md 파일을 이름순으로 하나씩 발행하고, 발행된 파일은
posts/published/ 로 옮긴다. 파일 첫 줄은 제목, 나머지는 본문.
"""

import argparse
import os
import random
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import schedule
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from mohw_collector import collect

NAVER_ID = os.environ.get("NAVER_ID", "donghangsol")
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

BASE_DIR = Path(__file__).resolve().parent
AUTH_FILE = BASE_DIR / "auth" / "naver_state.json"
POSTS_DIR = BASE_DIR / "posts"
PUBLISHED_DIR = POSTS_DIR / "published"

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


def next_post():
    files = sorted(f for f in POSTS_DIR.glob("*.md") if f.is_file())
    if not files:
        return None
    lines = files[0].read_text(encoding="utf-8").splitlines()
    title = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip()
    if not title:
        raise ValueError(f"{files[0].name}: 첫 줄(제목)이 비어 있습니다.")
    return files[0], title, body


def dismiss_if_present(frame, selector, timeout=3000):
    try:
        frame.locator(selector).first.click(timeout=timeout)
        pause(0.5, 1.0)
    except PlaywrightTimeout:
        pass


def write_and_publish(page, title, body, dry_run=False):
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

    # 본문
    editor.locator(".se-component.se-text .se-text-paragraph").first.click()
    for i, line in enumerate(body.splitlines()):
        if i:
            page.keyboard.press("Enter")
        if line:
            page.keyboard.type(line, delay=random.randint(20, 50))
    pause(1.5, 2.5)

    if dry_run:
        shot = BASE_DIR / f"preview_{time.strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=str(shot), full_page=True)
        return shot.name

    # 발행 → 발행 확인
    editor.locator("button[class*='publish_btn']").first.click()
    pause()
    editor.locator("button[class*='confirm_btn']").first.click()

    page.wait_for_url("**/PostView**", timeout=30000)
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
    path, title, body = post

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(viewport=VIEWPORT, storage_state=str(AUTH_FILE))
        page = context.new_page()
        try:
            url = write_and_publish(page, title, body, dry_run)
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

    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), PUBLISHED_DIR / path.name)
    print(f"[INFO] 발행 완료: '{title}' → {url}")


def safe_collect():
    try:
        collect()
    except Exception as e:
        print(f"[ERROR] 보건복지부 글 수집 실패: {e}")


def show_status():
    """대기 중인 글 목록과 각 글의 예상 발행 시각을 보여준다."""
    queue = sorted(f for f in POSTS_DIR.glob("*.md") if f.is_file())
    published = list(PUBLISHED_DIR.glob("*.md")) if PUBLISHED_DIR.exists() else []
    print(f"블로그: https://blog.naver.com/{NAVER_ID}")
    print(f"세션: {'저장됨' if AUTH_FILE.exists() else '없음 (--login 필요)'}")
    print(f"발행 완료 {len(published)}건 / 대기 {len(queue)}건\n")

    now = datetime.now()
    slots = []
    day = now.date()
    while len(slots) < len(queue):
        for t in SCHEDULE_TIMES:
            h, m = map(int, t.split(":"))
            slot = datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)
            if slot > now and len(slots) < len(queue):
                slots.append(slot)
        day += timedelta(days=1)

    weekdays = "월화수목금토일"
    for f, slot in zip(queue, slots):
        lines = f.read_text(encoding="utf-8").splitlines()
        title = lines[0].strip() if lines else "(제목 없음)"
        print(f"  {slot:%m/%d}({weekdays[slot.weekday()]}) {slot:%H:%M}  {title}  [{f.name}]")

    if queue:
        print(f"\n대기열은 {slots[-1]:%m/%d %H:%M} 발행분까지입니다.")
    else:
        print("대기 중인 글이 없습니다. posts/ 폴더에 .md 파일을 추가하세요.")


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 발행")
    parser.add_argument("--login", action="store_true", help="직접 로그인하여 세션 저장")
    parser.add_argument("--once", action="store_true", help="즉시 1건 발행 후 종료")
    parser.add_argument("--dry-run", action="store_true", help="글을 에디터에 입력하고 스크린샷만 저장 (발행 안 함)")
    parser.add_argument("--collect", action="store_true", help="보건복지부 고시·공지·자료실 새 글을 posts/ 에 수집")
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
