#!/usr/bin/env bash
# loom/C061 검증 재현 스크립트 — gil releases (배포 계보 조회)
# 사용: bash verify.sh   (저장소 어디서든; REPO를 자동 유추)
# ⚠ zsh 단어 분리 함정: gil을 변수에 담지 말고 python3로 직접 호출한다 (CLAUDE.md).
set -u
REPO="$(git rev-parse --show-toplevel)"
GILPY="$REPO/rooms/deployment/ariadne-spec/gil.py"
CONF="$REPO/rooms/deployment/ariadne-spec/conformance.py"

echo "### 1) 실저장소 스모크 — 배포 계보 + 저장소 무변화"
BEFORE="$(git -C "$REPO" status --porcelain)"
python3 "$GILPY" releases | tail -4
AFTER="$(git -C "$REPO" status --porcelain)"
[ "$BEFORE" = "$AFTER" ] && echo "저장소 무변화: OK" || echo "저장소 변경됨: FAIL"

echo; echo "### 2) drift + 비-git 우아화 — 격리 샌드박스"
S="$(mktemp -d)"; mkdir -p "$S/rooms/deployment/ariadne-spec"
cat > "$S/rooms/deployment/CHANGELOG.md" <<'EOF'
# Changelog

## [Unreleased]

## [1.2.0] — 2026-07-20

- 문서만 릴리스 (태그 없음)
- 도구 변경: 없음 (문서 릴리스)

## [1.0.0] — 2026-07-18

- 첫 릴리스
- 도구 변경: gil (마이너 이상 승격)
EOF
echo x > "$S/rooms/deployment/ariadne-spec/f.txt"
git -C "$S" init -q -b main; git -C "$S" config user.name fx; git -C "$S" config user.email fx@t
git -C "$S" add -A; git -C "$S" commit -q -m init
git -C "$S" tag -a v1.0.0 -m "Ariadne release v1.0.0 — 첫 릴리스"      # TC
git -C "$S" tag -a v1.1.0 -m "Ariadne release v1.1.0 — 태그만"          # T only → drift
git -C "$S" tag -a cycle/x/C001-y -m "cycle tag ignored"               # 릴리스 아님
echo "--- drift 케이스 (기대: drift=2, cycle 태그 배제) ---"
python3 "$GILPY" releases --package "$S/rooms/deployment/ariadne-spec"
echo "--- 비-git 디렉토리 우아화 (기대: exit 0, 태그 대조 생략) ---"
NG="$(mktemp -d)"; mkdir -p "$NG/rooms/deployment/ariadne-spec"
cp "$S/rooms/deployment/CHANGELOG.md" "$NG/rooms/deployment/CHANGELOG.md"
( cd "$NG" && python3 "$GILPY" releases ); echo "exit=$?"

echo; echo "### 3) 회귀 — conformance 양 구현"
echo "PYTHON: $(python3 "$CONF" --gil "python3 $GILPY" 2>&1 | tail -1)"
if command -v go >/dev/null 2>&1; then
  ( cd "$REPO/rooms/deployment/ariadne-spec/go" && GO111MODULE=off go build -o /tmp/gil-c061 main.go ) \
    && echo "GO:     $(python3 "$CONF" --gil "/tmp/gil-c061" 2>&1 | tail -1)"
else
  echo "GO: (go 미설치 — 건너뜀)"
fi
