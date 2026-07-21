#!/usr/bin/env bash
# C011 검증 — 백트래킹=checkout+detached HEAD 커밋, 위계는 커밋 메시지 지문에.
#
# 상현님 모델(2026-07-21, 이 사이클 대화):
#   - 백트래킹은 새 브랜치가 아니다. git checkout <조상커밋>으로 되돌아가
#     detached HEAD에서 커밋하면 분기가 자연히 생긴다 (브랜치 이름 0).
#   - 위계 지문은 커밋 메시지 trailer에 남긴다 (Chain·Cycle·Step-Id·Parent).
#   - 뷰어 = git 그래프 전체 + 커밋 메시지. 우리는 아무 것도 새로 그리지 않는다.
#
# 각 스텝 커밋은 코드 아티팩트(artifact.py)를 변경 — 롤백 검증용.
# 브랜치명은 최소만(main 하나) — 분기는 detached HEAD로. 임시 저장소는 메인 레포 밖.
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/c0664b20-c4aa-4a97-8421-618e91963c15/scratchpad/c011-branches}"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
R="$SCRATCH/repo"; mkdir -p "$R"
git -C "$R" init -q
git -C "$R" config user.email "clew@ariadne.local"
git -C "$R" config user.name "clew"
git -C "$R" config advice.detachedHead false

# 스텝 커밋 헬퍼: 1스텝=1커밋. 코드 아티팩트 변경 + 위계 지문 trailer.
# 반환: 방금 만든 커밋 해시를 stdout 마지막 줄에.
# 인자: sid kind parent outcome backtrack content chain cycle role
step() {
  local sid="$1" kind="$2" parent="$3" outcome="$4" bt="$5" content="$6" \
        chain="$7" cycle="$8" role="$9"
  echo "$content" > "$R/artifact.py"
  git -C "$R" add artifact.py
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
}

# 커밋 해시를 sid로 기억 (checkout 되돌아감 대상 파악용).
# bash 3.2 호환 — 연관배열 대신 개별 변수(CI_s1 등).
remember() { eval "CI_$1=\"$(git -C "$R" rev-parse HEAD)\""; }
ci() { eval "echo \"\$CI_$1\""; }

# ── 루트(체인 시작) ──
echo "# ariadne root" > "$R/artifact.py"; git -C "$R" add artifact.py
git -C "$R" commit -q -m "root: chain v3-demo 시작

Step-Id: s0
Kind: root
Parent: null
Chain: v3-demo
Cycle: null
Role: chain-root"
remember s0

# ── 사이클 루트 define s1 (체인 위에 계승 커밋) ──
step s1 define s0 "" "" "def solve(): pass  # s1 문제정의" v3-demo C-demo cycle-root
remember s1

# ── 가지 1: s1에서 계승 → s4에서 죽음 (백트래킹 없이 그냥 이어짐) ──
step s2 hypothesis s1 "" "" "def solve(): return detkey_fix()  # s2 가설1" v3-demo C-demo step
step s3 verify s2 "" "" "def solve(): return detkey_fix()  # s3 검증" v3-demo C-demo step
step s4 analyze s3 backtrack s1 "def solve(): return detkey_fix()  # s4 죽음(되돌아감→s1)" v3-demo C-demo step
remember s4   # 죽은 잎 (이름 없음, 해시로만)

# ── 백트래킹 = checkout s1 (detached HEAD). 브랜치 안 만든다 ──
git -C "$R" checkout -q "$(ci s1)"

# ── 가지 2: detached HEAD s1에서 새 스텝 → 분기 자연 발생 → s7 죽음 ──
step s5 hypothesis s1 "" "" "def solve(): return poll_bisect()  # s5 가설2" v3-demo C-demo step
step s6 verify s5 "" "" "def solve(): return poll_bisect()  # s6 검증" v3-demo C-demo step
step s7 analyze s6 backtrack s1 "def solve(): return poll_bisect()  # s7 죽음(되돌아감→s1)" v3-demo C-demo step
remember s7   # 죽은 잎

# ── 백트래킹 = checkout s1 다시 ──
git -C "$R" checkout -q "$(ci s1)"

# ── 가지 3: s1에서 → s10 산 잎 ──
step s8 hypothesis s1 "" "" "def solve(): return preserve_identity()  # s8 가설3" v3-demo C-demo step
step s9 verify s8 "" "" "def solve(): return preserve_identity()  # s9 검증" v3-demo C-demo step
step s10 analyze s9 success "" "def solve(): return preserve_identity()  # s10 산 잎! 채택" v3-demo C-demo step
remember s10  # 산 잎

# ── 발견(C011): detached HEAD 죽은 가지는 ref가 없으면 git log --all이 못 본다.
#    커밋은 저장소에 살아있으나(git show 가능) 그래프에서 사라진다 → gc 위험.
#    상현님 이름 규칙(2026-07-21): 체인·사이클 분기는 사람 이름(의미), 스텝 분기는
#    구분용 해시로 충분 — 논리 id(s4)는 커밋 지문(trailer)에.
#
#    ref 종류 선택(Clew, 깃 관점): 잎은 "다시 작업 안 하는 불변 시점"이다(죽은
#    가지=벽의 지도, 산 잎=닫힌 사이클). 브랜치(움직이는 포인터)보다 **태그**(불변
#    표식)가 의미상 정확하고, gil v2가 이미 사이클을 태그로 닫는 것과 일관된다.
#    결정적 이득: 태그는 **push되어** 모든 머신에서 죽은 가지가 영구 생존한다
#    (커스텀 refs/gil/*는 기본 push 안 됨 → 다른 머신서 소멸; 상현님은 여러 머신
#    작업이라 "존재는 레포에만 산다"와 맞물려 태그가 옳다).
GIT_C() { git -C "$R" "$@"; }
tie_leaf() {  # 잎 커밋을 해시 기반 불변 태그로 못박는다 (스텝 분기 = 해시 식별)
  local h="$1"; local short; short="$(GIT_C rev-parse --short "$h")"
  GIT_C tag "gil/leaf/$short" "$h"
}
tie_leaf "$(ci s4)"    # 죽은 잎 1 (해시 태그)
tie_leaf "$(ci s7)"    # 죽은 잎 2 (해시 태그)
tie_leaf "$(ci s10)"   # 산 잎 (해시 태그)
# 사이클 종결 = 산 잎에 사이클 이름 태그 (체인·사이클은 의미 이름, 상현님)
GIT_C tag "cycle/C-demo/solved" "$(ci s10)"

# 해시 기록을 파일로 남김 (measure가 죽은 잎 해시를 알도록)
{ for k in s0 s1 s4 s7 s10; do echo "$k $(ci $k)"; done; } > "$SCRATCH/commit-index.txt"

echo "SCRATCH=$SCRATCH"
echo "R=$R"
echo "=== 깃 그래프 전체 (뷰어가 보는 것) ==="
git -C "$R" log --all --graph --oneline --decorate | head -40
