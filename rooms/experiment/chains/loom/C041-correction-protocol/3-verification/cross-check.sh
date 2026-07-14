#!/usr/bin/env bash
# C041 교차 판정 — 두 몸, 한 계약. 같은 픽스처에 각 구현이 정정을 가하고 산출물을 바이트 대조한다.
#   사용: bash cross-check.sh <스크래치> <참조 gil 호출> <Go gil 호출>
set -uo pipefail
WORK="$1"; PY="$2"; GO="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"

for impl in py go; do
  case "$impl" in py) GIL="$PY";; go) GIL="$GO";; esac
  bash "$HERE/fixture.sh" "$WORK/$impl" "$GIL" >/dev/null
  ( cd "$WORK/$impl" && $GIL correct demo/C002-second \
      --field parent --to C001-first \
      --evidence 1-hypothesis.md:7 --author maru --date 2026-07-15 \
      --reason "open 시 --parent 누락 — 도구가 저자의 침묵을 대필했다" > "$WORK/$impl.correct.out" 2>&1 )
  ( cd "$WORK/$impl" && $GIL log   > "$WORK/$impl.log.out" 2>&1
    $GIL fsck  > "$WORK/$impl.fsck.out" 2>&1
    $GIL verify > "$WORK/$impl.verify.out" 2>&1; echo "verify rc=$?" >> "$WORK/$impl.verify.out"
    $GIL web -o "$WORK/$impl.html" >/dev/null 2>&1 )
  cp "$WORK/$impl/rooms/experiment/chains/demo/C002-second/cycle.yaml"       "$WORK/$impl.cycle.yaml"
  cp "$WORK/$impl/rooms/experiment/chains/demo/C002-second/corrections.yaml" "$WORK/$impl.corrections.yaml"
  ( cd "$WORK/$impl" && git log -1 --format='%s' > "$WORK/$impl.commit.out"
    git tag -n99 -l cycle/demo/C002-second | sed 's/[0-9a-f]\{8\}/<hash>/g' > "$WORK/$impl.tag.out" )
done

fail=0
for f in cycle.yaml corrections.yaml log.out fsck.out verify.out commit.out tag.out html; do
  if diff -q "$WORK/py.$f" "$WORK/go.$f" >/dev/null 2>&1; then
    echo "동일  $f"
  else
    echo "차이! $f"; diff "$WORK/py.$f" "$WORK/go.$f" | head -6; fail=1
  fi
done
# correct의 출력에는 커밋 해시가 들어가므로 해시를 가린 뒤 비교한다
sed 's/[0-9a-f]\{8\}/<hash>/g' "$WORK/py.correct.out" > "$WORK/py.correct.masked"
sed 's/[0-9a-f]\{8\}/<hash>/g' "$WORK/go.correct.out" > "$WORK/go.correct.masked"
if diff -q "$WORK/py.correct.masked" "$WORK/go.correct.masked" >/dev/null; then
  echo "동일  correct.out (해시 마스킹)"
else
  echo "차이! correct.out"; diff "$WORK/py.correct.masked" "$WORK/go.correct.masked"; fail=1
fi
exit $fail
