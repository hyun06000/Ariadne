#!/usr/bin/env bash
# C042 교차 판정 — 두 몸, 한 계약. 같은 픽스처에 각 구현이 뷰어를 자동 갱신하고 대조한다.
#   사용: bash cross-check.sh <스크래치> <참조 gil 호출> <Go gil 호출>
set -uo pipefail
WORK="$1"; PY="$2"; GO="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
extract() { python3 -c "import re,sys;m=re.search(r'gil-data\">(.*?)</script>',open(sys.argv[1]).read(),re.S);print(m.group(1) if m else '')" "$1"; }

for impl in py go; do
  case "$impl" in py) GIL="$PY";; go) GIL="$GO";; esac
  bash "$HERE/fixture.sh" "$WORK/$impl" "$GIL" >/dev/null
  ( cd "$WORK/$impl" && $GIL step demo C001-first 2 > "$WORK/$impl.step.out" 2>&1
    $GIL close demo C001-first --date 2026-07-15 --verdict supported >> "$WORK/$impl.step.out" 2>&1 )
  cp "$WORK/$impl/chains.html" "$WORK/$impl.html"
  extract "$WORK/$impl.html" > "$WORK/$impl.json"
  ( cd "$WORK/$impl" && git log --format='%s' -3 > "$WORK/$impl.gitlog.out" )
done

fail=0
for f in html json gitlog.out; do
  if diff -q "$WORK/py.$f" "$WORK/go.$f" >/dev/null 2>&1; then echo "동일  $f"
  else echo "차이! $f"; diff "$WORK/py.$f" "$WORK/go.$f" | head -8; fail=1; fi
done
# step.out은 생성 시각/커밋 없음 — ✎ 뷰어 갱신 줄만 대조
grep -c "✎ 뷰어 갱신" "$WORK/py.step.out" > "$WORK/py.refresh"
grep -c "✎ 뷰어 갱신" "$WORK/go.step.out" > "$WORK/go.refresh"
if diff -q "$WORK/py.refresh" "$WORK/go.refresh" >/dev/null; then echo "동일  뷰어 갱신 횟수 ($(cat $WORK/py.refresh)회)"
else echo "차이! 뷰어 갱신 횟수"; fail=1; fi
exit $fail
