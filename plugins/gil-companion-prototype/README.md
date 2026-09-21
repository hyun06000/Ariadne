# gil-companion-prototype

사람이 지속형 GIL Monitor를 열게 하는 Codex Plugin. 이 디렉터리가 **정본**이다.

```text
capability.mjs        표면 판정과 「Monitor 열기」 조율 — 바깥 효과 없음
say.mjs               사람에게 가는 문장과 경로·PID·socket·port 유출 문지기
server.mjs            MCP 배선과 바깥 세계에 닿는 port
capability.test.mjs   16개 시험 (`npm test`)
skills/gil-companion  Agent가 언제 무엇을 부를지
.codex-plugin/        plugin manifest
```

## 정본과 설치본

```text
plugins/gil-companion-prototype          ← 정본 (여기). 고치는 자리는 여기 하나다.
~/plugins/gil-companion-prototype        → 위를 가리키는 symlink. **개발·설치 진입점일 뿐이다.**
~/.codex/plugins/cache/personal/...      ← `codex plugin add` 가 만든 설치본. 혼자 선다.
```

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
형태다. 저장소를 읽을 수 없는 sandbox 안에서 설치본만으로 tool 목록·`gil_companion_status`·
`show_gil_companion`이 동작하는 것을 시험으로 확인한다.

`server.mjs`가 홈 아래를 보는 곳은 **Companion app 을 찾을 때 하나뿐**이고(`~/Applications`,
`/Applications`), 그것은 macOS의 앱 설치 자리지 Plugin source 경로가 아니다. 둘을 섞지 않는다.

다른 기계에서는 이 저장소를 받아 `npm ci` 한 뒤 아래 절차를 그대로 밟으면 된다. `.mcp.json` 은
고칠 것이 없다.

## 고친 뒤 반영하기

Codex의 공식 절차를 그대로 쓴다. marketplace 파일을 손으로 고치지 않는다.

```bash
S=~/.codex/skills/.system/plugin-creator/scripts
python3 "$S/read_marketplace_name.py"                     # → personal
python3 "$S/update_plugin_cachebuster.py" "$PWD"          # 판 번호의 cachebuster 만 교체
/Applications/ChatGPT.app/Contents/Resources/codex plugin add gil-companion-prototype@personal
```

그다음 **새 thread**에서 열어야 갱신된 skill과 tool이 붙는다. 옛 MCP server가 남아 있으면
그 프로세스만 정확한 PID로 끝낸다.

## 시험

```bash
npm test
```

바깥 효과는 전부 가짜로 끼운다 — launcher, handshake probe, 시계. production protocol을 약하게
만들거나 고정된 fixture 결과를 제품 코드에 넣지 않는다.

`node_modules`는 역사에 넣지 않는다. 새로 받으려면 `npm ci`.
