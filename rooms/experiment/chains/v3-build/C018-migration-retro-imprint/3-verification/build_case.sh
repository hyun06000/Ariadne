#!/usr/bin/env bash
# C018 검증 — git notes로 유령에 지문 소급 각인 (커밋 불변).
#
# C017 혼합 원장(pre-gil 유령 3 + v3 트리)을 재구성하고, pre-gil 3개에 notes로
# v3 지문을 소급 각인한 뒤 재구성기가 notes+trailer로 읽어 유령이 노드가 되는지 감사.
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c018-retro}"
HERE="$(cd "$(dirname "$0")" && pwd)"
GILV3="$HERE/gilv3.py"
RETRO="$HERE/retro_imprint.py"
REBUILD="$HERE/rebuild_migrate.py"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
R="$SCRATCH/repo"; mkdir -p "$R"
git -C "$R" init -q -b main
git -C "$R" config user.email "clew@ariadne.local"
git -C "$R" config user.name "clew"
git -C "$R" config advice.detachedHead false
g() { python3 "$GILV3" "$@"; }

# ── pre-gil 유령 3개 (v2 스타일 일반 커밋) ──
echo "legacy v1" > "$R/app.py"; git -C "$R" add app.py; git -C "$R" commit -q -m "feat: initial (pre-gil)"
echo "legacy v2" > "$R/app.py"; git -C "$R" add app.py; git -C "$R" commit -q -m "fix: bug (pre-gil)"
echo "# doc"     > "$R/README.md"; git -C "$R" add README.md; git -C "$R" commit -q -m "docs: readme (pre-gil)"

# 유령 3개의 해시 (시간순)
G1=$(git -C "$R" log --reverse --format=%H | sed -n 1p)
G2=$(git -C "$R" log --reverse --format=%H | sed -n 2p)
G3=$(git -C "$R" log --reverse --format=%H | sed -n 3p)

# ── 그 위에 v3 스텝 트리 ──
g open "$R" --title "C018 v3 트리" --git
g step "$R" --kind hypothesis --note "가설" --git
g step "$R" --kind verify --note "검증" --git
g step "$R" --kind analyze --outcome success --note "산 잎!" --git
g close "$R" --verdict supported --date 2026-07-22 --git

echo "SCRATCH=$SCRATCH"
echo ""
echo "=== 소급각인 전 재구성 (--report) ==="
python3 "$REBUILD" "$R" --report 2>&1 | head -1

# ── pre-gil 3개에 v3 지문 소급 각인 (legacy 계보 L1→L2→L3) ──
echo ""
echo "=== 소급각인 실행 ==="
python3 "$RETRO" "$R" "$G1" Step-Id=L1 Kind=define Parent=null
python3 "$RETRO" "$R" "$G2" Step-Id=L2 Kind=hypothesis Parent=L1
python3 "$RETRO" "$R" "$G3" Step-Id=L3 Kind=verify Parent=L2

# ── close 커밋에도 소급각인 시도 (H1d: 이미 v3라 건너뛰어야) ──
CLOSE=$(git -C "$R" log --format="%H %s" | awk '/gilv3 close/{print $1; exit}')
echo ""
echo "=== close 커밋 소급각인 시도 (건너뛰어야) ==="
python3 "$RETRO" "$R" "$CLOSE" Step-Id=XX Kind=merge Parent=null

echo ""
echo "=== 소급각인 후 재구성 (--report) ==="
python3 "$REBUILD" "$R" --report

# 해시 기록
{ echo "G1 $G1"; echo "G2 $G2"; echo "G3 $G3"; echo "CLOSE $CLOSE"; } > "$SCRATCH/commit-index.txt"
