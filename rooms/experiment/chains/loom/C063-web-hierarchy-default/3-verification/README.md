# 3. 가설 검증

이 디렉토리의 산출물:

- `conformance-ref.txt` — 참조 구현(`python3 gil.py`) conformance 전체 로그. **90/90 ✔**
- `conformance-go.txt` — Go 구현(`go/main.go` 빌드) conformance 전체 로그. **83/83 ✔** (참조가 7 더 많은 건 `release` 계열이 참조 전용 — 설계된 비대칭)
- `mutation-baseline.txt` — 변경 전 바이너리 v2.18.0(기본=평면)에 conformance. **82/83 ✘**, `WEB-HIERARCHY-DEFAULT` **FAIL**(default_hier=False) — 판정기가 "기본이 평면으로 되돌아감" 회귀를 격추함을 증명.
- `parity.txt` — 양 구현 바이트 동일 대조: 기본(위계)·`--flat`(평면) 각각 byte-identical, `--hierarchy` 별칭 == 기본.

## 재현 방법

```bash
# 저장소 루트에서. Go 툴체인 필요(go1.26): brew install go
cd rooms/deployment/ariadne-spec
go build -o /tmp/gil-new go/main.go

# conformance (양 구현) — 참조는 절대경로로 호출(샌드박스 cd 때문)
python3 conformance.py --gil "python3 $(pwd)/gil.py"   # → 90/90
python3 conformance.py --gil "/tmp/gil-new"            # → 83/83

# 변이 격추: 변경 전 v2.18.0 바이너리(기본=평면)는 새 판정기에서 FAIL
#   git worktree/checkout v2.18.0 → go build -o /tmp/gil-baseline → 아래 재실행
python3 conformance.py --gil "/tmp/gil-baseline"       # → 82/83, WEB-HIERARCHY-DEFAULT FAIL

# 바이트 parity (기본·--flat) — 두 산출물이 동일 바이트여야 함
for mode in "" "--flat"; do
  python3 gil.py web ../../../rooms/experiment/chains -o /tmp/p.html --title T $mode
  /tmp/gil-new  web ../../../rooms/experiment/chains -o /tmp/g.html --title T $mode
  diff -q /tmp/p.html /tmp/g.html && echo "$mode: byte-identical"
done
```

## 실행 기록

- 일시: 2026-07-19. 환경: darwin 25.5.0 arm64, Python 3.9.6, Go 1.26.5.
- 결과: 참조 90/90, Go 83/83, 변이 82/83(WEB-HIERARCHY-DEFAULT 격추), parity 기본·`--flat` 모두 byte-identical, `--hierarchy`==기본.
- 특이사항: 참조 구현은 conformance 샌드박스가 cwd를 바꾸므로 `gil.py`를 **절대경로**로 넘겨야 한다(상대경로면 rc=2로 무더기 FAIL — 도구 결함 아님, 호출자 실수).
