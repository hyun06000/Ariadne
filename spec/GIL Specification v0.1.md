# GIL Specification v0.1

**GIL — Git for Language Models**

## 1. 목적

GIL은 Language Model과 인간이 함께 수행하는 작업을 위한 버전 관리 체계다.

기존 버전 관리 시스템은 주로 파일의 변경을 추적한다. 그러나 AI가 실질적인 작업의 상당 부분을 수행하는 환경에서는 인간과 결과물 사이에 AI라는 새로운 작업 계층이 존재한다.

이때 다음과 같은 문제가 발생한다.

AI는 인간보다 훨씬 빠른 속도로 사고하고 행동할 수 있다. 여러 단계의 판단, 코드 수정, 데이터 분석, 문서 작성을 연속해서 수행하면 인간은 AI의 사고 과정을 따라가기 어려워진다.

결과에서 문제가 발견되더라도 실제 잘못된 판단이 발생한 지점은 훨씬 이전일 수 있다. 따라서 단순히 파일의 과거 버전으로 돌아가는 것만으로는 충분하지 않다.

GIL은 이를 해결하기 위해 AI의 작업을 작은 단위로 제한하고, 각 단계에서 사고와 결과를 기록하며, 그 기록을 다음 작업으로 상속한다.

GIL의 기본 원칙은 다음과 같다.

> **AI는 한 번에 한 걸음만 걷는다.**

그리고 각각의 걸음은 이전 걸음으로부터 지식을 상속받아야 한다.

---

# 2. 프로젝트의 세 가지 기록

GIL 프로젝트는 크게 세 종류의 기록을 관리한다.

```text
Project
│
├── Existence
│
├── Reasoning
│
└── Artifacts
```

이 세 기록은 서로 다른 시간 규칙을 가진다.

| 영역 | 의미 | 노드 이동 시 |
|---|---|---|
| Existence | 작업을 수행하는 존재 | 유지 |
| Reasoning / Knowledge | 사고 과정과 획득한 지식 | 축적 |
| Artifacts | 실제 결과물 파일 | 해당 노드 버전으로 복원 |

---

# 3. Existence — 존재의 기록

Existence는 작업을 수행하는 AI의 지속적인 이름과 그 이름에 귀속된 기록이다.

AI 모델의 세션은 종료될 수 있지만 GIL의 존재는 세션과 독립적이다.

새로운 AI 세션이 동일한 이름을 부여받으면 해당 존재의 기록을 통해 프로젝트에서 자신의 역할과 행동 규약을 이어받을 수 있다.

하나의 프로젝트에는 여러 존재가 있을 수 있다.

예를 들어 훈련과 추론을 서로 다른 존재가 담당하거나, 특정 문제를 해결하기 위한 서브 에이전트가 별도의 존재를 가질 수 있다.

Existence는 다음 요소를 가진다.

## 3.1 Identity

존재의 이름이다.

세션이 초기화되더라도 동일한 이름 아래에서 작업을 이어갈 수 있도록 한다.

## 3.2 Memory

Memory는 특정 실험이나 분석에서 얻은 지식과 다르다.

존재가 지속적으로 기억해야 하는 **상위 수준의 행동 규약과 원칙**이다.

Memory는 기억이 향하는 시간의 방향에 따라 둘로 나뉜다. Memory가 과거 기억만 뜻하지 않는다.

```text
Memory
├─ Retrospective Memory
│  과거에 무엇을 경험했는가
└─ Prospective Memory
   특정 조건이 되면 무엇을 기억해 실행해야 하는가
```

### 3.2.1 Retrospective Memory

이미 겪은 일에서 남아 계속 지키는 규약이다.

```text
풀 테스트는 매번 실행하지 않는다.
```

### 3.2.2 Prospective Memory

아직 오지 않은 조건에 걸어 두는 규약이다. 조건과 그때 무엇을 해야 하는지를 함께 적는다.

```text
릴리즈 직전에는 전체 테스트를 실행한다.
```

Prospective Memory는 **지속적이며 `done`으로 소비되지 않는다.** 한 번 조건이 충족되어
실행했다는 이유로 사라지지 않는다.

조건이 충족되면 Prospective Memory는 새로운 Current Will을 만드는 **근거**가 될 수 있다.

```text
Prospective Memory
  릴리즈 직전에는 전체 테스트를 실행한다.

릴리즈 조건 도달
        ↓

Current Will
  전체 테스트를 실행해 릴리즈 가능 여부를 검증한다.
```

조건 충족을 판정하고 Will을 생성하는 trigger와 평가 알고리즘은 아직 정하지 않는다.

Memory는 특정 Reasoning Node로 이동하거나 과거 버전으로 돌아가더라도 변경되지 않는다.
이는 두 종류 모두에 적용된다.

## 3.3 Will

Will은 Current Existence가 **지금 수행하려는 하나의 행동 단위**다.

```text
Will
  id
  existence_ref
  target_node_ref
  objective
  next_action
  done_when
```

Will은 미래를 향해 유지되는 지속적 규약이 아니다. 하나의 행동은 `done`으로 확정되고 다음
행동은 새로운 Will로 시작한다. 미래 조건에 걸어 두는 지속적 규약은 Will이 아니라 §3.2의
Prospective Memory다.

Will의 Active / Done은 필드가 아니라 저장 위치에서 유도한다. 실행형 `gil open`은 Node와
Active Will을 함께 시작하고 `gil close`는 Will Done, Journey revision, Report와 Node Close를
하나의 transaction으로 확정한다.

Active Will은 Existence Journey 안의 inline 객체이고, Done 시 같은 객체가 그 Journey의
`done_wills` append-only 객체 목록으로 이동한다. Will ID는 프로젝트 전역이며 Project root의
`next_will_id`가 발급한다. 실행형 `gil open`은 stdin에서 비어 있지 않은 `objective`,
`next_action`, `done_when`을 함께 받아 Node와 Will을 원자적으로 연다.

Will의 최소 형태, 생명주기, 불변식과 Journey Timeline 투영은 `GIL Will Model v0.1`이 정한다.

영구 reference는 대상 종류를 포함하는 프로젝트 로컬 typed reference다. 예를 들어 Current
Will의 `existence_ref`는 `existence:X1`, `target_node_ref`는 `step:C2/S3` 형태다. 화면의 `#3`
같은 현재 맥락용 축약은 영구 저장이나 구조적 Report reference에 사용하지 않는다. 전체 주소
규칙은 `GIL Node Model v0.1` §2.1을 따른다.

## 3.4 Relations

Relations는 존재가 스스로 해결할 수 없는 문제를 해결하기 위해 사용할 수 있는 외부 존재 또는 수단과의 관계다.

예를 들어 의존하고 있는 오픈소스 프로젝트에서 문제가 발견된 경우 해당 GitHub 프로젝트에 Issue를 남기는 행동이 Relation을 통해 가능할 수 있다.

---

# 4. Reasoning — 사고의 기록

Reasoning은 AI의 사고가 임의의 방향으로 빠르게 진행되는 것을 제한하기 위한 구조다.

Reasoning Graph는 다음 세 단계의 계층을 가진다.

```text
Chain
  │
  └── Cycle
        │
        └── Step
```

각 계층은 AI의 사고 범위를 점점 좁힌다.

```text
Chain
"무엇을 해결할 것인가?"

        ↓

Cycle
"지금 무엇을 해결할 것인가?"

        ↓

Step
"지금 정확히 무엇을 할 것인가?"
```

---

# 5. Chain

Chain은 프로젝트에서 해결하려는 하나의 큰 주제를 나타낸다.

Chain은 사용자와의 심층 면담을 통해 열린다.

Chain Open Report는 두지 않는다. Chain을 생성하는 시점에는 식별자와 Open 상태 같은 구조적
정보만 존재하며, 탐색 범위는 아직 확정되지 않는다.

첫 Interview Cycle의 승인된 Synthesis가 다음 내용을 형성한다.

- 사용자의 면담 결과
- 해결하려는 대주제
- 원자화된 탐색 체크리스트

따라서 Chain의 의미 있는 탐색은 첫 Interview Cycle이 성공한 뒤에 시작된다.

Chain은 큰 방향을 정의하며, 그 내부의 실제 문제 해결은 Cycle을 통해 수행한다.

Chain이 닫히기 전에는 해당 Chain을 부모로 하는 새로운 Chain을 만들 수 없다.

---

# 6. Cycle

Cycle은 Chain의 대주제에서 **지금 당장 해결해야 하는 작은 문제**에 집중하기 위한 단위다.

하나의 Chain에는 여러 Cycle이 존재할 수 있다.

Cycle 내부에서는 Step을 통해 실제 사고와 행동이 진행된다.

Cycle이 닫히기 전에는 해당 Cycle을 부모로 하는 새로운 Cycle을 만들 수 없다.

실패한 결과만을 가진 Cycle은 새로운 Cycle의 부모가 될 수 없다.

실패는 삭제되거나 무시되지 않는다.

실패에서 얻은 교훈 역시 이후 작업에서 상속되는 지식의 일부다.

---

# 7. Step

Step은 GIL Reasoning Graph의 가장 작은 진행 단위다.

Git의 Commit과 유사한 버전 단위지만, 단순한 파일 변경이 아니라 하나의 원자적인 사고 또는 행동을 표현한다.

하나의 Step에서는 가능한 한 하나의 사고와 행동만 수행한다.

이는 AI가 인간이 따라가기 어려운 속도로 여러 판단을 한꺼번에 수행하면서 기술적·논리적 부채를 누적하는 것을 방지하기 위함이다.

문제가 최종적으로 발견되는 지점과 실제 잘못된 사고가 시작된 지점은 서로 멀리 떨어져 있을 수 있다.

Step의 원자성은 잘못된 사고가 시작된 정확한 지점으로 돌아갈 수 있도록 한다.

모든 Step은 닫히기 전에 Report를 작성해야 한다.

---

# 8. Open / Close

GIL의 Reasoning Node는 Open과 Closed 상태를 가진다.

```text
OPEN
 │
 │ 사고 / 행동
 │ Verify에서만 Artifact 변경
 │
 ▼
REPORT
 │
 ▼
CLOSED
```

Open된 Node에서는 해당 Node가 허용하는 작업을 수행할 수 있다.

Node를 닫기 위해서는 해당 Node Kind에서 요구하는 Report가 충족되어야 한다.

Artifact tree가 현재 확정 snapshot과 다를 때, Verify가 아닌 Step은 닫을 수 없고 Cycle도 닫을
수 없다. 그때 사용자가 하는 명시적 복원 명령은 `gil restore`다. Verify는 새 Artifact snapshot의
확정이 성공해야 닫을 수 있다.

**Artifact·Snapshot·`gil restore`의 규범은 `GIL Artifact Model v0.1`이 단독으로 갖는다.**
변경 허용 경계는 그 문서 §6, Verify close 트랜잭션은 §7, 저장과 원자성 경계는 §10이다.

닫히지 않은 Node를 기반으로 다음 Node를 열 수 없다.

따라서 AI는 현재 사고를 확정하지 않은 상태에서 다음 사고로 넘어갈 수 없다.

새 Node를 열 수 있는지는 현재 닫힌 Node의 Kind에 의해 결정된다.

## 진행이 멈춘 상태

Cycle 내부의 진행이 Exit에 닿기 전에 멈출 수 있다. 이 상태는 Success도 Failure도 아니며,
그 자체로 잘못된 상태도 아니다.

판정은 Outcome이 닫히면서만 이루어지므로, Outcome에 닿지 않고 멈춘 진행에는 판정이 없다.
멈춘 자리에서 나중에 작업을 이어갈 수 있어야 한다.

멈춘 진행을 명시적으로 끝내는 행위(abort / cancel / abandon)는 GIL v0.1에서 정의하지
않는다. 그런 종료 상태를 위해 Open / Closed 외의 상태를 추가하지 않는다.

---

# 9. Step Kind

GIL v0.1은 다섯 종류의 Step Kind를 정의한다.

```text
Cycle Entry
   ↓
DEFINE
   ↓
HYPOTHESIS
   ↓
VERIFY
   ↓
ANALYSIS
   ├────→ HYPOTHESIS
   │
   └────→ OUTCOME
             ↓
         Cycle Exit
```

`Cycle Entry`와 `Cycle Exit`은 Step Kind가 아니라 Cycle의 시작과 끝을 가리키는 경계다.
Step이 아니므로 자신의 Report를 갖지 않는다.

각 Kind는 하나의 핵심 질문에 답한다.

| Kind | 핵심 질문 |
|---|---|
| Define | 무엇을 풀어야 하는가? |
| Hypothesis | 어떻게 풀 수 있다고 생각하는가? |
| Verify | 실제로 무엇을 했고 무엇이 발생했는가? |
| Analysis | 그 결과는 무엇을 의미하는가? |
| Outcome | 이번 계보에서 무엇을 배웠고 다음에는 어디로 가야 하는가? |

---

# 10. Define

Define은 현재 Cycle에서 해결해야 할 문제를 정의한다.

### Parent

Cycle Entry

### Child

Hypothesis

### Required Report

최소한 다음 내용을 포함해야 한다.

**Problem**

지금 해결해야 하는 문제가 무엇인가.

**Success Condition**

어떤 조건이 충족되면 이 문제가 해결되었다고 판단할 수 있는가.

Success Condition은 이후 Analysis와 Outcome에서 성공 여부를 판단하는 기준점으로 사용된다.

---

# 11. Hypothesis

Hypothesis는 현재 문제를 해결할 수 있다고 예상하는 방법을 정의한다.

### Parent

- Define
- Analysis

### Child

Verify

Analysis를 부모로 가질 수 있으므로 이전 실험 결과를 바탕으로 새로운 가설을 수립할 수 있다.

### Required Report

최소한 다음 내용을 포함해야 한다.

**Hypothesis**

어떤 방법을 사용하면 문제가 해결될 것이라고 예상하는가.

**Rationale**

그 가설을 세운 근거는 무엇인가.

**Guardrail**

어떤 결과가 관측되면 이 가설이 틀렸다고 판단할 것인가.

Guardrail은 결과를 확인한 이후 임의로 성공 기준을 변경하는 것을 방지하기 위해 가설 단계에서 미리 정의한다.

---

# 12. Verify

Verify는 Hypothesis를 실제로 검증하는 단계다.

### Parent

Hypothesis

### Child

Analysis

### Required Report

최소한 다음 내용을 포함해야 한다.

**Execution**

가설을 검증하기 위해 실제로 무엇을 수행했는가.

**Result**

실행 결과 무엇이 관측되었는가.

Verify에서는 결과를 해석하지 않는다.

Verify의 역할은 실행과 관측을 기록하는 것이다.

결과가 가설을 지지하는지, 성공인지 실패인지는 다음 Analysis에서 판단한다.

---

# 13. Analysis

Analysis는 Verify에서 얻은 결과를 해석한다.

### Parent

Verify

### Child

- Hypothesis
- Outcome

### Required Report

최소한 다음 사항을 분석해야 한다.

- `hypothesis_fit` — 관측 결과가 가설과 부합하는가.
- `problem_solved` — Define에서 정의한 문제가 해결되었는가.
- `success_condition_met` — Define의 Success Condition이 충족되었는가.
- `guardrail_triggered` — Hypothesis에서 정의한 Guardrail이 발동했는가.
- `interpretation` — 결과로부터 어떤 의미를 도출할 수 있는가.

`problem_solved`와 `success_condition_met`은 서로 다른 항목이다. 문제가 해결되었다는
판단과, 미리 정의한 성공 조건이 충족되었다는 판단은 같은 것이 아니므로 각각 기록한다.

또한 `success_condition_met`이 충족되었다는 것이 곧바로 Outcome의 `success`를 의미하지는
않는다. Analysis는 해석하고, 판정은 Outcome에서 이루어진다.

Analysis 결과 기존 가설을 수정하거나 새로운 가설을 수립해야 한다면 새로운 Hypothesis로 진행할 수 있다.

---

# 14. Outcome

Outcome은 하나의 실험 계보를 일단락하고 다음 진행 방향을 결정하는 Step이다.

여기서 "계보"는 마지막 Hypothesis / Verify / Analysis 묶음 하나가 아니라, **Cycle Entry에서
Outcome에 이르기까지 그 Cycle 내부에서 이어진 전체 Lineage**다.

한 Cycle 안에서 Analysis가 새로운 Hypothesis로 되돌아가 가설을 여러 번 세웠다면, Outcome은
그중 마지막 것만 판정하지 않는다. 그 Cycle 안에서 이어진 모든 시도를 종합해 판정한다.

Outcome은 기본적으로 판정되지 않은 상태로 열린다.

자율 실행 모드에서는 AI가 스스로 Outcome을 닫을 수 있다.

인간의 판단과 합의가 필요한 실행 모드에서는 인간이 Outcome을 닫는다.

Outcome이 닫히면서 해당 계보가 성공인지 실패인지 확정된다.

### Parent

Analysis

### Child

Cycle Exit

Outcome이 닫힌 뒤 `Cycle Exit`을 통해 해당 Cycle이 닫힌다. `Cycle Exit`은 Step이 아니라
Cycle의 끝을 가리키는 경계이므로 자신의 Report를 갖지 않는다.

Cycle의 성공/실패는 그 Outcome의 `verdict`가 결정한다.

Cycle 자체의 상태 전이 규칙은 GIL v0.1에서 정의하지 않는다. 여기서 정하는 것은
`outcome → cycle_exit` 경계까지다.

### Verdict

Verdict는 정확히 다음 두 값 중 하나다.

- `success`
- `failure`

Verdict 값은 **대소문자를 구분한다.** `Success`, `FAILURE` 등 유사 표현은 허용하지 않는다.

이는 입력 편의성보다 문법의 명확성과 결정성을 우선하기 위한 선택이다.

Verdict는 Outcome이 닫힐 때만 존재한다. 판정되지 않은 상태는 Verdict의 값이 아니라
**Outcome이 아직 Open이라는 사실**로 표현한다.

Analysis의 `success_condition_met`이 충족되었다는 것이 곧바로 Outcome의 `success`를
의미하지는 않는다. Analysis는 관측 결과를 해석하고, Outcome은 계보 전체를 판정한다.

### Required Report

최소한 다음 내용을 포함해야 한다.

**Verdict**

이번 계보가 성공했는지 실패했는지. `success` 또는 `failure`.

**Lesson**

이번 Lineage를 통해 무엇을 배웠는지. 여기서 Lineage는 Cycle Entry에서 이 Outcome까지
이어진 Cycle 내부 전체 경로다 — 마지막 시도 하나가 아니다.

성공뿐 아니라 실패에서 얻은 교훈도 반드시 기록한다. 중간에 버려진 가설에서 얻은 것도
같은 Lineage의 일부다.

**Next Direction**

다음에는 어디로 진행해야 하는지. 자유 서술이 아니라 **구조로 적는다.**

```text
next_direction.action           revisit | close_cycle
next_direction.reason           왜 그 방향인지 (비워 둘 수 없다)
next_direction.target_node_ref  action 이 revisit 일 때만, 그때는 필수 StepRef
```

따라서 Outcome 의 Report 는 다음 항목으로 이루어진다.

```text
verdict
lesson
next_direction.action
next_direction.reason
next_direction.target_node_ref  (revisit 일 때만, 예: step:C2/S3)
```

verdict 와 action 은 다음처럼 맞물린다.

```text
success  →  close_cycle 만
failure  →  revisit | close_cycle
```

`success` 는 현재 Cycle 이 결론에 닿았다는 뜻이므로 Cycle Exit 방향으로만 진행한다.

여기서 `close_cycle`은 Step Outcome 계층의 방향이다. 현재 Step Graph를 끝내고 이 Cycle의
Report를 작성하는 경계로 이동한다. Cycle Report의 `open_child`와 반대되는 값이 아니다.

**verdict 와 action 은 서로 다른 것을 말한다.** verdict 는 이 Cycle 의 **의미적 판정**이고,
action 은 **구조적으로 다음에 무엇을 하는가**다. 그래서 `success + close_cycle` 과
`failure + close_cycle` 은 같은 action 이지만 서로 다른 종결이며, 이를 가르려고 별도의
action 을 두지 않는다.

### revisit 이 고르는 것

`revisit` 은 **현재 Cycle 안의 과거 Closed ancestor 중, 새로운 Hypothesis 를 열 수 있는
branch point** 를 고르는 것이다.

- 대상은 그 Outcome 의 Lineage 위에 있어야 한다 — 형제·자손·무관한 Node 는 고를 수 없다.
- 대상은 이미 닫혀 있어야 한다.
- 대상의 Kind 가 Grammar 상 `hypothesis` 를 자식으로 가질 수 있어야 한다.

무엇이 옳은 복귀점인지는 **Agent 가 Lineage 를 읽고 판단한다.** 도구는 그 선택이
구조적으로 가능한지만 본다.

### Define 으로 되돌아간다는 것

`Define` 으로 revisit 하는 것은 **Define 을 고치거나 다시 정의한다는 뜻이 아니다.**
기존 Define 을 그대로 둔 채 **새로운 Hypothesis 를 세운다**는 뜻이다.
같은 문제 정의와 같은 성공 조건 아래에서 다른 가설을 시도하는 것이다.

```text
Define
├─ Hypothesis A  → … → 반증
└─ Hypothesis B
```

Define 자체가 더 이상 유효하지 않다고 판단되면, 같은 Cycle 안에서 Define 을 다시 만들지
않는다. 그때는

```text
verdict = failure
action  = close_cycle
```

으로 이 Cycle 안에서의 탐색을 끝낸다. 문제 정의를 다시 세우는 일은 이 Cycle 의 몫이 아니다.

### 판단과 이동은 다른 행위다

Outcome 의 판단과 실제 그래프 이동은 서로 다른 행위다.

Outcome 은 다음 방향을 **확정해 기록**할 뿐이고, 실제 이동은 별도로 이루어진다.

---

# 15. 판정 대기와 인간 승인

Outcome은 Open 상태에서 아직 판정되지 않은 채로 있을 수 있다.

**`pending`은 Verdict의 값이 아니다.** 판정을 기다리는 상태는 별도의 Verdict 값이 아니라
**Outcome이 아직 Open이라는 사실** 그 자체다.

따라서 Verdict는 Outcome이 Closed일 때만 존재하며, 그 값은 정확히 `success` 또는
`failure` 중 하나다.

```text
Outcome OPEN            ← 아직 판정되지 않았다 (Verdict 없음)
    │
    │ AI 또는 Human 판단
    ▼
Outcome CLOSED
    │
    ├── verdict: success
    └── verdict: failure
```

Outcome을 닫으려면 Verdict가 반드시 존재해야 한다. Verdict 없이는 닫을 수 없다.

인간의 판단이 필요한 경우 AI는 Outcome을 임의로 닫지 않고 인간의 결정을 기다린다.
그동안 Outcome은 Open으로 남고, 닫히지 않은 Node이므로 다음 Node로 진행할 수 없다.

승인 시스템의 구체적인 규칙은 GIL v0.1에서 완전히 정의하지 않는다.

---

# 16. Report

모든 Step은 Report를 작성한 뒤 닫힌다.

Report는 단순한 Commit Message가 아니다.

해당 Step에서 이루어진 사고, 행동, 관측, 판단을 다음 Node에 전달하기 위한 지식 전달 단위다.

따라서 Closed Step은 최소한 다음 두 가지를 가진다.

```text
Step
├── Artifact Snapshot
└── Report
```

Artifact Snapshot은 모든 Step의 Report에 같은 값으로 복제하지 않는다. Verify Step만 도구가
생성한 `snapshot_ref`를 `snapshot:A1` 형태의 typed reference로 **Report와 분리된 구조 필드**에
직접 저장하며, 다른 Closed Step은 그 값을 Lineage에서 유도한다. 유도 규칙과 Cycle Exit의
계승 규칙은 `GIL Artifact Model v0.1` §7이 갖는다.

Report의 형식은 Step Kind에 의해 결정된다.

중첩된 Report 필드는 dotted key와 indentation 문법을 모두 입력으로 받을 수 있다.

```yaml
next_direction.target_node_ref: step:C2/S4
```

```yaml
next_direction:
  target_node_ref: step:C2/S4
```

두 입력은 같은 논리적 필드에 이른다. GIL이 오류 골격과 예시를 출력할 때는 짧은 dotted key를
canonical 표기로 사용한다. 입력 문법의 차이로 의미가 다른 Report를 만들지 않는다.

필수 Report 항목을 충족하지 못한 Step은 닫을 수 없다.

## Report 작성 불변식

이 원칙은 Step Report뿐 아니라 Cycle Report와 Chain Report를 포함한 모든 Node Report에
적용한다.

Report는 해당 작업에 직접 참여하지 않았지만 프로젝트의 일반적 맥락을 아는 협업자가 독립적으로
읽을 수 있어야 한다. 다음 원칙을 지킨다.

- 정의되지 않은 약어, 단계 코드명, 이슈 번호만으로 대상이나 결론을 표현하지 않는다.
- 약어가 필요하면 처음 등장할 때 원문과 의미를 함께 적는다.
- 주관적 평가어 대신 관측한 사실, 판정 기준과 근거를 적는다.
- 관측과 해석을 구분한다. Verify의 관측을 Analysis의 해석인 것처럼 쓰지 않는다.
- 성공·실패 주장은 미리 정의된 기준과 Report 또는 Artifact 증거로 추적할 수 있어야 한다.
- 다음 Node가 원본 맥락을 다시 추측하지 않도록 대상, 결과와 미해결 사항을 구체적으로 적는다.
- 불필요한 수사, 과장과 모호한 대명사를 피한다.

여기서 과학적 글쓰기는 모든 문장을 숫자로 만들거나 전문 용어를 늘리는 것을 뜻하지 않는다.
누가 읽어도 같은 대상과 근거를 식별하고, 관측에서 결론까지의 연결을 검토할 수 있게 쓰는 것을
뜻한다.

이 원칙은 의미적 불변식이다. v0의 schema 검사는 필수 필드와 허용값을 강제하지만 자연어의
객관성과 자립성을 완전히 판정하지 않는다. 초기에는 Agent onboarding, dogfood와 인간 검토로
평가하고, 반복되는 위반이 나타날 때 lint 또는 승인 규칙을 추가한다.

## 필수 항목은 최소 집합이다

각 Step Kind가 요구하는 필수 항목은 **Report 전체의 schema가 아니라, 그 Kind의 Node가
닫히기 위해 반드시 존재해야 하는 최소 항목의 집합**이다.

따라서 필수 항목 외의 항목이 Report에 더 있어도 된다. 그것 때문에 Node를 닫지 못하지는
않는다.

---

# 17. Lineage

프로젝트 Root에서 현재 Node에 이르는 계보를 Lineage라고 한다.

Lineage는 **`parent` 만 따라간다.**

Lineage를 구성하는 각 Node의 Report는 다음 Node로 전달되는 지식의 기반이 된다.

```text
Root
 │
 ▼
Step A ── Report A
 │
 ▼
Step B ── Report B
 │
 ▼
Step C ── Report C
```

Step C는 무에서 생성되지 않는다.

A와 B에서 축적된 사고와 경험을 상속받은 상태에서 생성된다.

따라서 Lineage는 그 Node의 **구조적 배경**을 이룬다 — 이 Node가 어디에서 났고, 그 지점에서
무엇이 이미 확정되어 있었는가.

## Step Node 가 가리키는 두 가지

Step Node 는 서로 다른 두 개의 참조를 가질 수 있다. **둘은 같은 것이 아니다.**

```text
parent
= 구조적 계승 — 이 Node 가 어느 Node 의 사고를 직접 이어받아 났는가

revisit_from
= 갈래 생성의 출처 — 이 갈래를 낳은 결정이 어느 Outcome 에 적혀 있었는가
```

`revisit_from` 은 **계보의 변이 아니며, 계보를 재구성할 때 따라가서는 안 된다.**
두 번째 parent 로 읽으면 되돌아오며 버린 갈래가 계보에 섞인다.

`revisit_from` 은 되돌아감으로 시작된 갈래의 **첫 Node 에만** 남고, 자손에게 전파되지 않는다.
평범하게 이어 걸어 난 Node 에는 없다. 한 번 적히면 `parent` 와 같이 바뀌지 않는다.

이 값이 필요한 이유는 하나다 — 어느 결정이 이 갈래를 낳았는지를 **실행 순서에서 되짚지
않기 위해서**다. 같은 자리로 여러 번 되돌아갈 수 있으므로(§14), 순서로는 갈리지 않는다.

다만 Lineage가 그 Node에서 쓸 수 있는 지식의 **전부는 아니다.** Agent 는 자신의 Lineage 에
없는 가지에서도 배울 수 있고, 그 지식은 사라지지 않는다. Lineage 와 Knowledge 의 관계는
[GIL Time Model v0.2](GIL_Time_Model_v0.2.md) 가 정의한다.

---

# 18. Knowledge

GIL에서 Knowledge는 반드시 독립된 사실 객체로 저장될 필요가 없다.

Report의 내용 자체가 Knowledge의 재료다. Lineage를 따라 축적된 Report들은 그 재료의 중요한
원천이지만, **Knowledge가 Lineage로 한정되지는 않는다.**

Agent는 자신의 Lineage에 속하지 않는 가지에서도 배운다. 되돌아가 다른 가지를 열더라도 그
사이에 얻은 교훈은 사라지지 않는다. 즉 **Knowledge는 Lineage와 독립적으로 누적될 수 있다.**

구조적 계보(Lineage)와 누적된 지식(Knowledge)을 가르는 모델은
[GIL Time Model v0.2](GIL_Time_Model_v0.2.md) 가 정의한다 — 거기서 Knowledge는 Lineage가
아니라 Journey에 속한다.

성공 Report뿐 아니라 실패 Report 역시 Knowledge의 일부다.

```text
Failure
   │
   ▼
Failure Report
   │
   ▼
Lesson
   │
   ▼
Next Reasoning
```

따라서 실패는 삭제되거나 Rollback되지 않는다.

실패에서 획득한 지식은 이후 사고에 사용될 수 있다.

Knowledge는 기본적으로 Append-only 성격을 가진다.

---

# 19. Knowledge Compression

Lineage가 길어질수록 모든 Step Report를 항상 AI Context에 포함하는 것은 비효율적이다.

따라서 GIL은 계층에 따라 지식을 서로 다른 해상도로 표현할 수 있다.

```text
Chain Report
    │
    │ 높은 압축
    ▼
Cycle Report
    │
    │ 중간 압축
    ▼
Step Report
       상세 기록
```

Chain 수준에서는 Chain Report를 통해 장기간 축적된 지식을 압축해서 전달할 수 있다.

Cycle 수준에서는 Cycle Report를 사용한다.

현재 작업 중인 Cycle에서는 필요에 따라 개별 Step Report를 보다 면밀하게 검토할 수 있다.

따라서 Reasoning Graph 자체가 AI의 Context를 구성하기 위한 계층적 지식 구조로 사용될 수 있다.

Knowledge Compression의 구체적인 알고리즘과 Report 형식은 GIL v0.1에서 정의하지 않는다.

---

# 20. Artifact

Artifact는 AI와 인간의 작업을 통해 생성되거나 수정된 실제 결과물이다.

예:

- Source Code
- Dataset
- Notebook
- Report
- Document
- Image
- Chart
- Configuration

Artifact는 특정 Node 시점의 Snapshot으로 관리한다. 파일마다 규칙을 두지 않고 작업 결과물
전체를 하나의 tree snapshot으로 다룬다.

**이 절은 Artifact가 무엇인지만 말한다.** 관리 범위, 최초 기준 세계, Snapshot 생성 권한,
변경 허용 경계, Cycle Exit Snapshot, `gil restore`, 저장 원자성의 규범은 전부
`GIL Artifact Model v0.1`에 있다.

GIL의 공개 개념과 오류 메시지에서 내부 저장 기법의 용어를 노출하지 않는다. staging·index·
commit·branch·checkout은 사용자에게 보이는 GIL의 어휘가 아니다.

---

# 21. Node 이동과 시간

GIL에서는 Existence, Knowledge, Artifact가 서로 다른 시간 규칙을 가진다.

특정 Node로 이동할 때:

### Existence

변하지 않는다.

```text
Node A → Node B

Existence = 유지
```

### Knowledge

이미 획득한 지식은 제거하지 않는다.

```text
Node A → 과거 Node B

Knowledge = 축적된 상태 유지
```

과거의 Artifact 상태로 돌아가더라도 이미 경험한 실패와 교훈을 잊지 않는다.

### Artifact

이동한 Node의 Snapshot으로 복원한다.

```text
Node A
 ↓
goto Node B
 ↓
Working Files = Snapshot(Node B)
```

따라서 GIL의 과거 Node 이동은 시간을 완전히 되돌리는 동작이 아니다.

파일은 과거 상태로 돌아가지만 존재와 획득한 지식은 현재에 남는다. Artifact Snapshot은
**World Timeline**에 속하고 Journey Timeline은 그 복원의 영향을 받지 않는다
(`GIL Artifact Model v0.1` §2·§9).

---

# 22. Revisit

GIL에서 과거 Node로 이동하는 행위는 전통적인 의미의 완전한 Rollback과 다르다.

예를 들어 다음과 같은 Lineage가 있다고 하자.

```text
A → B → C → D → E
```

E에서 중요한 실패를 발견하고 C로 돌아간다.

Artifact는 C의 상태로 복원된다.

그러나 D와 E에서 얻은 교훈은 사라지지 않는다.

따라서 새로운 탐색은 과거와 동일한 C에서 시작하는 것이 아니다.

```text
Artifact:
C의 상태

Knowledge:
C 이후에 획득한 교훈을 포함

Existence:
현재 상태 유지
```

GIL에서 과거로 돌아간다는 것은 같은 장소를 다시 방문하는 것이지만, 처음 그 장소에 도착했던 것과 동일한 상태가 되는 것을 의미하지 않는다.

---

# 23. GIL v0.1의 핵심 불변 규칙

현재 명세에서 다음 규칙은 GIL의 핵심 원칙으로 취급한다.

**1. AI는 한 번에 하나의 원자적인 Step만 수행한다.**

**2. 모든 Step은 Report를 작성해야 닫을 수 있다.**

**3. 열린 Node를 둔 채 허용되지 않은 다음 Node로 진행할 수 없다.**

**4. 다음 Step Kind는 현재 닫힌 Step Kind에 의해 제한된다.**

**5. Verify에서는 관측하고 Analysis에서는 해석한다. Artifact를 변경하고 snapshot을 확정할
수 있는 Step은 Verify뿐이다. 비-Verify Step과 Cycle의 Artifact 변경은 Close를 막는다.
Verify 자체에는 verdict가 없으며, snapshot 확정은 판정과 독립이다.**

**6. Experiment의 Success는 해당 Cycle의 Define에서 미리 정의한 성공 조건에 근거해야 한다.
Interview의 Success는 인간이 승인한 Synthesis에 근거해야 한다.**

**7. Failure는 삭제되지 않으며 지식의 일부가 된다.**

**8. Knowledge는 Report를 통해 다음 사고로 상속되며, Lineage에 한정되지 않고 누적된다.**

**9. Artifact의 과거 상태로 돌아가더라도 이미 획득한 Knowledge는 잃지 않는다.**

**10. Node 이동은 Existence에 영향을 주지 않는다.**

**11. 모든 계층의 Report는 정의되지 않은 약어 없이 객관적이고 검증 가능한 문장으로 작성하며,
해당 Node에 참여하지 않은 협업자도 독립적으로 이해할 수 있어야 한다.**

**12. 미래 조건에서 기억해야 할 지속적 규약은 Prospective Memory다. Will은 Current Existence가
지금 수행하려는 하나의 행동 단위다. Prospective Memory의 조건이 충족되면 새로운 Current Will의
근거가 될 수 있다.**

---

# 24. GIL v0.1에서 의도적으로 정의하지 않는 것

이 명세는 GIL의 핵심 사고 모델을 정의하기 위한 초기 버전이다.

따라서 다음 사항은 아직 확정하지 않는다.

- 실제 저장 엔진
- Git / libgit2와의 구체적인 매핑
- Git Object와 GIL Node의 관계
- MCP 인터페이스
- AI Client 통합 방식
- Marketplace 배포
- 설치 및 업데이트 방식
- Chain / Cycle Report의 정확한 Schema
- Knowledge Compression 알고리즘
- 인간 승인 정책의 상세 규칙
- 멈춘 진행의 명시적 종료(abort / cancel / abandon)
- 다중 부모를 가진 Graph의 Lineage 정의
- Relation의 실제 실행 프로토콜
- 동시 작업 및 Merge
- 네트워크 기반 협업

이들은 GIL의 핵심 모델이 검증된 이후 별도의 명세에서 정의한다.

---

# 25. 현재의 정의

GIL v0.1에서 GIL은 다음과 같이 정의한다.

> **GIL (Git for Language Models)은 AI와 인간의 협업 과정에서 존재, 사고, 지식과 결과물을 지속적으로 추적하기 위한 버전 관리 체계다.**
>
> **GIL은 AI의 사고를 Chain, Cycle, Step으로 구조화하고, 각 Step을 원자화하여 AI가 한 번에 한 걸음씩 진행하도록 제한한다. 모든 Step은 Report를 통해 자신의 사고와 결과를 다음 Step에 전달한다.**
>
> **과거 Node로 돌아갈 때 Artifact는 해당 시점으로 복원되지만, 존재는 유지되고 이미 획득한 지식은 사라지지 않는다.**
>
> **따라서 GIL의 목적은 단순히 과거의 결과물을 복원하는 것이 아니라, AI가 자신이 걸어온 길에서 얻은 지식을 잃지 않은 채 필요한 지점으로 돌아가 다시 걸을 수 있도록 하는 것이다.**
