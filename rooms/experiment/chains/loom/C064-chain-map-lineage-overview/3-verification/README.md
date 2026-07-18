# 3. 가설 검증

이 디렉토리의 산출물:

- `conformance-ref.txt` — 참조(`python3 gil.py`) conformance. **90/90 ✔**
- `conformance-go.txt` — Go(`go/main.go` 빌드) conformance. **83/83 ✔**
- `parity.txt` — 양 구현 바이트 대조: 무옵션(위계+체인맵)·`--flat`(평면) 각각 **byte-identical**, 체인맵 요소(chainnode 5·chainbody 5) 존재 확인.
- `chain-map.png` — 헤드리스 Chrome 렌더 스크린샷(허브 loom 중앙, 초록 점선 화살표 + 건수 라벨, 원 안 사이클 수).

드릴다운(클릭→펼침)은 `file://…#chainbody-loom`으로 이동 시 loom `<details>`가 자동으로 열려 사이클 그래프가 보임을 세션 중 스크린샷으로 실증(프래그먼트→조상 details 자동 오픈, loomlight/C002 메커니즘 재사용).

## 재현 방법

```bash
# 저장소 루트에서. Go 툴체인 필요(go1.26): brew install go
cd rooms/deployment/ariadne-spec
go build -o /tmp/gil-map go/main.go

# conformance (양 구현) — 참조는 절대경로로(샌드박스 cd)
python3 conformance.py --gil "python3 $(pwd)/gil.py"   # → 90/90
python3 conformance.py --gil "/tmp/gil-map"            # → 83/83

# 바이트 parity (기본=위계+체인맵, --flat=평면) — 삼각함수 없이 sqrt-only라 Python↔Go 비트 동일
for mode in "" "--flat"; do
  python3 gil.py web ../../../rooms/experiment/chains -o /tmp/p.html --title T $mode
  /tmp/gil-map  web ../../../rooms/experiment/chains -o /tmp/g.html --title T $mode
  diff -q /tmp/p.html /tmp/g.html && echo "$mode byte-identical"
done

# 렌더 스크린샷 + 드릴다운 확인 (Chrome 헤드리스)
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python3 gil.py web ../../../rooms/experiment/chains -o /tmp/hier.html --title "체인 지도"
"$CHROME" --headless=new --force-device-scale-factor=2 --window-size=1100,470 \
  --screenshot=chain-map.png "file:///tmp/hier.html"
"$CHROME" --headless=new --window-size=1100,1000 \
  --screenshot=/tmp/loom-open.png "file:///tmp/hier.html#chainbody-loom"   # loom이 펼쳐져야 함
```

## 실행 기록

- 일시: 2026-07-19. 환경: darwin 25.5.0 arm64, Python 3.9.6, Go 1.26.5, Chrome headless.
- 결과: 참조 90/90·Go 83/83, parity 무옵션·`--flat` 모두 byte-identical, chainnode 5·chainbody 5, `#chainbody-loom` 이동 시 loom 펼쳐짐 확인.
- 특이사항: 초기 구현은 `math.atan2/cos/sin`으로 끝점을 냈으나 — 이는 IEEE correctly-rounded 미보장이라 Go 이식 시 바이트가 갈릴 위험 → **벡터 정규화(sqrt-only)로 교체** 후 비트 동일 확보. 시각 결과는 교체 전후 동일.
