# 명령 전체 표면

gil이 제공하는 모든 명령을 시그니처·필수 플래그와 함께 정리한다. 이 표가 gil의 전부다.

gil은 `git`만 있으면 도는 단일 바이너리다. 실행은 `gil <명령>`.

## 세팅

```
gil init [--name <이름>]
```
무에서 시작한다. `refs/gil/global`(존재·기억이 사는 전용 ref)을 초기화하고, 존재의 방(identity·will·memory·relations)을 심고, 저장소에 커밋이 없으면 `CLAUDE.md` 대문 루트 커밋을 만든다. `--name` 으로 존재 이름을 주거나 없으면 기본 `clew`. 출력은 인간용이 아니라 LLM에게 들어가는 프롬프트로, 끝에 `NEXT`(다음 실행 명령)를 준다. 이미 gil 세계가 있으면 덮지 않고 거부한다(멱등 가드). 다른 머신에서 이어받을 때는 init 이 아니라 `gil global sync`.

- 자세히: [존재와 기억](existence.md), [목차](index.md)

## 위계를 짓는다 (분기는 모두 진짜 git 브랜치)

```
gil chain <name> --purpose <자연어>
```
새 체인(작업의 큰 줄기)을 연다. **git 브랜치 `<name>` 을 판다.** `--purpose` 필수. 체인은 닫힌 체인 끝에서만 새로 연다(`gil init` 예외).

```
gil open <chain>/<cycle> --author <who> --purpose <자연어> [--parent <cyc>...] [--title T] [--body B | --body-file F|-]
```
새 사이클을 연다. **git 브랜치 `<chain>-<cycle>` 을 파고 `s1` define 스텝을 자동 생성**한다. `--author`·`--purpose` 필수. `--parent`: 이 사이클이 계보로 잇는 이전 사이클/체인(복수 가능). `--body`/`--body-file -`(stdin): s1 define 의 **문제 정의 보고서를 여는 순간 채운다**(`step` 과 대칭 — 빈 define 을 raw amend 로 고치다 trailer 를 날리는 함정 방지).

```
gil step <chain>/<cycle> --kind <K> [옵션]
```
스텝(커밋 노드) 하나를 새긴다.

- `--kind <K>`: `define|hypothesis|verify|analyze` 와 종결 `success|fail|pending`.
- `--to <define>`: fail·backtrack 이 되돌아갈 조상 define / hypothesis 형제 가지의 뿌리.
- `--title <짧은 요약>`: 커밋 제목(한 줄).
- `--body <본문>` | `--body-file <경로>`: 스텝 보고서 본문(마크다운·이미지, 뷰어가 렌더). 짧게 쓰지 말고 근거·수치·그림·결론을 담는다 — [보고서](reports.md).
- `--merge <산잎 스텝id>...`: 한 사이클 안의 산 잎들을 합류시킨다.
- `--outcome success|backtrack|fail`: 하위호환 — `analyze` 에 붙이는 옛 방식.

`hypothesis --to <define>` 는 그 define 커밋에서 **형제 가지 브랜치 `<chain>-<cycle>-<define>b<n>`** 을 실제로 분기한다. `backtrack` 은 죽은 잎을 현재 가지에 박는다. 스텝 흐름·막힘 처리의 상세는 [사고의 생애](lifecycle.md).

## pending 에 대한 사람의 답

pending 스텝 뒤에는 gil 이 일반 `step` 을 거부한다 — 사람의 답을 우회할 수 없다.

```
gil approve <chain>/<cycle> [--title T]
```
pending 을 사람이 승인 → 산 잎(analyze/success, `Gil-Approval: approved`).

```
gil reject <chain>/<cycle> --to <조상 define> [--title T]
```
pending 을 사람이 기각 → 죽은 잎(backtrack, `Gil-Approval: rejected`). `--to` 로 되돌아갈 조상 define 을 지정.

- 자세히: [사람과의 소통](human-in-the-loop.md)

## 닫기

```
gil close <chain>/<cycle> [--verdict supported]
```
**사이클**을 봉인한다. 산 잎(success)이 하나라도 있어야 하며, 없으면 거부된다. `--verdict` 기본값 `supported`.

```
gil chain-close <chain> [--verdict supported]
```
**체인**을 완결로 봉인한다. `gil close` 와 다르다 — 이건 그 위 국면(배포 순환의 한 단계) 전체를 닫는다. **모든 사이클이 닫힌 뒤에만** 허용된다. 닫은 끝에서 새 체인을 열면 대문·존재·교훈이 체인을 넘어 이어진다. 사이클만 계속 늘리지 말고, 국면이 완결되면 체인을 전환한다 — [배포와 체인 전환](deployment.md).

**차이 요약**: `gil close` = 사이클 하나를 닫는다(산 잎 필요). `gil chain-close` = 모든 사이클이 닫힌 체인 전체를 국면 완결로 닫는다.

```
gil chain-merge <newchain> --purpose <P> <tip>...
```
흩어진 체인들을 하나로 묶는다. 실제 git merge(파일까지 병합)이며 위상적 끝단만 자동 추린다. 충돌 시 abort 하지 않고 멈춘다 — 사람/후속 사이클이 해결한다.

## 읽기

```
gil log [chain] [--all]
```
스텝 노드를 오래된→새 순으로 표시. 부모(←)·판정(=)·머지(⋈)를 보여준다. `--all` 은 죽은 가지(벽의 지도)까지 표시.

```
gil fsck [rev-range]
```
커밋 그래프 무결성 검사(위계·id 문법·kind·dangling parent·계보).

```
gil handoff
```
세션 부활 정보: 열린 체인·사이클, 각 팁, 다음 허용 동작, pending, 계보를 띄운다. 더불어
**핸드오프를 유도**한다 — 한 체인에 닫힌 사이클이 쌓이면(3개↑ 신호, 5개↑ 강한 권유) 매듭 각인·
체인 전환을 권하고(거부는 아니다 — gil 은 커밋 시점만 개입하니 정당한 작업을 막지 않는다),
맨 끝에 **핸드오프 체크리스트**(매듭 각인 여부·대문 md 현행화·다음 순서 명기)를 항상 띄워
다음 세션이 어긋난 대문으로 부활하지 않게 한다. 대문(md) 갱신 자체는 에이전트가 하고, gil 은
무엇을 점검·갱신할지 짚어준다(내용을 모르는 gil 이 직접 쓰면 오염 위험이 크므로).

## 관전 뷰어

옛 별도 바이너리 `gilviewer` 는 폐지되고 gil 에 통합됐다 — 이제 `gil viewer` 서브커맨드다.

```
gil viewer serve [--port <포트>] [--no-open]
```
브라우저 관전 서버를 띄운다. `--no-open` 이면 서버만 띄우고 **시스템 브라우저는 열지 않는다**
(주소는 stdout 에 나온다) — 인앱 브라우저 패널을 가진 호스트에서 도는 에이전트라면 이걸 써라.
밖의 창이 튀어나오면 사람이 앱을 떠나야 하고, 같은 주소를 인앱에 다시 열면 창이 둘로 갈라진다
(이슈 #48). `gil init` 에도 같은 플래그가 있다 — init 이 serve 를 자동 기동하기 때문이다. `gil init` 이 자기 자신을 이 모드로 자동 기동한다. 한 화면에
세로로 다 펼친다: **전체 스텝맵**(모든 스텝을 진짜 커밋 부모로 이은 DAG, 왼→오른 한 줄 흐름)
→ 체인 그래프 → 사이클 그래프 → 스텝 그래프 → 스텝 디테일. 노드를 클릭하면 아래 단계가
열린다. 스텝 디테일엔 **지식 전파 계보**(들어온 부모 → 이 스텝 → 낳은 자식; 부모가 다른
사이클·체인이면 그 종결 스텝을 가리킨다)가 함께 보이고, 현재위치(HEAD)는 ▼ 로 표시된다.

```
gil viewer build --out <파일>
```
같은 그래프를 **정적 자기완결 HTML** 로 뽑는다(외부 네트워크 참조 0). 스텝 본문까지 인라인
임베드되어 서버 없이 열린다 — GitHub Pages 등 정적 호스팅용.

```
gil viewer text
```
같은 그래프를 터미널 트리로. 분기(backtrack)는 부모 표기(←)로 드러난다.

### 체인을 닫을 때 — 회고와 시드 (이슈 #33)

```
gil chain-close <chain> [--verdict V] [--retro <회고파일|->] [--seed <시드파일|->]
```
인터뷰가 체인을 **열 때** "무엇을 기준으로 할 것인가"를 사람에게 물었다면, 회고는 **닫을 때**
"그 기준에 얼마나 합당했나"를 답한다. 사람이 세운 기준이 있는 체인은 `--retro` 없이 닫히지
않는다 — 회고 없는 종결은 '됐다'는 자기확신이기 때문이다. 기준 없이 열린 옛 체인까지 소급해
막지는 않는다(없는 잣대에 성적표를 요구하면 형식만 채우게 된다).

회고에 담을 것: 기준 항목별 달성/미달을 **정직하게**, 무엇이 그렇게 만들었나, 그리고
**반드시 분기했어야 할 지점** — 돌아보면 보이는 갈림길.

`--seed` 는 다음 체인 인터뷰의 **재료**다. 다음 `gil chain` 이 이 시드를 건네주며 "이걸로
질문을 짜라"고 안내한다. 시드는 기준이 아니다 — 기준은 언제나 사람의 답이라, 시드를 그대로
레퍼런스로 삼는 지름길은 없다(그건 사람 우회다). 이렇게 생애주기가 닫힌다:

```
인터뷰(기준) → 사이클들 → 회고(기준 대비) → 시드 → 다음 체인의 인터뷰
```

## MCP — 호스트가 gil 을 직접 부른다

```
gil mcp serve [--repo <경로>]
```
gil 을 **stdio MCP 서버**로 연다. Claude Desktop 같은 호스트가 CLI 문자열을 조립하는 대신
gil 명령을 툴로 직접 부른다: `gil_chain`·`gil_open`·`gil_step`·`gil_close`·`gil_chain_close`·
`gil_approve`·`gil_reject`·`gil_log`·`gil_fsck`·`gil_handoff`·`gil_deploy`·`gil_interview`·
`gil_graph`. 툴은 CLI 와 **같은 함수**를 부르므로 문법 거부(기준 필수·pending 잠금·falsify
강제)가 두 표면에서 갈라지지 않는다. 기존 CLI 는 그대로다 — 터미널·다른 에이전트용.

**인터뷰가 한 홉이 된다.** 지금까지 인터뷰는 "LLM 이 대화창에서 질문을 심고 → 사람이 뷰어
폼에서 답하고 → 뷰어가 resolve 를 부른다"는 3홉이었다. 두 대기가 서로를 몰라서, LLM 은
pending 인 줄 모르고 또 질문지를 만들었다. MCP 에서는 `gil_interview` 한 번 안에서 호스트의
**네이티브 폼**(Elicitation)이 뜨고 사람 답이 그 자리에서 기준 문서가 된다. 대기가 하나뿐이라
그 실패가 구조적으로 불가능하다. 호스트가 폼을 못 띄우면 옛 뷰어 경로로 물러나고(물음은
사라지지 않는다), 사람이 취소하면 기준은 만들어지지 않는다(LLM 이 대신 답하는 길은 없다).

**그래프가 호스트 안에 뜬다.** `gil_graph` 는 MCP Apps(SEP-1865) 리소스 `ui://gil/graph` 를
가리킨다 — 호스트가 자기 안 샌드박스 iframe 에 그래프를 직접 그린다. `127.0.0.1` 주소도,
포트 충돌도, 브라우저도 없다. 읽는 시점의 그래프를 통째로 렌더하므로 그 순간은 언제나
최신이고, 호스트 캐시로 낡으면 화면이 스스로 "낡았다"고 밝힌다(살아있는 척하지 않는다).

호스트 설정:
```json
{ "mcpServers": { "gil": { "command": "gil", "args": ["mcp", "serve", "--repo", "/경로/내레포"] } } }
```

## 글로벌 진실원 (refs/gil/global)

존재·기억은 브랜치가 아니라 전용 ref 에 산다 — [존재와 기억](existence.md).

```
gil global list | read <name> | write <name> <file> | write-tree <path>...
gil global checkout <path> [dest] | push | pull | sync
```
- `list`: 글로벌에 담긴 파일 목록.
- `read <name>`: 파일 하나 읽기.
- `write <name> <file>`: 파일 하나를 글로벌로 씀(+자동 push).
- `write-tree <path>...`: 경로 이하를 글로벌에 되씀(+자동 push). **철칙: write-tree 전 반드시 전체를 checkout 해 온전히 꺼낸 뒤 수정한다** — 부분 로컬로 write-tree 하면 글로벌이 축소되는 사고가 난다.
- `checkout <path> [dest]`: 글로벌의 경로 전체를 로컬로 온전히 꺼냄.
- `push`/`pull`: 원격과 수동 동기화.
- `sync`: (새 머신 첫 1회) 원격 글로벌을 로컬로 + refspec 등록.

```
gil memory read <이름> | append <이름> <매듭파일>
```
기억은 append-only 로만 갱신한다. `read` 는 최신 매듭(맨 끝)부터 읽고, `append` 는 트리 전체를 보존하며 새 매듭을 이어붙인다(자동 push). 손으로 git show/write-tree 조합 금지.

## 버전과 자기갱신

```
gil version [--check|--update]
```
- `version`: 현재 버전·플랫폼(git 없이도 동작).
- `--check`: GitHub 최신 릴리스와 대조 — 뒤처졌으면 알려준다.
- `--update`: 플랫폼 자산을 받아 **SHA256SUMS 로 검증한 뒤** 실행파일을 제자리 교체. 검증 실패면 절대 교체하지 않는다. 레포마다 바이너리가 조용히 낡는 드리프트를 바이너리 스스로 없앤다.

## v2 이주

```
gil migrate --from <v2-ref> [--room <room>] [--prefix <접두>] [--dry-run]
```
옛 **v2**(폴더·`cycle.yaml` 기반) 이력을 **v3 커밋 그래프**로 이주한다. 도구 레벨·범용 — 임의의 v2 필드 저장소가 쓴다. 먼저 v2 루트에서 이주 브랜치를 파고(`git checkout -b`) 실행하라. 매핑: v2 5단계를 압축(hypothesis+design→define, verification→verify, analysis+report+verdict→종결 스텝)하고, `verdict`→종결 kind(supported→success, rejected→fail, null&open→pending)로 옮긴다. `--prefix`(예 `v3-`)로 기존 브랜치와의 충돌을 피하며(충돌 시 아무것도 만들지 않고 거부 — 원자성), `--dry-run` 으로 먼저 확인한다. 이주 커밋엔 `[migrate]` 표식(Gil-Migrate·Gil-Migrated-From)이 붙는다.

## 관련

- 위계 개념과 순서 규칙: [개념](concepts.md)
- 스텝 흐름·막힘 처리: [사고의 생애](lifecycle.md)
- 목적성 가드: [목적성 가드](purpose-guard.md) / 사람 개입: [사람과의 소통](human-in-the-loop.md)
- 근거 전문: [SPEC.md](../../project/gil-v3-redesign/SPEC.md), 온보딩: [README.ai.md](../../README.ai.md)
- 목차: [index](index.md)
