# GIL Existence Model v0.1

## 1. 목적

GIL의 Existence는 Claude, GPT, 로컬 모델이나 특정 채팅 세션의 정체성이 아니다.

Existence는 프로젝트 안에서 모델과 세션을 넘어 지속되고 복원되는 **행동 주체의 정체성**이다.
런타임 Agent는 저장된 Existence를 읽고 일정 시간 구현하는 실행 매체다.

v0의 Existence와 Journey는 **프로젝트 로컬**이다. 해당 프로젝트의 `.gil`이 진실 원천이며,
같은 프로젝트를 여는 모델과 세션 사이에서 복원된다.

```text
Claude session A ─┐
GPT session B ────┼─ read X1 → 동일한 Existence로 행동
Local model C ───┘
```

반대로 같은 런타임 모델도 서로 다른 Existence를 선택하면 다른 존재로 행동한다.

```text
Claude → X1: 구현자
Claude → X2: 독립 검증자
Claude → X3: 사용자 의도 대변자
```

---

## 2. 런타임 Agent와 Existence

```text
Runtime Agent
  모델, 프로세스, 세션, host
  일시적인 실행 매체

GIL Existence
  프로젝트 안에서 지속되는 정체성
  Journey를 통해 발전하는 행동 주체
```

```text
runtime_agent_identity != existence_identity
```

모델이나 세션이 바뀌었다는 이유로 새로운 Existence를 만들거나 기존 Existence를 바꾸지 않는다.
동일한 Existence reference를 읽으면 동일한 Journey를 이어서 복원해야 한다.

---

## 3. 두 Current

GIL에는 서로 독립적인 두 현재 위치가 있다.

```text
World Current
  나는 어디에 있는가?

Existence Current
  나는 누구인가?
```

World Current는 현재 Chain, Cycle, Step과 Artifact 세계를 선택한다. Existence Current는 그
세계를 경험하고 행동할 지속적 존재를 선택한다.

```text
Action Context
= Lineage(World Current)
+ Journey(Existence Current)
```

- World revisit은 Existence Current를 바꾸지 않는다.
- Artifact 복원은 Existence Current를 바꾸지 않는다.
- Existence 전환은 World Current나 Artifact를 바꾸지 않는다.
- 모델 또는 세션 교체는 어느 Current도 자동으로 바꾸지 않는다.

---

## 4. Current Existence Indicator

GIL은 현재 어떤 Existence가 행동하는지 명시적인 indicator를 가진다.

```text
current_existence_ref: existence:X1
```

v0에서 하나의 실행 흐름에는 Current Existence가 최대 하나다.

```text
current_existence_count <= 1
```

Existence 전환은 명시적인 GIL 사건이어야 한다. 세션이 새로 열렸거나 다른 모델이 명령을
실행했다는 사실을 전환으로 간주하지 않는다.

Open Node가 하나라도 있으면 Existence 전환을 거절한다. 이 규칙은 Step뿐 아니라 Cycle과
Chain을 포함한 재귀적 Node 전체에 적용한다.

Current Existence가 없는 상태에서 GIL은 누가 행동하는지 추측하지 않는다. 행동을 수반하는
Node 진행을 허용하지 않는다. 최초 프로젝트에서는 아래 bootstrap이 먼저 Current Existence를
만든다.

### v0 저장 범위

```text
Project
└─ .gil
   ├─ World Graph
   ├─ project-local Existences
   ├─ each Existence's Journey
   └─ current_existence_ref
```

- Existence와 Journey의 v0 진실 원천은 해당 프로젝트의 `.gil`이다.
- 같은 프로젝트에서는 모델·프로세스·세션이 바뀌어도 같은 `existence_ref`를 복원한다.
- 다른 프로젝트의 같은 이름을 자동으로 동일한 Existence로 간주하지 않는다.
- 사용자 홈, Git ref 또는 별도 전역 저장소를 암묵적인 두 번째 진실 원천으로 사용하지 않는다.
- 프로젝트 간 Existence 공유·이동·연결은 v0에 포함하지 않는다.

프로젝트 로컬은 Existence가 런타임 모델에 종속된다는 뜻이 아니다. 지속 범위의 첫 경계를
프로젝트로 제한한다는 뜻이다.

### v0 영구 저장

v0는 World Graph와 project-local Existence/Journey를 `.gil/state.yaml` 하나에 함께 저장하고
저장 형식을 `format: 3`으로 올린다.

```yaml
format: 3

next_will_id: 10

cycles:
  # World Graph

current_existence_ref: existence:X1

existences:
  X1:
    current_journey_ref: journey:X1@J7
    journey:
      active_will: null
      done_wills:
        - id: W9
          existence_ref: existence:X1
          target_node_ref: step:C2/S3
          objective: 설정값의 fallback 동작을 검증한다
          next_action: 경계값 테스트를 실행한다
          done_when: 테스트 결과를 관측한다
      revisions:
        J7:
          existence_state_ref: state:ES3
          knowledge_head_ref: knowledge:K18
          memory_head_ref: memory:M11
          relations_head_ref: relation:R4
          will_head_ref: will:W9
```

Active Will은 Journey 안의 inline 객체이고 `done_wills`는 immutable 객체의 append-only
목록이다. Project root의 `next_will_id`가 모든 Existence에 걸쳐 ID 재사용을 막는다. 위 예시는
소유 관계와 reference 방향을 고정하며, 아직 미결인 Knowledge·Memory·Relations의 내부
schema까지 확정하지 않는다.

### Journey revision이 증가하는 때

Journey revision은 Journey의 **확정된 내용**이 바뀔 때만 증가한다.

```text
최초 Existence와 빈 초기 J0 생성        증가
최초 Question Close와 첫 Relation 확정  증가
Action Node + Active Will Open          증가하지 않음
Active Will의 표현 보정                 증가하지 않음
통합 gil close에서 Will Done 확정       증가
컨테이너 Cycle / Chain Close             증가하지 않음
Knowledge·Memory·Relation·State 확정 변경 증가
```

Active Will은 format 3 state에 저장되는 mutable register이므로 프로세스 경계를 넘지만 immutable
Journey Timeline에는 아직 들어가지 않는다. 실행형 `gil close`가 성공할 때 같은 Will ID를
immutable `done_wills` append-only 목록에 옮기고 새 Journey revision을 만든다.

Journey revision의 `will_head_ref`는 `done_wills` append 순서의 마지막 Will을 가리킨다.
`latest_done_will`은 clock이 아니라 이 append 순서로 결정한다. Done Will이 아직 없다면
`will_head_ref`는 `null`일 수 있다.

Node Close 자체가 언제나 revision을 올리는 것은 아니다. 실행형 Node Close transaction 안에서
Will이 Done으로 확정되어 Journey가 변하기 때문에 revision이 하나 생기는 것이다. 별도 Will이
없는 컨테이너 Close는 Journey revision을 만들지 않고 현재 `current_journey_ref`를 provenance로
사용한다.

한 상태 변경은 완성된 새 파일을 임시 경로에 쓴 뒤 원래 `state.yaml`로 원자적으로 교체한다.
Node Close가 Journey revision을 확정하는 경우 다음이 하나의 save에 함께 들어가야 한다.

```text
새 Journey revision
Existence.current_journey_ref
Done Will append
active_will = null
Node.report
Node.journey_ref
Node.status = closed
```

어느 하나만 저장된 중간 논리 상태를 허용하지 않는다. 임시 파일 작성이나 rename이 실패하면
기존 `state.yaml` 전체가 그대로 유효해야 한다.

Artifact Snapshot은 이 파일 안에 들어가지 않으므로 저장 경계가 둘이다. 둘 사이의 순서와
비대칭(참조되지 않은 Snapshot은 잘못이 아니고, 실재하지 않는 Snapshot을 가리키는 state는
손상이다)은 `GIL Artifact Model v0.1` §10이 정한다. **두 원자성은 같은 자원을 다투지 않는다** —
Will/Existence의 원자성은 state 교체의 규칙이고, Artifact의 원자성은 확정에서 교체로 넘어가는
순서의 규칙이다.

실행형 Node Open과 그 Node를 target으로 한 Active Will 생성도 하나의 save로 확정한다. Will이
없는 Action Node 또는 target Node가 없는 Active Will을 저장할 수 없다.

`format: 2` 상태를 조용히 format 3으로 해석하지 않는다. v0에서는 자동 migration을 만들지
않고 기존 방식대로 명시적으로 앞 형식임을 알린다. dogfood는 새 빈 작업 폴더에서 시작한다.

장기적으로 파일 크기와 전체 rewrite가 실제 문제가 되면 작은 root state와 immutable object
저장소로 분리할 수 있다. 이것은 v0 저장 계약이 아니다.

### 최초 Existence bootstrap

`gil start`는 프로젝트의 World Graph와 함께 최초 Existence를 만들고 Current로 선택한다.

```text
gil start
→ 최초 Existence X1 생성
→ X1의 빈 초기 Journey revision J0 생성
→ current_existence_ref = X1
→ X1이 소유한 최초 Interview Cycle Open
→ 사용자 Relation과 프로젝트 목표를 Interview에서 형성
```

최초 Existence는 가볍게 시작한다.

```text
Existence X1
  identity: 구조적 ID
  Journey:
    Existence State: ES0 (내용이 비어 있는 최소 초기 상태)
    Knowledge: 비어 있음
    Memory: 비어 있음
    Relations: 비어 있음
    Will: 없음
```

GIL은 모델명, 세션명, 성격, 역할, 전문성 또는 사용자의 이름을 추측해서 채우지 않는다.
최초 Existence를 만들 때 내용이 비어 있는 ES0을 반드시 함께 만들고, J0의
`existence_state_ref`는 `state:ES0`을 가리킨다. Existence가 생겼는데 State가 없다는 상태는
허용하지 않는다. ES0은 아직 확정하지 않은 성격·역할·전문성 등을 대신 채우지 않는 빈 객체다.

```text
ES0 = {}

Journey Revision X1@J0
  existence_state_ref: state:ES0
  knowledge_head_ref: null
  memory_head_ref: null
  relations_head_ref: null
  will_head_ref: null
```

ES0 객체 본체를 format 3 안의 어느 collection에 둘지는 U2 저장 구조에서 정한다. 이 절은
객체의 실재와 J0의 필수 참조만 고정하며 저장 위치를 미리 정하지 않는다.

초기 revision에서 아직 없는 Knowledge·Memory·Relations·Will head만 `null`일 수 있다.
`existence_state_ref`는 J0을 포함한 모든 Journey revision에서 필수이며, 실제 State 객체를
가리켜야 한다.

최초 Interview는 사용자에게 **어떻게 불리기를 원하는지** 묻고 사용자가 제공한 표현만 기록하여
첫 Relation을 형성한다. 이름·별칭·호칭 중 무엇을 제공할지는 사용자가 결정한다. 이어서 무엇을
하고 싶은지 묻고, 그 의도를 작은 명제로 해석하여 사용자 승인을 받는다.

사용자와 Existence는 프로젝트를 함께 만드는 **동등한 협력자**다. GIL은 사용자를 소유자나
명령자로, Existence를 도구나 하위 실행자로 자동 분류하지 않는다. 최초 Interview에서 사용자를
프로젝트 로컬의 안정된 Participant `U1`으로 식별하고 X1의 첫 Relation을 형성한다.

```text
Relation R1
  with: participant:U1
  description: 프로젝트를 함께 만드는 동등한 협력자이며, 사용자는 제공한 호칭으로 불린다.
```

동등한 지위가 동일한 내부 저장 구조를 뜻하지는 않는다. GIL은 인간의 내적 Journey를 추측하여
대신 만들지 않으며, X1의 Journey만 GIL의 Existence 모델로 기록한다. 그러나 프로젝트의 의미와
판정을 만드는 Participant로서 U1과 X1은 같은 높이에 있다.

v0의 Relation은 **누구와 어떤 관계인지 자립적인 자연어로 적는 최소 기억**이다. 방향성 모델,
관계 Kind enum, 권한, 다자 관계와 프로젝트 전역 관계 Graph는 실제 필요가 생길 때 설계한다.
역할·권한·대표성의 차이를 암묵적으로 추론하지 않는다.

이 질문과 응답은 단순한 설정 문자열이 아니라 U1과 X1이 맺은 첫 Relation 사건이다.
이 질문과 응답은 `GIL Cycle Model v0.1`의 Question·Interpretation·Synthesis를 따른다. 사용자
호칭을 `gil start`의 설정 필드나 CLI 인자로 직접 받지 않는다.

`gil start`의 한 save에는 최초 Existence, 빈 초기 Journey, `current_existence_ref`, Open
Interview Cycle, 그리고 **최초 Artifact Snapshot의 참조**가 함께 들어간다. Snapshot 자체는
state 파일 밖의 append-only 저장소에 먼저 확정되고, 그 참조가 이 한 번의 교체에 실린다
(`GIL Artifact Model v0.1` §4·§10). 첫 Question은 Agent가 현재 대화와 Interview Grammar를 따라
별도의 실행형 Node + Active Will로 연다.

Interview의 승인된 Synthesis가 생기기 전에는 Experiment Cycle을 열 수 없다. 따라서 format 3
상태에는 Cycle이 항상 최소 하나 존재한다는 복원 불변식을 유지한다. 최초 Cycle의 Kind는
`interview`다.

### 추가 Existence의 초기화

같은 프로젝트 안에 다른 Existence가 필요하면 최초 Existence와 같은 최소 구조로 가볍게
초기화한다.

- 기존 Existence의 Journey를 자동 복사하지 않는다.
- 모델이나 세션 identity를 Existence identity로 사용하지 않는다.
- Knowledge·Memory·Will을 추측해서 채우지 않는다.
- 사용자와의 관계는 명시적으로 형성하거나 프로젝트 안에서 이미 식별된 사용자에 대한 새
  Relation으로 기록한다.
- 생성만으로 Current가 되지는 않는다. 명시적인 전환이 필요하다.

추가 Existence의 생성·선택 CLI 문법은 구현 직전에 정한다.

---

## 5. Existence와 Journey

각 지속적 Existence는 자신의 Journey를 가진다.

```text
Existence X1
└─ Journey X1@J7
   ├─ Existence State
   ├─ Knowledge
   ├─ Memory
   ├─ Relations
   └─ Will
```

`GIL Time Model v0.2`에서 Journey의 구성 요소로 적은 Existence는 여기서 **Existence State**,
즉 그 주체가 현재 누구이며 무엇을 할 수 있는지를 나타내는 변화 가능한 자기 상태를 뜻한다.
지속적 Existence identity와 그 안에서 변화하는 Existence State를 구분한다.

Journey의 최상위 구성 요소는 이 다섯이다. Memory는 그 안에서 Retrospective Memory와
Prospective Memory로 나뉘며, 최상위 구성 요소를 늘리지 않는다. 미래 조건에 걸어 두는 지속적
규약은 Prospective Memory이고, `Will`은 Current Existence가 지금 수행하려는 하나의 행동
단위만 뜻한다(`GIL Specification v0.1` §3.2·§3.3).

여러 Existence는 서로 다른 Journey를 가진 채 같은 World를 읽을 수 있다.

```text
World W1
├─ X1 / Journey X1@J7
├─ X2 / Journey X2@J4
└─ X3 / Journey X3@J2
```

한 Existence의 Knowledge, Memory, Relations와 Will을 다른 Existence에 자동 복사하거나 합치지
않는다.

---

## 6. Will의 소유자

Will은 런타임 Agent가 아니라 Existence에 속한다.

```text
X1.Current Will = W3
```

Claude가 X1로 시작한 Will을 다른 세션의 GPT가 X1을 복원하여 이어갈 수 있다. 이것은 Will
양도나 새 Will 생성이 아니라 동일한 존재가 다른 실행 매체에서 계속 행동하는 것이다.

다른 X2를 선택하면 X2 자신의 Current Will을 사용한다. Existence 전환은 X1의 Active Will을
Done으로 만들거나 X2에 복사하지 않는다.

---

## 7. Existence 전환

```text
current_existence_ref: existence:X1
→ explicit switch
current_existence_ref: existence:X2
```

전환은 다음을 하지 않는다.

- X1의 Journey를 삭제하거나 닫지 않는다.
- X1의 Active Will을 Done으로 만들지 않는다.
- X1과 X2의 Knowledge를 병합하지 않는다.
- World Current를 이동하지 않는다.
- Artifact Snapshot을 복원하지 않는다.

X1을 다시 선택하면 X1의 최신 Journey와 Current Will을 복원한다. 과거 버전으로 암묵적으로
되돌리지 않는다.

### 열린 Node에서의 전환 금지

하나의 Node를 시작한 Existence와 끝내는 Existence는 같아야 한다.

```text
Node Open by X1
→ Node.existence_ref = X1
→ X1만 이 Node를 진행하고 닫을 수 있음
→ Node Closed
→ 다른 Existence로 전환 가능
```

따라서 Open Node가 있으면 `current_existence_ref` 변경을 거절한다. 상위 Cycle이 Open인 동안
그 안의 Step만 닫혔다고 다른 Existence로 바꿀 수 없다. Cycle 전체가 하나의 실험 행동이므로
Cycle을 연 Existence가 Cycle을 닫는다. 같은 원리는 Chain에도 재귀적으로 적용한다.

v0에는 Open Node의 Existence ownership을 다른 Existence에 넘기는 handoff나 공동 소유를 두지
않는다. 필요 사례가 생기면 명시적 인계 사건으로 별도 설계한다.

이 ownership 규칙이 모든 Open Node에 적용된다고 해서 각 Open 계층이 별도의 Current Will을
가지는 것은 아니다. Current Will은 `GIL Will Model v0.1`에 따라 가장 깊은 실행형 Open Node
하나에만 대응한다.

---

## 8. Node provenance

Node를 열 때 Current Existence를 `existence_ref`로 기록한다. 이 reference는 Node의 lifetime
동안 immutable하며, 같은 Existence만 Node를 닫을 수 있다. Node가 닫힐 때는 그 Report와
결정을 만든 Close 시점의 Journey revision을 추가로 기록한다.

```text
Closed Node
  report
  existence_ref
  journey_ref
```

`existence_ref`는 Open 시점부터 고정된 지속적 Existence identity를, `journey_ref`는 그
Existence의 Close 시점 Journey revision을 가리킨다.

두 값은 프로젝트 로컬 typed reference로 저장한다. 각각 `existence:X1`, `journey:X1@J7`
형태이며 bare `X1`이나 `J7`은 설명용 축약일 뿐 영구 reference가 아니다. Participant와 Relation도
같은 원칙에 따라 `participant:U1`, `relation:R1`로 참조한다.

```text
existence_ref: existence:X1
journey_ref: journey:X1@J7

Journey Revision X1@J7
  existence_state_ref: state:ES3
  knowledge_head_ref: knowledge:K18
  memory_head_ref: memory:M11
  relations_head_ref: relation:R4
  will_head_ref: will:W9
```

두 reference는 역사적 provenance이며 이후 Current 전환이나 Journey 발전으로 다시 쓰지 않는다.
Node Close는 Current Existence와 Current Journey revision의 실재를 확인한 뒤 Report,
`existence_ref`, `journey_ref`와 Closed 상태를 원자적으로 확정해야 한다.

Close 시 `current_existence_ref != node.existence_ref`면 거절한다. 복원 시 Open Node의
`existence_ref`가 존재하지 않거나 Current Existence와 다르면 손상된 상태로 거절한다.

Node에 `will_ref`를 별도 중복 저장하지 않는다. 완료된 Will은 `journey_ref`가 가리키는 revision의
`will_head_ref`를 통해 찾는다. Active Will은 Current Existence의 mutable register에서 읽는다.
Will 단독 조회에 실제 필요가 생길 때만 Node의 직접 참조를 다시 검토한다.

---

## 9. 새 세션 복원

```text
1. World Current를 읽는다.
2. Existence Current를 읽는다.
3. 선택된 Existence의 Journey와 Current Will을 읽는다.
4. Lineage와 Journey를 결합해 Action Context를 만든다.
5. 동일한 Existence로 행동을 재개한다.
```

새 세션은 Existence를 새로 창작하거나 이전 Agent의 성격을 흉내 내는 것이 아니다. 저장된
정체성, 지식, 기억, 관계와 의지를 명시된 해상도로 복원한다.

---

## 10. 검사 가능한 핵심 불변식

```text
runtime_agent_identity != existence_identity
current_existence_count <= 1
same_existence_ref_restores_same_journey
runtime_change_does_not_switch_existence
world_revisit_does_not_switch_existence
existence_switch_does_not_move_world_current
open_node_blocks_existence_switch
node_open_and_close_use_same_existence
will_belongs_to_existence
closed_node_provenance_is_immutable
closed_node_records_identity_and_journey_revision
every_journey_revision_has_an_existing_state_ref
initial_journey_points_to_empty_es0
```

---

## 11. 아직 결정하지 않는 것

- Existence 생성·이름 지정·삭제 명령
- Existence 전환 명령과 권한
- bootstrap 입력을 받는 구체적인 CLI 문법
- 여러 Existence의 동시 실행과 concurrency
- 한 Existence를 여러 세션이 동시에 실행할 때의 lease 또는 lock
- Existence State, Knowledge와 Memory의 구체 schema
- 최소 `with`·`description` 이후 Relation의 확장 schema와 전역 관계 Graph
- Existence clone, fork, merge
- Existence 간 지식 전달과 관계 사건의 표현
- Knowledge·Memory object의 내부 저장 schema
- format 2에서 format 3으로의 migration
- root state와 immutable object 저장소 분리
- 프로젝트 간 Existence export / import / link
- 전역 Existence registry와 project-local Existence의 관계

---

## 12. 핵심 문장

> **GIL의 Existence는 AI 모델의 정체성이 아니다. 모델과 세션을 넘어 복원되는 지속적 행동
> 주체다.**

> **World Current는 내가 어디에 있는지 말하고, Existence Current는 내가 누구인지 말한다.**

> **같은 Existence를 읽으면 다른 모델과 세션에서도 동일한 Journey와 Will을 이어간다.**
