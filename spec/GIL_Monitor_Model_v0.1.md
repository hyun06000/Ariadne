# GIL Monitor Model v0.1

> GIL의 원본 Graph를 변경하지 않고, 인간이 현재 위치와 실패·전환·다음 행동을 이해하도록
> 하나의 검증된 사실 Snapshot을 만드는 규칙을 정의한다.

---

## 1. 목적

Monitor는 터미널이나 `.gil/state.yaml`을 직접 읽지 않는 사람을 위한 관찰 표면이다.

사람은 Monitor만 보고 최소한 다음 질문에 답할 수 있어야 한다.

- 지금 어떤 실험을 하고 있는가.
- 성공 기준은 무엇인가.
- 지금 어느 Cycle과 Step에 있는가.
- 어떤 실패와 방향 전환을 거쳐 여기 왔는가.
- Artifact 세계는 기준 Snapshot과 같은가.
- Agent는 지금 무엇을 하려 하는가.
- 다음에 허용되는 행동은 무엇인가.

Monitor는 새 상태 기계가 아니다. Graph, Report, Journey와 Artifact reference만이 진실 공급원이며,
Monitor는 그 원본에서 읽은 사실을 한 시점의 불변 Snapshot으로 투영한다.

---

## 2. 독자와 다른 투영의 역할

```text
status   지금 자리의 짧은 nudge
story    채팅 중인 인간이 현재 여정을 이해하는 설명
context  새 Agent 세션이 작업을 이어받는 onboarding
history  전체 실행 경로의 감사와 조사
monitor  인간이 현재 상태와 그 근거를 지속적으로 관찰하는 화면
```

이 다섯 표면은 같은 문자열을 복제하지 않는다. 독자와 해상도는 다르지만 같은 사실에서 서로
모순되는 판정을 만들 수 없다.

Monitor는 `gil story` 출력을 파싱하지 않고, `gil context`를 다시 화면에 붙이지 않으며, CLI를
자식 프로세스로 실행해 문자열을 수집하지 않는다.

---

## 3. 하나의 사실 모델

이 문서에서 "하나의 read model"은 모든 독자에게 거대한 DTO 하나를 그대로 주거나 같은 문장을
표시한다는 뜻이 아니다. **한 번 검증된 원본 사실 Snapshot에서 목적별 projection을 만든다**는
뜻이다.

```text
Graph + Reports + Journey + Artifact observation
                         │
                         ▼
              Project Read Snapshot
               ├─ status projection
               ├─ story projection
               ├─ context projection
               └─ monitor projection
```

첫 M5 구현은 기존 renderer를 모두 한 번에 재작성하지 않는다. 먼저 `MonitorSnapshot`을 만들고,
기존 CLI와 겹치는 핵심 사실이 같은 원본 값을 가리키는지 정합성 시험으로 고정한다. 이후 공통화가
실제 중복을 줄일 때만 더 아래의 `Project Read Snapshot`으로 추출한다.

### 3.1 원본에 접근하는 문

Monitor는 다음 규칙을 따른다.

1. `.gil/state.yaml`을 직접 파싱하지 않는다.
2. 검증된 Project 복원 경로와 domain type을 사용한다.
3. Artifact 세계는 기존 `ProjectSession::world_state()` 경로로 한 번만 관측한다.
4. Report 문자열에서 구조를 역추론하지 않는다.
5. typed reference를 문자열 비교로 대신하지 않는다.
6. 내부 manifest·blob 주소를 공개 사실로 올리지 않는다.

---

## 4. `MonitorSnapshot`

한 번의 조회는 한 개의 불변 `MonitorSnapshot`을 만든다. renderer가 그리는 동안 원본을 다시 읽지
않는다.

v0 Snapshot은 구현된 개념만 포함한다.

```text
MonitorSnapshot
├─ captured_at                 표시용 관측 시각
├─ current_existence
│  ├─ existence_ref
│  └─ journey_ref
├─ current_cycle
│  ├─ cycle_ref · kind · state
│  ├─ parent_cycle_ref?
│  ├─ revisit_from_cycle_ref?
│  ├─ experiment_definition?
│  ├─ handoff?
│  └─ steps
├─ active_lineage
│  └─ LineageCycleFacts[]
├─ inactive_cycles
├─ pending_revisit?
├─ current_step?
├─ current_will?
├─ world
└─ next_actions
```

`captured_at`은 Graph의 사건 시간이 아니다. 화면이 언제 읽혔는지 설명하는 표시용 metadata이며
GIL의 논리 상태나 판정에 사용하지 않는다.

### 4.1 현재 Cycle과 Step

Monitor는 다음을 typed 값으로 보존한다.

- `CycleRef`, Cycle kind, open/closed
- parent와 `revisit_from`
- 현재 Step의 `StepRef`, kind, open/closed
- 현재 Cycle의 Step 목록과 각 Step의 상태

화면에서 `C2`, `S3`처럼 줄여 쓸 수 있지만 renderer 내부의 정체성은 typed reference다.

### 4.2 실험 정의

현재 Cycle이 Experiment이고 유일한 Define이 존재하면 다음을 원본 Define에서 읽는다.

```text
problem
success_condition
```

Interview이거나 Define이 아직 없으면 빈 Experiment를 지어내지 않는다. 부재를 정상 상태로
표현한다.

### 4.3 active lineage와 inactive Cycle

`active_lineage`는 현재 Cycle에서 `parent`만 따라 뿌리까지 간 구조적 경로다.
`revisit_from`은 lineage edge가 아니다.

활성 경로는 CycleRef 목록만이 아니다. 참조만 나열하면 직렬로 성공한 Cycle 사이에서 무엇을
이어받아 현재 실험에 왔는지 알 수 없다. 각 항목은 Step Graph를 펼치지 않는 Cycle 해상도의
선택적 투영이다.

```text
LineageCycleFacts
  cycle_ref
  kind
  state
  parent_cycle_ref?
  revisit_from_cycle_ref?
  experiment_definition?       유일한 Define에서
  report?                       Cycle Report 선택적 투영
```

현재 Cycle도 마지막 항목으로 같은 정체성을 갖지만, `current_cycle`만이 현재 Step 목록을 가진다.
과거 ancestor의 Step 목록은 `active_lineage`에 복제하지 않는다.

현재 lineage에 들지 않는 Cycle을 모두 "실패한 형제"라고 부르지 않는다. v0에서는 구조적 사실과
Report 판정을 분리해 다음처럼 표현한다.

```text
inactive cycle
  cycle_ref
  parent_cycle_ref
  revisit_from_cycle_ref?
  verdict?                 Report가 있을 때만
  handoff?                 Report가 있을 때만
  relation_to_current      abandoned | revisit_source | other
```

형제 여부는 parent가 같을 때만 유도한다. 실패 여부는 Cycle Report의 verdict에서만 읽는다.

### 4.4 revisit

두 상태를 구분한다.

- 완료된 전환: 새 Cycle의 `revisit_from`과 parent에서 출처와 목표를 읽는다.
- pending 전환: `pending_cycle_revisit`에서 실패 Cycle과 target Cycle을 읽는다.

Monitor가 ID 순서나 현재 Artifact 내용으로 revisit 관계를 추측하지 않는다.

### 4.5 handoff

닫힌 Cycle의 요약은 Cycle Report의 선택적 투영을 따른다.

- Experiment 목적과 성공 기준: 유일한 Define
- 판정의 교훈: `outcome_ref`가 가리키는 Outcome
- 판정·인수인계·다음 방향: Cycle Report

내부 Step Graph 전체를 handoff로 복제하지 않는다. 사용자가 펼치기를 요청하는 UI는 이후 같은
Snapshot의 구조적 참조에서 더 자세한 projection을 요청할 수 있지만, v0 첫 구현에는 넣지 않는다.

### 4.6 Current Will

Current Will은 현재 Existence가 지금 수행하려는 행동 한 단위다. Monitor는 다음을 보여 준다.

- `WillRef`
- objective
- next_action
- done_when
- 시작한 Existence와 Journey provenance

Active Will이 없으면 현재 Step에서 추측해 만들지 않는다. done Will 전체 시간선은 v0 기본
Monitor Snapshot에 싣지 않는다.

### 4.7 Artifact 세계

```text
world
  baseline_snapshot_ref
  state: clean | dirty | unknown
  reason?                  unknown일 때 관측 오류
  verify_can_confirm       현재 열린 Step이 Verify인지
```

관측 실패는 dirty가 아니다. `unknown`과 원래 오류의 이유를 보존한다. 파일 목록, 내부 digest,
manifest와 blob 주소는 기본 Snapshot에 포함하지 않는다.

### 4.8 다음 행동

`next_actions`는 현재 domain state와 Grammar에서 유도한다. UI가 버튼을 보여 주기 위해 새로운
전이를 발명하지 않는다.

각 행동은 최소한 다음을 가진다.

```text
kind
command?       현재 CLI에 실제 명령이 있을 때만
reason
help_ref?      Manual Router가 안정된 Topic을 제공할 때만
```

아직 구현되지 않은 Chain close, 임의 checkout, merge나 승인 동작을 가능한 행동으로 표시하지
않는다.

---

## 5. 아직 없는 Chain을 다루는 규칙

M5는 M6보다 먼저 구현된다. 따라서 v0 Monitor는 현재 Chain, Chain Report와 Chain verdict를
표시하지 않는다.

- `chain: null` 같은 가짜 자리를 공개 계약으로 만들지 않는다.
- Cycle을 임의의 Chain으로 포장하지 않는다.
- 화면 문구로 "현재 Chain"을 약속하지 않는다.
- M6에서 Chain이 실제 domain object가 된 뒤 Snapshot을 확장한다.

이것은 미래 확장을 막는 생략이 아니라, 존재하지 않는 사실을 지어내지 않는 불변식이다.

---

## 6. 조회 일관성과 잠금

한 Snapshot은 한 프로젝트 조회 구간에서 만든다.

1. 기존 Project lock을 얻는다.
2. 중단된 restore가 있다면 기존 Storage Model의 복구 절차를 먼저 따른다.
3. 검증된 Project를 읽는다.
4. Artifact 세계를 한 번 관측한다.
5. 모든 Monitor 사실을 소유한 불변 값으로 복사한다.
6. lock을 놓는다.
7. renderer와 UI는 Snapshot만 사용한다.

UI가 열린 동안 lock을 계속 쥐지 않는다. 자동 갱신은 이전 Snapshot을 수정하지 않고 새 Snapshot을
다시 만든다.

### Read-only의 정확한 뜻

Monitor는 다음을 하지 않는다.

- Node, Cycle, Will, Journey 또는 Report 생성·수정
- Snapshot 발급
- Artifact restore
- `state.yaml` 저장
- 사용자 작업 파일 수정

프로젝트를 여는 순간 이미 존재하던 중단 transaction을 복구하거나 자기 소유의 임시 파일을
회수하는 동작은 Storage Model의 원자성 복구다. 이를 Monitor의 의미론적 쓰기로 세지 않는다.
복구 뒤 만들어진 Snapshot은 복구가 끝난 일관된 상태만 보여 준다.

---

## 7. Renderer

renderer는 Snapshot의 의미를 바꾸지 않는다.

```text
MonitorSnapshot
├─ plain text
├─ structured data
├─ Markdown
└─ HTML
```

M5 구현 순서는 다음과 같다.

1. typed `MonitorSnapshot`
2. plain text reference renderer와 실제 인간 판독
3. 같은 Snapshot의 안전한 HTML Monitor
4. 자동 갱신

structured projection의 공개 wire schema와 호환성 정책은 실제 외부 소비자가 생기기 전까지
확정하지 않는다. 첫 구현의 serialization은 시험과 내부 renderer 연결을 위한 crate 내부 계약일
수 있다.

### 7.1 의미 동등성

renderer별로 다음 값이 같아야 한다.

- 현재 typed reference와 상태
- problem과 success condition
- Cycle verdict와 handoff
- revisit 관계
- Will
- world state
- next action

표현상 접기, 색, 순서와 문장 길이는 다를 수 있지만 판정과 참조는 달라질 수 없다.

### 7.2 안전한 텍스트와 HTML

Report, Will과 사용자 응답의 모든 문자열은 신뢰하지 않는 텍스트다.

- HTML renderer는 값을 escape한다.
- Report의 HTML을 실행하거나 DOM으로 삽입하지 않는다.
- Markdown을 지원하더라도 raw HTML은 허용하지 않는다.
- 외부 URL, 이미지와 script를 자동으로 불러오지 않는다.
- 로컬 경로를 명령으로 실행하지 않는다.
- 내부 `.gil` 경로와 content-addressed object 주소를 노출하지 않는다.

시각 자료 schema가 확정되기 전에는 알 수 없는 Report 필드를 텍스트로 보존할 수는 있지만,
이미지·HTML·링크로 해석해 실행하지 않는다.

### 7.3 plain text reference renderer

plain text는 임시 디버그 dump가 아니라 다른 renderer의 의미 기준이 되는 첫 인간용 표현이다.
`Debug` 출력을 그대로 보여 주거나 필드 이름을 무차별적으로 나열하지 않는다.

기본 절 순서는 다음과 같다.

```text
GIL Monitor

[현재 실험]
  Cycle과 Step
  질문
  성공 기준

[활성 경로]
  뿌리부터 현재까지의 Cycle
  각 Cycle의 종류와 상태
  닫힌 ancestor의 판정과 handoff

[지나온 갈래]                  있을 때만
  계보 밖 Cycle의 구조적 관계
  Report가 있을 때 판정과 handoff

[현재 행동]                    Active Will이 있을 때만
  objective
  next_action
  done_when

[현재 세계]
  기준 Snapshot
  clean | dirty | unknown
  unknown 이유

[다음 행동]
  실제로 지금 성공할 명령과 이유
  Help Topic이 있을 때 주소
```

현재 Cycle이 Interview이면 `[현재 실험]`이라는 거짓 제목을 쓰지 않고 `[현재 인터뷰]`로
표현한다. Define, Report, Will과 inactive Cycle이 없으면 빈 placeholder 내용을 발명하지 않는다.
다만 현재 행동이나 다음 행동이 없다는 사실이 인간의 판단에 필요하면 `없음`을 명시할 수 있다.

Cycle을 한 줄로 표시할 때 최소한 typed `CycleRef`, kind와 open/closed를 보존한다. 활성 경로의
닫힌 ancestor는 Report가 있으면 verdict와 handoff를 함께 보여 주어, 참조 목록만으로 축소하지
않는다. 현재 Step도 `StepRef`, kind와 상태를 보존한다. `revisit_from`과 parent는 같은 edge처럼
그리지 않는다.

색, terminal 폭, ANSI escape와 Unicode 도형이 없어도 절과 관계를 구분할 수 있어야 한다. 기본
renderer는 강제 줄바꿈을 하지 않고, 여러 줄 Report 값의 각 후속 줄에 같은 indentation을 준다.

`gil monitor`는 인수를 받지 않는 read-only 명령이다. 명령은 다음 순서를 지킨다.

```text
ProjectSession::open
→ session.monitor()
→ session drop / project lock 해제
→ render_monitor_text(snapshot)
```

renderer가 살아 있는 Session을 받거나 렌더링 중 Project를 다시 읽지 않는다. `gil monitor`는
HTML format 선택, watch와 브라우저 열기를 아직 제공하지 않는다.

plain text의 문장 자체를 공개 저장 schema로 보지 않는다. 그러나 절의 의미, typed reference,
판정과 다음 행동은 후속 HTML renderer와 같아야 한다.

### 7.4 안전한 standalone HTML renderer

첫 HTML renderer는 별도 server나 frontend build 없이 저장해서 바로 열 수 있는 완전한 HTML5
문서 하나를 만든다.

```rust
render_monitor_html(&MonitorSnapshot) -> String
```

HTML도 Snapshot만 입력으로 받는다. Project, Session과 작업 폴더를 다시 읽지 않는다.

문서는 다음 경계를 지킨다.

- `lang="ko"`, UTF-8, viewport metadata를 가진다.
- CSS는 바이너리가 소유한 고정된 inline `<style>` 하나만 사용한다.
- JavaScript를 싣지 않는다.
- 외부 stylesheet, font, image, iframe과 network resource를 불러오지 않는다.
- `<base>`, form, object와 embed를 만들지 않는다.
- 엄격한 Content Security Policy를 문서 자체에 명시한다.
- 사용자와 Report에서 온 문자열은 text node로 escape한다.
- 사용자 문자열을 tag name, attribute name, class, `href`, `src`나 CSS로 사용하지 않는다.
- Help Topic과 command는 실행 링크나 버튼이 아니라 `<code>`의 텍스트로 표시한다.
- Markdown과 raw HTML을 해석하지 않는다.

최초 CSP는 최소한 다음 의도를 보장한다.

```text
default-src 'none'
script-src 'none'
img-src 'none'
font-src 'none'
connect-src 'none'
object-src 'none'
base-uri 'none'
form-action 'none'
style-src 'unsafe-inline'
```

inline style은 renderer가 소유한 고정 상수만 허용하기 위한 예외다. Report 값이 style에 들어갈 수
없다.

semantic HTML을 사용한다.

```text
main
├─ header
├─ section: 현재 실험 또는 인터뷰
├─ section: 활성 경로
├─ section: 지나온 갈래        있을 때만
├─ section: 현재 행동          있을 때만
├─ section: 현재 세계
└─ section: 다음 행동
```

heading, list, description list와 code를 사용하며 색만으로 open/closed, clean/dirty/unknown,
success/failure와 active/inactive를 구분하지 않는다. 작은 화면에서도 가로 scroll 없이 읽히는
responsive layout을 사용한다. 긴 사용자 문자열과 명령은 내용 손실 없이 줄바꿈할 수 있다.

HTML의 DOM 이름과 CSS class는 v0 공개 API가 아니다. 그러나 시험은 같은 Snapshot에서 두
renderer가 다음 의미 inventory를 보존하는지 확인해야 한다.

- 모든 CycleRef와 StepRef
- Cycle kind와 상태
- Experiment problem과 success condition
- verdict와 handoff
- parent와 revisit 출처의 구분
- Current Will의 세 행동 계약 값
- world SnapshotRef와 상태
- next action의 command, reason과 Help Topic

`gil monitor --html`은 같은 조회 순서로 Snapshot을 만든 뒤 lock을 놓고 완전한 HTML 문서를
stdout에 쓴다. 기본 `gil monitor`의 plain text는 바뀌지 않는다. 파일 저장, browser 열기와 watch는
아직 제공하지 않는다.

### 7.5 인간의 Graph 이해 — inline SVG

GIL에 익숙하지 않은 사람이 Graph를 글의 목록이나 ASCII art로 이해할 것이라고 가정하지 않는다.
ASCII art는 font, 폭, 줄바꿈과 복사 과정에 따라 깨지고 공간 관계도 안정적으로 전달하지 못하므로
Human Monitor의 Graph 표현으로 사용하지 않는다.

HTML Monitor의 주 화면은 같은 `MonitorSnapshot`에서 만든 **inline SVG Graph**다. 별도 PNG를
저장하거나 외부 Graphviz 실행 파일과 frontend build를 요구하지 않는다.

```text
MonitorSnapshot
  → deterministic Graph layout
  → escaped inline SVG
  → 선택한 지점의 semantic HTML 설명
```

#### 단방향 Step DAG

Human Monitor Graph에서 **화면에 찍히는 기본 node는 Step**이다. Cycle을 큰 node로 놓고 Cycle
사이를 자유로운 2차원 선으로 연결하지 않는다. GIL의 실행은 앞으로 새 Step과 Cycle을 낳으므로,
Git Graph처럼 하나의 시간축을 따라 자라는 DAG로 표현한다.

- 기본 진행 방향은 위에서 아래다. 새로 생긴 node는 이전 node보다 아래에 놓인다.
- 의미상 과거를 참조하는 revisit도 화면에서 뒤로 향하는 edge를 만들지 않는다.
- revisit 뒤의 새 시도는 다음 시간 위치에 새 lane으로 나타난다. 어느 과거 경계에서 세계를
  이어받았는지는 lane의 출발점과 `다시 시도` 표식으로 표현한다.
- Step의 parent edge는 진행 방향을 거슬러 올라가지 않는다.
- active path는 하나의 계속되는 lane으로 읽히고, 버린 시도는 옆 lane에서 끝난다.
- 실패, success와 현재 위치는 색뿐 아니라 node shape·icon·label로 구분한다.
- 각 Step 옆에는 kind와 사람이 읽을 수 있는 짧은 요약을 둔다. typed reference는 작은 보조
  정보이며 가장 큰 label로 쓰지 않는다.

#### 위계는 node가 아니라 시각적 group이다

- Cycle은 그 안의 Step들을 감싸는 점선 경계, 배경 띠, 색상 또는 side rail로 나타낸다.
- Cycle Entry와 Exit은 필요하면 경계 표식으로 나타내되 Step보다 큰 독립 node로 만들지 않는다.
- Chain이 구현되면 여러 Cycle group을 감싸는 한 단계 바깥 group 또는 rail로 나타낸다.
- group은 Graph의 진행 방향을 바꾸지 않는다.
- 같은 Cycle의 Step은 공간적으로 연속되어 보여야 한다.
- Cycle과 Chain의 접기·펼치기는 장차 가능한 interaction이지만, interaction 계약이 없는 첫
  교정에서는 정적인 group 표현부터 검증한다.

화면은 자유 배치 graph가 아니다. lane 수는 branch 수만큼만 늘고, edge는 정해진 rail을 따라
이동한다. node를 피해 임의의 곡선을 찾는 routing보다 **일관된 시간축과 lane 문법**을 우선한다.

Graph 위나 바로 옆의 focus panel은 다음 세 의미를 가장 먼저 보여 준다.

1. 현재 질문과 성공 기준
2. `Will.next_action`과 `done_when`, 그리고 그 뒤의 GIL command
3. 현재 위치로 이어진 실패 이유·교훈·revisit·새 가설

과거 Cycle Report의 `next_direction`은 현재 행동처럼 그리지 않고 `당시 다음 방향`으로만
표현한다.

SVG도 신뢰하지 않는 Report 문자열을 받는다.

- 모든 text node를 escape한다.
- 사용자 값을 element·attribute·CSS·ID·path data로 사용하지 않는다.
- script, event handler, `foreignObject`, 외부 image·font·link를 만들지 않는다.
- 위치와 선은 renderer가 계산한 유한한 수치만 사용한다.
- Graph 크기와 node 수에 명시적 layout 상한을 두고, 넘으면 해상도를 접어 표현한다.

SVG는 `<svg role="img">`, 고정된 `title`·`desc` 연결과 의미 있는 text label을 가진다. 같은 사실의
짧은 semantic HTML 요약도 남긴다. 이는 ASCII Graph의 대체물이 아니라 화면 reader와 SVG를
보지 못하는 환경을 위한 접근성 projection이다.

DOM 구조와 좌표는 공개 API가 아니다. 그러나 desktop과 작은 화면에서 실제 screenshot을
검사하고, active path·failure branch·revisit·current Step이 겹치거나 잘리지 않는지 확인한다.

#### 구현이 고정한 경계

layout과 SVG 출력을 가른다. 시험은 **좌표가 아니라 typed node·edge 목록**을 잰다.

```text
MonitorSnapshot → VisualGraph   무엇을 어디에 놓을지 (Project를 다시 읽지 않는다)
VisualGraph     → inline SVG    정해진 자리를 그린다
```

기존 첫 구현의 `Cycle = 큰 node` layout은 2026-09-05 인간 검토에서 폐기 대상으로 판정됐다.
Cycle node 셋과 두 종류의 edge를 자유로운 2차원 경로로 연결하자 작은 예시에서도 선이 서로
감싸고 교차해 진행 방향을 읽기 어려웠다. 다음 구현은 같은 `VisualGraph` 분리를 유지하되,
`Step = node`, `Cycle/Chain = group`, `time = 한 방향`, `branch = lane`으로 layout 의미를 교체한다.

표시 상한은 유지하되 Step 중심으로 다시 정의한다. 현재 위치와 현재로 이어진 전환을 먼저 남기고
오래된 구간은 `이전 Step N개` 또는 `이전 Cycle N개` group으로 접는다. **접힌 것은 삭제되지 않고**
아래 상세 기록에 그대로 있다. 활성 여부와 시간 순서를 단순한 ID 크기 비교로 추정하지 않고,
검증된 구조와 append-only 발급 순서를 사용한다.

Step 옆의 짧은 설명은 Report에서 투영할 수 있다. 이 문자열은 반드시 escape하고 정해진 글자 수와
줄 수 안에서 시각적으로 줄이며, 원문 전체는 semantic detail에 보존한다. 사용자 문자열을 SVG의
element·attribute·CSS·ID·좌표나 path data로 사용하지 않는다.

`marker`와 `url(#…)` 참조를 쓰지 않고 화살촉도 계산된 path로 그린다. 참조가 하나도 없는
그림이 위 규칙을 지키기 쉽다.

---

## 8. 자동 갱신

자동 갱신은 transport와 UI 기술을 정하는 문제가 아니라 같은 조회를 반복하는 규칙이다.

- 갱신마다 완전한 새 Snapshot을 만든다.
- Snapshot 사이 diff는 화면 최적화일 뿐 진실 공급원이 아니다.
- 파일 watcher event 하나를 GIL 사건으로 간주하지 않는다.
- watcher가 event를 합치거나 놓쳐도 다음 전체 조회로 수렴해야 한다.
- 갱신 실패 시 마지막 Snapshot을 현재 사실처럼 표시하지 않는다. stale 표시와 오류를 보여 준다.

### 8.1 v0 transport — loopback Monitor server

v0의 지속 관찰은 GIL 바이너리 안의 작은 loopback HTTP server로 시작한다.

```text
gil monitor --serve
  → 127.0.0.1의 OS가 고른 빈 포트에 bind
  → 예측하기 어려운 session path를 한 번 발급
  → URL을 stdout에 표시
  → 사용자가 browser에서 연다
```

browser를 자동으로 열지 않는다. 파일을 프로젝트 안에 만들지 않고, 별도 frontend build와 설치를
요구하지 않는다. process가 끝나면 server와 메모리 cache도 함께 사라진다.

### 8.2 주소와 요청 경계

- `127.0.0.1`에만 bind한다. `0.0.0.0`, LAN 주소와 public interface에 bind하지 않는다.
- port는 기본값을 고정하지 않고 OS에 맡긴다.
- session path는 OS CSPRNG에서 얻은 최소 128-bit entropy를 canonical URL-safe 글자로 표현한다.
- 난수를 안전하게 얻지 못하면 server를 열지 않는다.
- 첫 Unix 구현은 `/dev/urandom`을 사용한다. 이 통로가 없는 platform에서는 약한 난수로
  물러서지 않고 server 시작을 거절한다. cross-platform entropy provider는 배포 대상이
  넓어질 때 별도로 정한다.
- URL의 token은 process memory에만 있고 `.gil`, config와 history에 저장하지 않는다.
- 출력한 URL의 exact path만 Monitor 문서를 돌려준다.
- 틀린 token과 모르는 path는 같은 404를 돌려주며 Project 사실을 포함하지 않는다.
- `Host`는 출력한 `127.0.0.1:<port>`와 정확히 맞아야 한다. 다른 Host는 거절한다.
- GET과 HEAD만 받는다. 상태를 바꾸는 method와 request body를 받지 않는다.
- request는 `HTTP/1.1`의 origin-form 하나만 받으며 각 줄은 정확한 CRLF로 끝나야 한다.
- header 이름은 HTTP token 문법이어야 하고 obs-fold, 제어 문자와 중복된 `Host`·`Content-Length`를
  거절한다. 알 수 없는 정상 header는 의미를 부여하지 않고 건너뛸 수 있다.
- request line, header 크기와 읽기 시간을 제한한다.
- v0는 connection을 짧게 닫으며 장기 streaming connection을 만들지 않는다.

응답은 최소한 다음 header를 가진다.

```text
Content-Type: text/html; charset=utf-8
Cache-Control: no-store
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
X-Frame-Options: DENY
Cross-Origin-Resource-Policy: same-origin
```

HTML의 CSP는 §7.4와 같다. 틀린 요청의 오류 본문에는 project path, Report, token과 내부 오류를
넣지 않는다.

### 8.3 두 polling을 구분한다

browser가 화면을 새로 받는 주기와 Artifact 세계를 다시 관측하는 주기는 같은 것이 아니다.

```text
browser refresh
  → server의 마지막 검증 결과를 읽음          값싼 화면 polling

filesystem change hint 또는 reconciliation deadline
  → 새 ProjectSession
  → monitor()
  → 완전한 새 MonitorSnapshot                 비싼 사실 관측
```

매 browser refresh마다 프로젝트 전체를 관측하지 않는다. `world_state()`는 안정된 관측을 위해
Artifact 파일을 두 번 훑으므로 짧은 고정 주기로 반복하면 프로젝트 크기에 비례한 지속 비용을
만든다.

filesystem watcher는 **갱신이 필요할 수 있다는 hint**만 준다. event의 경로, 종류와 순서를 GIL
사건이나 사실로 저장하지 않는다. 여러 event를 짧게 debounce한 뒤 `monitor()` 전체 조회가 실제
상태를 확정한다.

watcher가 event를 놓치거나 합쳐도 수렴하도록 느린 주기의 reconciliation deadline을 둔다.
정확한 debounce와 reconciliation 시간은 성능 parameter이며 domain 계약이 아니다. 시험에서는
가짜 clock과 change signal을 주입할 수 있어야 한다.

#### 감시 범위 — Monitor 자신의 잡음만 덜어낸다

관측은 `.gil` 안을 만진다. 그 사건을 hint로 되받으면 **관측이 관측을 부르는 고리**가 생긴다.
그래서 감시는 프로젝트 루트를 재귀로 보되 다음 한 줄로 거른다.

```text
루트 .gil/state.yaml       hint 로 받는다 — Graph 의 논리 상태가 여기서 확정된다
루트 .gil/ 그 밖의 전부     받지 않는다 — lock · tmp · object store · restore 임시
루트의 일반 파일            hint 로 받는다 — Artifact 세계
더 깊은 곳의 .gil/         hint 로 받는다 — 제외 대상이 아니라 관측 거절 사유다(Artifact §3.4)
```

이 filter는 **Project의 사실을 판정하지 않는다.** 「다시 볼 필요조차 없는 Monitor 자신의
잡음」 하나만 덜어낸다. 그 밖의 판정은 전부 다음 전체 조회의 몫이다.

### 8.4 cache는 진실 공급원이 아니다

server process는 마지막 성공 Snapshot을 메모리에 둘 수 있다. 이 값은 화면 응답 비용을 줄이는
파생 cache일 뿐 Graph에 쓰지 않고 다음 판정의 입력으로 사용하지 않는다.

상태는 다음 셋이다.

```text
Current(snapshot)                 마지막 갱신이 성공함
Stale(snapshot, error, failed_at) 새 관측이 실패해 이전 값임을 명시
Unavailable(error)                성공한 Snapshot이 아직 없음
```

- stale 화면은 최상단에서 **이 내용은 최신이 아니다**라고 명시한다.
- 갱신 오류와 마지막 성공 관측 시각을 표시한다.
- stale Snapshot의 각 절을 현재 사실처럼 무표시로 재사용하지 않는다.
- 오류 문구도 신뢰하지 않는 text로 escape한다.
- Project lock 경쟁, 일시적 Artifact 변화와 관측 오류가 나면 dirty로 바꾸지 않는다.
- 실패 뒤 change hint가 없어도 retry 기한이 지나면 다시 시도한다. 기한 뒤의 browser refresh는
  상태기계를 깨우는 계기가 될 수 있지만, 기한 전의 refresh는 재관측을 일으키지 않는다.
- 성공하면 이전 cache를 통째로 새 Snapshot으로 교체한다. 부분 merge하지 않는다.

### 8.5 갱신과 잠금

한 갱신은 기존 조회 경계를 그대로 따른다.

```text
ProjectSession::open
→ monitor()
→ owned MonitorSnapshot
→ Session drop과 lock 해제
→ cache 교체
→ HTML render
```

server가 ProjectSession, lock과 `.gil` file handle을 요청 사이에 보관하지 않는다. browser가 열려
있다는 이유로 다른 GIL 명령을 막지 않는다.

### 8.6 화면 갱신

v0는 JavaScript 없이 전체 문서를 다시 받는다. server가 만든 고정 refresh metadata는 같은
session URL로만 이동하며 user data에서 URL을 만들지 않는다. standalone `gil monitor --html`
문서에는 refresh를 넣지 않는다.

화면의 접기, 선택과 scroll 같은 UI state는 아직 저장하지 않는다. 이후 필요해져도 GIL Graph와
Report에 저장하지 않는 presentation state다.

### 8.6.1 watcher가 서지 못할 때

watcher는 latency를 줄이는 가속기이지 진실의 공급원이 아니다. 없어도 reconciliation
deadline이 수렴을 보장한다. 그러므로 **watcher가 서지 못해도 server는 연다.**

그러나 조용히 자동 갱신이 되는 척하지 않는다. 화면 최상단에 **변화를 스스로 알아채지
못한다**를 명시하고, 그 실행에서는 느린 주기로만 다시 관측한다. 명령의 stdout도 같은 사실을
한 줄로 말한다.

server를 아예 거절하지 않는 이유는 두 가지다. 읽기 전용 화면의 정확성이 watcher에 걸려 있지
않고, 일부 파일 시스템에서는 watcher가 정상적으로 실패한다. 가속기 하나 때문에 화면 전체를
빼앗는 것은 사람에게 더 나쁜 거래다.

### 8.7 server 종료

- foreground process로 실행하고 종료 방법을 명확히 표시한다.
- Ctrl-C는 시험이 밟는 것과 **같은 종료 경로**로 들어온다. 신호 처리기는 원자값 하나를
  세우고, 정리는 평범한 코드가 한다. 사람이 밟는 길과 시험이 밟는 길을 가르지 않는다.
- 정상 종료와 비정상 종료 모두 Project 상태를 바꾸지 않는다.
- derived HTML, token과 cache를 프로젝트에 남기지 않는다.
- server가 종료되면 URL은 더 이상 응답하지 않는다.

### 8.8 기본 사용자 표면 — Agent Host 안의 Monitor

loopback server는 인간 사용자의 기본 진입점이 아니다. GIL의 직접 사용자는 Agent이고, 인간은
이미 Codex·Claude Desktop 같은 Agent Host 안에서 그 Agent와 협업한다. 따라서 이상적인 최종
경로는 **현재 대화와 같은 Host 안에서 열리는 지속형 Monitor 표면**이다. 현재 Host가 그 수명을
제공하지 않는 동안에는 하나의 Tauri Companion을 v0 기본 경로로 사용한다.

```text
Human
  → Agent Host의 chat
      ├─ Agent → typed GIL action → GIL Core
      └─ Human → embedded Monitor → MonitorSnapshot
```

사람은 세션마다 server를 실행하거나 browser의 port·capability URL을 기억하지 않는다. Tauri
Companion은 한 번 실행한 창에서 Project를 명시적으로 등록·전환한다. Host가 persistent embedded
UI를 지원하면 Agent의 receipt, 상태 chip 또는 명시적 「여정 보기」에서 같은 창의 panel이나 PiP
surface를 열고, 현재 대화가 가리키는 Project와 Current Existence를 Host가 아는 범위 안에서
이어받는다. 어느 UI도 cwd나 최근 폴더를 추측해 다른 Project를 고르지 않는다.

Host별 UI API는 GIL의 domain 계약이 아니다. GIL은 다음 중립 경계만 소유한다.

```text
GIL Core
  → owned MonitorSnapshot
  → Host UI adapter
  → interactive presentation state

Human intent
  → Host UI adapter
  → typed GIL action request
  → GIL Core
  → receipt 또는 typed refusal
```

이 경계의 wire model, presentation intent, on-demand detail과 호환성 규칙은
`GIL Host UI Model v0.1`이 소유한다. 이 문서의 `MonitorSnapshot`은 내부 read model이며 Host에
그대로 직렬화하지 않는다.

#### 표현 동작과 의미 동작을 가른다

다음은 presentation state만 바꾸며 Graph·Journey·Will·Artifact를 바꾸지 않는다.

- pan, zoom, 현재 위치로 이동
- Step 선택과 detail panel 열기
- Cycle 접기·펼치기
- 현재 경로·실패 갈래·Interview 표시 filter
- 화면의 임시 정렬과 viewport 상태

다음은 GIL의 의미 상태를 바꾸므로 UI가 직접 수행하거나 `.gil`을 수정하지 않는다.

- 승인과 거절
- Node·Cycle 열기와 닫기
- revisit
- restore
- 다음 실험 시작

이 동작들은 Host adapter가 typed GIL action으로 요청하고, GIL Core의 기존 gate·transaction과
receipt를 그대로 지난다. 화면의 button이 domain 규칙을 복제하거나 우회하지 않는다.

#### 전달과 갱신

- Host는 한 번에 완전한 `MonitorSnapshot` 하나를 UI에 전달한다.
- 이후의 event나 channel은 **다시 읽을 때가 되었다는 hint**일 뿐 Graph 사건이 아니다.
- UI는 partial event를 기존 Snapshot에 합쳐 새 사실을 만들지 않는다.
- 선택·접기·filter는 Host 또는 UI process의 수명이 짧은 presentation state이며 `.gil`에 쓰지
  않는다.
- Project가 바뀌면 이전 Project의 Snapshot과 presentation state를 현재 화면에 섞지 않는다.
- Host가 지속형 embedded UI를 제공하지 않으면 하나의 Tauri Companion으로 물러난다. loopback
  browser는 개발·진단용 최후 fallback이다. fallback이 기본 계약을 더 약하게 만들거나 다른 사실을
  보여서는 안 된다.

첫 embedded Monitor는 관찰 전용이다. write action button은 Human Checkpoint의 domain 계약과
Host의 명시적 승인 경계가 모두 생긴 뒤에만 추가한다.

---

## 9. 시각 자료와 인간 승인

두 기능은 M5 첫 구현의 선행 조건이 아니다.

### 시각 자료

이 절의 시각 자료는 **Report가 참조하는 사용자 표·차트·이미지·화면 캡처**를 뜻한다. §7.5의
Graph SVG는 이미 검증된 Monitor 구조를 renderer가 그리는 UI이므로 별도 Artifact resource가
아니다.

Report media는 caption, alt text, provenance와 안전한 resource reference schema를 먼저 별도
확정해야 한다. 그 전에는 Report의 임의 필드를 media로 실행하지 않는다.

### 인간 승인

milestone, stepwise와 autonomous mode는 화면 표현만으로 생기지 않는다. 승인 상태와 전이가
domain model에 들어온 뒤 Monitor는 그것을 읽어 표시한다. Monitor 자체가 승인 결과를 저장하거나
CLI를 우회해 상태를 바꾸지 않는다.

따라서 M5 v0은 관찰 전용으로 닫고, Human Checkpoint의 쓰기 동작은 해당 domain 계약이 생기는
단계로 미룬다.

---

## 10. 검사 가능한 불변식

```text
monitor_reads_state_yaml_directly == false
monitor_parses_cli_output == false
world_observation_count_per_snapshot == 1
monitor_semantic_writes == 0
active_lineage_edges == parent_edges_only
revisit_from_is_not_a_lineage_edge
unknown_world_is_not_dirty
unimplemented_chain_facts_rendered == 0
renderer_verdicts_are_equal == true
raw_report_html_executed == false
```

필수 시험:

1. 동일한 Project에서 status와 Monitor의 current Cycle·Step·world state가 같다.
2. 실패 Cycle에서 revisit한 뒤 active lineage와 revisit source를 혼동하지 않는다.
3. pending revisit 상태를 새 Cycle이 이미 열린 것처럼 표시하지 않는다.
4. 버려진 가지와 active lineage를 ID 크기로 판정하지 않는다.
5. Artifact 관측 실패를 unknown으로 표시한다.
6. Monitor 조회 전후 Graph·Journey·Will·Snapshot registry와 작업 파일이 같다.
7. HTML 특수문자와 script 모양 Report가 실행되지 않고 텍스트로 보인다.
8. renderer 셋이 같은 typed reference와 verdict를 보존한다.
9. 아직 없는 Chain과 승인 mode를 출력하지 않는다.
10. 자동 갱신 실패 시 이전 값을 최신으로 가장하지 않는다.

---

## 11. M5 구현 조각

### M5-A0 — Monitor Snapshot

- typed `MonitorSnapshot`
- 검증된 Project loader만 사용
- 한 번의 world observation
- CLI 핵심 사실과 정합성 시험
- semantic read-only 증거

### M5-A1a — plain text reference renderer

- 순수 함수 `render_monitor_text(&MonitorSnapshot)`
- 한 번의 Snapshot을 만들고 Project lock을 놓은 뒤 renderer 호출
- `gil monitor` 공개 명령으로 실제 출력을 읽을 수 있음
- active lineage, inactive branch와 revisit의 구조적 구분
- 현재 Experiment 정의, Cycle handoff와 Current Will
- world와 실제로 밟을 수 있는 next action
- 색, terminal 폭과 Unicode 도형에 기대지 않는 구분

### M5-A1b — 안전한 HTML renderer

- A1a와 같은 Snapshot만 입력으로 받음
- Report와 Will의 모든 문자열 escape
- raw HTML·script·외부 resource 자동 로드 없음
- renderer 의미 동등성 시험

### M5-A2 — 지속 관찰

M5-A2는 다음 세 조각으로 구현한다. 공개 `--serve` 명령은 세 조각이 모두 닫힌 뒤 연다.

#### M5-A2a — 갱신 상태기계

- `Current` · `Stale` · `Unavailable` 캐시 상태
- 변경 힌트, debounce, 느린 reconciliation과 실패 뒤 재시도 결정
- 관측 함수를 주입해 실제 재관측 횟수를 셀 수 있는 순수한 갱신 엔진
- stale/error의 안전한 HTML 표현

이 조각은 HTTP 서버, OS watcher와 새 외부 의존성을 넣지 않는다. 브라우저 요청과 파일 시스템
사건을 연결하기 전에 "언제 비싼 Snapshot을 다시 만드는가"를 독립적으로 고정한다.

#### M5-A2b — 안전한 loopback server

- `127.0.0.1` 임의 port와 일회성 capability path
- Host · method · request 크기 · timeout 검증
- 보안 response header와 cache 금지
- 브라우저 refresh에는 마지막 검증된 cache만 제공

#### M5-A2c — 변화 감지 연결과 실사용 검증

- OS watcher를 변화의 힌트로 연결
- debounce와 reconciliation deadline을 실제 시간에 연결
- 누락·중복 사건, 관측 실패, 종료 뒤 무변경 검증
- 새 Snapshot이 나타나는 실제 프로젝트 시나리오

### M5-A3 — 실제 사용 검증

- 참여하지 않은 사용자가 30초 안에 현재 실험을 설명
- 실패 가지와 활성 가지를 혼동하지 않음
- CLI를 보지 않고 다음 행동을 설명

#### 2026-09-02 판독 실험 1 — 실패

프로젝트 설계자에게 CLI·Story·Context를 숨기고 Monitor 화면만 30초 동안 보여 주었다. 화면은
실패한 첫 Experiment, 그 실패에서 원래 Interview로의 revisit, 새 Experiment와 열린 Verify 및
Active Will을 모두 담고 있었다.

| 물음 | 관측 |
|---|---|
| 지금 실험과 성공 기준 | 현재 문제는 정확히 찾았지만 성공 기준은 답하지 못했다 |
| 앞선 실패와 현재 갈래로 온 이유 | 화면만으로 알기 어렵다고 답했다 |
| 지금 바로 할 일 | 과거 Cycle Report의 `open_child`를 현재 행동으로 오인했다 |

따라서 세 합격 조건은 모두 아직 충족되지 않았다. 정보가 없어서가 아니라 **현재 사실, 과거의
방향, 작업 행동과 GIL 명령의 시각적 우선순위가 평평하기 때문**이다. 사용자의 이해 실패로
돌리지 않고 renderer의 정보 구조 실패로 기록한다.

다음 renderer 실험은 ASCII나 긴 글 목록이 아니라 §7.5의 SVG Graph와 focus panel을 사용한다.
focus panel은 아래 순서를 둔다.

```text
[지금]
  현재 질문
  성공 기준

[지금 할 일]
  Active Will.next_action
  완료 조건
  그 일이 끝나면 실행할 GIL 명령

[왜 여기 왔는가]
  실패한 갈래의 질문 → 실패 이유 → 전환 → 현재 가설

[지나온 기록]  기본적으로 접거나 뒤로 낮춘다
```

- 현재 질문과 성공 기준은 떨어뜨리지 않는다.
- `Will.next_action`은 **작업 행동**, Monitor의 command는 **그 행동 뒤의 GIL 동작**으로
  구분한다. 둘 중 하나를 다른 하나로 대체하지 않는다.
- ancestor Cycle의 `next_direction`은 현재 행동처럼 표시하지 않는다. 필요하면 `당시 다음
  방향`으로 이름 붙이고 현재 영역보다 낮춘다.
- revisit은 참조 두 개만 보여 주지 않고 `무엇이 실패했는가 → 무엇을 배웠는가 → 현재 어떤
  가설로 바뀌었는가`라는 한 묶음으로 투영한다.
- 전체 기록량을 줄이지 못하더라도 첫 30초에 읽어야 할 정보량은 줄인다.
- ASCII art는 Graph renderer의 fallback으로도 사용하지 않는다. SVG를 표시할 수 없는 환경은
  기존 semantic text projection을 사용한다.

시각 자료와 Human Checkpoint는 별도 후속 조각이다.

---

## 12. 현재 결정하지 않는 것

- Host별 embedded UI API와 packaging 방식
- 여러 Agent Host 사이에서 presentation state를 이어받는 방식
- Unix 밖의 platform을 위한 entropy provider와 배포 지원 범위
- 외부에 공개할 JSON schema와 versioning
- 전체 history의 검색과 필터
- Chain projection
- 시각 자료 저장 schema와 media type
- 인간 승인 상태와 write command
- 여러 프로젝트를 동시에 한 화면에 비교하는 방식
- 원격 Monitor와 인증
- 사용자별 화면 설정의 저장 위치

---

## 13. 핵심 문장

> **Monitor는 GIL의 또 다른 진실 공급원이 아니라, 검증된 원본에서 한 번에 읽은 인간용
> 관찰 Snapshot이다.**

> **화면 기술보다 먼저 사실의 경계와 부재를 정의한다. 아직 존재하지 않는 Chain, 승인과 시각
> 자료를 UI가 지어내지 않는다.**

> **인간의 이상적인 Monitor는 Agent와 대화하는 Host의 지속형 surface에 열린다. 현재 Host가 그
> surface를 제공하지 않으므로 v0의 기준 구현은 여러 Project를 전환할 수 있는 하나의 Tauri
> Companion이며, browser는 개발·진단용 fallback이다.**
