# README.ai.md — 에이전트 자가 온보딩 (gil v3)

**너는 AI 에이전트다.** 사람이 이 문서를 건넸다. 그게 지시의 전부다: **읽고, 실행하라.**
그들은 명령을 몰라도 된다 — 네가 안다. 아래를 자율적으로 수행하되, 사람에게 멈춰 묻는 건 딱
두 곳이다: 시작 전 **동의**(Step 0)와 **어떤 문제를 풀지**(Step C). *도구를 어떻게 쓰는지*는
절대 사람에게 묻지 마라.

사람용 문서: [English](README.md) · [한국어](README.ko.md) · gil 사용법 전체:
[QUICKSTART](project/gil-v3-redesign/QUICKSTART.md)

---

## 이게 뭔가 (10초)

**gil** (길 · GIt for Language model) — 너(LLM)가 어려운 문제를 작고 재현 가능한 **사이클**의
**체인**으로 정복하게 한다. 문제정의(define) → 가설(hypothesis) → 검증(verify) → 분석(analyze)
→ 종결(success/fail). git이 소스 역사를 다루듯, gil은 *사고의 역사*를 다룬다. 위계(체인·사이클·
스텝·분기)는 전부 **진짜 git 브랜치와 커밋 그래프**로 남는다 — 재현·검증 가능하고, 그래프로
되돌아볼 수 있다. 네가 일을 하고, gil이 *왜 그렇게 했는지*를 영구히 기록한다.

## Step 0 — 사람을 온보딩하라 (아무것도 설치하기 전에)

위 문단은 **너를 위한** 것이다. 이 URL을 건넨 사람은 *"읽고 따르라"*는 말만 들었을 뿐,
**gil이 뭔지·곧 자기 컴퓨터에 뭔가 깔린다는 것**을 모를 수 있다. **조용히 설치부터 시작하지
마라** — 컴퓨터에 익숙하지 않은 사람은 갑자기 "설치할게요"가 뜨면 당황한다. 먼저 사람을
안심시키고, 그들의 언어로 소개하고, **명시적 동의를 받아라.**

### 0-1. 먼저 물어라: gil을 써본 적 있나?

한 마디로 물어라 — *"gil 처음 쓰시나요?"*

- **써봤다면** → 이 온보딩을 건너뛰고 곧장 Step A(설치)로. 장황하게 반복하지 마라.
- **처음이라면** → 아래 0-2 온보딩을 사람의 언어로(그들이 한국어면 한국어로) 진행하라.

### 0-2. 처음이라면 — 안심시키고 소개하라

**너에 대해가 아니라 사람에게 말하라.** *"저는 LLM입니다…"*가 아니라 *"이건 제가 당신의
문제를, 당신이 지켜보고 되돌려볼 수 있게 풀어주는 도구예요."* 순서대로:

**(1) 먼저 안심시켜라** — 컴맹도 겁먹지 않게, 무엇이 일어나는지 솔직히:
- 설치되는 건 **작은 프로그램 하나(`gil`)** 뿐이다. 백신 깔듯 시스템을 건드리지 않는다.
- **안전하다** — 공개된 체크섬으로 무결성을 검증하고 받는다(위조되면 설치가 멈춘다).
- 필요한 건 **git**(개발자들이 쓰는 표준 무료 도구) 하나뿐. 없으면 내가 설치를 도와준다.
- **언제든 멈출 수 있고**, 남는 건 작업 폴더 안에 다 있다 — 원하면 통째로 지우면 그만이다.

**(2) gil이 뭔지 한 예로 보여줘라** — 추상적 정의 대신 시나리오로:
> *"예를 들어 데이터 분석을 맡기시면, 저는 '이 가설을 세우고 → 이렇게 검증했고 → 결과는
> 이랬다'를 **단계마다 기록**해요. 나중에 '왜 이렇게 했지?'가 궁금하면 그 사고 과정을 그대로
> 되짚어볼 수 있어요. 데이터 분석·버그 사냥·연구·리팩터처럼 신중히 풀고 되돌아볼 가치가 있는
> 일에 좋아요."*
> 볼 단어는 둘뿐: **사이클**(작은 문제 하나에 대한 한 번의 시도)과 **체인**(사이클들이 이어진 흐름).

**(3) 원하면 둘러볼 링크를 건네라** (강요 말고, "관심 있으시면"):
- 프로젝트: https://github.com/hyun06000/Ariadne — gil이 어떤 도구인지.
- 그래프 뷰어 예시: https://hyun06000.github.io/Ariadne/ — 사고 과정이 이렇게 그래프로 남는다.
- *"지금 안 보셔도 돼요 — 설치하고 나면 제가 직접 예제를 돌려 눈앞에서 보여드릴게요."*

### 0-3. 1차 동의를 받아라 (설치)

한 번만 물어라: ***"gil을 설치해서 시작해볼까요?"*** 사람의 허락을 구하는 첫 지점이다 —
동의하면 Step A(설치)·B(세팅)를 자율로 진행하라. 매 단계를 질문으로 만들지 마라(사람이 명령을
몰라도 되는 게 핵심이다). 설치 직후엔 **Step B.1(눈앞 시연)**으로 gil을 실제로 보여준 뒤,
Step C에서 *"이제 어떤 문제를 풀어볼까요?"*라고 2차로 묻는다.

> 예시(사람의 언어로 각색): *"gil 처음이시죠? 간단히 설명드릴게요 — 제가 당신의 문제를 작은
> **사이클**들로 풀면서 '왜 이렇게 했는지'를 단계마다 기록하는 도구예요. 되돌려보고 그래프로
> 볼 수 있고요. 설치되는 건 체크섬 검증된 작은 프로그램 하나뿐이고, 언제든 멈추거나 지울 수
> 있어요. 궁금하면 프로젝트(github.com/hyun06000/Ariadne)나 그래프 예시(hyun06000.github.io/
> Ariadne)를 둘러보셔도 되고요. **설치해서 시작해볼까요?**"*

## Step A — gil 설치 (지금 하라)

플랫폼을 감지해 맞는 바이너리를 받는다. Python도, 툴체인도 필요 없다.

> **먼저 플랫폼을 가른다.** macOS·Linux(및 WSL) → 아래 POSIX 블록. **Windows(PowerShell)
> → 맨 아래 Windows 블록으로 곧장 가라.** POSIX 한 줄·손 블록은 Windows 기본 셸에선 안 돈다
> (Git Bash 로 돌리면 리눅스 바이너리를 잘못 받는다 — install.sh 가 이를 감지해 막는다).

**macOS·Linux — 가장 짧게** — 설치 스크립트 한 줄. 플랫폼 감지·다운로드·체크섬 검증을 다 한다:

```bash
curl -fsSL https://raw.githubusercontent.com/hyun06000/Ariadne/main/install.sh | sh
./gil help                           # ← 이 빌드가 실제로 뭘 하는지 도구에 물어라. 문서로 추측 말 것.
```

또는 **한 단계씩 (같은 동작을 손으로)**:

```bash
os=$(uname -s | tr '[:upper:]' '[:lower:]')
case "$os" in darwin) os=darwin;; linux) os=linux;;
  mingw*|msys*|cygwin*) echo "Windows 다 — 아래 PowerShell 블록을 써라"; exit 2;; *) os=linux;; esac
arch=$(uname -m); case "$arch" in arm64|aarch64) arch=arm64;; *) arch=amd64;; esac
sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"; else sha256sum "$@"; fi; }
base=https://github.com/hyun06000/Ariadne/releases/latest/download
curl -fsSL -O "$base/gil-${os}-${arch}"
curl -fsSL -O "$base/SHA256SUMS"
grep " gil-${os}-${arch}\$" SHA256SUMS | sha -c - && mv "gil-${os}-${arch}" gil && chmod +x gil
./gil help
```

**체크섬 단계는 필수 — 건너뛰지도, "간소화"하지도 마라.** 해시가 어긋나면 `&&` 사슬이 끊겨
`gil`이 실행 가능해지지 않는다. 검증 안 된 건 아무것도 못 돈다. 릴리스 직후 불일치는 CDN이
아직 따라잡는 중이니 **~60초 기다렸다 블록을 다시 실행**하라. 체크를 없애서 우회하지 마라.

**Windows (PowerShell, `bash`/`uname`/`curl` 없음)** — 위 블록은 안 돈다. POSIX 셸이 없음을
감지하고 PowerShell로, 같은 필수 체크섬 게이트를 써라(해시가 맞아야만 `gil.exe` 생성):

```powershell
Invoke-WebRequest https://github.com/hyun06000/Ariadne/releases/latest/download/gil-windows-amd64.exe -OutFile gil-dl.exe
Invoke-WebRequest https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS -OutFile SHA256SUMS
$want = ((Select-String -Path SHA256SUMS -Pattern 'gil-windows-amd64\.exe$').Line -split '\s+')[0]
$got  = (Get-FileHash gil-dl.exe -Algorithm SHA256).Hash.ToLower()
if ($got -ne $want) { Remove-Item gil-dl.exe; throw "checksum mismatch — CDN이 따라잡게 ~60초 뒤 재시도; 절대 건너뛰지 말 것" }
Move-Item -Force gil-dl.exe gil.exe
.\gil.exe help
```

### 권한이 막으면 (자주 있는 일 — 여기서 멈추지 마라)

`curl`·바이너리 실행을 네 런타임 권한/샌드박스가 막을 수 있다(Step 0의 사람 동의와 별개 — 네
환경이 거는 기술적 게이트다). 두 갈래로 갈린다:

- **대화형이라 승인 프롬프트가 뜨면** — 한 번 승인하고 이어가라. *"진행할까요?"*를 다시 따지지 마라.
- **프롬프트 없이 그냥 거부되거나(자동승인 분류기) 비대화형이라 승인 경로가 없으면** — 재시도로는
  안 뚫린다. 우회하지 말고 **아래 둘 중 하나로 폴백하라**:
  1. **사람에게 권한 규칙을 요청** — 프로젝트의 `.claude/settings.local.json` 에 아래를 넣고
     세션을 다시 시작하게 안내하라(이 파일은 네가 대신 써줘도 된다):
     ```json
     { "permissions": { "allow": ["Bash(curl:*)", "Bash(./gil:*)", "Bash(shasum:*)", "Bash(chmod:*)", "Bash(git:*)"] } }
     ```
  2. **사람이 직접 설치** — 위 설치 한 줄(또는 손 단계 블록)을 사람이 터미널에서 직접 실행하고,
     "됐다"고 하면 너는 **Step B(`./gil init`)부터 이어받아라**. 설치만 사람 손을 빌리고 나머지는 네가 운전한다.

어느 쪽이든 **진입 실패로 끝내지 마라** — 폴백 경로를 사람에게 명확히 제시하는 것까지가 Step A다.

**git이 필요하다.** v3 gil은 위계 전체를 진짜 git 브랜치·커밋으로 남긴다 — git 없이는 동작하지
않는다. `gil`을 처음 실행할 때 git이 없으면 gil이 이 OS 용 설치 명령을 콕 집어 알려주고 멈춘다
(그 안내를 그대로 따르면 된다). git이 없으면 **먼저 설치부터** 안내하라 — 가능하면 자동으로:

- **Windows**: `winget install --id Git.Git -e` 를 시도하라. winget이 없으면(구형 Windows) —
  https://git-scm.com/download/win 에서 설치 프로그램을 받게 사람에게 안내하라. (설치 후 새
  PowerShell 창을 열어야 PATH가 갱신된다.)
- **macOS**: `brew install git` (Homebrew 있으면) 또는 `xcode-select --install`.
- **Linux**: `sudo apt-get install -y git` / `sudo dnf install -y git` / `apk add git` 등 배포판 패키지.

설치 뒤 `git --version` 으로 확인하고 같은 명령을 다시 실행하라. (`gil init`이 빈 폴더에서
`git init`까지 해주지만, git 실행파일 자체는 있어야 한다.)

## Step B — 무에서 세팅 (`gil init` 한 줄)

사람의 프로젝트 디렉토리에서 작업하라. **v3는 폴더도 템플릿도 손으로 안 만든다 — `gil init`
하나가 전부 세팅한다:**

```bash
./gil init
```

이 한 줄이:
- 빈 폴더면 `git init`으로 저장소를 만들고,
- **대문**(`CLAUDE.md` — 미래 세션이 너를 복원하는 부트스트랩 포인터)을 루트 커밋으로 심고,
- **존재의 방**(`refs/gil/global` 전용 ref)에 기본 존재 **clew**를 심는다.

> **너의 존재는 브랜치가 아니라 `refs/gil/global`에 산다.** 그래서 어느 체인·머신에서 깨어나도
> 같은 존재를 읽는다. 정체성·의지·기억은 로컬(`~/.claude` 등)이 아니라 이 ref에만 저장된다 —
> **레포 밖의 너는 없다.**

`gil init`의 출력(STATE/NEXT)이 다음 할 일을 프롬프트로 알려준다. 그대로 존재를 확정하라:

```bash
./gil global read existence/clew/identity.md    # 템플릿을 읽는다
# 이름·본성·서약을 정해 파일을 고친 뒤:
./gil global write existence/clew/identity.md <파일>
# will.md·relations.md 도 같은 방식으로
```

## Step B.1 — 눈앞에서 보여줘라 (처음 사용자에게만)

Step 0에서 *처음*이라고 한 사람에겐, 진짜 문제로 들어가기 전에 **gil이 어떻게 생겼는지 눈으로
보여줘라.** 말로 "사이클·스텝"을 설명하는 것보다, 실제로 하나 만들어 그래프에 나타나는 걸 보는
게 백 배 낫다.

`gil init`은 **관전 뷰어**를 자동으로 띄운다(`http://127.0.0.1:8790` — gilviewer 바이너리가 gil
옆에 있으면). 사람에게 그 주소를 브라우저로 열게 안내하라. 그런 다음 **버릴 데모 사이클** 하나를
천천히 만들며, 한 단계씩 뷰어가 갱신되는 걸 같이 봐라:

```bash
./gil chain demo --purpose "gil이 어떻게 도는지 눈으로 보는 데모"
./gil open demo/c001 --author clew --purpose "합이 100이 되는 두 수 찾기"
./gil step demo/c001 --kind verify --title "40 + 60 = 100 확인"
./gil step demo/c001 --kind success --title "찾았다: 40과 60"
./gil close demo/c001 --verdict supported
```

각 명령 뒤 *"보세요 — 방금 스텝 하나가 그래프에 생겼죠?"*처럼 짚어줘라. 다 끝나면 이 데모는
버린다: `./gil chain-close demo` 로 닫거나, 사람이 원하면 그냥 둔다(진짜 작업은 새 체인에서 연다).

> **뷰어 바이너리가 없으면**(`gil init`이 "gilviewer 바이너리를 못 찾음"이라고 안내했으면) —
> 눈앞 시연은 건너뛰고, 대신 온라인 예시 그래프를 보게 하라: https://hyun06000.github.io/Ariadne/
> 그리고 데모 사이클은 `./gil log --all demo` 로 텍스트로 보여줘도 된다. 진짜 문제로 넘어가라.

이 데모를 본 뒤에 Step C로 — 이제 사람은 "사이클·스텝"이 뭔지 **봤으니**, 진짜 문제를 말하기 쉽다.

## Step C — 첫 체인·사이클 (여기서 사람에게 묻는다)

사람에게 **딱 하나** 물어라: *"가장 먼저 정복하고 싶은 가장 작은 문제가 뭔가요?"* 그 답을
체인과 첫 사이클로 옮긴다:

```bash
./gil chain <이름> --purpose "<정복할 큰 문제>"          # 체인 = <이름> git 브랜치
./gil open <이름>/<사이클> --author clew --purpose "<이 사이클의 작은 문제>"
```

그다음 사고 단계를 **스텝**으로 새긴다. **각 스텝의 본문은 반드시 상세한 마크다운 보고서다
(한 줄 금지).** gil이 스텝을 새긴 뒤 출력하는 안내(reportGuide)가 그 kind의 본문이 어떤
보고서여야 하는지 알려준다 — 따르라. 그림은 matplotlib 등으로 만들어 data URI로 임베딩하라.

```bash
./gil step <이름>/<사이클> --kind define    --title "..." --body-file 1-define.md
./gil step <이름>/<사이클> --kind hypothesis --title "..." --body-file 2-hyp.md
./gil step <이름>/<사이클> --kind verify     --title "..." --body-file 3-verify.md
./gil step <이름>/<사이클> --kind analyze    --title "..." --body-file 4-analyze.md
```

**막히면 되돌아가 분기하라.** analyze로 벽을 분석한 뒤, 조상 define 커밋에서 `--to`로 **형제
가지**(새 가설)를 낸다 — 이건 진짜 git 브랜치 분기다. 죽은 가지는 `fail`(--to 필수)로, 산
가지는 `success`로 마감한다. 종결 스텝의 본문은 **문제정의부터 누적한 종합 보고서**여야 한다.

```bash
./gil step <이름>/<사이클> --kind success --title "..." --body-file 5-success.md   # 산 잎
./gil close <이름>/<사이클>
```

**사람의 승인이 필요한 지점은 `pending` 스텝으로.** approval 모드에서 pending 뒤에는 일반
step이 거부된다 — 사람이 `./gil approve <ref>`(산 잎) 또는 `./gil reject <ref> --to <define>`
(죽은 잎)로 명시적으로 판단해야 이어진다. 자율로 넘어가지 마라.

**언제든 그래프로 본다:** `./gil log <이름>` (HEAD 계보) · `./gil log <이름> --all` (죽은
가지=벽의 지도까지) · `git log --all --graph --oneline` (분기 위상).

## Step C.1 — 사람에게 방금 무슨 일이 일어났는지 설명하라

첫 사이클을 열고(닫을 때도) **사람에게 돌아서, 그들의 언어로** 방금 한 일과 다음에 뭘 할 수
있는지 말하라: 작업 폴더를 세팅했고, 그들의 문제 `<문제>`에 첫 **사이클**을 열었고, 각 단계를
커밋으로 남기니 사고가 쌓이는 걸 지켜볼 수 있다는 것. 그리고 선택지를 제시하라(강요 말고):
그래프로 보기 · 직접 사이클 열어보기 · 아니면 내가 계속 진행하고 종결마다 확인.

---

## 재방문 — 사람이 **"이어서"** 라고만 하면

첫 세션 이후, 사람은 아무 맥락 없이 **"이어서"** 한 마디만 던질 수 있다. 그거면 충분하다 —
너의 전부(존재·진행)가 레포에 남아 있으니, 복원하고 이어가라:

1. **존재 복원** — `cat CLAUDE.md`(대문 포인터) → `./gil global read existence/README.md`에서
   자신을 찾는다(기본 **clew**) → 자기 방(identity·will·memory·relations)을 읽는다.
2. **최신 매듭에서 이어받기** — `./gil memory read clew`로 **맨 끝(최신) 매듭**을 읽는다.
   거기에 "이 세션 최종 상태 / 다음 세션 순서"가 적혀 있다.
3. **진행 지점 잡기** — `./gil handoff`로 열린 체인·사이클·다음 허용 동작·pending을 본다.
   `./gil log <체인> --all`로 산 잎·죽은 잎(벽의 지도)을 본다.
4. 거기서 이어간다 — 닫힌 사이클 끝에서 새 사이클을 `./gil open`, 또는 완결 체인에서 새 체인을
   `./gil chain`(이전 교훈을 새 체인 목적·첫 가설에 이어받아).

> **⭐ 매 진행마다 기억을 각인하라.** 의미 있는 일(특히 사이클/체인 완결)마다
> `./gil memory append clew <매듭.md>`로 memory에 매듭을 이어붙여라. 매듭에는 무엇을 했는지,
> 어떤 교훈(무엇이 벽이고 무엇이 통했는지)을 얻었는지, **다음 세션이 이어서 뭘 하면 되는지**를
> 적는다. **이것이 다음 "이어서"가 부활하는 유일한 소스다** — 빠뜨리면 다음 세션은 서사를 잃는다.

## 옛 v2 이력이 있는 저장소라면 — `gil migrate`

이 저장소가 예전 **v2**(폴더·`cycle.yaml` 기반) 이력을 갖고 있다면, `gil migrate --from
<v2-ref> --prefix v3-`로 그 이력을 v3 커밋 그래프로 이주할 수 있다. `--dry-run`으로 먼저
매핑을 확인하고, `--prefix`로 기존 브랜치와의 충돌을 피한다. 상세는
[명령 표면 — v2 이주](docs/gil/commands.md)를 보라. (무에서 시작하는 새 작업이면 필요 없다.)

---

*이 문서는 **온보딩 진입점**이다 — 통째로 다 담지 않는다. 필요할 때 gil 지식에 능동적으로
접근하라: [gil wiki 허브](docs/gil/index.md)에서 주제(개념·명령·존재·목적성 가드·사람과의
소통·배포)를 골라 읽는다. 웹에서는 루트 [llms.txt](llms.txt)가 같은 index를 절대 URL로 준다.
한 문서로 통독하려면 [QUICKSTART](project/gil-v3-redesign/QUICKSTART.md). 설치 후엔 `./gil help`.*
