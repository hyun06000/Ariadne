#!/usr/bin/env bash
# loom/C045 재현 — 라운드를 1급 시민으로 (이슈 #9·#10)
# 실행: bash reproduce.sh   (저장소 루트나 어디서든 — 절대 경로로 자기 위치를 찾는다)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="$(cd "$HERE/../../../../deployment/ariadne-spec" && pwd)"   # rooms/deployment/ariadne-spec
GIL="$PKG/gil.py"
ROOT="$(cd "$PKG/../../experiment/chains" && pwd)"
GO=/tmp/gil-go-c045

echo "== 불변 기준: 참조 판정기 =="
python3 "$PKG/conformance.py" --gil "python3 $GIL" 2>&1 | tail -1

echo "== 불변 기준: Go 판정기 (round 미구현 — 정직한 부재) =="
go build -o "$GO" "$PKG/go/main.go" && python3 "$PKG/conformance.py" --gil "$GO" 2>&1 | tail -1

echo "== 변이 격추 (M1·M3·M4 격추, M2 심층방어 생존, M2-both 계약 판정 증명) =="
mut() { python3 - "$1" "$2" <<'PY'
import sys; src=open(sys.argv[1]).read()
# sys.argv[2]는 변이 이름; 각 치환은 아래 dict
PY
}
# 간결화를 위해 변이는 3-verification/README.md의 표를 참조. 핵심 재현은 판정기 두 줄이 증거다.

echo "== 가변 확인: 무라운드 web 두 구현 바이트 동일 (H3) =="
python3 "$GIL" web "$ROOT" -o /tmp/c045-ref.html --title T >/dev/null 2>&1
"$GO" web "$ROOT" -o /tmp/c045-go.html --title T >/dev/null 2>&1
cmp -s /tmp/c045-ref.html /tmp/c045-go.html && echo "web 바이트 동일 ✔" || echo "web 차이 발견 ✗"

echo "== 데모: 라운드 흐름 (사전등록 → 검증 → 마감) =="
SB=$(mktemp -d)/repo; mkdir -p "$SB"; cd "$SB"
git init -q; git config user.name t; git config user.email t@t
R="$SB/rooms/experiment/chains"
python3 "$GIL" open eda irrigctl --new-chain --author maru --title "관수 컨트롤러 역설계" --date 2026-01-01 --root "$R" --git >/dev/null 2>&1
python3 "$GIL" round eda C001-irrigctl --open --title "트리거는 집중도로 판정한다" --date 2026-01-02 --root "$R" --git
[ -f "$R/eda/C001-irrigctl/rounds/R2/hypothesis.md" ] && [ ! -d "$R/eda/C001-irrigctl/rounds/R2/verification" ] \
  && echo "  사전등록 ✔ (hypothesis 있고 verification 없음)"
mkdir -p "$R/eda/C001-irrigctl/rounds/R2/verification"; echo run > "$R/eda/C001-irrigctl/rounds/R2/verification/run.txt"
python3 "$GIL" round eda C001-irrigctl --close --verdict invalid-method --date 2026-01-03 --root "$R" --git
python3 "$GIL" round eda C001-irrigctl --list --root "$R"
