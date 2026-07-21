#!/usr/bin/env bash
# C013 검증 — 실제 코드 아티팩트(다중 파일 calc/)를 공유 경로 한 벌로 두고,
# 스텝 커밋이 "증분 변경분"을 담게 한다. 사이클 디렉토리 복사 없음.
#
# C011(부모)의 모델 계승:
#   - 백트래킹 = git checkout <조상> + detached HEAD 커밋 (브랜치 이름 0, 머지 0).
#   - 1스텝 = 1커밋. 위계 = 커밋 메시지 trailer 지문. 잎 = 태그(못).
#
# C011과의 차이(이 사이클의 고유 기여):
#   - artifact.py 한 파일 "덮어쓰기" → calc/ 다중 파일 "증분 수정".
#   - 세 가지(A·B·C)가 모두 s1에서 갈라져 같은 파일 core.py를 서로 다르게 고침 (H4).
#     디렉토리 복사 방식이 흉내낼 수 없는 것: 물리 파일은 한 벌인데 세 버전이 그래프에 공존.
#
# 순수 깃으로만. gil.py/참조구현 소스는 안 고침. 임시 저장소는 메인 레포 밖(scratchpad).
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/bb9fdd96-c034-4239-a589-5d66caf9e63b/scratchpad/c013-codebase}"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
R="$SCRATCH/repo"; mkdir -p "$R"
git -C "$R" init -q
git -C "$R" config user.email "bobbin@ariadne.local"
git -C "$R" config user.name "bobbin"
git -C "$R" config advice.detachedHead false

CALC="$R/calc"; mkdir -p "$CALC"

# 스텝 커밋 헬퍼: 1스텝=1커밋. 파일 시스템 상태(작업트리)를 그대로 커밋한다.
# 즉 이전 스텝의 파일에 대한 "증분 수정"이 diff로 잡힌다 (전체 덮어쓰기 아님).
# 인자: sid kind parent outcome backtrack chain cycle role
step() {
  local sid="$1" kind="$2" parent="$3" outcome="$4" bt="$5" chain="$6" cycle="$7" role="$8"
  git -C "$R" add -A
  local subj="step: $sid $kind"; [ -n "$outcome" ] && subj="$subj/$outcome"
  local body="Step-Id: $sid
Kind: $kind
Parent: $parent
Chain: $chain
Cycle: $cycle
Role: $role"
  [ -n "$outcome" ] && body="$body
Outcome: $outcome"
  [ -n "$bt" ] && body="$body
Backtrack-To: $bt"
  git -C "$R" commit -q -m "$subj

$body"
  remember "$sid"   # 모든 스텝 커밋을 자동 기억 (measure가 전 스텝 해시 필요 — M1)
}
remember() { eval "CI_$1=\"$(git -C "$R" rev-parse HEAD)\""; }
ci() { eval "echo \"\$CI_$1\""; }

# ── 루트(체인 시작): 빈 골격 ──
cat > "$CALC/__init__.py" <<'EOF'
"""calc — a tiny calculator package (C013 code-artifact demo)."""
__version__ = "0.0.0"
EOF
git -C "$R" add -A
git -C "$R" commit -q -m "root: chain v3-demo 시작 (calc 골격)

Step-Id: s0
Kind: root
Parent: null
Chain: v3-demo
Cycle: null
Role: chain-root"
remember s0

# ── 사이클 루트 define s1: util.py 도입 + core.py 문제정의 스텁 ──
cat > "$CALC/util.py" <<'EOF'
"""calc.util — shared helpers."""


def validate(x):
    if not isinstance(x, (int, float)):
        raise TypeError("numbers only")
    return x
EOF
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. s1: problem defined, not yet implemented."""


def add(a, b):
    raise NotImplementedError("s1: add() to be implemented")
EOF
step s1 define s0 "" "" v3-demo C-demo cycle-root
remember s1   # 세 가지가 여기서 갈라진다

# ── 가지 A (s2·s3·s4, 죽음): core.add를 "순진한 문자열 연결" 방식으로 (버그 있는 접근) ──
# s2: core.py의 add()만 수정 (증분) — util은 안 건드림
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. BRANCH-A: naive string-concat approach."""


def add(a, b):
    # BRANCH-A-SIGNATURE: naive concat then cast (fragile)
    return int(str(a) + str(b))  # s2 branch-A 가설
EOF
step s2 hypothesis s1 "" "" v3-demo C-demo step
# s3: core.py에 검증 호출 추가 (또 증분)
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. BRANCH-A: naive string-concat approach."""
from calc.util import validate


def add(a, b):
    # BRANCH-A-SIGNATURE: naive concat then cast (fragile)
    validate(a); validate(b)
    return int(str(a) + str(b))  # s3 branch-A 검증
EOF
step s3 verify s2 "" "" v3-demo C-demo step
# s4: 분석 — "12"+"3"="123" 이라 add(12,3)=123, 틀림. 되돌아감.
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. BRANCH-A: DEAD — concat is not addition."""
from calc.util import validate


def add(a, b):
    # BRANCH-A-SIGNATURE: naive concat then cast (fragile) — WRONG: add(12,3)=123
    validate(a); validate(b)
    return int(str(a) + str(b))  # s4 branch-A 죽음(되돌아감→s1)
EOF
step s4 analyze s3 backtrack s1 v3-demo C-demo step
remember s4   # 죽은 잎 A

# ── 백트래킹 = checkout s1 (detached HEAD). core.py가 s1 스텁으로 자동 복원됨 ──
git -C "$R" checkout -q "$(ci s1)"

# ── 가지 B (s5·s6·s7, 죽음): core.add를 "재귀 increment" 방식으로 (같은 core.py, 다른 알고리즘) ──
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. BRANCH-B: recursive increment approach."""


def add(a, b):
    # BRANCH-B-SIGNATURE: recursion on b (blows stack for large b)
    if b == 0:
        return a
    return add(a + 1, b - 1)  # s5 branch-B 가설
EOF
step s5 hypothesis s1 "" "" v3-demo C-demo step
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. BRANCH-B: recursive increment approach."""
from calc.util import validate


def add(a, b):
    # BRANCH-B-SIGNATURE: recursion on b (blows stack for large b)
    validate(a); validate(b)
    if b == 0:
        return a
    return add(a + 1, b - 1)  # s6 branch-B 검증
EOF
step s6 verify s5 "" "" v3-demo C-demo step
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. BRANCH-B: DEAD — RecursionError on floats/large b."""
from calc.util import validate


def add(a, b):
    # BRANCH-B-SIGNATURE: recursion on b — WRONG: add(1, 1e9) blows stack, floats break
    validate(a); validate(b)
    if b == 0:
        return a
    return add(a + 1, b - 1)  # s7 branch-B 죽음(되돌아감→s1)
EOF
step s7 analyze s6 backtrack s1 v3-demo C-demo step
remember s7   # 죽은 잎 B

# ── 백트래킹 = checkout s1 다시 ──
git -C "$R" checkout -q "$(ci s1)"

# ── 가지 C (s8·s9·s10, 산 잎): core.add를 "+" 로 올바르게 + util.py에 헬퍼 추가 (다중 파일 증분) ──
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. BRANCH-C: the obvious correct approach."""


def add(a, b):
    # BRANCH-C-SIGNATURE: just use the language operator
    return a + b  # s8 branch-C 가설
EOF
step s8 hypothesis s1 "" "" v3-demo C-demo step
# s9: core.py에 validate 추가 + util.py에 헬퍼 추가 → 두 파일 증분 (H1 다중파일)
cat > "$CALC/core.py" <<'EOF'
"""calc.core — arithmetic. BRANCH-C: the obvious correct approach."""
from calc.util import validate


def add(a, b):
    # BRANCH-C-SIGNATURE: just use the language operator
    validate(a); validate(b)
    return a + b  # s9 branch-C 검증
EOF
cat >> "$CALC/util.py" <<'EOF'


def add_many(xs):
    """s9: helper added on BRANCH-C only."""
    total = 0
    for x in xs:
        total = total + validate(x)
    return total
EOF
step s9 verify s8 "" "" v3-demo C-demo step
# s10: __init__ 버전 올림 (또 다른 파일 증분) → 채택
cat > "$CALC/__init__.py" <<'EOF'
"""calc — a tiny calculator package (C013 code-artifact demo)."""
from calc.core import add
from calc.util import validate, add_many

__version__ = "1.0.0"  # s10 branch-C 산 잎! 채택
__all__ = ["add", "validate", "add_many"]
EOF
step s10 analyze s9 success "" v3-demo C-demo step
remember s10  # 산 잎

# ── 잎에 못(태그) 박기 (C011 규율): 죽은 잎도 태그로 영구 생존 ──
GIT_C() { git -C "$R" "$@"; }
tie_leaf() { local h="$1"; local s; s="$(GIT_C rev-parse --short "$h")"; GIT_C tag "gil/leaf/$s" "$h"; }
tie_leaf "$(ci s4)"    # 죽은 잎 A
tie_leaf "$(ci s7)"    # 죽은 잎 B
tie_leaf "$(ci s10)"   # 산 잎 C
GIT_C tag "cycle/C-demo/solved" "$(ci s10)"

# 산 잎을 작업트리에 체크아웃 (뷰어/사용자가 보는 "현재 코드" = 산 잎 한 벌)
GIT_C checkout -q "$(ci s10)"

# 해시 인덱스 기록 (measure가 죽은 잎 해시를 알도록)
{ for k in s0 s1 s2 s3 s4 s5 s6 s7 s8 s9 s10; do echo "$k $(ci $k)"; done; } > "$SCRATCH/commit-index.txt"

echo "SCRATCH=$SCRATCH"
echo "R=$R"
echo "=== 깃 그래프 전체 (뷰어가 보는 것 — 재구현 0) ==="
git -C "$R" log --all --graph --oneline --decorate | head -50
echo
echo "=== 작업트리 물리 파일 (공유 한 벌 — 복사 없음) ==="
( cd "$R" && git ls-files )
