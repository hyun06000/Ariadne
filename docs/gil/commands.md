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
gil open <chain>/<cycle> --author <who> --purpose <자연어> [--parent <cyc>...] [--title T]
```
새 사이클을 연다. **git 브랜치 `<chain>-<cycle>` 을 파고 `s1` define 스텝을 자동 생성**한다. `--author`·`--purpose` 필수. `--parent`: 이 사이클이 계보로 잇는 이전 사이클/체인(복수 가능).

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
세션 부활 정보: 열린 체인·사이클, 각 팁, 다음 허용 동작, pending, 계보를 띄운다.

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
