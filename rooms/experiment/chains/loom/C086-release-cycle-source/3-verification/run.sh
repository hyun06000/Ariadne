#!/usr/bin/env bash
# C086 검증 — release --cycle 근거 사이클 계약화. 임시 저장소에서 재현.
set -u
GIL="$(cd "$(dirname "$0")/../../../../../.." && pwd)/rooms/deployment/ariadne-spec/gil.py"
W="$(mktemp -d)"; echo "work=$W"
cd "$W"
git init -q; git config user.email t@t; git config user.name t

PKG=rooms/deployment/ariadne-spec
mkdir -p "$PKG" rooms/experiment/_template
# 최소 패키지: gil 복사, CHANGELOG, RELEASE
cp "$GIL" "$PKG/gil.py"
printf '# CHANGELOG\n\n## [Unreleased]\n' > rooms/deployment/CHANGELOG.md
printf '# RELEASE\n\n## v0.1.0\n## v0.2.0\n' > "$PKG/RELEASE.md"
: > rooms/experiment/_template/keep
GILP="python3 $PKG/gil.py"

mkcycle() { # chain id status
  local cd="rooms/experiment/chains/$1"; local d="$cd/$2"; mkdir -p "$d/3-verification"
  [ -f "$cd/chain.md" ] || printf '# %s\n문제 정의.\n' "$1" > "$cd/chain.md"
  cat > "$d/cycle.yaml" <<EOF
id: $2
chain: $1
status: $3
$( [ "$3" = closed ] && echo "closed: 2026-07-20" && echo "step: \"5\"" && echo "verdict: supported" || echo "step: \"1\"" )
parent: null
EOF
  for n in 1 2 3 4 5; do : > "$d/$n-x.md"; done
}
mkcycle demo C001-done closed
mkcycle demo C002-open  open
git add -A; git commit -qm init

echo "--- T1: --cycle 닫힌 → 기록됨 ---"
$GILP release 0.1.0 --notes "first" --cycle demo/C001-done >/dev/null 2>t1.err && {
  grep -q "근거 사이클: demo/C001-done" rooms/deployment/CHANGELOG.md && echo "  T1 CHANGELOG: PASS" || echo "  T1 CHANGELOG: FAIL"
  git tag -l --format='%(contents)' v0.1.0 | grep -q "근거 사이클: demo/C001-done" && echo "  T1 TAG: PASS" || echo "  T1 TAG: FAIL"
  $GILP releases 2>/dev/null | grep -q "근거: demo/C001-done" && echo "  T1 releases렌더: PASS" || echo "  T1 releases렌더: FAIL"
  $GILP releases 2>/dev/null | grep -q "gil:release 0.1.0 .* cycles=1" && echo "  T1 훅 cycles=1: PASS" || echo "  T1 훅: FAIL"
} || { echo "  T1: FAIL (release exit≠0)"; cat t1.err; }

echo "--- T2: --cycle 열린 → 무변화 거부 ---"
before=$(git rev-parse HEAD); tbefore=$(git tag | wc -l | tr -d ' ')
$GILP release 0.2.0 --notes "x" --cycle demo/C002-open >/dev/null 2>t2.err
rc=$?; after=$(git rev-parse HEAD); tafter=$(git tag | wc -l | tr -d ' ')
[ $rc -ne 0 ] && [ "$before" = "$after" ] && [ "$tbefore" = "$tafter" ] \
  && echo "  T2: PASS (거부+무변화)" || echo "  T2: FAIL rc=$rc head동일=$([ "$before" = "$after" ] && echo y) 태그동일=$([ "$tbefore" = "$tafter" ] && echo y)"
grep -q "닫히지 않" t2.err && echo "  T2 메시지: PASS" || echo "  T2 메시지: (확인) $(cat t2.err | tail -1)"

echo "--- T3: --cycle 없는 id → 무변화 거부 ---"
before=$(git rev-parse HEAD)
$GILP release 0.2.0 --notes "x" --cycle demo/C999-nope >/dev/null 2>t3.err
rc=$?; after=$(git rev-parse HEAD)
[ $rc -ne 0 ] && [ "$before" = "$after" ] && echo "  T3: PASS (거부+무변화)" || echo "  T3: FAIL rc=$rc"

echo "--- T4: --cycle 무 → 종전 동작 ---"
$GILP release 0.2.0 --notes "plain" >/dev/null 2>t4.err && {
  grep -q "## \[0.2.0\]" rooms/deployment/CHANGELOG.md && ! grep -A3 "## \[0.2.0\]" rooms/deployment/CHANGELOG.md | grep -q "근거 사이클" \
    && echo "  T4: PASS (릴리스됨, 근거 불릿 없음)" || echo "  T4: FAIL"
} || { echo "  T4: FAIL (exit≠0)"; cat t4.err; }
echo "done"
