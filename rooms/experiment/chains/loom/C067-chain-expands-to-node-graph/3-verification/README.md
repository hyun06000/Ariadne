# 3. 가설 검증

산출물:

- `../design-mockup-before-after.png` / `.html` — 상현님께 컨펌받은 전/후 목업(현재 세로 목록 vs 제안 가로 0—o—o—o).
- `conformance-ref.txt` / `conformance-go.txt` — 참조 **90/90** · Go **83/83**(회귀 0).
- `parity.txt` — 기본·`--flat` **byte-identical**. 구조: cyclegraph(가로 그래프) 5 · gnode(클릭 노드) 75 · cycdoc(:target 문서) 75.
- `graph-expanded.png` — loomlight 펼침: 지도 카드 안에서 가로 노드-엣지 그래프 `C001—C002—C003`, C001 아래 초록 `⇠ C005-web-viewer +9`.
- `node-clicked-doc.png` — `#cycdoc-loomlight-C001-…` 이동: 그래프 아래에 C001 5스텝 문서(lineage 칩·메타·+1~+5) 드러남(:target).

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec && go build -o /tmp/gil-c67 go/main.go
python3 conformance.py --gil "python3 $(pwd)/gil.py"   # 90/90
python3 conformance.py --gil "/tmp/gil-c67"             # 83/83
for mode in "" "--flat"; do
  python3 gil.py web ../../../rooms/experiment/chains -o /tmp/p.html --title T $mode
  /tmp/gil-c67  web ../../../rooms/experiment/chains -o /tmp/g.html --title T $mode
  diff -q /tmp/p.html /tmp/g.html && echo "$mode byte-identical"
done
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python3 gil.py web ../../../rooms/experiment/chains -o /tmp/h.html --title T
"$CHROME" --headless=new --window-size=1300,720 --screenshot=graph-expanded.png "file:///tmp/h.html#chainbody-loomlight"
"$CHROME" --headless=new --window-size=1300,1050 --screenshot=node-clicked-doc.png "file:///tmp/h.html#cycdoc-loomlight-C001-gather-viewer-lineage"
```

## 실행 기록

- 일시: 2026-07-19. 환경: darwin 25.5.0 arm64, Python 3.9.6, Go 1.26.5, Chrome headless.
- 결과: 참조 90/90·Go 83/83, 기본·`--flat` byte-identical, 스크린샷으로 가로 그래프 펼침·노드 클릭 문서 :target·lineage ⇠ 확인.
- 특이사항: 정수 좌표(`_layout_columns` 전치)만 써 C064의 삼각함수 parity 위험 없음. flat 경로 무수정.
