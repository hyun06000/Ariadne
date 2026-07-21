#!/usr/bin/env bash
# C020 검증 — 실제 원장 전량을 격리 복제본에서 순회 소급 (드라이런).
#
# ⭐ 격리 철칙: 우리 실제 저장소는 절대 안 건드린다. git clone 복제본에서만 각인.
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c020-fullledger}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# 우리 실제 저장소 루트 (이 파일에서 6단계 위)
REAL_REPO="$(cd "$HERE/../../../../../.." && pwd)"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
CLONE="$SCRATCH/clone"

echo "=== 실제 저장소: $REAL_REPO ==="
echo "=== 격리 복제본 clone 중... ==="
git clone -q "$REAL_REPO" "$CLONE"
git -C "$CLONE" config user.email "clew@ariadne.local"
git -C "$CLONE" config user.name "clew"

# 소급 전 상태
echo ""
echo "=== 소급 전 복제본 상태 ==="
echo "전체 커밋: $(git -C "$CLONE" rev-list --count HEAD)"
echo "gil step 커밋: $(git -C "$CLONE" log --format=%s | grep -cE '^gil: step')"

echo ""
echo "=== 전량 순회 드라이런 (도출만, 미각인) ==="
python3 "$HERE/full_ledger_migrate.py" "$CLONE"

echo ""
echo "=== 전량 순회 실제 각인 (복제본에 notes) ==="
python3 "$HERE/full_ledger_migrate.py" "$CLONE" --apply

# 복제본 원본 커밋 SHA 스냅샷 (불변 확인용)
git -C "$CLONE" rev-list HEAD > "$SCRATCH/clone-shas-after.txt"
echo ""
echo "SCRATCH=$SCRATCH"
echo "CLONE=$CLONE"
echo "REAL_REPO=$REAL_REPO"
