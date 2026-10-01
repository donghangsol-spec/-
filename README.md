# 네이버 블로그 자동 발행

`posts/` 폴더의 글을 하루 3회(09:00, 14:00, 20:00) 네이버 블로그에 하나씩 발행합니다.

## 설치

```bash
pip install -r requirements.txt
playwright install chromium
export NAVER_ID=내블로그아이디
```

## 사용

```bash
python naver_blog_auto_post.py --login   # 최초 1회: 브라우저에서 직접 로그인 → auth/ 에 세션 저장
python naver_blog_auto_post.py --once    # 1건 즉시 발행 (테스트)
python naver_blog_auto_post.py           # 스케줄러 실행
```

- 글 파일: `posts/*.md` — 첫 줄은 제목, 나머지는 본문. 이름순으로 발행되며 발행 후 `posts/published/`로 이동합니다.
- 세션이 만료되면 `--login`을 다시 실행하세요.
- 발행 실패 시 `error_*.png` 스크린샷이 남습니다. 네이버 에디터 구조가 바뀌면 `write_and_publish()`의 셀렉터를 수정해야 합니다.
- `HEADLESS=1`로 브라우저 창 없이 실행할 수 있습니다.
