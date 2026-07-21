#!/usr/bin/env bash
# C017 검증 — v3의 눈이 지문 없는 v2 유령을 건너뛴다 (읽기호환).
#
# 두 원장:
#   MIX  — pre-gil 유령(v2 스타일 일반 커밋 3개) 위에 v3 스텝 트리 각인.
#   PURE — 유령 0, 순수 v3 스텝 트리 (회귀 대조 = C016 caseB 축약).
# rebuild_migrate 가 MIX에서 안 죽고 v3 트리 온전 복원 + 유령 수 보고하는지 감사.
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c017-migrate}"
HERE="$(cd "$(dirname "$0")" && pwd)"
GILV3="$HERE/gilv3.py"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"

init_repo() {
  local R="$1"; mkdir -p "$R"
  git -C "$R" init -q -b main
  git -C "$R" config user.email "clew@ariadne.local"
  git -C "$R" config user.name "clew"
  git -C "$R" config advice.detachedHead false
}
g() { python3 "$GILV3" "$@"; }

# v3 스텝 트리 한 벌 각인 (open→3step→close, 산 잎 1)
imprint_v3() {
  local R="$1"
  g open "$R" --title "C017 v3 트리" --git
  g step "$R" --kind hypothesis --note "가설" --git
  g step "$R" --kind verify --note "검증" --git
  g step "$R" --kind analyze --outcome success --note "산 잎!" --git
  g close "$R" --verdict supported --date 2026-07-22 --git
}

# ══════════════════════════════════════════════════════════════════
# MIX — pre-gil 유령 3개(v2 스타일) 위에 v3 트리
# ══════════════════════════════════════════════════════════════════
RMIX="$SCRATCH/mix"; init_repo "$RMIX"
# v2 스타일 유령: gilv3 명령 아닌 일반 커밋 (trailer 지문 없음)
echo "legacy code v1" > "$RMIX/app.py"
git -C "$RMIX" add app.py && git -C "$RMIX" commit -q -m "feat: initial app (v2 시절, gil 이전)"
echo "legacy code v2" > "$RMIX/app.py"
git -C "$RMIX" add app.py && git -C "$RMIX" commit -q -m "fix: bug in app (여전히 pre-gil)"
echo "# README" > "$RMIX/README.md"
git -C "$RMIX" add README.md && git -C "$RMIX" commit -q -m "docs: add readme (마지막 유령)"
GHOST_COUNT=$(git -C "$RMIX" rev-list --count HEAD)   # =3 유령
# 그 위에 v3 스텝 트리 각인 (open은 빈 사이클 요구 → steps.yaml 없어야 함, 있음)
imprint_v3 "$RMIX"

# ══════════════════════════════════════════════════════════════════
# PURE — 유령 0, 순수 v3 (회귀 대조)
# ══════════════════════════════════════════════════════════════════
RPURE="$SCRATCH/pure"; init_repo "$RPURE"
imprint_v3 "$RPURE"

echo "SCRATCH=$SCRATCH"
echo "GHOST_COUNT=$GHOST_COUNT (MIX의 pre-gil 유령 수)"
echo ""
echo "=== MIX 재구성 (rebuild_migrate --report) ==="
python3 "$HERE/rebuild_migrate.py" "$RMIX" --report
echo ""
echo "=== MIX 그래프 (유령 + v3) ==="
git -C "$RMIX" log --oneline | head -20
echo ""
echo "=== PURE 재구성 (--report) ==="
python3 "$HERE/rebuild_migrate.py" "$RPURE" --report
