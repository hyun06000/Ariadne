#!/usr/bin/env bash
# [loomlight/C010] 재현 가능한 검증 러너 — meta refresh 결함 재현 + 폴링 상태보존 실측 + 데이터 갱신 실측.
# 렌더/상태보존은 판정기가 못 본다(§3.1) → 헤드리스 Chrome(CDP)으로 실측한다.
# 사용법: bash verify.sh <gil실행기: "python3 /abs/gil.py" 또는 /abs/gil-go>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GIL="${1:?사용법: verify.sh '<gil실행기>'}"
REPO_ROOT="$(cd "$HERE/../../../../../.." && pwd)"   # 워크트리 루트(체인 원장이 있는 곳)
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"; kill %1 2>/dev/null || true' EXIT
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

echo "== 1. meta refresh 부재 + 폴링 마운트 + 자기완결 (구조 판정) =="
( cd "$REPO_ROOT" && $GIL web -o "$WORK/v.html" --title T --refresh 3 >/dev/null )
grep -q 'http-equiv="refresh"' "$WORK/v.html" && { echo "FAIL: meta refresh가 남아있다"; exit 1; } || echo "  OK meta refresh 부재"
grep -q 'function poll' "$WORK/v.html" && grep -q 'setInterval' "$WORK/v.html" && echo "  OK 폴링 마운트 존재" || { echo "FAIL: 폴링 마운트 없음"; exit 1; }
[ "$(grep -oE '(src=|href=|url\(|@import)[^">]*https?://' "$WORK/v.html" | wc -l | tr -d ' ')" = "0" ] && echo "  OK 외부 리소스 0" || { echo "FAIL: 외부 리소스 발견"; exit 1; }

echo "== 2. 헤드리스 실측: 폴링이 열린 details·스텝·스크롤을 보존하며 데이터를 갱신 =="
cp "$WORK/v.html" "$WORK/viewer.html"
PORT=8988
( cd "$WORK" && exec python3 -m http.server "$PORT" >/dev/null 2>&1 ) &
SRV=$!; trap 'rm -rf "$WORK"; kill "$SRV" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  curl -sf -o /dev/null "http://127.0.0.1:$PORT/viewer.html" && break || sleep 0.3
done
curl -sf -o /dev/null "http://127.0.0.1:$PORT/viewer.html" || { echo "FAIL: 서버가 viewer.html을 서빙하지 못함"; exit 1; }
echo "  [2a] 폴링 상태보존:"
python3 "$HERE/cdp.py" "http://127.0.0.1:8988/viewer.html" "$HERE/steps-2-poll-preserves-state.json"
echo "  기대: A_chainOpen:true, A_step1Open:true, A_scroll:420 (리로드였다면 전부 리셋)"
echo "== 검증 스크립트 완료 — 판정은 위 JSON 출력을 3-verification/README.md 표와 대조 =="
