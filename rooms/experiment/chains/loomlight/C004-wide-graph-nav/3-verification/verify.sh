#!/bin/bash
# loomlight/C004 재현 검증 — 워크트리 루트의 rooms/deployment/ariadne-spec 에서 실행.
set -e
CH=../../../rooms/experiment/chains
GO=$(mktemp -d)/gil-go
GO111MODULE=off GOCACHE=$(mktemp -d) go build -o "$GO" go/main.go
# 1) parity: 기본
python3 gil.py web "$CH" -o /tmp/py.html >/dev/null; "$GO" web "$CH" -o /tmp/go.html >/dev/null
cmp /tmp/py.html /tmp/go.html && echo "PARITY default: BYTE-IDENTICAL"
# 2) parity: --flat
python3 gil.py web "$CH" --flat -o /tmp/pyf.html >/dev/null; "$GO" web "$CH" --flat -o /tmp/gof.html >/dev/null
cmp /tmp/pyf.html /tmp/gof.html && echo "PARITY flat: BYTE-IDENTICAL"
# 3) conformance
python3 conformance.py --gil "python3 $(pwd)/gil.py" | tail -1
python3 conformance.py --gil "$GO" | tail -1
# 4) 넓은 체인만 미니맵
echo -n "chains with minimap: "; grep -o 'aria-label="[a-z]* 미니맵"' /tmp/py.html | wc -l
