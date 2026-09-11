# GIL Host UI Model v0.1

> 상태: Draft  
> 범위: GIL Core의 Monitor 사실을 Agent Host와 지속형 Desktop Companion의 공용 UI에 전달하는 계약  
> 비범위: 특정 Host SDK, Tauri component 구현, SVG 좌표, domain write action

---

## 1. 목적

GIL의 인간 사용자는 Codex·Claude Desktop 같은 Agent Host 안에서 Agent와 협업한다. 그러나
Monitor는 대화가 길어져도 밀려나지 않고 계속 보여야 한다. Host가 지속형 panel이나 PiP surface를
제공하면 그 안에 싣고, 제공하지 않으면 하나의 Tauri Companion이 같은 UI를 지속형 창으로 제공한다.
어느 경우에도 GIL의 내부 Rust 타입이나 특정 Host API에 결합하지 않아야 한다.

이 문서는 다음 두 경계를 고정한다.

1. GIL Core가 Host UI에 넘기는 **버전 있는 읽기 모델**
2. 사람이 화면을 탐색할 때 발생하는 **표현 의도**

Graph·Journey·Will·Artifact를 바꾸는 의미 동작은 이 문서의 표현 의도가 아니다.

---

## 2. 소유권과 구조

```text
GIL domain state
  → owned MonitorSnapshot                 내부 read model
  → pure projection
  → MonitorViewV1                         Host 중립 wire model
  → shared UI bundle                      layout·interaction·accessibility
  → Host adapter                          수명·전달·현재 Project 연결
```

- `MonitorSnapshot`은 GIL Core의 내부 타입이다. 직접 직렬화하지 않는다.
- `MonitorViewV1`은 좌표가 없는 사실 계약이다.
- 공용 UI bundle이 DAG layout과 interaction을 한 번만 구현한다.
- Host adapter는 같은 UI를 싣는 얇은 수명·전달 경계다. Host마다 Graph layout을 다시 만들지 않는다.
- 특정 Host가 지속형 embedded UI를 제공하지 못하면 같은 `MonitorViewV1`을 Tauri Companion에
  싣는다. loopback browser는 개발·진단용 최후 fallback이다. 어느 표면도 다른 사실 계약을 만들지
  않는다.

---

## 3. `MonitorViewV1`

논리 구조는 다음과 같다.

```text
MonitorViewV1
├─ schema_version
├─ captured_at_unix_ms
├─ current
│  ├─ existence_ref
│  ├─ journey_ref
│  ├─ cycle_ref
│  └─ step_ref
├─ timeline[]
│  └─ TimelineCycleV1
├─ current_will
├─ world
└─ next_actions[]
```

### 3.1 최상위 칸

| 칸 | 형 | 규칙 |
|---|---|---|
| `schema_version` | integer | v1에서는 정확히 `1` |
| `captured_at_unix_ms` | integer | UTC Unix epoch 이후 밀리초, `0..2^53-1` |
| `current` | object | 현재 Existence·Journey·Cycle·Step |
| `timeline` | array | 이 Journey가 발급한 모든 Cycle, 발급 순서 |
| `current_will` | object 또는 `null` | 현재 행동 단위 |
| `world` | object | 기준 Snapshot과 clean·dirty·unknown |
| `next_actions` | array | 지금 실제로 성공할 수 있는 동작만 |

`current.step_ref`는 Cycle 경계에 서 있으면 `null`이다. 나머지 최상위 칸은 생략하지 않는다.

### 3.2 `TimelineCycleV1`

```text
TimelineCycleV1
├─ cycle_ref
├─ kind
├─ state
├─ relation_to_current
├─ parent_cycle_ref
├─ revisit_from_cycle_ref
├─ experiment_definition
├─ report
└─ steps[]
```

- `relation_to_current`는 `active_path | revisit_source | abandoned | other` 중 하나다.
- 네 관계는 상호 배타적이다. 여러 boolean으로 표현하지 않는다.
- `parent_cycle_ref`와 `revisit_from_cycle_ref`는 서로 다른 관계다. revisit을 parent edge로
  바꾸지 않는다.
- `experiment_definition`은 Experiment의 유일한 Define에서 읽은 `problem`과
  `success_condition`이다. 없으면 `null`이다.
- `report`는 닫힌 Cycle의 선택적 투영이다. 열려 있으면 `null`이다.
- `steps`는 그 Cycle이 만든 순서 그대로이며 비어 있어도 `[]`다.

`report`가 있을 때의 구조는 다음과 같다.

```text
CycleReportV1
├─ verdict
├─ handoff_summary
├─ outcome_lesson
└─ next_direction
   ├─ action
   ├─ reason
   └─ target_cycle_ref
```

`outcome_lesson`과 `next_direction`은 없으면 `null`이다. `next_direction`이 있을 때도 `reason`과
`target_cycle_ref`는 각각 없을 수 있다. 이 구조는 내부 `CycleReportFacts`의 선택적 투영보다
새 사실을 만들지 않는다.

Host wire에는 내부 `MonitorSnapshot.active_lineage`와 `inactive_cycles`를 싣지 않는다. 같은 Cycle을
여러 목록으로 보내면 UI가 어느 쪽을 진실로 삼을지 다시 결정해야 한다. `timeline` 하나가 Step DAG를
그리는 유일한 Cycle 목록이다.

### 3.3 `StepV1`

각 Step은 다음 네 사실만 초기 View에 싣는다.

```text
step_ref · kind · state · summary
```

`summary`는 Monitor read model이 정한 Report 원문의 대표 칸이며, 없으면 `null`이다. wire model은
이를 자르거나 다시 요약하지 않는다. 줄임표와 줄바꿈은 UI의 표현 책임이다.

`StepKindV1`은 `question | interpretation | synthesis | define | hypothesis | verify | analysis |
outcome`만 가진다. `cycle_entry`와 `cycle_exit`는 Step kind가 아니며 Step 목록이나 상세에 나타나지
않는다. Cycle 경계에 서 있다는 사실은 `current.step_ref: null`과 Cycle의 상태·가능한 다음 행동으로
표현한다. 내부 Snapshot이 경계를 Step처럼 싣고 있으면 투영은 이를 정상 Step으로 표시하지 않고
명시적으로 거절한다.

전체 Step Report는 초기 View에 넣지 않는다. 선택한 Step의 상세는 §7의 `NodeDetailV1`으로 요청한다.

### 3.4 `current_will`, `world`, `next_actions`

`current_will`은 `will_ref`, `objective`, `next_action`, `done_when`, `target_step_ref`,
`existence_ref`, `journey_ref`를 가진다.

`world`는 `baseline_snapshot_ref`, `state`, `reason`, `verify_can_confirm`을 가진다.

- `state`는 `clean | dirty | unknown`이다.
- `reason`은 `unknown`의 원인이 있을 때 그 원문이며, 그 밖에는 `null`이다.
- 파일 목록·manifest 주소·blob 주소·digest는 내보내지 않는다.

각 `next_actions` 항목은 `kind`, `step_kind`, `cycle_kind`, `command`, `reason`, `help_ref`를
가진다. 명령과 도움말이 없으면 각각 `null`이다. 아직 구현되지 않은 전이를 가능성처럼 싣지
않는다.

- `kind`는 `close_step | open_step | close_cycle | open_cycle | open_branch | revisit | restore`다.
- Step 동작은 `step_kind`에 대상 Step kind를 보존하고 `cycle_kind`는 `null`이다.
- Cycle 동작은 `cycle_kind`에 대상 Cycle kind를 보존하고 `step_kind`는 `null`이다.
- `revisit`과 `restore`는 두 대상 kind가 모두 `null`이다.
- `command`는 사람이 실행할 글자이지 동작의 구조를 판정하는 값이 아니다.

따라서 값을 지닌 내부 `ActionKind`를 합성 문자열로 폭발시키거나 인자를 버리지 않는다.

---

## 4. Canonical JSON v1

Host 경계의 canonical encoding은 UTF-8 JSON이다. Host가 같은 모양의 native object를 직접
전달해도 의미는 이 JSON 계약과 같아야 한다. 이는 MCP나 특정 SDK를 요구하지 않는다.

구현은 typed `MonitorViewV1` 투영과 JSON encoder를 독립된 조각으로 나눌 수 있다. typed 투영만
있는 과도기에는 이 절의 의미를 바꾸지 않으며, JSON 호환 완료를 주장하지 않는다. transport를
나중에 고르더라도 외부 byte encoding이 필요해지는 순간에는 이 canonical JSON을 사용한다.

- Graph·Journey·Artifact의 typed reference는 명세의 canonical 문자열로 쓴다. 예:
  `cycle:C2`, `step:C2/S3`. Manual의 `TopicId`는 이 불변식의 typed reference가 아니라 주소이며,
  View에서는 표시와 조회에 필요한 canonical 문자열만 보존한다.
- typed View 안의 닫힌 낱말은 **View 전용 enum**으로 표현한다. 내부 domain enum을 그대로
  재사용하지 않고 사용자 문자열로도 대신하지 않는다.
- JSON에서 enum은 이 문서가 정한 ASCII lowercase snake_case 문자열로 쓴다.
- optional object·scalar key는 생략하지 않고 `null`로 쓴다.
- collection key는 생략하지 않고 빈 경우 `[]`로 쓴다.
- 문자열은 원문 전체를 보존한다. HTML escape·Markdown 변환·요약·truncation을 하지 않는다.
- 배열의 순서는 의미다. renderer가 ID나 제목으로 다시 정렬하지 않는다.
- 객체 key 순서는 의미가 아니다.
- 숫자로 시간 순서를 추정하지 않는다. `timeline`과 `steps`의 배열 순서를 따른다.
- 같은 `schema_version`의 소비자는 모르는 object key를 무시할 수 있다. 그러나 모르는 enum 값이나
  지원하지 않는 `schema_version`은 추측해 그리지 않고 명시적으로 거절한다.

View 전용 enum을 `&'static str`로 대신하지 않는다. 그 형식은 출력에는 편하지만 외부 JSON을
typed View로 되읽는 계약을 표현하지 못한다. enum의 JSON 문자열 표현은 encoder 경계의 일이고,
typed View 자체는 닫힌 값의 집합을 보존한다.

### 4.1 Grammar 지원 범위

`MonitorViewV1`의 닫힌 enum은 함께 실린 **GIL Grammar v0.1**의 어휘를 지원한다. 현재 CLI는 이
Grammar를 사용한다. 라이브러리 안에서 별도 `RuleSet`을 주입할 수 있다는 사실만으로 그 확장값이
Host UI v1의 공개 어휘가 되지는 않는다.

주입된 Grammar가 v1에 없는 verdict나 direction action을 실제 Snapshot에 만들면 투영은 Cycle
Report를 `null`로 숨기거나 `other`로 바꾸지 않고 **View 전체를 명시적으로 거절**한다. 오류에는
해당 `cycle_ref`와 읽지 못한 원문을 보존한다. 새 어휘를 Host UI가 지원하기로 결정할 때는 View의
호환성 규칙에 따라 enum과 schema version을 함께 검토한다.

`MonitorSnapshot → MonitorViewV1` 투영은 순수 함수다. 파일·Project·clock을 다시 읽거나 잠금을
추가로 잡지 않는다. `captured_at_unix_ms`도 Snapshot이 이미 가진 관측 시각에서 만든다.

---

## 5. 좌표가 없는 계약

다음은 `MonitorViewV1`에 들어가지 않는다.

- x·y 좌표, lane 번호, 폭·높이
- SVG path, HTML, CSS class
- 접힘 여부, 선택된 Step, viewport와 zoom
- 색·아이콘·문자열 길이 제한
- Host panel ID나 browser URL

이 값은 Project의 사실이 아니라 공용 UI의 파생 표현이다. 같은 View가 넓은 panel, 좁은 inline
surface, 접근성용 목록에서 서로 다르게 보여도 가리키는 Step·Cycle·관계는 같아야 한다.

---

## 6. Presentation Intent v1

초기 interaction은 다음 표현 의도만 가진다.

| intent | 필요한 값 | 효과 |
|---|---|---|
| `select_step` | `step_ref` | Step을 선택하고 상세 요청의 대상을 정한다 |
| `clear_selection` | 없음 | 선택을 지운다 |
| `focus_current` | 없음 | 현재 Step 또는 Cycle 경계로 viewport를 옮긴다 |
| `collapse_cycle` | `cycle_ref` | Cycle 안의 Step을 접는다 |
| `expand_cycle` | `cycle_ref` | 접힌 Cycle을 펼친다 |
| `set_filters` | `FilterStateV1` | active path·failed branch·Interview의 표시를 바꾼다 |
| `reset_view` | 없음 | 임시 선택·접기·filter·viewport를 기본값으로 돌린다 |

이 의도는 공용 UI 안에서 처리하는 수명이 짧은 presentation state다.

- `.gil`에 저장하지 않는다.
- Report·Journey·Memory·Will로 승격하지 않는다.
- GIL action receipt처럼 가장하지 않는다.
- 다른 Agent Host가 반드시 이어받아야 할 상태가 아니다.
- 없는 Step이나 Cycle을 가리키면 UI는 의도를 버리고 최신 View를 유지한다.

pan과 zoom은 renderer 내부의 연속적인 viewport 상태라 wire intent 종류로 고정하지 않는다.

`FilterStateV1`은 `show_active_path`, `show_failed_branches`, `show_interviews` 세 boolean을 모두
가진다. key를 생략해 이전 값을 암묵적으로 유지하지 않는다. filter는 대상을 Graph에서 삭제하지
않고 화면에서만 감춘다. 현재 선택이 감춰지면 선택도 함께 해제한다.

### 6.1 Step DAG의 기준 표현

2026-09-11 인간 판독 시제품 검토에서 다음 표현을 v0 Companion의 기준으로 확정했다. 이 규칙은
`MonitorViewV1`의 사실을 바꾸지 않는 공용 UI의 presentation 계약이다.

1. Graph의 기본 단위는 **Step**이다. 모든 Step은 작은 원형 node로 표시한다. 선택한 Step도 node
   자체를 카드 크기로 키우지 않고 선택 강조만 더한다.
2. Step은 발급 시간 순서에 따른 서로 다른 행에 하나씩 놓인다. 같은 Cycle의 Step과 순차 자식
   Cycle은 같은 열을 유지한다. 실패 뒤 형제 Cycle처럼 실제 형제가 생길 때만 생성 순서에 따라
   오른쪽의 새 열을 쓴다.
3. 형제 분기 edge는 **항상 오른쪽**으로 갈라진다. 출발점에서 오른쪽으로 짧게 분기한 뒤 새 열을
   따라 진행하며, 공간이 부족하다는 이유로 왼쪽 열을 선택하거나 왼쪽으로 우회하지 않는다. 필요한
   오른쪽 여백은 layout이 먼저 확보한다. 필요 이상으로 길게 휘어 Graph를 가로지르지 않는다.
4. revisit은 생성 edge와 구분되는 점선이며 **항상 왼쪽**으로 되돌아간다. 완료된 전환에서 새 Cycle의
   `revisit_from_cycle_ref`는 **되돌아간 목표가 아니라 출발하게 만든 실패 Cycle**이고,
   `parent_cycle_ref`가 **실제로 되돌아간 목표 Cycle**이다. 따라서 점선은 `revisit_from` 실패
   Cycle의 마지막 Step 왼쪽에서 출발해 parent Cycle의 마지막 Step, 즉 화면에서 표현 가능한 Exit
   경계로 왼쪽 corridor를 따라 향한다. 같은 열의 revisit도 오른쪽으로 물러서지 않는다. 왼쪽 공간이
   부족하면 방향을 바꾸지 않고 Graph의 왼쪽 gutter를 늘린다. 화살촉은 parent 쪽 도착점을 명시한다.
   새 Cycle의 첫 Step에서 실패 Cycle로 향하는 선을 그리면 관계를 반대로 표현한 것이므로 금지한다.
5. Step kind는 색으로 보조 구분하되 색만으로 뜻을 전달하지 않는다. Cycle은 Step 묶음을 감싸는
   점선 경계와 이름으로 표시한다.
6. 정확히 하나의 Step을 선택한다. 선택한 node 옆에는 짧은 요약 카드를 띄우고, node 중심에서
   카드까지 굵고 반투명한 화살표를 직접 연결한다. 카드는 pointer event를 가로채 node 선택을
   막지 않는다.
7. 요약 카드는 Graph 안의 위치 관계를 설명한다. 전체 Report는 별도의 detail inspector에 계속
   표시하며, 요약 카드가 detail을 대신하지 않는다.
8. 펼친 Cycle의 우측 상단에는 접기 control을 둔다. 접으면 Cycle 안의 Step을 숨기고 약간 큰 원형
   Cycle node 하나로 바꾼다. 그 원형 node를 누르면 원래 Step 묶음으로 다시 펼친다.
9. Cycle을 접으면 빈 행을 그대로 남기지 않는다. 이후 Cycle과 Step을 위로 재배치하고 생성 edge,
   revisit edge, 선택 요약 카드와 연결 화살표도 새 좌표에서 다시 계산한다. 따라서 Cycle 수와 Step
   수가 커져도 접힌 Graph의 정보 밀도가 실제로 높아진다.
10. 접기·펼치기, 선택과 재배치는 presentation state다. `.gil`, Report, Journey, Memory, Will 또는
    `MonitorViewV1`에 기록하지 않는다.

Cycle을 접어도 Cycle의 존재, 순서, 부모·형제·revisit 관계를 삭제하지 않는다. 접힌 원은 같은
Cycle의 축약 표현이며, 펼치기는 원래 View 사실을 다시 보여 주는 동작이다.

---

## 7. `NodeDetailV1`

초기 View는 Graph를 읽는 데 필요한 낮은 해상도만 싣는다. 사용자가 Step을 선택했을 때 Host
adapter는 같은 Project scope에서 canonical `StepRef` 하나로 상세를 요청한다.

```text
NodeDetailV1
├─ schema_version: 1
├─ step_ref
├─ cycle_ref
├─ kind
├─ state
└─ report
   └─ fields[]
      ├─ name
      └─ value
```

- `report`는 저장된 Report의 이름과 값을 **이름순으로** 보존한 목록이며, 열려 있으면 `null`이다.
  현재 `Report`의 canonical 순서가 이름순이고 삽입·저장 순서는 기록되지 않는다.
- 닫힌 Step의 `report.fields`는 `{ "name": string, "value": string }` 객체의 배열이다. JSON
  object의 key 순서에 기대지 않고 배열 순서로 이름순 계약을 보존한다. 빈 Report를 닫힌 Report로
  가장하지 않으며, domain이 허용한 실제 Report만 투영한다.
- field 이름과 값은 원문이다. UI가 아는 이름만 고르는 whitelist나 renderer용 label을 적용하지
  않는다.
- Cycle Entry와 Exit는 Step이 아니므로 `NodeDetailV1`의 조회 대상이 아니다. 그런 `StepRef`는
  다른 대상을 추측하지 않고 `not_found`다.
- UI는 임의의 `.gil/state.yaml` 경로를 받아 직접 읽지 않는다.
- 요청한 Step이 현재 Project에 없으면 v1은 `not_found`로 답하고 다른 Step을 추측하지 않는다.
- Project가 바뀌었는지는 Host adapter가 scope identity로 먼저 가른다. 서로 다른 Project의 요청을
  현재 Project에 보내지 않는다.
- 상세 조회도 read-only이며 domain state와 Artifact 세계를 바꾸지 않는다.

Report media의 resource 계약은 아직 없으므로 v1 상세가 임의 HTML·script·외부 resource를
실행하지 않는다.

---

## 8. 갱신과 stale 상태

Host는 최초에 완전한 `MonitorViewV1` 하나를 전달한다. 이후 watcher나 Host channel은 다음 의미만
가진 hint를 보낼 수 있다.

> 이 Project의 사실이 바뀌었을 수 있으니 완전한 View를 다시 요청한다.

- hint는 Node·edge·Report 사실을 담지 않는다.
- UI는 partial event를 기존 View에 합쳐 Graph 사실을 만들지 않는다.
- 새 View가 오기 전까지 기존 View를 마지막으로 확인된 상태로 표시할 수 있다.
- Project scope가 바뀌면 이전 View와 detail을 즉시 폐기한다.
- refresh 실패를 `dirty`나 빈 Graph로 바꾸지 않는다. 마지막 View와 조회 실패를 구분한다.

---

## 9. Host Adapter의 책임

Host adapter는 다음만 책임진다.

1. 현재 대화가 명시적으로 가리키는 Project scope 연결
2. View와 detail의 전달 및 수명 관리
3. refresh hint를 받으면 완전한 View 재조회
4. 공용 UI bundle을 Host panel 또는 inline surface에 탑재
5. 지원하지 않는 schema를 사람에게 명시적으로 표시

Host adapter는 다음을 하지 않는다.

- `.gil` 직접 파싱·수정
- Cycle 관계·lane·요약 재계산
- domain gate 복제
- 최근 폴더나 cwd를 추측해 Project 선택
- Host별로 다른 Graph 의미 구현

초기 embedded Monitor는 read-only다. 승인·open·close·revisit·restore 같은 버튼은 별도의 Human
Checkpoint와 typed action 계약이 확정될 때까지 제공하지 않는다.

### 9.1 Desktop Companion adapter

Host가 지속형 surface를 제공하지 않는 동안 v0의 기준 adapter는 **하나의 Tauri Companion**이다.

- Companion process와 창은 Project나 Agent session마다 새로 만들지 않는다.
- 하나의 창에서 여러 GIL Project를 명시적으로 등록하고 전환한다.
- 각 Project는 canonical root와 stable scope identity로 구분한다.
- Project를 바꾸면 이전 View·detail·presentation state를 현재 Project에 섞지 않고 폐기하거나
  Project별 임시 상태로 격리한다.
- 현재 선택한 Project만 foreground 해상도로 관찰한다. 등록되었다는 이유만으로 모든 Project를
  계속 비싸게 재관측하지 않는다.
- 최근 Project 목록, 마지막 선택과 창 위치는 Companion 설정이다. `.gil`의 Graph·Journey·Memory가
  아니며 Project Artifact에도 포함하지 않는다.
- Companion은 `.gil/state.yaml`을 직접 해석하지 않고 GIL의 검증된 read API 또는 canonical
  `MonitorViewV1` adapter만 사용한다.
- Companion이 떠 있지 않아도 GIL의 의미 동작과 저장은 정상 동작한다.

Tauri는 v0 packaging 결정이지 wire 계약이 아니다. 장차 Agent Host가 지속형 panel을 제공하면 같은
UI bundle과 View/detail 계약을 그 adapter에 싣고, Tauri를 필수 설치에서 다시 내릴 수 있다.

### 9.2 2026-09-08 Host surface 실측

Codex Desktop의 Plugin UI에서 fixture 기반 GIL Companion을 열고
`requestDisplayMode({ mode: "pip" })`를 버튼과 초기 자동 요청 두 경로로 실행했다. 두 경우 모두 API
호출은 가능했지만 Host가 보고한 실제 `displayMode`는 `inline`이었다. 따라서 다음을 확정한다.

1. Codex inline Plugin UI는 공용 UI bundle과 interaction의 시제품·회귀 표면으로 유지한다.
2. 현재 Codex Host에서 PiP를 지속형 Monitor의 전제로 삼지 않는다.
3. 같은 세션마다 loopback server를 새로 띄우는 browser 경로를 기본 UX로 삼지 않는다.
4. 지속 관찰의 v0 기준 구현은 Tauri Companion이다.

이 판정은 Codex가 앞으로 PiP를 영원히 지원하지 않는다는 주장이 아니다. capability가 생기면 adapter
시험을 다시 수행하며, GIL Core와 `MonitorViewV1`은 바꾸지 않는다.

---

## 10. 보안과 격리

- View의 모든 문자열은 data다. HTML·Markdown·명령으로 실행하지 않는다.
- UI는 Project 밖의 경로를 요청하거나 표시를 근거로 파일을 열지 않는다.
- 한 Project의 View·detail·presentation state를 다른 Project와 섞지 않는다.
- browser fallback의 capability URL과 loopback 검증은 Monitor Model의 기존 계약을 따른다.
- Host가 가진 더 넓은 권한은 GIL UI의 권한이 아니다.

---

## 11. 호환성

- `schema_version`은 wire 의미의 판 번호다. 저장 format 번호와 다르다.
- key 추가처럼 기존 의미를 바꾸지 않는 확장은 v1 안에서 가능하다.
- key 제거·형 변경·enum 의미 변경·배열 순서 의미 변경은 새 schema version을 요구한다.
- 내부 Rust 타입과 파일 배치는 공개 계약이 아니므로 wire 의미를 보존하면 바꿀 수 있다.
- fallback과 모든 Host adapter는 같은 fixture에 대해 의미상 같은 View를 받아야 한다.

---

## 12. 시험 가능한 불변식

1. 같은 `MonitorSnapshot`은 Host 종류와 무관하게 같은 `MonitorViewV1`을 만든다.
2. 투영은 추가 관측·저장·잠금을 하지 않는다.
3. wire에는 `timeline`만 있고 `active_lineage`·`inactive_cycles` 중복 목록은 없다.
4. Cycle과 Step의 배열 순서는 내부 read model의 발급 순서와 같다.
5. Graph·Journey·Artifact의 모든 typed reference는 canonical 문자열로 왕복한다.
6. optional key와 collection key의 모양은 상태에 따라 사라지지 않는다.
7. 긴 summary와 Report 값은 wire에서 잘리지 않는다.
8. 좌표·SVG·HTML·presentation state가 wire에 없다.
9. presentation intent 전후 `.gil`, Journey, Will, Artifact 세계가 같다.
10. 선택한 Step만 `NodeDetailV1`으로 읽고 초기 View에는 전체 Report가 없다.
11. 현재 Project에 없는 detail 요청은 `not_found`이며 다른 Node로 물러서지 않는다.
12. update hint만으로 화면의 Graph 사실이 바뀌지 않는다.
13. 모르는 schema·enum은 조용히 추측해 그리지 않는다.
14. 공용 fixture를 Host surface와 fallback에서 읽었을 때 Step·Cycle·관계가 같다.
15. 같은 Cycle의 Step은 같은 열을 유지하고, 실제 형제 Cycle만 새 열을 사용한다.
16. Cycle 접기 뒤 숨겨진 행만큼 이후 node가 재배치되며 edge와 선택 카드가 새 좌표를 따른다.
17. 선택 요약 카드의 연결 화살표는 선택한 Step 또는 접힌 Cycle node에서 시작한다.
18. 완료된 revisit 점선은 `revisit_from` Cycle의 마지막 Step에서 parent Cycle의 마지막 Step으로
    향하며, 새 Cycle에서 `revisit_from` Cycle로 향하지 않는다.
19. 형제 생성 edge의 첫 분기 방향은 항상 오른쪽이고, revisit edge의 첫 이동과 corridor는 항상
    왼쪽이다. viewport나 현재 열 위치 때문에 두 방향을 서로 바꾸지 않는다.

---

## 13. 아직 정하지 않는 것

- Codex·Claude Desktop이 장차 제공할 지속형 UI SDK와 packaging 방법
- 공용 UI bundle의 구체 framework와 배포 단위
- Tauri Companion과 GIL Core 사이 View/detail transport의 구체 선택
- GIL Grammar v0.1 밖의 사용자 정의 Grammar를 Host UI에서 지원하는 방식
- semantic zoom, minimap, 검색과 대형 Graph virtualization
- presentation state를 Host 재시작 뒤 복원할지 여부
- 같은 Project 안에서 View가 갱신된 뒤의 detail 요청까지 식별하는 `view_token` 또는 revision.
  v1 첫 구현은 이를 추측하지 않고 없는 Step에 `not_found`만 답한다
- Report media의 안전한 resource reference
- Human Checkpoint와 domain write action UI
- 등록 Project가 매우 많을 때 background 관찰·알림 정책

이 항목은 `MonitorViewV1`의 사실 의미를 바꾸지 않는 범위에서 후속 명세가 정한다.

---

## 14. 핵심 문장

> **GIL Host UI 계약은 Graph를 그린 결과가 아니라 그릴 수 있는 사실을 전달한다. 좌표와 선택은
> UI의 임시 상태이고, Project의 사실은 오직 GIL Core가 만든 버전 있는 View에서 온다.**

> **지속형 surface가 없는 Host에 Monitor의 수명을 억지로 맡기지 않는다. v0 Companion은 한 번 뜬
> 창에서 여러 Project를 명시적으로 전환하며, Host가 그 수명을 제공하게 되면 같은 계약을 옮긴다.**
