# gil-companion-prototype

**Agent 가 쓸 GIL 과 사람이 볼 Monitor 의 문**을 함께 소유하는 공용 Plugin 정본.
이 디렉터리가 **정본**이다.

```text
core/<platform>/gil   실린 GIL Core — Agent 가 부르는 실행 파일 (생성물)
core.mjs              Core 의 descriptor·probe 와 argv 실행
actions.mjs           Agent 명령표 — tool 하나가 subcommand 하나
capability.mjs        표면 판정과 「Monitor 열기」 조율 — 바깥 효과 없음
say.mjs               사람에게 가는 문장과 경로·PID·socket·port 유출 문지기
server.mjs            MCP 배선과 바깥 세계에 닿는 port
core.test.mjs         Core 판정과 동치 시험
capability.test.mjs   coordinator 시험
manifest.test.mjs     두 adapter 가 같은 하나를 가리키는지의 시험
make-core.sh          실린 Core 를 짓는 자리
skills/gil-companion  Agent가 언제 무엇을 부를지
.codex-plugin/        Codex adapter manifest — 여기 말고 아무것도 담지 않는다
.claude-plugin/       Claude Code adapter manifest — 같은 규칙
```

Codex와 Claude Code는 별도 GIL 제품이 아니다. 같은 `server.mjs`·Rust Core·tool 표·Skill을 쓰고,
Host가 요구하는 manifest와 Plugin root 표기만 나눈다. 사용자에게는 둘 다 **GIL Plugin**이다.
일반 Claude Desktop용 `.mcpb`는 후속 packaging adapter이며 이 정본을 복사한 두 번째 구현으로
만들지 않는다.

## Host adapter 는 manifest 하나뿐이다

MCP 등록은 **각 Host 의 manifest 안에** 적는다. plugin root 의 `.mcp.json` 은 두지 않는다 —
두 Host 모두 그 파일을 스스로 찾아내므로, inline 등록과 겹치면 server 가 둘이 된다.

```text
.codex-plugin/plugin.json    "args": ["./server.mjs"],                     "cwd": "."
.claude-plugin/plugin.json   "args": ["${CLAUDE_PLUGIN_ROOT}/server.mjs"], "cwd": "${CLAUDE_PLUGIN_ROOT}"
```

다른 것은 **plugin root 를 부르는 이름 하나**뿐이다. 두 줄 모두 같은 `server.mjs` 로 내려앉고,
`manifest.test.mjs` 가 그 자리를 풀어 같은 파일인지 확인한다. Skill·Core·tool 표는 나누지
않는다 — adapter 디렉터리는 자기 `plugin.json` 말고 **아무것도** 담지 않으며, 그것도 시험이
지킨다.

Codex 는 `skills/` 자리를 manifest 에 적고, Claude Code 는 `skills/` 를 언제나 스스로 훑으므로
적지 않는다. 같은 Skill 파일 하나를 두 Host 가 각자의 방식으로 찾아갈 뿐이다.

## 무엇을 소유하는가

```text
Plugin      Agent 용 GIL Core · MCP bridge · Manual/Skill · Companion coordinator
Companion   읽기 전용 Monitor · DAG·Report UI · Project watcher · 지속형 창
```

두 역할을 섞지 않는다. Companion 에 Agent 의 write 명령을 넣지 않고, Plugin 이 사람이 볼
지속 창을 만들지 않는다. 그래서 Agent 표면에 `monitor` 가 없다 — 그 자리는
`gil_companion_status` 와 `show_gil_companion` 이 소유한다. (Rust 의 `gil monitor` 는 그대로
있다. 이 Plugin 이 노출하지 않을 뿐이다.)

## Agent 가 부르는 문

`gil_start` · `gil_open` · `gil_close` · `gil_restore` · `gil_revisit` ·
`gil_status` · `gil_story` · `gil_context` · `gil_cycle` · `gil_help`

경계는 이렇게 생겼다.

```text
typed MCP 인자 → 고정된 실행 파일과 argv → 필요한 본문은 stdin
→ Rust GIL 실행 → 종료 코드로 성패 → 산문은 그대로 전달
```

shell 을 쓰지 않고 command 문자열을 조립하지 않는다. 사용자 입력은 **값**이 되지 실행 파일도
flag 이름도 되지 않는다. Core 의 말을 요약하거나 다시 쓰지 않으며, 그 문장을 substring 으로
검사해 상태를 짐작하지도 않는다 — 성패는 종료 코드 하나다.

Project 자리는 **명시적으로** 받는다. cwd 도, 최근 폴더도, Companion 이 사람에게 보여 주는
선택도 Agent action 의 대상으로 짐작하지 않는다.

## 실린 Core

```bash
./make-core.sh   # 짓고 확인만 한다
./package.sh     # 짓고 · 확인하고 · cachebuster 를 올리고 · 다시 설치한다
```

저장소의 Rust Core 를 `core/darwin-arm64/gil` 로 짓고, **지은 뒤 실제로 실행해** identity·
architecture·fresh challenge 를 확인한다. 확인에 실패하면 실린 것을 지우고 멈춘다 — 낡은
binary 를 조용히 다시 쓰지 않는다.

### 배포의 한계 — 이 sidecar 가 아직 아닌 것

이 binary 는 **로컬에서 만든 개발 artifact** 다. git 에 들어가지 않으므로:

- **source clone 만으로는 Plugin 설치가 완성되지 않는다.** 받은 사람은 `make-core.sh` 를 직접
  돌려야 하고, 그러려면 Rust 와 cargo 가 필요하다 — 비개발자용 경로가 아직 아니다.
- packaging 전에 `make-core.sh` 가 **반드시** 먼저 돌아야 한다. `package.sh` 가 그 순서를
  강제한다: 짓고 → identity·arch·fresh challenge·digest 를 확인하고 → 그제서야 cachebuster 를
  올리고 다시 설치한다.
- **Core 가 없거나 이 기계의 것이 아니면 cachebuster 와 재설치를 하지 않는다.** 확인되지 않은
  설치본을 만드느니 멈춘다.
- **public marketplace 용 binary publication 은 미결이다.** 서명·공증·배포 자리·platform 별
  artifact 가 모두 정해지지 않았다.
- 지금 실측한 것은 **macOS arm64 development packaging feasibility** 하나뿐이다.

서명도 공증도 하지 않았고 공개 배포판이 아니다. Companion 의 `release-macos.sh` 와 혼동하지
않는다 — 그쪽은 사람이 볼 창을 짓고, 여기는 Agent 가 부를 Core 를 짓는다.

지금 실측한 자리는 **macOS arm64 하나뿐**이다. 다른 platform 에서는 임의의 binary 를 실행하지
않고 `agent_surface=unavailable` 로 답한다. platform 이 늘면 `core/<platform>/gil` 이 늘고
`core.mjs` 의 자리표에 한 줄이 붙는다.

## 정본과 설치본

```text
plugins/gil-companion-prototype          ← 정본 (여기). 고치는 자리는 여기 하나다.
~/plugins/gil-companion-prototype        → 위를 가리키는 symlink. **개발·설치 진입점일 뿐이다.**
~/.codex/plugins/cache/personal/...      ← `codex plugin add` 가 만든 설치본. 혼자 선다.
```

Claude Code adapter도 같은 정본에서 설치 cache를 만들며, 그 cache가 Codex cache를 참조하거나
반대쪽 cache를 정본으로 삼지 않는다. 두 설치본은 독립적으로 지울 수 있지만 담긴 MCP 동작과 Skill은
같아야 한다. 한쪽 Plugin을 끄면 그 Host의 Agent tool만 사라지고, Companion도 Project 기록도
그대로 남는다.

personal marketplace(`~/.agents/plugins/marketplace.json`)의 항목이 `./plugins/gil-companion-prototype`
를 가리키고, 그 자리가 이 디렉터리로 이어지는 symlink다. 그래서 편집하는 파일과 marketplace가
읽는 파일이 **같은 파일 하나**다. 손으로 복사해 두 정본을 만들지 않는다.

### symlink 는 runtime 의존이 아니다

설치가 끝나면 symlink도, 이 저장소도 **실행에 필요하지 않다.** `codex plugin add`가 설치본을
cache로 복사하고, 그 안의 `.mcp.json`은 자기 root 를 기준으로만 말한다.

```json
{ "command": "node", "args": ["./server.mjs"], "cwd": "." }
```

절대 경로도, 홈 디렉터리도, 이 저장소의 자리도 적지 않는다 — Codex 번들 plugin이 쓰는 것과 같은
형태다. Claude Code 쪽도 같은 약속을 `${CLAUDE_PLUGIN_ROOT}` 로 말할 뿐이고, manifest 와
marketplace 에 기계에 매인 자리가 없다는 것을 시험이 지킨다. 저장소를 읽을 수 없는 sandbox 안에서 설치본만으로 tool 목록·`gil_companion_status`·
`show_gil_companion`이 동작하는 것을 시험으로 확인한다.

`server.mjs`가 홈 아래를 보는 곳은 **Companion app 을 찾을 때 하나뿐**이고(`~/Applications`,
`/Applications`), 그것은 macOS의 앱 설치 자리지 Plugin source 경로가 아니다. 둘을 섞지 않는다.

다른 개발 기계에서는 이 저장소를 받아 `npm ci` 와 `make-core.sh` 를 돌린 뒤 아래 절차를 그대로
밟는다. manifest 는 고칠 것이 없다. 이것은 **개발자 절차**다 — clone·Node·npm·Rust·cargo 가
모두 있어야 하므로 받는 사람의 설치 완성본이 아니다.

`.mcp` manifest 의 `"command": "node"` 는 **Host 나 기계에 Node runtime 이 있다는 전제**를 깐다.
clean machine 에 Node 가 있다고 가정하지 않는다 — 없으면 server 가 뜨지 않고 Plugin 은 설치된
것처럼 보이면서 tool 이 붙지 않는다. 이 전제를 없애는 것이 M5-E 의 Rust MCP 단일 실행 파일이다.

## 고친 뒤 반영하기 — Codex

Codex의 공식 절차를 그대로 쓴다. marketplace 파일을 손으로 고치지 않는다.

```bash
S=~/.codex/skills/.system/plugin-creator/scripts
python3 "$S/read_marketplace_name.py"                     # → personal
python3 "$S/update_plugin_cachebuster.py" "$PWD"          # 판 번호의 cachebuster 만 교체
/Applications/ChatGPT.app/Contents/Resources/codex plugin add gil-companion-prototype@personal
```

그다음 **새 thread**에서 열어야 갱신된 skill과 tool이 붙는다. 옛 MCP server가 남아 있으면
그 프로세스만 정확한 PID로 끝낸다.

## 고친 뒤 반영하기 — Claude Code

개발 인수에 실제로 쓴 경로는 **local Plugin upload** 하나다. 이 정본을 묶어 Claude Desktop 에
올리면 Host 가 `local-desktop-app-uploads` marketplace 아래에 설치본을 둔다. `package.sh` 는
Codex 쪽 절차이며 이 묶음을 만들지 않는다 — 묶는 자리는 아직 script 로 서 있지 않다. 설치 registry(`~/.claude/plugins/…`)는 손으로 고치지 않는다. 갱신된 skill 과 tool 은
**새 session** 에서 붙는다.

저장소 최상위의 `.claude-plugin/marketplace.json` 은 그 묶음의 정본 descriptor 다. **Desktop UI
에서 로컬 디렉터리를 marketplace 로 더하는 자리는 확인되지 않았다** — 그 문을 전제로 절차를
적지 않는다. 사용자 배포 경로는 local upload 가 아니라 **remote marketplace** 이며, 그것은 아직
열려 있다(M5-E).

```text
local Plugin upload    개발 인수 경로 — 이 저장소에서 지어 올리고, 받는 쪽도 개발자다
remote marketplace     사용자 배포 경로 — self-contained artifact 와 release pipeline 이 필요하다
```

어느 쪽이든 source clone 은 **비개발자 설치의 완성본이 아니다.** `make-core.sh` 가 필요하고,
그래서 Rust 와 cargo 가 필요하다. 일반 Claude Desktop 용 `.mcpb` 는 후속 adapter 이고 아직
구현하지 않았다.

## 시험

```bash
./make-core.sh   # Core 를 먼저 짓는다 — 동치 시험이 이것을 쓴다
npm test
```

바깥 효과는 전부 가짜로 끼운다 — launcher, handshake probe, 시계. production protocol을 약하게
만들거나 고정된 fixture 결과를 제품 코드에 넣지 않는다.

`node_modules`는 역사에 넣지 않는다. 새로 받으려면 `npm ci`.
