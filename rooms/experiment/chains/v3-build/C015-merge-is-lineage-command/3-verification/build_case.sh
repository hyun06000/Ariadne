#!/usr/bin/env bash
# C015 검증 — lineage=머지=git merge --no-ff 를 gilv3 명령으로 재현.
#
# C012 build_merge.sh는 생 git checkout -b lane + git merge --no-ff 를 손으로 호출해
# 다중부모 머지 노드(C036 축약)를 짰다. C015는 그 합류를 gilv3.py 명령만으로 재현한다 —
# 생 git merge 0. 도구가 안에서 checkout(백트래킹)·merge(lineage)를 한다.
#
# 트리: s1 define 루트에서 두 형제 가지가 각각 산 잎으로 → multi_solution → lineage 머지.
#   가지A: s2 hyp → s3 verify → s4 analyze/success   (산 잎 A)
#   [live_leaf 백트래킹 → s1] (C015 정정: 산 잎 뒤 --to 로 새 정답 갈래)
#   가지B: s5 hyp → s6 verify → s7 analyze/success   (산 잎 B)
#   close --lineage s4,s7 → git merge --no-ff 다중부모 봉인 커밋
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c015-merge}"
HERE="$(cd "$(dirname "$0")" && pwd)"
GILV3="$HERE/gilv3.py"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
R="$SCRATCH/repo"; mkdir -p "$R"
git -C "$R" init -q -b main
git -C "$R" config user.email "clew@ariadne.local"
git -C "$R" config user.name "clew"
git -C "$R" config advice.detachedHead false

g() { python3 "$GILV3" "$@"; }

# ── open: 루트 define s1 ──
g open "$R" --title "C015 lineage=머지 실사례 (두 산 잎)" --git

# ── 가지 A: s2→s3→s4(success) ── 산 잎 A
g step "$R" --kind hypothesis --note "가설A" --git
g step "$R" --kind verify --note "검증A" --git
g step "$R" --kind analyze --outcome success --note "가지A 산 잎!" --git

# ── live_leaf 백트래킹 → 가지 B: s5(--to s1)→s6→s7(success) ── 산 잎 B
#   C015 정정: 산 잎 뒤 --to 로 '다른 정답' 갈래 (도구가 checkout s1 백트래킹)
g step "$R" --kind hypothesis --to s1 --note "가설B (다른 정답)" --git
g step "$R" --kind verify --note "검증B" --git
g step "$R" --kind analyze --outcome success --note "가지B 산 잎!" --git

# ── close --lineage s4,s7 (다중부모 머지 봉인) ──
#   도구가 checkout s4 → git merge --no-ff s7 → 다중부모 커밋 (생 merge 0)
g close "$R" --lineage s4,s7 --verdict supported --date 2026-07-22 --git

echo "SCRATCH=$SCRATCH"
echo "R=$R"

# ── 해시 기록: measure가 산 잎·머지 커밋을 알도록 ──
S4=$(git -C "$R" log --all --format="%H %(trailers:key=Step-Id,valueonly)" | awk '$2=="s4"{print $1}' | head -1)
S7=$(git -C "$R" log --all --format="%H %(trailers:key=Step-Id,valueonly)" | awk '$2=="s7"{print $1}' | head -1)
MERGE=$(git -C "$R" log --all --format="%H %(trailers:key=Step-Id,valueonly)" | awk '$2=="close-merge"{print $1}' | head -1)
{
  echo "s4 $S4"
  echo "s7 $S7"
  echo "merge $MERGE"
} > "$SCRATCH/commit-index.txt"

echo ""
echo "=== 깃 그래프 전체 (도구가 만든 것 — git log --all --graph) ==="
git -C "$R" log --all --graph --oneline --decorate | head -40
echo ""
echo "=== close-merge 커밋 전문 (다중부모 + trailer) ==="
git -C "$R" cat-file -p "$MERGE" | head -20
