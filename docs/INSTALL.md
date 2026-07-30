# gil 직접 설치하기 (사람용) · Installing gil yourself

이 문서는 **사람이 자기 손으로** gil을 설치하는 경로다. 보통은 AI 에이전트가 대신 설치하지만,
그게 안 되는 경우가 둘 있다:

1. **Windows** — `install.sh` 는 POSIX 셸 전용이라 Windows 기본 셸(PowerShell)에는 스크립트
   경로가 아예 없다.
2. **에이전트가 설치를 거부할 때** — "검증되지 않은 제3자 저장소의 스크립트·실행파일을 확인
   없이 실행할 수 없다"는 거부는 **옳은 판단**이다. 우회하지 마라. 에이전트는 *검증*만 하고,
   *실행*은 사람이 한다. 아래가 그 실행 경로다. (에이전트 쪽 지침: [README.ai.md](../README.ai.md))

어느 경로든 **체크섬 검증은 필수**다 — 해시가 어긋나면 아무것도 실행 가능해지지 않는다.

> This page is the **human** install path — used on Windows (where `install.sh`, a POSIX shell
> script, simply does not run) and whenever your agent declines to execute a third‑party
> binary. That refusal is correct: the agent verifies, **you** execute. The checksum gate is
> mandatory in every path below.

---

## Windows (PowerShell)

PowerShell 창을 열고 아래 블록을 **통째로** 복사해 붙여넣어라. 받고 → 해시를 대조하고 →
맞을 때만 `gil.exe` 로 만든다.

```powershell
$ProgressPreference = 'SilentlyContinue'   # 없으면 Windows PowerShell 5.1 에서 다운로드가 아주 느리다
$dir  = "$HOME\.local\bin"
$base = "https://github.com/hyun06000/Ariadne/releases/latest/download"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Invoke-WebRequest "$base/gil-windows-amd64.exe" -OutFile "$dir\gil-dl.exe"
Invoke-WebRequest "$base/SHA256SUMS"            -OutFile "$dir\SHA256SUMS"
$want = ((Select-String -Path "$dir\SHA256SUMS" -Pattern 'gil-windows-amd64\.exe$').Line -split '\s+')[0]
$got  = (Get-FileHash "$dir\gil-dl.exe" -Algorithm SHA256).Hash.ToLower()
if ($got -ne $want) { Remove-Item "$dir\gil-dl.exe"; throw "체크섬 불일치 — 설치 중단" }
Move-Item -Force "$dir\gil-dl.exe" "$dir\gil.exe"
Remove-Item "$dir\SHA256SUMS"
& "$dir\gil.exe" version
```

마지막 줄이 버전을 찍으면 설치된 것이다. **체크섬이 어긋나면** 릴리스 직후 CDN이 아직
따라잡는 중일 수 있다 — ~60초 뒤 다시 실행하라. **검사를 지워서 우회하지 마라.**

### 어디서든 `gil` 로 쓰려면 (PATH 등록, 한 번만)

```powershell
$dir = "$HOME\.local\bin"
$old = [Environment]::GetEnvironmentVariable('Path','User')
if ($old -notlike "*$dir*") { [Environment]::SetEnvironmentVariable('Path', "$old;$dir", 'User') }
```

등록 뒤 **새 PowerShell 창**을 열어야 반영된다. 새 창에서 `gil version` 이 돌면 끝이다.

### git 이 필요하다

gil은 사고 이력을 진짜 git 커밋으로 남기므로 git 없이는 동작하지 않는다.

```powershell
winget install --id Git.Git -e --silent
```

winget이 없는 구형 Windows면 https://git-scm.com/download/win 에서 설치 프로그램을 받아라.
설치 후 **새 PowerShell 창**에서 `git --version` 으로 확인한다.

> **Git Bash / MSYS / Cygwin 에서 `install.sh` 를 돌리지 마라** — 그 스크립트는 POSIX
> 바이너리만 받으므로 Windows에서 돌리면 엉뚱한 리눅스 ELF를 받게 된다. `install.sh` 는 이를
> 감지해 스스로 멈추고 이 문서로 안내한다. (**WSL** 안이라면 그건 리눅스다 — 아래 POSIX 경로를 써라.)

---

## macOS · Linux (WSL 포함)

한 줄:

```bash
curl -fsSL https://raw.githubusercontent.com/hyun06000/Ariadne/main/install.sh | sh
```

**스크립트를 먼저 읽고 판단하고 싶으면**(권장 — 그러라고 짧게 유지한다) 받아서 읽은 뒤 돌려라:

```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/hyun06000/Ariadne/main/install.sh
less install.sh          # 100줄 남짓 — 플랫폼 감지·다운로드·체크섬 게이트가 전부다
sh install.sh
```

스크립트를 아예 쓰지 않고 손으로:

```bash
os=$(uname -s | tr '[:upper:]' '[:lower:]'); case "$os" in darwin) os=darwin;; *) os=linux;; esac
arch=$(uname -m); case "$arch" in arm64|aarch64) arch=arm64;; *) arch=amd64;; esac
sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"; else sha256sum "$@"; fi; }
base=https://github.com/hyun06000/Ariadne/releases/latest/download
curl -fsSL -O "$base/gil-${os}-${arch}"
curl -fsSL -O "$base/SHA256SUMS"
grep " gil-${os}-${arch}\$" SHA256SUMS | sha -c - && mv "gil-${os}-${arch}" gil && chmod +x gil
./gil version
```

`~/.local/bin` 이 PATH에 없으면 셸 rc 파일(`~/.zshrc`·`~/.bashrc`)에 한 줄을 더한다:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## 에이전트가 할 수 있는 일 — 검증 (실행은 사람이)

에이전트가 설치 실행을 거부해도 **여기서 끝내지 마라**. 에이전트는 실행하지 않고도 아래를
전부 해줄 수 있고, 그게 사람이 붙여넣기 전에 얻는 근거다:

- `install.sh` (또는 위 PowerShell 블록)를 **읽고 무엇을 하는지 한 줄씩 설명**한다.
- 릴리스의 `SHA256SUMS` 를 가져와, 사람이 받은 파일의 해시와 **대조할 기대값**을 알려준다.
- 릴리스 페이지·[llms.txt](https://raw.githubusercontent.com/hyun06000/Ariadne/main/llms.txt)·
  소스(`project/gil-v3-redesign/go/`)를 확인해 **자산 이름과 출처**를 확인한다.
- 사람이 "설치했다"고 하면 **`gil init` 부터 이어받아** 나머지를 운전한다.

설치 하나만 사람 손을 빌리고, 그 앞의 검증과 그 뒤의 운전은 전부 에이전트가 한다.
