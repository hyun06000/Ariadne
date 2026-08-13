# GIL Node Model v0.1

> Chain, Cycle, Step을 하나의 계층적 Node 모델로 바라보기 위한 설계 노트

## 1. 문서의 목적

이 문서는 GIL의 `Chain`, `Cycle`, `Step`을 장기적으로 어떤 공통 구조로 표현할지 정리한다.

현재 구현 중인 GIL Grammar v0.1과 in-memory `Walk` 구현의 범위를 확장하기 위한 명세가 아니라, 이후 Cycle과 Chain을 구현할 때 기준으로 삼기 위한 **구조 설계 문서**다.

핵심 아이디어는 다음과 같다.

> Chain, Cycle, Step은 완전히 별개의 종류의 객체라기보다, 깊이가 다른 동일한 Node 구조로 볼 수 있다.

각 Node는 자신의 시작과 끝을 나타내는 Boundary를 가지며, 필요하다면 내부에 더 낮은 계층의 Graph를 포함한다.

---

## 2. 공통 Node 모델

개념적으로 GIL의 Node는 다음 요소를 가진다.

```text
Node
├── Boundary
│   ├── Entry
│   └── Exit
│
├── State
│   ├── Open
│   └── Closed
│
├── Report
│
├── Artifact Snapshot
│
└── Subgraph?          // optional
```

이 모델에서 `Subgraph`만 선택적이다.

- Chain은 Cycle Graph를 가진다.
- Cycle은 Step Graph를 가진다.
- Step은 Subgraph를 가지지 않는다.

```text
Chain.subgraph = Cycle Graph
Cycle.subgraph = Step Graph
Step.subgraph  = None
```

---

## 3. Boundary

### 3.1 Entry와 Exit

모든 Node는 내부와 외부를 구분하는 두 개의 Boundary를 가진다.

```text
                 Node
        ┌─────────────────────┐
        │ Entry Boundary      │
        │      ↓              │
        │     OPEN            │
        │      ↓              │
        │ [Optional Subgraph] │
        │      ↓              │
        │    Report           │
        │      ↓              │
        │    CLOSE            │
        │      ↓              │
        │ Exit Boundary       │
        └─────────────────────┘
```

Boundary는 일반적인 작업 Node가 아니다.

Boundary 자체는:

- 사고하지 않는다.
- Report를 작성하지 않는다.
- Artifact를 생성하지 않는다.
- Knowledge를 생성하지 않는다.
- 성공이나 실패를 판단하지 않는다.

Boundary의 역할은 **Node의 내부와 외부를 연결하는 접점**을 제공하는 것이다.

### 3.2 Open / Close와 Boundary의 관계

`Open`과 `Close`는 별도의 Node가 아니다.

- Entry Boundary를 통과하면서 Node가 `Open` 상태가 된다.
- Node의 작업과 Report가 완료된 뒤 `Close`된다.
- Closed Node는 Exit Boundary를 통해 외부 그래프로 결과를 전달한다.

따라서 Open / Close는 Boundary 그 자체라기보다 **Boundary를 통과하는 Node lifecycle의 상태 전이**다.

---

## 4. Step

Step은 GIL에서 가장 작은 작업 Node이며 Subgraph를 가지지 않는다.

```text
Step
┌─────────────────────┐
│ Entry               │
│   ↓                 │
│ OPEN                │
│                     │
│ 사고 / 행동         │
│ Artifact 변경       │
│ Report 작성         │
│                     │
│ CLOSE               │
│   ↓                 │
│ Exit                │
└─────────────────────┘
```

현재 GIL Grammar v0.1의 `define`, `hypothesis`, `verify`, `analysis`, `outcome`은 모두 Step의 Kind다.

Step의 Entry/Exit을 독립적인 Step Node로 저장할 필요는 없다. 이는 Step lifecycle의 경계다.

---

## 5. Cycle

Cycle은 상위 Cycle Graph에서는 하나의 Node로 보이지만, 내부에는 Step Graph를 가진다.

```text
Cycle
┌──────────────────────────────┐
│ Entry                        │
│   ↓                          │
│ OPEN                         │
│                              │
│       Step Graph             │
│                              │
│       Define                 │
│         ↓                    │
│       Hypothesis             │
│         ↓                    │
│       Verify                 │
│         ↓                    │
│       Analysis               │
│        ↙     ↘               │
│ Hypothesis   Outcome         │
│                ↓             │
│                              │
│       Cycle Report           │
│                              │
│ CLOSE                        │
│   ↓                          │
│ Exit                         │
└──────────────────────────────┘
```

따라서 현재 Step Grammar의 다음 표현:

```text
cycle_entry → define → ... → outcome → cycle_exit
```

은 `cycle_entry`와 `cycle_exit`이라는 실제 Step Node 두 개가 존재한다는 뜻이 아니다.

이들은 **Cycle 내부의 Step Graph에서 Cycle의 Entry/Exit Boundary를 바라보는 표현**이다.

Cycle의 최종 Report는 `Cycle Exit`이 아니라 **Cycle Node 자체**가 가진다.

---

## 6. Chain

Chain도 동일한 구조를 가진다.

Chain은 상위 Chain Graph에서는 하나의 Node이며, 내부에 Cycle Graph를 가진다.

```text
Chain
┌──────────────────────────────┐
│ Entry                        │
│   ↓                          │
│ OPEN                         │
│                              │
│       Cycle Graph            │
│                              │
│       Cycle A                │
│          ↓                   │
│       Cycle B                │
│          ↓                   │
│       Cycle C                │
│                              │
│       Chain Report           │
│                              │
│ CLOSE                        │
│   ↓                          │
│ Exit                         │
└──────────────────────────────┘
```

전체 계층은 다음과 같이 표현할 수 있다.

```text
Project
  │
  └── Chain Graph
        │
        └── Chain Node
              │
              └── Cycle Graph
                    │
                    └── Cycle Node
                          │
                          └── Step Graph
                                │
                                └── Step Node
```

---

## 7. Containment와 Lineage

GIL에서는 **계층적 포함 관계**와 **같은 계층에서의 계보 관계**를 구분한다.

### 7.1 Containment

```text
Project contains Chain
Chain contains Cycle
Cycle contains Step
```

Containment는 서로 다른 계층 사이의 구조적 포함 관계다.

### 7.2 Lineage

```text
Chain A → Chain B
Cycle A → Cycle B
Step A  → Step B
```

Lineage는 같은 레벨의 Graph에서 Node들이 이어지는 관계다.

따라서 용어는 다음과 같이 구분하는 것을 원칙으로 한다.

- `contains` — 서로 다른 계층의 포함 관계
- `parent / child` — 같은 계층 Graph에서의 계보 관계

예를 들어 Cycle은 Chain의 `child`라기보다 Chain에 `contained`된다. 반면 같은 Cycle Graph에서 Cycle B는 Cycle A를 parent로 가질 수 있다.

---

## 8. 계층적 캡슐화

상위 Graph는 하위 Node 내부의 세부 경로를 알 필요가 없다.

예를 들어 Cycle A 내부에서 다음과 같이 여러 번 가설을 수정했다고 하자.

```text
Define
  ↓
Hypothesis A
  ↓
Verify
  ↓
Analysis
  ↓
Hypothesis B
  ↓
Verify
  ↓
Analysis
  ↓
Outcome
```

Cycle Graph의 관점에서는 이 전체 과정이 하나의 Cycle Node로 보인다.

```text
Cycle A ─────→ Cycle B
```

이 원칙은 Chain에도 동일하게 적용된다.

하위 Graph의 복잡성은 Node 내부에 캡슐화되고, 상위 Graph에는 해당 Node의 Report와 결과가 전달된다.

---

## 9. Report와 지식 압축

Boundary는 Report를 가지지 않는다.

Report는 항상 해당 작업 범위를 소유한 Node가 가진다.

```text
Step Reports
     ↓
Cycle Report
     ↓
Cycle Reports
     ↓
Chain Report
```

Cycle은 자신의 내부 Step Graph에서 축적된 정보를 Cycle Report로 요약할 수 있다.

Chain은 자신의 내부 Cycle Graph에서 축적된 정보를 Chain Report로 요약할 수 있다.

이 구조는 긴 Lineage에서 모든 세부 Step Report를 항상 Context에 넣지 않고 계층별로 지식을 압축하기 위한 기반이 된다.

중요한 원칙은 다음과 같다.

> Boundary는 지식을 만들지 않는다. Node가 지식을 만든다.
>
> Boundary는 그 지식이 어느 범위에서 생성되었고 언제 확정되었는지를 구분한다.

---

## 10. Artifact Snapshot

Artifact Snapshot도 장기적으로 Node에 귀속시키는 방향을 사용한다.

예를 들어 하나의 Cycle 내부에서 Artifact가 다음과 같이 변할 수 있다.

```text
Cycle Entry      Artifact A
     ↓
Step 1           Artifact B
     ↓
Step 2           Artifact C
     ↓
Cycle Exit       Artifact C
```

상위 Cycle Graph에서는 Cycle 하나를 통해 Artifact가 A에서 C로 변화했다는 사실만 볼 수 있다.

필요하다면 Cycle 내부 Step Graph를 열어 어느 Step에서 Artifact가 B 또는 C로 변화했는지 확인할 수 있다.

따라서 Artifact history 역시 계층적으로 탐색할 수 있다.

Artifact 저장 방식, snapshot 엔진, Git/libgit2와의 매핑은 이 문서에서 정의하지 않는다.

---

## 11. 현재 `cycle_entry` / `cycle_exit`의 의미

현재 GIL Grammar v0.1에는 다음 경계값이 존재한다.

```text
cycle_entry
cycle_exit
```

현재 구현 단계에서는 Cycle 객체가 아직 존재하지 않으므로 Step Graph의 시작과 끝을 표현하기 위해 이 경계를 직접 노출한다.

장기 모델에서 이들은 독립적인 Step Kind가 아니다.

```text
Cycle.entry boundary
        ↓
     Step Graph
        ↓
Cycle.exit boundary
```

즉 현재의 `cycle_entry` / `cycle_exit`은 향후 Cycle Node 내부로 들어갈 Step Graph 엔진의 외부 접점으로 이해한다.

---

## 12. 현재 Walk 구현과의 관계

현재 구현 중인 `Walk`는 새로운 GIL 도메인 개념이 아니다.

Cycle 객체와 일반화된 Graph 구조가 아직 존재하지 않는 상태에서, **Cycle 내부의 Step Graph를 메모리에서 실행하기 위한 최소 실행 구조**다.

따라서 현재 단계에서 다음 구조를 미리 구현하지 않는다.

- 공통 Node trait
- generic Node
- Chain 객체
- Cycle 객체
- Boundary 타입
- Subgraph 타입
- Graph abstraction
- Containment 구조
- Lineage 구조
- Artifact Snapshot
- Report 압축

현재 Walk 구현은 향후 Cycle Node 내부에 위치할 Step Graph 실행기의 초기 형태로 해석한다.

---

## 13. 현재 결정된 것과 아직 결정되지 않은 것

### 현재 방향으로 결정된 것

1. Chain, Cycle, Step은 공통 Node 모델로 일반화할 수 있다.
2. 모든 Node는 Entry/Exit Boundary를 가진다.
3. Open/Close는 별도 Node가 아니라 lifecycle state transition이다.
4. Boundary는 Report나 Knowledge를 생성하지 않는다.
5. Report는 Node 자체에 귀속된다.
6. Chain은 Cycle Graph를 포함한다.
7. Cycle은 Step Graph를 포함한다.
8. Step은 Subgraph를 가지지 않는다.
9. Containment와 Lineage는 서로 다른 관계다.
10. 현재 `cycle_entry` / `cycle_exit`은 Cycle Boundary를 Step Graph에서 바라본 표현이다.

### 아직 정의하지 않는 것

- 공통 Node의 실제 Rust 타입 설계
- Node ID 및 주소 체계
- Chain/Cycle의 정확한 Open/Close Report schema
- Cycle/Chain 상태 머신
- Cycle/Chain의 Success/Failure 전파 규칙의 상세
- 다중 부모 및 분기 Graph
- goto / revisit 시 계층별 동작
- Artifact Snapshot 저장 방식
- Git/libgit2 매핑
- Knowledge compression 알고리즘
- Lineage 계산 방식
- Persistence 형식

이 항목들은 실제 구현 필요가 생길 때 별도의 Step으로 정의한다.

---

## 14. 핵심 모델

현재의 장기 구조를 가장 짧게 표현하면 다음과 같다.

```text
Node
│
├── Entry Boundary
│       ↓
├── Open
│       ↓
├── Optional Subgraph
│       ↓
├── Report
│       ↓
├── Close
│       ↓
└── Exit Boundary
```

그리고 계층별 차이는 다음 하나로 압축된다.

```text
Chain → contains Cycle Graph
Cycle → contains Step Graph
Step  → contains no Subgraph
```

GIL의 상위 Graph는 하위 Graph의 세부 진행을 캡슐화하고, Node의 Report와 Artifact 상태를 통해 그 결과를 전달받는다.

이 모델은 GIL의 사고 기록, 지식 압축, Artifact versioning을 동일한 계층 구조 안에서 다룰 수 있도록 하기 위한 기반이다.
