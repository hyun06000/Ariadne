# 3. 가설 검증

산출물:

- `conformance-ref.txt` / `conformance-go.txt` — 참조 **90/90** · Go **83/83**(회귀 0).
- `parity.txt` — 기본·`--flat` 각각 **byte-identical**. 구조: `card.hmap` 안 `mapchains` 1 · `name="hchain"` 아코디언 5.
- `chains-in-card-open.png` — loomlight 펼침: 한 카드 안에 지도 SVG(위) → 구분선 → 체인 아코디언(gateway·genesis·loom 접힘, loomlight 열림) → loomlight의 사이클 노드 스트림+lineage 칩. 서브카드 박스 없음.
- `chains-in-card-closed.png` — 기본: 지도 + 접힌 체인들이 한 카드 안.

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec && go build -o /tmp/gil-c66 go/main.go
python3 conformance.py --gil "python3 $(pwd)/gil.py"   # 90/90
python3 conformance.py --gil "/tmp/gil-c66"             # 83/83
for mode in "" "--flat"; do
  python3 gil.py web ../../../rooms/experiment/chains -o /tmp/p.html --title T $mode
  /tmp/gil-c66  web ../../../rooms/experiment/chains -o /tmp/g.html --title T $mode
  diff -q /tmp/p.html /tmp/g.html && echo "$mode byte-identical"
done
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python3 gil.py web ../../../rooms/experiment/chains -o /tmp/h.html --title T
"$CHROME" --headless=new --window-size=1200,1150 --screenshot=chains-in-card-open.png "file:///tmp/h.html#chainbody-loomlight"
```

## 실행 기록

- 일시: 2026-07-19. 환경: darwin 25.5.0 arm64, Python 3.9.6, Go 1.26.5, Chrome headless.
- 결과: 참조 90/90·Go 83/83, 기본·`--flat` byte-identical, 스크린샷으로 카드 안 인라인 등장·서브카드 없음 확인.
- 특이사항: 순수 마크업·CSS 변경(좌표 없음)이라 이식이 곧 바이트 동일. flat 경로 무수정.
