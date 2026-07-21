#!/usr/bin/env bash
# C016 검증 — 잎 못을 브랜치에서 태그로 정식화(C011 결론).
#
# 두 케이스를 태그판 도구로 재실행:
#   caseM (merge): 두 산 잎 → lineage 머지 (C015 표적). 산 잎 태그·종결 태그.
#   caseB (backtrack): 3층 분기, 죽은 잎 2·산 잎 1 (C014 표적). 죽은 잎 태그·산 잎 태그·종결 태그.
# 도구가 gil/leaf/<hash> 태그·cycle/<name>/solved 태그를 내는지, 브랜치 못이 0인지 감사.
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c016-leaf-tag}"
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

# ══════════════════════════════════════════════════════════════════
# caseM — 두 산 잎 → lineage 머지 (C015 표적, 태그판)
# ══════════════════════════════════════════════════════════════════
RM="$SCRATCH/merge"; init_repo "$RM"
g open "$RM" --title "C016 caseM: 두 산 잎 → lineage 머지" --git
g step "$RM" --kind hypothesis --note "가설A" --git
g step "$RM" --kind verify --note "검증A" --git
g step "$RM" --kind analyze --outcome success --note "가지A 산 잎!" --git
g step "$RM" --kind hypothesis --to s1 --note "가설B" --git
g step "$RM" --kind verify --note "검증B" --git
g step "$RM" --kind analyze --outcome success --note "가지B 산 잎!" --git
g close "$RM" --lineage s4,s7 --verdict supported --date 2026-07-22 --git

# ══════════════════════════════════════════════════════════════════
# caseB — 3층 분기: 죽은 잎 2·산 잎 1 (C014 표적, 태그판)
# ══════════════════════════════════════════════════════════════════
RB="$SCRATCH/backtrack"; init_repo "$RB"
g open "$RB" --title "C016 caseB: 3층 분기 죽은 잎 2·산 잎 1" --git
g step "$RB" --kind hypothesis --note "가설1" --git
g step "$RB" --kind verify --note "검증1" --git
g step "$RB" --kind analyze --outcome backtrack --to s1 --note "가지1 죽음" --git
g step "$RB" --kind hypothesis --to s1 --note "가설2" --git
g step "$RB" --kind verify --note "검증2" --git
g step "$RB" --kind analyze --outcome backtrack --to s1 --note "가지2 죽음" --git
g step "$RB" --kind hypothesis --to s1 --note "가설3" --git
g step "$RB" --kind verify --note "검증3" --git
g step "$RB" --kind analyze --outcome success --note "가지3 산 잎!" --git
g close "$RB" --verdict supported --date 2026-07-22 --git

echo "SCRATCH=$SCRATCH"
echo ""
echo "=== caseM 태그·브랜치 ==="
echo "태그:"; git -C "$RM" tag -l | sed 's/^/  /'
echo "브랜치(gil/*):"; git -C "$RM" branch --list 'gil/*' | sed 's/^/  /' || echo "  (없음)"
echo ""
echo "=== caseB 태그·브랜치 ==="
echo "태그:"; git -C "$RB" tag -l | sed 's/^/  /'
echo "브랜치(gil/*):"; git -C "$RB" branch --list 'gil/*' | sed 's/^/  /' || echo "  (없음)"
echo ""
echo "=== caseB 그래프 (태그 데코레이션) ==="
git -C "$RB" log --all --graph --oneline --decorate | head -30
