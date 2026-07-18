#!/usr/bin/env bash
# loom/C072-release-drift-gate — 재현 스크립트
# release drift 게이트의 계약을 두 층위로 검증한다:
#   (A) 판정기 통합 항목 RELEASE-DRIFT-GATE (참조 gil.py 통과, Go는 정직한 부재)
#   (B) 손수 재현: drift 저장소는 무변화 거부, 일치 저장소는 게이트 통과
#
# 사용: SPEC=<...>/ariadne-spec bash reproduce.sh
# 기본 SPEC 경로는 배포 패키지. 워크트리에서 돌리려면 SPEC를 그 워크트리 경로로 준다.
set -u
SPEC="${SPEC:-$(cd "$(dirname "$0")/../../../../../deployment/ariadne-spec" && pwd)}"
GIL="python3 $SPEC/gil.py"

echo "===================================================================="
echo "(A) 판정기: RELEASE-DRIFT-GATE + 회귀 0"
echo "===================================================================="
echo "--- 참조 구현 (gil.py): RELEASE-DRIFT-GATE PASS ∧ 총계 ---"
python3 "$SPEC/conformance.py" --gil "$GIL" 2>&1 | grep -E "RELEASE-DRIFT-GATE|계약 준수"

echo
echo "--- Go 구현: release는 referenceOnly → 게이트 미노출(정직한 부재), 총계 불변 ---"
GOBUILD=$(mktemp -d); cp "$SPEC/go/main.go" "$GOBUILD/"
( cd "$GOBUILD" && go mod init gilgo >/dev/null 2>&1 && go build -o "$GOBUILD/gil-go" . )
python3 "$SPEC/conformance.py" --gil "$GOBUILD/gil-go" 2>&1 | grep -E "RELEASE-DRIFT-GATE|계약 준수"

echo
echo "===================================================================="
echo "(B) 손수 재현: 게이트 거동"
echo "===================================================================="
mk() {  # $1=경로 $2=CHANGELOG본문 — v1.0.0 태그 있는 최소 릴리스 저장소
  local d="$1"; rm -rf "$d"; mkdir -p "$d/rooms/deployment/ariadne-spec" "$d/rooms/experiment/chains"
  printf '%b' "$2" > "$d/rooms/deployment/CHANGELOG.md"
  echo x > "$d/rooms/deployment/ariadne-spec/f.txt"
  git -C "$d" init -q -b main; git -C "$d" config user.name fx; git -C "$d" config user.email fx@t
  git -C "$d" add -A; git -C "$d" commit -q -m init
  git -C "$d" tag -a v1.0.0 -m "release v1.0.0"
}
rel() { $GIL release "$2" --notes n --package "$1/rooms/deployment/ariadne-spec" --root "$1/rooms/experiment/chains"; }
snap() { git -C "$1" status --porcelain; git -C "$1" rev-parse HEAD; git -C "$1" tag -l; }

echo "--- (B1) drift 저장소 (태그 v1.0.0만, CHANGELOG 엔트리 없음): release 1.1.0 ---"
D=$(mktemp -d)/drift; mk "$D" "# Changelog\n\n## [Unreleased]\n"
B=$(snap "$D"); rel "$D" 1.1.0; echo "exit=$?"; A=$(snap "$D")
[ "$B" = "$A" ] && echo "무변화(트리·커밋·태그): OK" || echo "무변화: FAIL"

echo "--- (B2) 일치 저장소 (태그 v1.0.0 + CHANGELOG [1.0.0]): release 1.1.0 ---"
C=$(mktemp -d)/clean
mk "$C" "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] — 2026-07-18\n\n- 첫 릴리스\n- 도구 변경: gil (마이너 이상 승격)\n"
OUT=$(rel "$C" 1.1.0 2>&1); echo "exit=$?"; echo "$OUT"
echo "$OUT" | grep -q drift && echo ">>> 위양성(일치를 drift로 막음): FAIL" || echo ">>> 게이트 통과(위양성 0): OK"
