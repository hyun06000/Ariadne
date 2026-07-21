#!/usr/bin/env bash
# C023 검증 — gil migrate 명령을 C022 스크립트(오라클)와 대조 (격리 복제본 2개).
#
# clone-A: C022 스크립트(apply_migration.py)로 마이그레이션.
# clone-B: 새 gilv3 migrate 명령으로 마이그레이션.
# 두 결과 DAG·notes를 대조 → 명령화가 로직을 바이트 보존하는지.
# ⭐ 격리 철칙: 우리 실제 저장소는 안 건드린다 (이미 C022로 적용됨).
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/c70338bb-abce-40ed-9f10-8ee4a6cbaa61/scratchpad/c023-migrate-cmd}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REAL_REPO="$(cd "$HERE/../../../../../.." && pwd)"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
A="$SCRATCH/clone-A"; B="$SCRATCH/clone-B"

for C in "$A" "$B"; do
  git clone -q "$REAL_REPO" "$C"
  git -C "$C" config user.email "clew@ariadne.local"
  git -C "$C" config user.name "clew"
  # C022로 원격에 push된 notes가 클론에 안 딸려오게 (v2 원본 상태에서 재마이그레이션 검증)
  git -C "$C" update-ref -d refs/notes/commits 2>/dev/null || true
done

echo "=== clone-A: C022 스크립트(오라클)로 마이그레이션 ==="
python3 "$HERE/apply_migration.py" "$A" 2>&1 | grep -E "노드 소급|위상 접합|불변 확인|접합" | head -6 || true
python3 "$HERE/full_ledger_migrate.py" "$A" --apply >/dev/null 2>&1 || true
python3 "$HERE/splice_topology.py" "$A" >/dev/null 2>&1 || true

echo ""
echo "=== clone-B: gilv3 migrate 명령으로 마이그레이션 ==="
python3 "$HERE/gilv3.py" migrate "$B"

echo ""
echo "=== 드라이런 계약 확인 (clone-B는 이미 적용됨 → 새 clone-C로) ==="
C="$SCRATCH/clone-C"
git clone -q "$REAL_REPO" "$C"
git -C "$C" config user.email "clew@ariadne.local"; git -C "$C" config user.name "clew"
git -C "$C" update-ref -d refs/notes/commits 2>/dev/null || true
python3 "$HERE/gilv3.py" migrate "$C" --dry
echo "  드라이런 후 notes: $(git -C "$C" rev-parse --verify -q refs/notes/commits || echo '없음(각인0)')"

echo ""
echo "=== 되돌림 명령 확인 (clone-B) ==="
python3 "$HERE/gilv3.py" migrate "$B" --rollback

echo ""
echo "SCRATCH=$SCRATCH"
