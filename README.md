# 네이버 블로그 자동 발행

`posts/` 폴더의 글을 하루 3회(09:00, 14:00, 20:00) 네이버 블로그에 하나씩 발행합니다.

대상 블로그: https://blog.naver.com/donghangsol (다른 블로그는 `NAVER_ID` 환경변수로 지정)

## 설치

```bash
pip install -r requirements.txt
playwright install chromium
```

## 사용

```bash
python naver_blog_auto_post.py --login   # 최초 1회: 브라우저에서 직접 로그인 → auth/ 에 세션 저장
python naver_blog_auto_post.py --status  # 대기열과 각 글의 예상 발행 시각 확인
python naver_blog_auto_post.py --dry-run # 에디터에 입력만 하고 preview_*.png 저장 (발행 안 함)
python naver_blog_auto_post.py --once    # 1건 즉시 발행
python naver_blog_auto_post.py --collect --dry-run  # 새 글 목록만 확인
python naver_blog_auto_post.py --collect            # 새 글을 posts/ 에 저장
python naver_blog_auto_post.py           # 스케줄러 실행 (08:00 수집, 09/14/20시 발행)
```

- 글 파일: `posts/*.md` — 첫 줄은 제목, 나머지는 본문. 이름순으로 발행되며 발행 후 `posts/published/`로 이동합니다.
- 카테고리 지정: 첫 줄을 `카테고리: 이름`으로 쓰면 그 카테고리에 발행합니다(제목은 둘째 줄). 블로그 관리에서 같은 이름의 카테고리를 먼저 만들어 두어야 하며, 없으면 발행하지 않고 오류를 남깁니다.
- 세션이 만료되면 `--login`을 다시 실행하세요.
- 발행 실패 시 `error_*.png` 스크린샷이 남습니다. 네이버 에디터 구조가 바뀌면 `write_and_publish()`의 셀렉터를 수정해야 합니다.
- `HEADLESS=1`로 브라우저 창 없이 실행할 수 있습니다.

## 보건복지부·국민건강보험공단 게시판 자동 수집

`sources.json`에 적힌 게시판의 최신 글 중
제목에 키워드(장기요양, 평가, 청구, 수가 등)가 들어간 글을 원문 링크·본문·첨부파일 목록과 함께 `posts/00_news_*.md`로 만듭니다.

- 보건복지부: 훈령/예규/고시/지침, 공지사항, 연구/조사/발간자료, 보도자료
- 국민건강보험공단 노인장기요양보험: 장기요양기관 평가 공지·매뉴얼(전체 수집), 공지사항

- 스케줄러 실행 시 바로 1회, 이후 매일 08:00에 수집합니다. 수집된 글은 다른 글보다 먼저(오래된 글부터) 발행됩니다.
- 이미 수집한 글은 `data/seen.json`에 기록되어 중복으로 만들지 않습니다.
- 게시판 추가·키워드 변경·하단 문구(footer)는 `sources.json`에서 수정합니다. `keywords`를 `[]`로 두면 해당 게시판의 모든 새 글을 수집합니다.
- 목록을 찾지 못하면 `[WARN]`이 출력됩니다. 누리집 구조가 바뀌었을 수 있으니 `sources.json`의 `link_selector`나 `notice_collector.py`의 본문 셀렉터를 확인하세요.

## 평가바이블365 연재

```bash
python book_to_posts.py 원고.md
```

원고의 `## 1`~`## 20` 장에 부록의 같은 번호 실습을 붙여 `posts/10_SSS_book_NN.md`로 만듭니다.
연재 2화마다 `건강한 음식·식재료` 카테고리 글(`posts/10_SSS_food_KK.md`) 1편이 끼어 발행되도록 순서 번호가 매겨집니다.
