#!/usr/bin/env bash
# C012 검증 — 머지 = lineage = 지식 통합.
#
# C011은 분기(백트래킹=checkout+detached)를 순수 깃으로 증명했다.
# C012는 그 짝 — 합류(머지=lineage)를 순수 깃으로 증명한다.
#
# 실증 표적: loom/C036의 축약 재현 — parent: [C020, C016] 병합 노드.
#   C016 (number-ledger 계보) ─┐
#                               ├─▶ C036 (다중부모 머지 커밋 = lineage)
#   C020 (go-web-port 계보) ────┘
#
# 규율(C011 계승): 도구(gilv3.py) 안 고침. 순수 깃으로 원리만. 임시 저장소는 메인 밖.
# 각 갈래는 자기 코드 아티팩트를 다르게 발전 → 머지가 둘을 실제 통합(M4).
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/bb9fdd96-c034-4239-a589-5d66caf9e63b/scratchpad/c012-merge}"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
R="$SCRATCH/repo"; mkdir -p "$R"
git -C "$R" init -q -b main
git -C "$R" config user.email "clew@ariadne.local"
git -C "$R" config user.name "clew"
git -C "$R" config advice.detachedHead false

GIT_C() { git -C "$R" "$@"; }

# 스텝 커밋 헬퍼: 1스텝=1커밋. 위계 지문 trailer + 코드 아티팩트 변경.
# 인자: file content sid kind parent chain cycle [outcome] [extra_trailer]
step() {
  local file="$1" content="$2" sid="$3" kind="$4" parent="$5" chain="$6" cycle="$7" outcome="$8" extra="$9"
  echo "$content" > "$R/$file"
  GIT_C add "$file"
  local subj="step: $sid $kind"; [ -n "$outcome" ] && subj="$subj/$outcome"
  local body="Step-Id: $sid
Kind: $kind
Parent: $parent
Chain: $chain
Cycle: $cycle"
  [ -n "$outcome" ] && body="$body
Outcome: $outcome"
  [ -n "$extra" ] && body="$body
$extra"
  GIT_C commit -q -m "$subj

$body"
}
remember() { eval "CI_$1=\"$(GIT_C rev-parse HEAD)\""; }
ci() { eval "echo \"\$CI_$1\""; }

# ── 체인 루트 s0 ──
echo "# ariadne v3-demo 체인 루트" > "$R/README.md"
GIT_C add README.md
GIT_C commit -q -m "root: chain v3-demo 시작

Step-Id: s0
Kind: root
Parent: null
Chain: v3-demo
Cycle: null"
remember s0

# ══════════════════════════════════════════════════════════════════
# 갈래 A — 사이클 C016 (number-ledger 계보): ledger.py를 발전시킴
# ══════════════════════════════════════════════════════════════════
GIT_C checkout -q -b lane-C016 "$(ci s0)"
step ledger.py "def next_number():  # C016 s1: 원장에서 번호 채번
    return read_ledger_tip() + 1" \
    s1 define s0 v3-demo C016
step ledger.py "def next_number():  # C016 s2: 경합 시 재번호-재시도
    while True:
        n = read_ledger_tip() + 1
        if try_claim(n): return n" \
    s2 verify s1 v3-demo C016 success
remember lane_C016   # C016 갈래 팁 (통합될 첫 부모)

# ══════════════════════════════════════════════════════════════════
# 갈래 B — 사이클 C020 (go-web-port 계보): web.py를 발전시킴
#   C011이 증명한 분기: s0에서 checkout 후 새 갈래 (독립 파일 = 다른 영역)
# ══════════════════════════════════════════════════════════════════
GIT_C checkout -q -b lane-C020 "$(ci s0)"
step web.py "def render_web():  # C020 s1: 자기완결 HTML 이식
    return html_shell() + gil_data_json()" \
    s1 define s0 v3-demo C020
step web.py "def render_web():  # C020 s2: 스텝 배지까지 26/26
    return html_shell() + gil_data_json() + step_badges()" \
    s2 verify s1 v3-demo C020 success
remember lane_C020   # C020 갈래 팁 (통합될 둘째 부모)

# ══════════════════════════════════════════════════════════════════
# ★ 합류 = 머지 = lineage = 지식 통합 ★
#   두 갈래(C016·C020)를 --no-ff 머지 → 다중부모 커밋 C036.
#   --no-ff 필수: fast-forward로 접히면 다중부모 커밋이 안 생김(M4 기각 조건).
#   gil의 parent: [C020, C016]  ≅  git 머지 커밋의 두 부모.
#   trailer에 gil 논리 위계(Parent: C020, C016) 지문 각인.
# ══════════════════════════════════════════════════════════════════
# C020 갈래 위에서 C016 갈래를 병합 (현재 HEAD=lane-C020)
# 두 갈래가 다른 파일(web.py vs ledger.py)을 고쳐 자동 병합 성공 → 두 기여 모두 담김.
GIT_C merge --no-ff -q "$(ci lane_C016)" -m "merge: C036 ← lineage [C020, C016] 지식 통합

Step-Id: C036-merge
Kind: merge
Parent: C020, C016
Chain: v3-demo
Cycle: C036
Merge: lineage
Note: go-web-port(C020)과 number-ledger(C016) 두 계보의 통합"
remember c036_merge   # 다중부모 머지 커밋

# ── 통합 이후: C036이 두 계보를 물려받아 스텝 계속 → 산 잎 ──
# ledger.py와 web.py가 둘 다 존재해야 함(M4: 실제 통합의 증거)
step integrated.py "def go_open_git_ledger():  # C036 s1: 두 계보 위에서 open --git 이식
    render_web()      # C020 계보에서
    next_number()     # C016 계보에서
    return 'imprinted'" \
    s1 define C036-merge v3-demo C036
step integrated.py "def go_open_git_ledger():  # C036 s2: 산 잎! 두 몸 나란히 (supported)
    render_web(); next_number(); return 'go 28/28'" \
    s2 analyze s1 v3-demo C036 success
remember c036_leaf   # 산 잎

# ── 잎 = 태그(못) — C011 계승 ──
tie_leaf() { local h="$1"; local s; s="$(GIT_C rev-parse --short "$h")"; GIT_C tag "gil/leaf/$s" "$h"; }
tie_leaf "$(ci c036_leaf)"                          # 산 잎 해시 태그
GIT_C tag "cycle/C036/solved" "$(ci c036_leaf)"     # 사이클 종결 태그(의미 이름)

# ── 해시 기록을 파일로 (measure가 갈래 팁·머지 커밋을 알도록) ──
{
  echo "s0 $(ci s0)"
  echo "lane_C016 $(ci lane_C016)"
  echo "lane_C020 $(ci lane_C020)"
  echo "c036_merge $(ci c036_merge)"
  echo "c036_leaf $(ci c036_leaf)"
} > "$SCRATCH/commit-index.txt"

echo "SCRATCH=$SCRATCH"
echo "R=$R"
echo "=== 깃 그래프 전체 (뷰어가 보는 것 — git log --all --graph) ==="
GIT_C log --all --graph --oneline --decorate | head -40
