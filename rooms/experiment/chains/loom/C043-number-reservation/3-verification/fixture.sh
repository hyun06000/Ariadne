#!/usr/bin/env bash
# C043 픽스처 — loom/C037의 그 순간을 재현한다: 소환자가 병렬 존재에게 번호를 예약하고,
# 자기가 main에서 사이클을 여는 상황. C037에서는 소환자(Clew)가 예약을 모르고 Weft의 번호를
# 재발급해 양보해야 했다. 이제 예약이 데이터이므로 gil open이 그 번호를 건너뛴다.
#   사용: bash fixture.sh <작업디렉토리> <gil 호출 문법>
set -euo pipefail
WORK="$1"; shift
GIL="$*"

rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK"
git init -q -b main .
git config user.email fixture@ariadne.test
git config user.name fixture

# 씨앗 사이클 (체인의 tip = C001)
$GIL open loom seed --title "씨앗" --author clew --new-chain >/dev/null
printf '# 5. 결과 보고\n\n## 요약\n\n씨앗.\n' > rooms/experiment/chains/loom/C001-seed/5-report.md
git add -A && git commit -q -m seed

echo "=== ① Clew가 Weft에게 C002를 예약한다 (병렬 소환 전) ==="
$GIL reserve loom go-web-port --for weft
git add -A && git commit -q -m "reserve C002 → weft"
echo "--- 예약 원장 (데이터가 됐다) ---"; sed -n '3p' rooms/experiment/chains/loom/reservations.tsv

echo ""
echo "=== ② Clew가 main에서 자기 사이클을 연다 — C037의 함정 지점 ==="
$GIL open loom clew-work --author clew --parent C001-seed
echo "   (C037에서는 여기서 C002를 재발급해 Weft의 번호를 뺏었다)"

echo ""
echo "=== ③ Weft가 (격리 워크트리에서) 자기 예약을 승격한다 ==="
$GIL open loom actual-work --author weft --parent C001-seed

echo ""
echo "=== 결과 ==="
echo "사이클 디렉토리:"; ls rooms/experiment/chains/loom/ | grep '^C0'
echo "예약 원장 (승격으로 비었나):"; cat rooms/experiment/chains/loom/reservations.tsv 2>/dev/null || echo "  (파일 없음 — 예약 소비됨)"
echo ""
echo "판정:"
test -d rooms/experiment/chains/loom/C002-actual-work && echo "  ✓ Weft가 예약된 C002를 받았다 (승격)"
test -d rooms/experiment/chains/loom/C003-clew-work && echo "  ✓ Clew는 C003으로 밀렸다 (선점 — 예약을 건너뛰었다)"
test ! -d rooms/experiment/chains/loom/C002-clew-work && echo "  ✓ Clew가 Weft의 번호를 뺏지 않았다 (C037의 버그가 불가능해졌다)"
$GIL fsck rooms/experiment/chains >/dev/null && echo "  ✓ fsck 위반 0 (예약은 사이클이 아니다 — 비침습)"
