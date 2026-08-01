#!/bin/zsh
# 옛 레이아웃 저장소를 만든다 — dev 층 없이 체인들이 대문 위에·서로 위에 얹힌 나무.
set -e
export GIL_NO_VIEWER=1
G=${GIL_BIN:-/tmp/gil-x}
D=${1:?사용: make-old.sh <경로>}
rm -rf "$D"; mkdir -p "$D"; cd "$D"
git init -q .; git config user.email d@e.com; git config user.name demo
q(){ $G "$@" >/dev/null 2>&1 || { echo "✗ $*"; $G "$@" 2>&1 | tail -4; exit 1; }; }

q init --name clew
git checkout -q main
git branch -D dev            # 옛 레이아웃 재현: 층이 없다
echo "기준 문서" > ref.md; echo "회고" > retro.md
git add -A; git commit -q -m "기준 문서"

cyc(){ # $1=체인 $2=사이클
  q open "$1/$2" --author clew --purpose "무엇을 만들 것인가" \
    --body "문제 정의." --fits "체인 목적 그 자체"
  q step "$1/$2" --kind hypothesis --title "가설" --body "이렇게 하면 된다." \
    --falsify "안 되면 거짓" --falsify-to s1 --plan "구현 1개" --advances "핵심 경로를 덮는다"
  q step "$1/$2" --kind verify --title "돌려봤다" --body "결과." \
    --verdict supported --plan-held --falsify-unmet "반증조건 미관측"
  q step "$1/$2" --kind analyze --title "배운 것" --body "해석." --finding "지지됐다."
  q step "$1/$2" --kind success --title "된다" --body "종합." \
    --toward "기준 충족" --next-design "다음: 남은 조각을 사이클로"
  q close "$1/$2" --verdict supported
}

# 체인 하나: 사이클 둘(두 번째는 backtrack 형제 가지까지)
q chain alpha --purpose "첫 국면" --reference ref.md --criterion "A 가 된다"
cyc alpha c1
q open alpha/c2 --author clew --purpose "두 번째 문제" --body "정의" --fits "같은 국면"
q step alpha/c2 --kind hypothesis --title "가설B" --body "본문" \
  --falsify "안 되면 거짓" --falsify-to s1 --plan "구현 1개" --advances "덮는다"
q step alpha/c2 --kind verify --title "검증B" --body "본문" \
  --verdict refuted --plan-broke "설계가 틀렸다" --falsify-met "반증조건 관측됨"
q step alpha/c2 --kind analyze --title "왜 틀렸나" --body "해석" --finding "이 경로는 벽이다"
q step alpha/c2 --kind fail --to s1 --title "이 경로는 막혔다" --body "죽은 잎으로 봉인" \
  --toward "목적엔 못 다가섰다 — 벽 하나를 지도에 올렸다" --next-design "다른 경로를 s1 에서 다시"
# 되돌아가 새 가지 — 죽은 형제 가지가 남는다(벽의 지도)
q step alpha/c2 --kind hypothesis --title "가설B2" --body "다른 경로" --to s1 \
  --falsify "안 되면 거짓" --falsify-to s1 --plan "구현 1개" --advances "덮는다" --inherit "앞 가지에서 벽을 봤다"
q step alpha/c2 --kind verify --title "검증B2" --body "본문" \
  --verdict supported --plan-held --falsify-unmet "미관측"
q step alpha/c2 --kind analyze --title "배운 것" --body "해석" --finding "이 경로가 맞다"
q step alpha/c2 --kind success --title "된다" --body "종합" --toward "기준 충족" --next-design "다음 설계"
q close alpha/c2 --verdict supported
q chain-close alpha --verdict supported --retro retro.md

# 이어받은 체인(계승 선언) — 이주 뒤에도 계승이어야 한다
q chain beta --purpose "이어받은 국면" --reference ref.md --criterion "B 가 된다" \
  --from alpha --inherit "alpha 의 교훈"
cyc beta c1
q chain-close beta --verdict supported --retro retro.md

# 무관한 체인 — 옛 문법에선 얹힐 수밖에 없었다(이게 stacked 로 짖던 것)
q chain gamma --purpose "무관한 탐색" --reference ref.md --criterion "C 가 된다"
cyc gamma c1
q chain-close gamma --verdict supported --retro retro.md

echo "✓ 옛 나무: $D"
git branch --format='%(refname:short)' | tr '\n' ' '; echo
