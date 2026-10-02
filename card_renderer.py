"""글 내용으로 블로그용 카드 이미지(표지·장면·인용·목록·표)를 PNG 로 만든다.

Playwright 크로미움으로 HTML 을 그려 저장하며, 글꼴은 assets/fonts 의 Pretendard(OFL)를 쓴다.
"""

import base64
import html
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


def _font(name):
    data = base64.b64encode((FONT_DIR / f"Pretendard-{name}.woff2").read_bytes()).decode()
    return f"url(data:font/woff2;base64,{data}) format('woff2')"


WIDTH = 960

CSS = f"""
@font-face {{ font-family: P; font-weight: 400; src: {_font('Regular')}; }}
@font-face {{ font-family: P; font-weight: 600; src: {_font('SemiBold')}; }}
@font-face {{ font-family: P; font-weight: 700; src: {_font('Bold')}; }}
@font-face {{ font-family: P; font-weight: 800; src: {_font('ExtraBold')}; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: P, sans-serif; background: #fff; width: {WIDTH}px; }}
.card {{ width: {WIDTH}px; padding: 56px 64px; background: #f7f4ee; color: #222;
         border-top: 10px solid #1f3a68; border-bottom: 6px solid #d9822b; }}
.kicker {{ font-size: 22px; font-weight: 700; color: #d9822b; letter-spacing: .5px; }}
.title {{ font-size: 46px; font-weight: 800; color: #1f3a68; line-height: 1.3; margin-top: 14px; word-break: keep-all; }}
.sub {{ font-size: 24px; font-weight: 600; color: #555; margin-top: 18px; line-height: 1.5; word-break: keep-all; }}
.brand {{ margin-top: 40px; font-size: 18px; color: #888; font-weight: 600; }}
.cover {{ background: #1f3a68; color: #fff; border-top-color: #d9822b; padding: 80px 64px; }}
.cover .title {{ color: #fff; font-size: 52px; }}
.cover .sub {{ color: #dfe6f2; }}
.cover .brand {{ color: #b9c6dc; }}
.big {{ font-size: 76px; font-weight: 800; color: #1f3a68; line-height: 1; }}
.quote {{ font-size: 36px; font-weight: 700; color: #1f3a68; line-height: 1.55; word-break: keep-all;
          border-left: 10px solid #d9822b; padding-left: 28px; margin-top: 18px; }}
ol, ul {{ margin-top: 26px; list-style: none; }}
li {{ display: flex; gap: 18px; font-size: 25px; line-height: 1.6; margin-top: 18px; word-break: keep-all; }}
li .n {{ flex: 0 0 46px; height: 46px; border-radius: 50%; background: #1f3a68; color: #fff;
         font-weight: 800; font-size: 24px; display: flex; align-items: center; justify-content: center; margin-top: 2px; }}
li .c {{ flex: 0 0 34px; height: 34px; border: 3px solid #d9822b; border-radius: 6px; margin-top: 6px; }}
.box {{ background: #fff; border-radius: 14px; padding: 28px 32px; margin-top: 26px; font-size: 25px;
        line-height: 1.65; word-break: keep-all; box-shadow: 0 2px 0 #e6e0d4; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 26px; font-size: 23px; background: #fff; }}
th {{ background: #1f3a68; color: #fff; font-weight: 700; text-align: left; padding: 16px 18px; }}
td {{ border-bottom: 2px solid #e6e0d4; padding: 16px 18px; line-height: 1.5; vertical-align: top; word-break: keep-all; }}
td.blank {{ color: #bbb; }}
td:first-child, th:first-child {{ min-width: 150px; font-weight: 600; }}
tr:nth-child(even) td {{ background: #fbf9f5; }}
"""

BRAND = "동행솔루션 · 장기요양기관 평가·청구 실무"


def e(text):
    return html.escape(str(text).replace("**", ""))


def cover(kicker, title, sub=""):
    return (f'<div class="card cover"><div class="kicker">{e(kicker)}</div>'
            f'<div class="title">{e(title)}</div>'
            + (f'<div class="sub">{e(sub)}</div>' if sub else "")
            + f'<div class="brand">{BRAND}</div></div>')


def scene(label, place):
    return (f'<div class="card"><div class="kicker">SCENE</div><div class="big">{e(label)}</div>'
            f'<div class="sub">{e(place)}</div></div>')


def quote(text, kicker="이번 화의 한마디"):
    return f'<div class="card"><div class="kicker">{e(kicker)}</div><div class="quote">{e(text)}</div></div>'


def numbered(kicker, title, items):
    lis = "".join(f'<li><span class="n">{i}</span><span>{e(t)}</span></li>' for i, t in enumerate(items, 1))
    return f'<div class="card"><div class="kicker">{e(kicker)}</div><div class="title">{e(title)}</div><ol>{lis}</ol></div>'


def checklist(kicker, title, items):
    lis = "".join(f'<li><span class="c"></span><span>{e(t)}</span></li>' for t in items)
    return f'<div class="card"><div class="kicker">{e(kicker)}</div><div class="title">{e(title)}</div><ul>{lis}</ul></div>'


def boxed(kicker, title, text):
    return (f'<div class="card"><div class="kicker">{e(kicker)}</div><div class="title">{e(title)}</div>'
            f'<div class="box">{e(text)}</div></div>')


def table(kicker, title, header, rows):
    th = "".join(f"<th>{e(h)}</th>" for h in header)
    trs = "".join("<tr>" + "".join(
        f'<td class="blank">{e(c)}</td>' if set(str(c)) <= set("_ ") else f"<td>{e(c)}</td>"
        for c in r) + "</tr>" for r in rows)
    return (f'<div class="card"><div class="kicker">{e(kicker)}</div><div class="title">{e(title)}</div>'
            f"<table><tr>{th}</tr>{trs}</table></div>")


class Renderer:
    """with Renderer() as r: r.save(cover(...), 'a.png')"""

    def __enter__(self):
        self._pw = sync_playwright().start()
        exe = os.environ.get("CHROMIUM_PATH")
        self._browser = self._pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        self._page = self._browser.new_page(viewport={"width": WIDTH, "height": 600}, device_scale_factor=1)
        return self

    def save(self, card_html, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._page.set_content(f"<html><head><style>{CSS}</style></head><body>{card_html}</body></html>")
        self._page.evaluate("document.fonts.ready.then(() => true)")
        self._page.locator(".card").screenshot(path=str(path))
        return path

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()
