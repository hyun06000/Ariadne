# 3. 가설 검증

산출물:

- `conformance-ref.txt` / `conformance-go.txt` — 참조 **90/90** · Go **83/83** (회귀 0).
- `parity.txt` — 기본(스트림)·`--flat`(평면) 각각 **byte-identical**. 구조 확인: cycstream 5 · `name="hchain"` 아코디언 5 · linchip(lineage 칩) 27 · 구 per-chain SVG그래프 0(제거됨). (L0 체인 지도는 별개로 유지.)
- `node-stream.png` — loomlight 펼침: 좌측 레일 노드 스트림, C001에 lineage 초록 칩 전부 표시(잘림 없음), 아코디언(하나만 열림).
- `cycle-open.png` — `#cyc-loomlight-C003-…` 이동: 아코디언+노드가 함께 열려 그 자리 아래로 메타+5스텝(가설~보고) 인라인.

## 재현 방법

```bash
# 저장소 루트에서. Go 툴체인(go1.26): brew install go
cd rooms/deployment/ariadne-spec && go build -o /tmp/gil-stream go/main.go

python3 conformance.py --gil "python3 $(pwd)/gil.py"   # 90/90
python3 conformance.py --gil "/tmp/gil-stream"          # 83/83

for mode in "" "--flat"; do   # 바이트 parity (정수·문자열뿐이라 Python↔Go 동일)
  python3 gil.py web ../../../rooms/experiment/chains -o /tmp/p.html --title T $mode
  /tmp/gil-stream  web ../../../rooms/experiment/chains -o /tmp/g.html --title T $mode
  diff -q /tmp/p.html /tmp/g.html && echo "$mode byte-identical"
done

# 상호작용 스크린샷 (Chrome 헤드리스)
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python3 gil.py web ../../../rooms/experiment/chains -o /tmp/h.html --title T
"$CHROME" --headless=new --window-size=1200,1500 --screenshot=node-stream.png "file:///tmp/h.html#chainbody-loomlight"
"$CHROME" --headless=new --window-size=1200,1400 --screenshot=cycle-open.png "file:///tmp/h.html#cyc-loomlight-C003-go-hierarchy-port"
```

## 실행 기록

- 일시: 2026-07-19. 환경: darwin 25.5.0 arm64, Python 3.9.6, Go 1.26.5, Chrome headless.
- 결과: 참조 90/90·Go 83/83, 기본·`--flat` 모두 byte-identical, 스크린샷으로 아코디언·스트림·lineage 칩·노드 클릭 5스텝 인라인 확인.
- 특이사항: 이 재설계는 좌표 계산이 전혀 없어(순수 HTML/CSS 문자열) C064의 삼각함수-parity 위험이 아예 없다. flat 경로 무수정이라 `--flat` parity는 자명.
