#!/bin/zsh
# main-dev-chain 레이아웃 데모 — 제로에서 나무 하나를 짓는다.
#   main(대문) → dev(층) → 체인 둘(시조) → merge → deploy
set -e
export GIL_NO_VIEWER=1
G=${GIL_BIN:-/tmp/gil-x}
D=${1:?사용: make-demo.sh <경로>}
rm -rf "$D"; mkdir -p "$D"; cd "$D"
git init -q .; git config user.email d@e.com; git config user.name demo
q(){ $G "$@" >/dev/null 2>&1 || { echo "✗ $*"; $G "$@" 2>&1 | tail -4; exit 1; }; }

q init --name clew
echo "기준 문서: 로그인과 검색을 갖춘 서비스를 만든다." > ref.md
echo "회고: 기준을 충족했다." > retro.md

# ── 체인 하나를 통째로 짓는 함수 (dev 에서 나는 시조) ─────────────────────────
chain_run(){  # $1=체인 $2=목적 $3=기준 $4=가설 $5=반증
  q chain "$1" --purpose "$2" --reference ref.md --criterion "$3"
  q open "$1/c1" --author clew --purpose "무엇을 만들 것인가" \
    --body "문제 정의: $2. 입력·출력·제약을 여기 적는다." --fits "체인 목적 그 자체"
  q step "$1/c1" --kind hypothesis --title "$4" --body "$4 — 이렇게 하면 된다고 본다." \
    --falsify "$5" --falsify-to s1 --plan "구현 1개" \
    --advances "체인 목적($2)의 핵심 경로를 이 가설이 덮는다"
  q step "$1/c1" --kind verify --title "돌려봤다" --body "실행 결과: 기대대로 동작했다." \
    --verdict supported --plan-held --falsify-unmet "반증조건은 관측되지 않았다"
  q step "$1/c1" --kind analyze --title "무엇을 배웠나" --body "결과 해석." \
    --finding "가설이 지지됐다 — 이 경로로 간다."
  q step "$1/c1" --kind success --title "된다" --body "기준 충족. 종합 보고." \
    --toward "체인 기준($3)을 만족한다" --next-design "다음: 세션 만료·권한 분기를 각각 한 사이클로 설계한다"
  q close "$1/c1" --verdict supported
  q chain-close "$1" --verdict supported --retro retro.md
}

chain_run login  "로그인 기능" "로그인이 된다"  "세션 쿠키로 된다" "쿠키가 안 남으면 거짓"
chain_run search "검색 기능"   "검색이 된다"    "역색인으로 된다" "느리면 거짓"

# ── 합류 → 배포 ─────────────────────────────────────────────────────────────
q merge login search --into dev --reason "두 기능이 한 배포 단위로 함께 나간다"
q deploy --tag v1.0.0 --url https://example.com/v1.0.0

echo "✓ 데모 완성: $D"
$G fsck 2>&1 | tail -1
