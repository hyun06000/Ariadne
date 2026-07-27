#!/usr/bin/env sh
# release-build.sh — gil 릴리스 자산을 재현 가능하게 굽는다.
#
# 왜 이 스크립트가 있나: 어떤 플랫폼을 릴리스에 올리는지가 "누군가의 기억"이 아니라
# 레포의 코드로 못박혀 있어야 한다. Windows 타깃이 조용히 빠져도 아무도 눈치 못 채는
# 사고를 구조적으로 막는다. gil 철학과 같다 — 재현 불가능한 것은 진실이 아니다.
#
# 사용:
#   scripts/release-build.sh v3.8.1                 # dist/ 에 8개 자산 + SHA256SUMS 생성
#   scripts/release-build.sh v3.8.1 && \
#     gh release create v3.8.1 -R hyun06000/Ariadne dist/*   # 업로드는 사람이 판단
#
# 산출물(dist/): 아래 TARGETS 의 바이너리들 + install.sh + llms.txt + SHA256SUMS.
# git·go 만 있으면 되고, 크로스컴파일은 Go 툴체인이 다 한다(C 의존 없음, CGO_ENABLED=0).

set -eu

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
	echo "usage: scripts/release-build.sh <version>   예: v3.8.1" >&2
	exit 2
fi
case "$VERSION" in
	v[0-9]*) : ;;
	*) echo "거부: 버전은 v 로 시작해야 한다(예: v3.8.1) — 받은 값: $VERSION" >&2; exit 2 ;;
esac

# 지원 플랫폼 — 릴리스가 굽는 정확한 타깃들. 여기가 단일 진실원이다.
# (SPEC '지원 플랫폼' 절과 install.sh 의 감지 로직이 이 목록과 일치해야 한다.)
TARGETS="darwin/amd64 darwin/arm64 linux/amd64 linux/arm64 windows/amd64"

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
GO_DIR="$ROOT/project/gil-v3-redesign/go"
DIST="$ROOT/dist"

command -v go >/dev/null 2>&1 || { echo "거부: go 가 필요하다(크로스컴파일 툴체인)." >&2; exit 1; }

rm -rf "$DIST"
mkdir -p "$DIST"

echo "릴리스 빌드 $VERSION — $DIST"
for t in $TARGETS; do
	os=${t%/*}; arch=${t#*/}
	out="gil-${os}-${arch}"
	[ "$os" = "windows" ] && out="${out}.exe"
	echo "  → $out"
	# -X main.gilVersion 으로 버전을 각인(version.go: 릴리스 빌드는 이 ldflags 로 채운다).
	# CGO_ENABLED=0 로 정적 단일 바이너리(git 만 있으면 도는 gil 철학).
	( cd "$GO_DIR" && CGO_ENABLED=0 GOOS="$os" GOARCH="$arch" \
		go build -trimpath -ldflags "-s -w -X main.gilVersion=$VERSION" -o "$DIST/$out" . )
done

# 설치 스크립트·wiki 인덱스도 자산으로(설치 한 줄이 릴리스에서 곧장 받도록).
cp "$ROOT/install.sh" "$DIST/install.sh"
cp "$ROOT/llms.txt"   "$DIST/llms.txt"

# 체크섬 — install.sh 의 필수 게이트가 이 파일로 무결성을 검증한다. 건너뛸 수 없다.
echo "  → SHA256SUMS"
(
	cd "$DIST"
	if command -v shasum >/dev/null 2>&1; then
		shasum -a 256 * > SHA256SUMS
	else
		sha256sum * > SHA256SUMS
	fi
)

echo ""
echo "완료 — $DIST 의 자산 $(ls "$DIST" | wc -l | tr -d ' ') 개:"
ls -1 "$DIST"
echo ""
echo "다음(사람이 판단): gh release create $VERSION -R hyun06000/Ariadne \"$DIST\"/*"
