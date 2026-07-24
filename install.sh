#!/bin/sh
# gil 한 줄 설치 — 플랫폼 감지 → 릴리스 바이너리 다운로드 → 체크섬 검증 → ./gil.
#
# 사용:
#   curl -fsSL https://raw.githubusercontent.com/hyun06000/Ariadne/main/install.sh | sh
# 또는 특정 디렉토리에:
#   curl -fsSL .../install.sh | sh -s -- --dir /path/to/project
#
# 체크섬은 절대 건너뛰지 않는다 — 해시가 어긋나면 스크립트가 비-0 으로 멈추고 gil 은 생기지
# 않는다. 검증 안 된 건 아무것도 실행 가능해지지 않는다.
set -eu

REPO="hyun06000/Ariadne"
DIR="."
while [ $# -gt 0 ]; do
	case "$1" in
		--dir) DIR="$2"; shift 2 ;;
		--dir=*) DIR="${1#--dir=}"; shift ;;
		*) echo "gil install: 알 수 없는 인자 '$1'" >&2; exit 2 ;;
	esac
done

# 플랫폼 감지
os=$(uname -s | tr '[:upper:]' '[:lower:]')
[ "$os" = darwin ] || os=linux
arch=$(uname -m)
case "$arch" in arm64|aarch64) arch=arm64 ;; *) arch=amd64 ;; esac
asset="gil-${os}-${arch}"

# git 은 gil 실행에 필수다(설치엔 불필요하지만 미리 안내한다).
if ! command -v git >/dev/null 2>&1; then
	echo "⚠ git 이 없다 — gil 은 사고 이력을 진짜 git 커밋으로 남기므로 git 이 필요하다." >&2
	echo "  설치: https://git-scm.com/downloads  (설치 뒤 gil 을 쓸 수 있다)" >&2
	echo "  (설치는 계속 진행한다 — 바이너리만 내려받는다.)" >&2
fi

sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"; else sha256sum "$@"; fi; }

base="https://github.com/${REPO}/releases/latest/download"
mkdir -p "$DIR"
cd "$DIR"

echo "gil install: $asset 내려받는 중 (latest)…" >&2
curl -fsSL -O "$base/$asset"
curl -fsSL -O "$base/SHA256SUMS"

# 체크섬 게이트 — 이 줄이 실패하면 set -e 로 멈춘다(gil 안 생김).
if ! grep " ${asset}\$" SHA256SUMS | sha -c - >/dev/null 2>&1; then
	rm -f "$asset"
	echo "✗ 체크섬 불일치 — 설치 중단. 릴리스 직후면 CDN 이 따라잡게 ~60초 뒤 재시도하라." >&2
	echo "  절대 체크섬을 건너뛰지 마라." >&2
	exit 1
fi

mv "$asset" gil
chmod +x gil
rm -f SHA256SUMS
echo "✓ gil 설치 완료 → $(cd "$DIR" && pwd)/gil" >&2
echo "  다음: ./gil help  (이 빌드가 뭘 하는지 도구에 직접 물어라)" >&2
