#!/usr/bin/env bash
# 재현 스크립트 — loom/C046 (Go에 round 이식)
# 저장소 루트에서 실행한다. --gil에는 반드시 절대경로를 준다 (C028·C043·C045의 함정).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
SPEC="$ROOT/rooms/deployment/ariadne-spec"

echo "1) Go 바이너리 빌드"
go build -o /tmp/gil-weft-c046 "$SPEC/go/main.go"

echo "2) 참조 구현 conformance (기준선 — 72/72 기대)"
python3 "$SPEC/conformance.py" --gil "python3 $SPEC/gil.py"

echo "3) Go 바이너리 conformance (64/64 기대 — 라운드 8항목 PASS, 예약 8항목은 미판정)"
python3 "$SPEC/conformance.py" --gil "/tmp/gil-weft-c046"

echo "4) 실 저장소 web 바이트 비교 (무라운드·무예약 상태)"
python3 "$SPEC/gil.py" web "$ROOT/rooms/experiment/chains" -o /tmp/web-ref.html --title "Ariadne — 사이클 체인"
/tmp/gil-weft-c046 web "$ROOT/rooms/experiment/chains" -o /tmp/web-go.html --title "Ariadne — 사이클 체인"
diff /tmp/web-ref.html /tmp/web-go.html && echo "BYTE-IDENTICAL"
