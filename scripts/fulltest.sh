#!/bin/sh
# fulltest.sh — 전체 시험을 **스냅샷에서** 돌린다. 도는 동안 소스를 계속 고쳐도 안 오염된다.
#
# 왜 있나. 전체 판은 4~6분이고, 그걸 커밋마다 기다리면 한 세션에 30분이 시험 대기로 간다
# (2026-08-10 실측: 한 세션에 6회·29분 — 그리고 그 6회가 **전부 통과**했다. 실패를 잡은
# 것은 전부 `-k` 로 돌린 관련 클래스였다).
#
# 그런데 전체가 값을 하는 자리가 분명히 있다: **구조를 옮겼을 때**다. 렌더러를 다른 파일로
# 옮기자 그 파일 이름을 박아 둔 시험 둘이 **다른 클래스에서** 눈이 멀었고, `-k` 로는 못
# 잡았다. 뷰어를 지웠을 때도 다섯 클래스가 그랬다.
#
# 그래서 비용을 없앤다 — 돌리는 것과 **기다리는 것**을 가른다. 이 스크립트는 저장소를
# 스냅샷으로 뜨고 그 사본에서 돌린다(`GIL_BIN` 으로 그때의 바이너리를 물린다). 배경에
# 걸어 두고 계속 작업하면 된다.
#
# 쓰는 법:
#   scripts/fulltest.sh                 (스냅샷 뜨고 전체)
#   scripts/fulltest.sh -k <이름조각>   (스냅샷 뜨고 일부)
#   결과: <스냅샷>/out.txt  — 끝에 exit= 가 붙는다
#
# **배치를 그대로 뜬다 — 추적 파일 전부.** 시험 여럿이 저장소를 relative 로 짚는다
# (ROOT = tests/../../.. 아래의 docs/·*.md·llms.txt·dist/). 골라 담다가 두 번 빨개졌고,
# 둘 다 **러너의 결함이 코드의 결함처럼 보였다**. 추적 파일은 3MB 남짓이라 통째로 뜨는
# 것이 싸고 확실하다(빌드 산물만 따로 얹는다).
set -e
here=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$here/.." && pwd)
SNAP=${GIL_SNAP:-${TMPDIR:-/tmp}/gil-snap}

rm -rf "$SNAP"
mkdir -p "$SNAP"
( cd "$REPO" && git ls-files -z | xargs -0 tar cf - ) | ( cd "$SNAP" && tar xf - )

bin="$REPO/project/gil-v3-redesign/go/gil"
[ -x "$bin" ] || { echo "gil 바이너리가 없다: $bin  (go build -o gil . 먼저)" >&2; exit 1; }
cp "$bin" "$SNAP/project/gil-v3-redesign/go/gil"

cd "$SNAP/project/gil-v3-redesign/tests"
GIL_BIN="$SNAP/project/gil-v3-redesign/go/gil" python3 run_tests.py "$@" > "$SNAP/out.txt" 2>&1
code=$?
echo "exit=$code" >> "$SNAP/out.txt"
tail -8 "$SNAP/out.txt"
exit $code
