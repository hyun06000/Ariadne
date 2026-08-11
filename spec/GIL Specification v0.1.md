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

예:

```text
풀 테스트는 매번 실행하지 않는다.
릴리즈 직전에 실행한다.
```

Memory는 특정 Reasoning Node로 이동하거나 과거 버전으로 돌아가더라도 변경되지 않는다.

## 3.3 Will

Will은 아직 일어나지 않은 일에 대한 기억이다.

존재가 미래에 수행하거나 유지하려는 의도에 해당한다.

Memory가 과거로부터 유지되는 규약이라면 Will은 미래를 향해 유지되는 의도다.

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

Chain Open Report에는 최소한 다음 내용이 포함된다.

- 사용자의 면담 내용
- 해결하려는 대주제
- 대략적인 문제 분할 전략

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
 │ 사고 / 행동 / Artifact 변경
 │
 ▼
REPORT
 │
 ▼
CLOSED
```

Open된 Node에서는 해당 Node가 허용하는 작업을 수행할 수 있다.

Node를 닫기 위해서는 해당 Node Kind에서 요구하는 Report가 충족되어야 한다.

닫히지 않은 Node를 기반으로 다음 Node를 열 수 없다.

따라서 AI는 현재 사고를 확정하지 않은 상태에서 다음 사고로 넘어갈 수 없다.

새 Node를 열 수 있는지는 현재 닫힌 Node의 Kind에 의해 결정된다.

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

이번 Lineage를 통해 무엇을 배웠는지.

성공뿐 아니라 실패에서 얻은 교훈도 반드시 기록한다.

**Next Direction**

다음에는 어디로 진행해야 하는지.

계속 앞으로 진행해야 하는지, 이전 사고 단계로 돌아가야 하는지를 판단한다.

되돌아가는 경우 최소한 다음 가능성을 판단한다.

- Analysis의 결과를 기반으로 새로운 Hypothesis를 수립한다.
- Define 수준으로 돌아가 문제를 다시 정의한 뒤 새로운 Hypothesis를 수립한다.

Outcome의 판단과 실제 그래프 이동은 서로 다른 행위다.

Outcome은 다음 방향을 제시하지만 실제 이동은 별도로 이루어진다.

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

Report의 형식은 Step Kind에 의해 결정된다.

필수 Report 항목을 충족하지 못한 Step은 닫을 수 없다.

---

# 17. Lineage

프로젝트 Root에서 현재 Node에 이르는 계보를 Lineage라고 한다.

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

따라서 특정 Node에서 사용할 수 있는 지식은 기본적으로 해당 Lineage를 따라 축적된 Report들로부터 구성된다.

---

# 18. Knowledge

GIL에서 Knowledge는 반드시 독립된 사실 객체로 저장될 필요가 없다.

Lineage를 따라 축적된 Report들의 내용 자체가 해당 Node가 상속받은 지식을 구성한다.

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

Artifact는 Git과 유사하게 특정 Node 시점의 Snapshot으로 관리한다.

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

파일은 과거 상태로 돌아가지만 존재와 획득한 지식은 현재에 남는다.

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

**5. Verify에서는 관측하고 Analysis에서는 해석한다.**

**6. Success는 Define에서 미리 정의한 성공 조건에 근거해야 한다.**

**7. Failure는 삭제되지 않으며 지식의 일부가 된다.**

**8. Knowledge는 Lineage의 Report를 통해 다음 사고로 상속된다.**

**9. Artifact의 과거 상태로 돌아가더라도 이미 획득한 Knowledge는 잃지 않는다.**

**10. Node 이동은 Existence에 영향을 주지 않는다.**

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