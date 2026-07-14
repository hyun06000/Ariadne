#!/usr/bin/env bash
# loom/C035 — superseded_by 전방 포인터 검증.
# 두 구현(참조 gil.py / Go 바이너리)에 같은 시나리오를 걸고, 산출물을 대조한다.
#
#   ./run.sh                     # 저장소의 배포 패키지를 쓴다 (기본)
#   GIL_GO=/path/to/gil ./run.sh # 미리 빌드한 Go 바이너리 지정
#
# 결과는 runs/ 아래에 남는다. 종료 코드 0 = 기대 행동 전부 통과.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../../.." && pwd)"
PKG="$REPO/rooms/deployment/ariadne-spec"
RUNS="$HERE/runs"
WORK="$(mktemp -d)"
mkdir -p "$RUNS"

GIL_PY="python3 $PKG/gil.py"
GIL_GO="${GIL_GO:-$WORK/gil}"
[ -x "$GIL_GO" ] || (cd "$PKG/go" && go build -o "$GIL_GO" main.go) || { echo "Go 빌드 실패"; exit 1; }

pass=0; fail=0
check() { # check <이름> <조건이 참인가(0/1)> <메모>
  if [ "$2" -eq 0 ]; then printf '  ✓ %-28s %s\n' "$1" "${3:-}"; pass=$((pass+1));
  else printf '  ✗ %-28s %s\n' "$1" "${3:-}"; fail=$((fail+1)); fi
}

# 한 구현으로 같은 시나리오를 처음부터 수행한다: 두 사이클을 닫고(태그 각인) → 무효화.
scenario() { # scenario <이름> <gil 호출> <출력 디렉토리>
  local name="$1" gil="$2" out="$3"
  rm -rf "$out"; mkdir -p "$out"
  local sb="$WORK/sandbox-$name"
  rm -rf "$sb"; mkdir -p "$sb"; cd "$sb"
  git init -q -b main . && git config user.email t@t && git config user.name tester

  $gil open bench dirty --new-chain --author tester --date 2026-07-14 \
      --title "오염된 벤치마크: 원샷이라 믿었으나 멀티턴이었다" > "$out/01-open-dirty.txt" 2>&1
  echo "# 5. 보고 — 측정값 A (뒤에 오염 판명)" > rooms/experiment/chains/bench/C001-dirty/5-report.md
  $gil close bench C001-dirty --date 2026-07-14 --verdict supported > "$out/02-close-dirty.txt" 2>&1

  $gil open bench clean --parent C001-dirty --author tester --date 2026-07-15 \
      --title "오염 제거 후 재실험: 진짜 원샷" > "$out/03-open-clean.txt" 2>&1
  echo "# 5. 보고 — 측정값 B (유효)" > rooms/experiment/chains/bench/C002-clean/5-report.md
  $gil close bench C002-clean --date 2026-07-15 --verdict supported > "$out/04-close-clean.txt" 2>&1

  $gil verify > "$out/05-verify-before.txt" 2>&1; echo "rc=$?" >> "$out/05-verify-before.txt"
  # 기준선: supersede 전의 작업 트리 상태(‘?? bench/chain.md’ — open --new-chain의 산물, close는 사이클
  # 디렉토리만 커밋한다). 무변화의 기준은 "비어 있음"이 아니라 "기준선과 같음"이다.
  git status --short > "$out/00-worktree-baseline.txt"
  # 무효화가 5스텝 산출물을 건드리지 않았음의 증거: 문서들의 해시 (cycle.yaml만 변해야 한다)
  find rooms/experiment/chains/bench/C001-dirty -type f ! -name cycle.yaml | sort | xargs shasum \
      | sed 's|.*/||' > "$out/00-artifacts-before.txt"

  # T2: 닫힌(태그된) 사이클에 전방 포인터를 각인한다 — 5스텝·산출물은 손대지 않는다
  $gil supersede bench/C001-dirty bench/C002-clean > "$out/06-supersede.txt" 2>&1
  echo "rc=$?" >> "$out/06-supersede.txt"
  cp rooms/experiment/chains/bench/C001-dirty/cycle.yaml "$out/07-cycle-after.yaml"
  git log --format='%s' -1 > "$out/08-commit-subject.txt"
  git tag -n1 cycle/bench/C001-dirty > "$out/09-tag.txt" 2>&1
  git status --short > "$out/10-worktree-after.txt"
  find rooms/experiment/chains/bench/C001-dirty -type f ! -name cycle.yaml | sort | xargs shasum \
      | sed 's|.*/||' > "$out/10-artifacts-after.txt"

  $gil verify > "$out/11-verify-after.txt" 2>&1; echo "rc=$?" >> "$out/11-verify-after.txt"
  $gil fsck > "$out/12-fsck.txt" 2>&1; echo "rc=$?" >> "$out/12-fsck.txt"
  $gil log > "$out/13-log.txt" 2>&1
  $gil web -o "$out/14-web.html" > /dev/null 2>&1

  # T1: R11 음성 — 유령 참조와 자기 참조는 위반이어야 한다
  local y=rooms/experiment/chains/bench/C001-dirty/cycle.yaml
  sed -i.bak 's|^superseded_by:.*|superseded_by: bench/C999-ghost|' $y
  $gil fsck > "$out/15-fsck-ghost.txt" 2>&1; echo "rc=$?" >> "$out/15-fsck-ghost.txt"
  sed -i.bak 's|^superseded_by:.*|superseded_by: C001-dirty|' $y
  $gil fsck > "$out/16-fsck-self.txt" 2>&1; echo "rc=$?" >> "$out/16-fsck-self.txt"
  sed -i.bak 's|^superseded_by:.*|superseded_by: C002-clean|' $y   # 로컬 id 표기도 해소돼야 한다
  $gil fsck > "$out/17-fsck-local-ref.txt" 2>&1; echo "rc=$?" >> "$out/17-fsck-local-ref.txt"
  rm -f $y.bak
  git checkout -q -- $y

  # T1: supersede 자신의 거부 — 실재하지 않는 대상, 자기 자신. 거부는 저장소를 바꾸지 않아야 한다.
  git rev-parse HEAD > "$out/17-head-before-rejects.txt"
  $gil supersede bench/C001-dirty bench/C999-ghost > "$out/18-reject-ghost.txt" 2>&1
  echo "rc=$?" >> "$out/18-reject-ghost.txt"
  $gil supersede bench/C002-clean bench/C002-clean > "$out/19-reject-self.txt" 2>&1
  echo "rc=$?" >> "$out/19-reject-self.txt"
  git status --short > "$out/20-worktree-after-rejects.txt"
  git rev-parse HEAD > "$out/20-head-after-rejects.txt"
  cp rooms/experiment/chains/bench/C001-dirty/cycle.yaml "$out/20-cycle-after-rejects.yaml"
  cd "$REPO"
}

echo "=== 시나리오 실행 (참조 구현) ==="
scenario py "$GIL_PY" "$RUNS/ref"
echo "=== 시나리오 실행 (Go 구현) ==="
scenario go "$GIL_GO" "$RUNS/go"

echo
echo "=== T1: R11 — 참조 해소 검증 ==="
grep -q "R11" "$RUNS/ref/15-fsck-ghost.txt" && grep -q "rc=1" "$RUNS/ref/15-fsck-ghost.txt"; check "T1a 유령 참조 차단(ref)" $?
grep -q "R11" "$RUNS/ref/16-fsck-self.txt"  && grep -q "rc=1" "$RUNS/ref/16-fsck-self.txt";  check "T1b 자기 참조 차단(ref)" $?
grep -q "rc=0" "$RUNS/ref/17-fsck-local-ref.txt"; check "T1c 로컬 id 해소 허용(ref)" $?
grep -q "rc=1" "$RUNS/ref/18-reject-ghost.txt"; check "T1d supersede 유령 거부(ref)" $?
grep -q "rc=1" "$RUNS/ref/19-reject-self.txt";  check "T1e supersede 자기 거부(ref)" $?
diff -q "$RUNS/ref/17-head-before-rejects.txt" "$RUNS/ref/20-head-after-rejects.txt" > /dev/null \
  && diff -q "$RUNS/ref/07-cycle-after.yaml" "$RUNS/ref/20-cycle-after-rejects.yaml" > /dev/null \
  && diff -q "$RUNS/ref/00-worktree-baseline.txt" "$RUNS/ref/20-worktree-after-rejects.txt" > /dev/null
check "T1f 거부 시 저장소 무변화" $?   # HEAD·cycle.yaml·작업 트리 전부 기준선과 동일

echo "=== T2: 불변성 — supersede 후에도 verify가 조용하다 ==="
grep -q "rc=0" "$RUNS/ref/11-verify-after.txt"; check "T2a verify 무변조(ref)" $?
grep -q "rc=0" "$RUNS/go/11-verify-after.txt";  check "T2b verify 무변조(go)" $?
grep -q "migrate" "$RUNS/ref/08-commit-subject.txt"
check "T2c [migrate] 커밋" $? "$(cat "$RUNS/ref/08-commit-subject.txt")"
grep -q "migrate" "$RUNS/ref/09-tag.txt"; check "T2d 태그 이주 커밋으로 이동" $?
diff -q "$RUNS/ref/00-artifacts-before.txt" "$RUNS/ref/10-artifacts-after.txt" > /dev/null \
  && diff -q "$RUNS/ref/00-worktree-baseline.txt" "$RUNS/ref/10-worktree-after.txt" > /dev/null
check "T2e 5스텝 산출물 무변경" $?   # cycle.yaml 외 문서 해시 동일 + 작업 트리 기준선과 동일

echo "=== T3: 감사자가 정독 없이 본다 (log·web) ==="
grep -q "↣ superseded: bench/C002-clean" "$RUNS/ref/13-log.txt"; check "T3a log 전방 포인터" $?
grep -q 'class="supersede"' "$RUNS/ref/14-web.html"; check "T3b web 무효화 간선" $?
grep -q 'class="superseded"' "$RUNS/ref/14-web.html"; check "T3c web 무효화 노드(흐리게)" $?
grep -q '"superseded_by": "bench/C002-clean"' "$RUNS/ref/14-web.html"; check "T3d web 내장 JSON" $?
! grep -qE 'src=|href="http' "$RUNS/ref/14-web.html"; check "T3e web 외부 리소스 0" $?

echo "=== T4: 두 구현 대조 ==="
diff -q "$RUNS/ref/07-cycle-after.yaml" "$RUNS/go/07-cycle-after.yaml" > /dev/null; check "T4a cycle.yaml 동일" $?
diff -q "$RUNS/ref/13-log.txt" "$RUNS/go/13-log.txt" > /dev/null
[ $? -eq 0 ] && echo "  (log 전문 동일)" || diff <(grep "superseded" "$RUNS/ref/13-log.txt") <(grep "superseded" "$RUNS/go/13-log.txt") > /dev/null
check "T4b log superseded 표기 동일" $?   # 렌더 전문은 계약이 아니다 (SPEC §3.1, loom/C021)
diff -q "$RUNS/ref/14-web.html" "$RUNS/go/14-web.html" > /dev/null; check "T4c web 바이트 동일" $?
diff -q "$RUNS/ref/08-commit-subject.txt" "$RUNS/go/08-commit-subject.txt" > /dev/null; check "T4d [migrate] 커밋 메시지 동일" $?
grep -q "rc=1" "$RUNS/go/15-fsck-ghost.txt" && grep -q "R11" "$RUNS/go/15-fsck-ghost.txt"; check "T4e R11 판정 동일(go)" $?
grep -q "rc=1" "$RUNS/go/18-reject-ghost.txt" && grep -q "rc=1" "$RUNS/go/19-reject-self.txt"; check "T4f supersede 거부 동일(go)" $?

echo "=== T5: conformance (계약 판정) ==="
python3 "$PKG/conformance.py" --gil "python3 $PKG/gil.py" > "$RUNS/21-conformance-ref.txt" 2>&1
grep -qE "26/26" "$RUNS/21-conformance-ref.txt"
check "T5a 참조 구현 26/26" $? "$(tail -1 "$RUNS/21-conformance-ref.txt")"
python3 "$PKG/conformance.py" --gil "$GIL_GO" > "$RUNS/22-conformance-go.txt" 2>&1
grep -qE "26/26" "$RUNS/22-conformance-go.txt"
check "T5b Go 구현 26/26" $? "$(tail -1 "$RUNS/22-conformance-go.txt")"

echo
echo "합계: 통과 $pass · 실패 $fail"
rm -rf "$WORK"
[ "$fail" -eq 0 ]
