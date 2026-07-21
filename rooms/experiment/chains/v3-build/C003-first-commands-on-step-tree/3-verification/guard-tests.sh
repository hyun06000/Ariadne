#!/usr/bin/env bash
# M3: 전이 가드가 불법 전이를 전부 거부하는가.
# 각 케이스는 반드시 비-0 종료해야 PASS.
HERE="$(cd "$(dirname "$0")" && pwd)"
G="python3 $HERE/gilv3.py"
T="$HERE/guard-tmp"
pass=0; fail=0

check() { # desc, expect_reject(1) or expect_ok(0)
  desc="$1"; expect="$2"; shift 2
  "$@" >/dev/null 2>&1; rc=$?
  if [ "$expect" = "reject" ]; then
    if [ $rc -ne 0 ]; then echo "  PASS(거부) $desc"; pass=$((pass+1)); else echo "  FAIL(통과됨) $desc"; fail=$((fail+1)); fi
  else
    if [ $rc -eq 0 ]; then echo "  PASS(허용) $desc"; pass=$((pass+1)); else echo "  FAIL(거부됨) $desc"; fail=$((fail+1)); fi
  fi
}

rm -rf "$T"; mkdir -p "$T/c1" "$T/c2" "$T/c3" "$T/c4" "$T/c5"

# 1) open 없이 step 거부
check "open 없이 step" reject $G step "$T/c1" --kind hypothesis

# 2) define 다음 바로 verify 거부 (순환 건너뜀)
$G open "$T/c2" --title x >/dev/null 2>&1
check "define→verify (hypothesis 건너뜀)" reject $G step "$T/c2" --kind verify

# 3) analyze 없이 close 거부
$G open "$T/c3" --title x >/dev/null 2>&1
$G step "$T/c3" --kind hypothesis >/dev/null 2>&1
check "산 잎 없이 close" reject $G close "$T/c3"

# 4) analyze에 outcome 없이 거부
$G open "$T/c4" --title x >/dev/null 2>&1
$G step "$T/c4" --kind hypothesis >/dev/null 2>&1
$G step "$T/c4" --kind verify >/dev/null 2>&1
check "analyze --outcome 누락" reject $G step "$T/c4" --kind analyze

# 5) backtrack --to 가 조상 define 아님 (verify를 가리킴) 거부
$G open "$T/c5" --title x >/dev/null 2>&1
$G step "$T/c5" --kind hypothesis >/dev/null 2>&1
$G step "$T/c5" --kind verify >/dev/null 2>&1
check "backtrack --to s2(hypothesis, non-define)" reject $G step "$T/c5" --kind analyze --outcome backtrack --to s2

# 6) (양성 대조) 정상 전이는 허용
check "define→hypothesis 정상" ok $G step "$T/c5" --kind analyze --outcome success

echo "----"
echo "가드 테스트: PASS=$pass FAIL=$fail"
[ $fail -eq 0 ] && echo "M3 PASS" || echo "M3 FAIL"
rm -rf "$T"
