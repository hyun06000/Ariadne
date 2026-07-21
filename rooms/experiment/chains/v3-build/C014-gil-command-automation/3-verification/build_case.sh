#!/usr/bin/env bash
# C014 검증 — 백트래킹=checkout을 gilv3.py 명령으로 재현.
#
# C011 build_branches.sh는 생 git checkout을 손으로 호출해 3층 분기를 짰다.
# C014는 그 트리를 gilv3.py 명령(open/step)만으로 재현한다 — 생 git checkout 0.
# 도구가 안에서 checkout 백트래킹을 한다(C011 원리 → 도구 동작).
#
# 트리(C011 실사례와 동형): s1 define 루트에서 세 형제 가지가 갈라짐.
#   가지1: s2 hyp → s3 verify → s4 analyze/backtrack→s1   (죽은 잎)
#   가지2: s5 hyp → s6 verify → s7 analyze/backtrack→s1   (죽은 잎)
#   가지3: s8 hyp → s9 verify → s10 analyze/success        (산 잎)
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/bb9fdd96-c034-4239-a589-5d66caf9e63b/scratchpad/c014-auto}"
HERE="$(cd "$(dirname "$0")" && pwd)"
GILV3="$HERE/gilv3.py"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
R="$SCRATCH/repo"; mkdir -p "$R"
git -C "$R" init -q -b main
git -C "$R" config user.email "clew@ariadne.local"
git -C "$R" config user.name "clew"
git -C "$R" config advice.detachedHead false

g() { python3 "$GILV3" "$@"; }

# ── open: 루트 define s1 (커밋 각인) ──
g open "$R" --title "C014 백트래킹=checkout 실사례" --git

# ── 가지 1: s2→s3→s4(backtrack→s1) ── 죽은 잎
g step "$R" --kind hypothesis --note "가설1" --git
g step "$R" --kind verify --note "검증1" --git
g step "$R" --kind analyze --outcome backtrack --to s1 --note "가지1 죽음" --git

# ── 가지 2: s5(--to s1)→s6→s7(backtrack→s1) ── 죽은 잎
#   여기서 도구가 checkout s1 백트래킹을 수행(dead_leaf 상태 + --to s1)
g step "$R" --kind hypothesis --to s1 --note "가설2" --git
g step "$R" --kind verify --note "검증2" --git
g step "$R" --kind analyze --outcome backtrack --to s1 --note "가지2 죽음" --git

# ── 가지 3: s8(--to s1)→s9→s10(success) ── 산 잎
g step "$R" --kind hypothesis --to s1 --note "가설3" --git
g step "$R" --kind verify --note "검증3" --git
g step "$R" --kind analyze --outcome success --note "가지3 산 잎!" --git

# ── close (봉인) ──
g close "$R" --verdict supported --date 2026-07-22 --git || true

echo "SCRATCH=$SCRATCH"
echo "R=$R"
echo "=== 깃 그래프 전체 (도구가 만든 것 — git log --all --graph) ==="
git -C "$R" log --all --graph --oneline --decorate | head -40
echo ""
echo "=== steps.yaml (논리 트리) ==="
cat "$R/steps.yaml"
