# 3. 가설 검증

산출물:

- `conformance-ref.txt` / `conformance-go.txt` — 참조 **90/90** · Go **83/83**(회귀 0).
- `parity.txt` — 기본·`--flat` **byte-identical**. 수정: `.card.hmap>svg`(직계 자식) 셀렉터.
- `scroll-natural-size.png` — loom(67노드) 펼침: 노드가 자연 크기(C001~C009 읽힘)로 보이고 그래프가 오른쪽으로 스크롤(전부 축소 표시가 아님). C001 아래 lineage 초록 표시도 정상 크기.

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec && go build -o /tmp/gil-c68 go/main.go
python3 conformance.py --gil "python3 $(pwd)/gil.py"   # 90/90
python3 conformance.py --gil "/tmp/gil-c68"             # 83/83
for mode in "" "--flat"; do
  python3 gil.py web ../../../rooms/experiment/chains -o /tmp/p.html --title T $mode
  /tmp/gil-c68  web ../../../rooms/experiment/chains -o /tmp/g.html --title T $mode
  diff -q /tmp/p.html /tmp/g.html && echo "$mode byte-identical"
done
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python3 gil.py web ../../../rooms/experiment/chains -o /tmp/h.html --title T
"$CHROME" --headless=new --window-size=1300,760 --screenshot=scroll-natural-size.png "file:///tmp/h.html#chainbody-loom"
```

## 실행 기록

- 일시: 2026-07-19. 환경: darwin 25.5.0 arm64, Python 3.9.6, Go 1.26.5, Chrome headless.
- 결과: 참조 90/90·Go 83/83, 기본·`--flat` byte-identical, loom 그래프 자연 크기+가로 스크롤 확인.
