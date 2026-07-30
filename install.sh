#!/bin/sh
# gil 한 줄 설치 — 플랫폼 감지 → 릴리스 바이너리 다운로드 → 체크섬 검증 → 호스트 PATH 에 설치.
#
# 왜 호스트 설치가 기본인가(AIL #11): gil 은 git·go·docker 처럼 "도구"다. 사람도 AI 도 도구는
# 호스트 머신 단위로 사고한다 — 한 번 설치하면 어느 저장소에서든 `gil`. 저장소-로컬(./gil)이
# 기본이면 `which gil` 이 실패해 "gil 없음"으로 오인하고, 도구가 멀쩡히 있는데 능력을 빼앗긴
# 것처럼 잘못 안내하게 된다(실사용 4단계 오류로 실증). 그래서 기본을 ~/.local/bin 으로.
# 저장소별 버전 고정이 필요하면 `--dir .` 로 여전히 로컬 설치할 수 있다(옵션).
#
# 사용:
#   curl -fsSL https://raw.githubusercontent.com/hyun06000/Ariadne/main/install.sh | sh
# 특정 디렉토리(저장소-로컬 등)에:
#   curl -fsSL .../install.sh | sh -s -- --dir /path/to/project
#
# 체크섬은 절대 건너뛰지 않는다 — 해시가 어긋나면 스크립트가 비-0 으로 멈추고 gil 은 생기지
# 않는다. 검증 안 된 건 아무것도 실행 가능해지지 않는다.
set -eu

REPO="hyun06000/Ariadne"
# 기본 설치 위치 = 호스트 PATH(사용자 단위, sudo 불필요). XDG 관례의 ~/.local/bin.
DIR="${HOME}/.local/bin"
DIR_EXPLICIT=0
while [ $# -gt 0 ]; do
	case "$1" in
		--dir) DIR="$2"; DIR_EXPLICIT=1; shift 2 ;;
		--dir=*) DIR="${1#--dir=}"; DIR_EXPLICIT=1; shift ;;
		*) echo "gil install: 알 수 없는 인자 '$1'" >&2; exit 2 ;;
	esac
done

# 플랫폼 감지
os=$(uname -s | tr '[:upper:]' '[:lower:]')
case "$os" in
	darwin) os=darwin ;;
	linux) os=linux ;;
	# Windows 의 POSIX 환경(Git Bash·MSYS·Cygwin). 이 스크립트는 POSIX 바이너리만 받으므로
	# Windows 에서 돌리면 엉뚱한 리눅스 ELF 를 받게 된다 — 막고 PowerShell 경로로 안내한다.
	mingw*|msys*|cygwin*|windows*)
		echo "✗ 이 설치 스크립트는 macOS/Linux 전용이다 (POSIX)." >&2
		echo "  Windows 에서는 PowerShell 로 gil-windows-amd64.exe 를 받아라(체크섬 검증 포함)." >&2
		echo "  복사해 붙여넣을 블록이 여기 있다:" >&2
		echo "  https://github.com/hyun06000/Ariadne/blob/main/docs/INSTALL.md#windows-powershell" >&2
		exit 2 ;;
	*) os=linux ;;  # 알 수 없으면 linux 로 가정(가장 흔함)
esac
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

echo "gil install: $asset 내려받는 중 (latest) → $DIR …" >&2
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
installed="$(cd "$DIR" && pwd)/gil"
echo "✓ gil 설치 완료 → $installed" >&2

# PATH 확인 — 도구는 어디서든 `gil` 로 잡혀야 한다(AIL #11 의 핵심). 저장소-로컬(--dir)
# 설치가 아니고, 설치 위치가 PATH 에 없으면 추가 방법을 안내한다.
case ":${PATH}:" in
	*":${DIR}:"*) on_path=1 ;;
	*) on_path=0 ;;
esac
if [ "$DIR_EXPLICIT" = 1 ]; then
	# 사용자가 --dir 로 위치를 직접 지정 — 저장소-로컬 등 의도적 선택이라 PATH 안내 대신 호출법만.
	echo "  다음: $installed help   (또는 이 디렉토리에서 ./gil help)" >&2
elif [ "$on_path" = 1 ]; then
	echo "  다음: gil help   (도구에 직접 물어라 — 어디서든 gil 로 잡힌다)" >&2
else
	# 호스트 설치인데 PATH 에 없다 — 여기서 안내 안 하면 `which gil` 실패로 #11 이 재발한다.
	echo "" >&2
	echo "  ⚠ $DIR 이 PATH 에 없다 — 지금은 $installed 로만 실행된다." >&2
	echo "    어디서든 'gil' 로 쓰려면 셸 설정에 아래 한 줄을 더하라(당신 셸의 rc 파일):" >&2
	echo "" >&2
	echo "      export PATH=\"\$HOME/.local/bin:\$PATH\"" >&2
	echo "" >&2
	echo "    (bash=~/.bashrc, zsh=~/.zshrc. 추가 뒤 새 셸을 열거나 source 하라.)" >&2
	echo "  당장 쓰려면: $installed help" >&2
fi
