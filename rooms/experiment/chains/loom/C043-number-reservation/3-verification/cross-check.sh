#!/usr/bin/env bash
# C043 교차 판정 — 두 몸, 한 계약. 예약은 참조 구현만 구현했다(Go는 범위 밖).
# 계약의 두 축을 대조한다:
#   (A) 무예약 기준선: 예약을 안 쓰는 저장소에서 두 구현의 web/log/json이 바이트 동일한가.
#   (B) 정직한 부재: Go가 reserve/unreserve를 exit 3(미구현 신호)으로 정직히 보고하는가.
# "판정기가 안 보는 계약은 없는 계약이다"(C036)의 반대편 — 부분 구현은 합법이고, 거짓 보고만 불법이다.
#   사용: bash cross-check.sh <스크래치> <참조 gil 호출> <Go gil 호출>
set -uo pipefail
WORK="$1"; PY="$2"; GO="$3"
rm -rf "$WORK"; mkdir -p "$WORK"
extract() { python3 -c "import re,sys;m=re.search(r'gil-data\">(.*?)</script>',open(sys.argv[1]).read(),re.S);print(m.group(1) if m else '')" "$1"; }

fail=0

# ---- (A) 무예약 기준선: 두 구현이 같은 저장소에서 같은 산출물을 내는가 ----
for impl in py go; do
  case "$impl" in py) GIL="$PY";; go) GIL="$GO";; esac
  D="$WORK/$impl"; mkdir -p "$D"; ( cd "$D" && git init -q -b main . \
    && git config user.email t@t && git config user.name t )
  ( cd "$D" && $GIL open loom seed --title "무예약 기준선" --author clew --new-chain >/dev/null
    printf '# 5.\n\n## 요약\n\nx.\n' > rooms/experiment/chains/loom/C001-seed/5-report.md
    $GIL open loom second --author clew --parent C001-seed >/dev/null
    $GIL web rooms/experiment/chains -o out.html --title "T" >/dev/null
    $GIL log rooms/experiment/chains > log.out 2>&1 )
  extract "$D/out.html" > "$WORK/$impl.json"
  cp "$D/out.html" "$WORK/$impl.html"; cp "$D/log.out" "$WORK/$impl.log"
done
echo "=== (A) 무예약 기준선 — 두 구현 대조 (web·json은 계약면 → 바이트 동일) ==="
for f in html json; do   # log 텍스트는 계약이 아니다 — 렌더는 계약이 아니다 (C021)
  if diff -q "$WORK/py.$f" "$WORK/go.$f" >/dev/null 2>&1; then echo "동일  $f"
  else echo "차이! $f"; diff "$WORK/py.$f" "$WORK/go.$f" | head -6; fail=1; fi
done
# log은 계약면이 아니지만(C021), 둘 다 같은 사이클을 그리는지 의미로 확인한다
if grep -q "C001-seed" "$WORK/py.log" && grep -q "C001-seed" "$WORK/go.log" \
   && grep -q "C002-second" "$WORK/py.log" && grep -q "C002-second" "$WORK/go.log"; then
  echo "의미동일  log (두 구현 모두 C001-seed·C002-second 렌더 — 렌더 형식은 계약 아님)"
else echo "차이! log 의미"; fail=1; fi

# ---- (B) 정직한 부재: Go는 예약을 exit 3으로 보고하는가 ----
echo ""
echo "=== (B) Go의 정직한 부재 (미구현 신호 exit 3) ==="
for cmd in reserve unreserve; do
  $GO $cmd >/dev/null 2>&1; rc=$?
  $GO help $cmd >/dev/null 2>&1; rch=$?
  if [ "$rc" = "3" ] && [ "$rch" = "3" ]; then echo "정직  go $cmd → exit 3 (없다고 말한다)"
  else echo "거짓! go $cmd → exit $rc / help exit $rch (기대 3)"; fail=1; fi
done
# 참조는 반대로 능력을 보고한다
py_has=$($PY help 2>/dev/null | grep -c "reserve")
[ "$py_has" -ge 1 ] && echo "정직  참조 구현은 reserve를 능력으로 보고한다 (gil:commands)" || { echo "누락! 참조가 reserve를 안 나열"; fail=1; }

echo ""
[ "$fail" = 0 ] && echo "교차 판정: 통과 (무예약 바이트 동일 + 정직한 부재)" || echo "교차 판정: 실패"
exit $fail
