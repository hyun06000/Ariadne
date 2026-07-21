#!/usr/bin/env bash
# 세 트리 변형을 gilv3 명령으로 짓는다: in-progress·solved·multi.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
G="python3 $HERE/gilv3.py"
C="$HERE/cases"
rm -rf "$C"; mkdir -p "$C"

# --- in-progress: 죽은 잎만 (산 잎 0) ---
IP="$C/in-progress"
$G open "$IP" --title "진행 중 사이클 (아직 정답 없음)"
$G step "$IP" --kind hypothesis --note "가설 A"
$G step "$IP" --kind verify --note "검증 A"
$G step "$IP" --kind analyze --outcome backtrack --to s1 --note "실패, 되돌아감"
# 여기서 멈춤 — 산 잎 없음

# --- solved: 산 잎 1 (C002 case 재현, 축약) ---
SV="$C/solved"
$G open "$SV" --title "정답 도달 사이클"
$G step "$SV" --kind hypothesis --note "가설 A"
$G step "$SV" --kind verify --note "검증 A"
$G step "$SV" --kind analyze --outcome backtrack --to s1 --note "실패"
$G step "$SV" --kind hypothesis --to s1 --note "가설 B"
$G step "$SV" --kind verify --note "검증 B"
$G step "$SV" --kind analyze --outcome success --note "채택 — 산 잎"

# --- multi: 산 잎 2 (최적화 사이클) ---
MU="$C/multi"
$G open "$MU" --title "최적화 사이클 (정답 여럿)"
$G step "$MU" --kind hypothesis --note "가설 A"
$G step "$MU" --kind verify --note "검증 A"
$G step "$MU" --kind analyze --outcome success --note "정답 1 — 산 잎"
# 되돌아가 두 번째 정답 (다른 정답도? = 최적화). 산 잎 뒤엔 step 불가하므로
# multi는 손으로 형제 가지를 잇는다: 산 잎에서 되돌아가는 건 v3 그리디상 새 사이클이나,
# 여기선 "한 트리에 산 잎 2"를 분류기가 구별하는지만 본다 → steps.yaml에 직접 추가.
python3 - "$MU" <<'PY'
import sys, os
d = sys.argv[1]
p = os.path.join(d, "steps.yaml")
extra = """- id: s5
  kind: hypothesis
  parent: s1
  outcome: null
  backtrack: null
  body: steps/s5.md
- id: s6
  kind: verify
  parent: s5
  outcome: null
  backtrack: null
  body: steps/s6.md
- id: s7
  kind: analyze
  parent: s6
  outcome: success
  backtrack: null
  body: steps/s7.md
"""
with open(p, "a", encoding="utf-8") as f:
    f.write(extra)
os.makedirs(os.path.join(d, "steps"), exist_ok=True)
for sid in ("s5","s6","s7"):
    open(os.path.join(d,"steps",sid+".md"),"w").write("# %s (두 번째 정답 가지)\n"%sid)
PY

echo "=== built cases ==="
for k in in-progress solved multi; do echo "-- $k --"; $G status "$C/$k"; done
echo "$C"
