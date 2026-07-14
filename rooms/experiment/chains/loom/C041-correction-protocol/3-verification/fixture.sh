#!/usr/bin/env bash
# C041 픽스처 — 회색지대를 그대로 재현한다: 봉인된 사이클에 도구가 대필한 거짓 출처.
#   사용: bash fixture.sh <작업디렉토리> <gil 호출 문법>
#   예:   bash fixture.sh /tmp/fx "python3 /abs/path/gil.py"
# 산출: <작업디렉토리>에 demo 체인 2사이클. C002는 parent: null(거짓)로 봉인됐고,
#       그 사이클의 불변 문서 1-hypothesis.md는 "부모: demo/C001-first"라고 증언한다.
set -euo pipefail

WORK="$1"; shift
GIL="$*"

rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK"
git init -q -b main .
git config user.email fixture@ariadne.test
git config user.name fixture

report() {  # close는 템플릿 그대로인 보고서를 거부한다 (C003)
  printf '# 5. 결과 보고\n\n## 요약\n\n%s\n' "$2" > "rooms/experiment/chains/demo/$1/5-report.md"
}

# 첫 사이클 — 빈 체인이므로 루트가 맞다 (§3.2 P3)
$GIL open demo first --title "첫 사이클" --author maru --new-chain >/dev/null
report C001-first "첫 사이클의 보고. 채택."
$GIL close demo C001-first --verdict supported >/dev/null

# 둘째 사이클 — 저자는 부모를 문서에 적었지만 open에 --parent를 주지 않았다.
# (v2.0.0부터 open은 이것을 거부하므로, 거짓의 탄생은 --new-root로 재현한다:
#  maru의 v1.x 바이너리가 조용히 만들어낸 것과 바이트 단위로 같은 상태다.)
$GIL open demo second --title "둘째 사이클" --author maru --new-root >/dev/null
cat >> rooms/experiment/chains/demo/C002-second/1-hypothesis.md <<'DOC'

## 이전 사이클의 교훈

부모: [demo/C001-first](../C001-first/5-report.md) — 이 사이클은 첫 사이클의 보고서에서 태어났다.
DOC
report C002-second "둘째 사이클의 보고. 채택."
$GIL close demo C002-second --verdict supported >/dev/null

echo "--- 픽스처 완성: 봉인된 거짓 ---"
grep '^parent:' rooms/experiment/chains/demo/C002-second/cycle.yaml
grep -n '부모:' rooms/experiment/chains/demo/C002-second/1-hypothesis.md
git tag -l 'cycle/*'
