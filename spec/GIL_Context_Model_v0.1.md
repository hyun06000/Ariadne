# GIL Context Model v0.1

> 같은 GIL Graph를 인간, 새 Agent 세션과 감사자가 서로 다른 해상도로 읽는 규칙을 정의한다.

---

## 1. 목적

GIL의 기록은 계속 누적된다. 매 Step을 열 때 전체 기록을 다시 LLM context에 넣으면 같은 내용이
반복되고, 프로젝트가 길어질수록 context 비용이 불필요하게 증가한다.

반대로 지나치게 압축하면 새 Agent나 새 세션이 현재 작업을 이어갈 수 없다.

이 문서는 다음 세 투영을 분리하여 이 문제를 다룬다.

```text
story    인간이 현재 상황을 이해한다.
context  새 Agent 세션이 현재 작업을 이어받는다.
history  전체 실행 경로를 감사하고 조사한다.
```

세 투영은 별도의 상태를 소유하지 않는다. Graph, Report와 Artifact reference가 유일한 진실
공급원이며, 각 투영은 같은 read model을 목적에 맞는 해상도로 읽는다.

---

## 2. 핵심 원칙 — 거리에 따른 해상도

현재 행동에서 멀리 있는 기록일수록 상위 Report로 압축하고, 가까운 기록일수록 자세하게 읽는다.

```text
이전 Chain들               → Chain Report
현재 Chain의 이전 Cycle들 → Cycle Report
현재 Cycle                 → Step Report
현재 Node                  → 상태, 요구 schema, 허용된 다음 행동
```

이를 Context Resolution Rule이라 부른다.

```text
Project
├─ Previous Chains          coarse: Chain Report
└─ Current Chain
   ├─ Previous Cycles       medium: Cycle Report
   └─ Current Cycle
      ├─ Previous Steps     fine: Step Report
      └─ Current Node       exact: current state and rules
```

상위 Report가 존재하는 닫힌 범위의 내부 Graph를 기본 context에 다시 펼치지 않는다.

---

## 3. 압축은 삭제가 아니다

context에서 과거 Step을 생략해도 Step Node와 Report는 Graph에 그대로 존재한다.

- Knowledge를 삭제하지 않는다.
- 실패 가지를 삭제하지 않는다.
- Artifact snapshot을 삭제하지 않는다.
- 필요하면 history 또는 명시적 조회로 세부 근거를 읽을 수 있다.

압축은 무엇이 존재하는지를 바꾸지 않고, 현재 목적에 어떤 해상도로 투영하는지만 바꾼다.

`existence_ref`와 `journey_ref`는 기본 context에서 재귀적으로 펼치지 않는다. 복원은 동일한
원본 Existence와 Journey를 선택한다는 뜻이며 전체 역사와 모든 Knowledge·Memory를 프롬프트에
복제한다는 뜻이 아니다.

```text
Node 하나의 provenance              O(1) reference
Journey revision                    고정된 구성 요소 head reference
기본 Action Context                 선택된 현재 투영
명시적 history 또는 ref 조회        요청한 범위만 펼침
```

renderer는 historical provenance reference를 만났다는 이유만으로 그 reference가 다시 가리키는
과거 reference를 자동 확장하지 않는다.

---

## 4. `gil story`

`gil story`는 인간을 위한 현재 Journey의 설명이다.

주요 사용자는 CLI나 GUI를 직접 사용하지 않고 AI와 채팅하는 사람이다. 대화 세션에는 이미 최근
맥락이 있으므로 전체 실행 기록을 매번 반복할 필요가 없다.

기본 story는 다음 질문에 답한다.

- 지금 어떤 큰 문제를 다루고 있는가?
- 현재 어떤 실험을 하고 있는가?
- 어디까지 진행됐는가?
- 이 위치로 오게 만든 중요한 성공·실패와 전환은 무엇인가?
- 다음에 무엇을 하려는가?

기본 story는 다음을 하지 않는다.

- 모든 이전 Chain의 내부 Cycle을 펼치지 않는다.
- 모든 이전 Cycle의 Step을 펼치지 않는다.
- LLM onboarding에 필요한 schema 전체를 보여주지 않는다.
- 전체 감사 로그를 대신하지 않는다.

story의 문장은 `GIL Specification v0.1`의 Report 작성 불변식을 따라 객관적이고 자립적으로
읽혀야 한다.

---

## 5. `gil context`

`gil context`는 새로운 Agent 세션이 현재 위치에서 작업을 이어가기 위한 계층적 onboarding
입력이다.

명시적으로 다음과 같은 때 호출한다.

- 새로운 AI 세션이 시작될 때
- 다른 Agent가 프로젝트를 이어받을 때
- 대화 context가 압축되어 과거 작업 설명이 사라졌을 때
- 장시간 중단한 작업을 재개할 때
- 인간 또는 Agent가 현재 실행 context의 재구성을 요청할 때

새 Step이나 Node를 열 때마다 전체 `gil context`를 자동으로 출력하지 않는다. 같은 세션에서는
이미 전달된 대화 context를 사용하고, 새 Node의 역할·필수 Report·다음 행동에 관한 delta만
안내한다.

### Context의 최소 구성

```text
[GIL 규칙]
  현재 Node에 적용되는 문법과 Report 원칙

[프로젝트에서 이어받은 것]
  이전 Chain들의 Chain Report

[현재 Chain]
  승인된 방향
  이전 Cycle들의 Cycle Report
  현재 Journey에서 반드시 알아야 하는 실패 Cycle Report

[현재 Cycle]
  현재 Cycle의 Define
  현재 Cycle 안에서 지금까지 생성된 Step Report
  현재 Artifact 상태

[현재 위치]
  Current Node와 상태
  clean / dirty
  허용된 구조적 행동
```

아직 구현되지 않은 계층이나 상태는 출력하지 않는다. 존재하지 않는 Chain, Artifact snapshot 또는
dirty 상태를 있는 것처럼 표현하지 않는다.

Context는 현재 무엇이 참인지 기술한다. 현재 Agent가 실제로 무엇을 수행하려 하는지는 Journey의
Current Will이 담당하고, GIL Grammar는 현재 또는 작업 완료 뒤 허용되는 구조적 행동을 담당한다.
새 Agent onboarding에서는 세 절을 구분해 함께 읽는다.

```text
Action Context
= Lineage(World Current)
+ Journey(Existence Current)
+ Applicable Grammar
```

Will의 생명주기와 불변식은 `GIL Will Model v0.1`을 따른다. Context는 Current Node를 보고
구체적인 Will을 추측하거나 생성하지 않는다.

새 세션은 `GIL Existence Model v0.1`에 따라 World Current와 Existence Current를 독립적으로
복원한다. 모델이나 세션이 달라져도 같은 Existence를 선택하면 같은 Journey와 Current Will을
이어간다.

최초 Interview가 진행 중이면 context는 정상 Experiment 상태를 지어내지 않고, Current
Existence의 Relation·목표·Synthesis 중 아직 형성되지 않은 것을 보여준다. 승인된 Synthesis
이후에는 Current Existence와 사용자와의 Relation을 onboarding에 필요한 해상도로 투영한다.

실행형 Open Node에서는 Active Will을 별도 절로 보여준다. Applicable Grammar는 실제 작업을
마친 뒤 Report와 함께 `gil close`를 실행하면 Will Done과 Node Close가 함께 확정된다고
표시한다.

### 실패 지식

해상도 압축은 실패 지식을 누락할 이유가 아니다.

- 닫힌 과거 Cycle의 실패는 Cycle Report 해상도로 전달한다.
- 현재 열린 Cycle 안의 실패한 Step 접근은 Step Report 해상도로 전달한다.
- 현재 방향과 무관한 세부 Step은 기본 context에서 생략할 수 있다.
- 동일한 실패를 피하는 데 필요한 Report는 반드시 포함한다.

정확한 relevance 선택 알고리즘은 이후에 결정한다. v0에서는 구조적 lineage와 명세가 항상
전달하도록 요구한 실패 Report를 기준으로 한다.

---

## 6. `gil history`

`gil history`는 전체 실행 경로를 감사하고 조사하기 위한 투영이다.

다음을 펼칠 수 있어야 한다.

- 모든 Chain과 Chain Report
- 모든 Cycle과 Cycle Report
- 모든 Step과 Step Report
- parent와 revisit_from
- 실패 가지와 전환점
- Artifact snapshot reference

history는 기록의 완전성을 우선하고 context 크기를 줄이는 것을 목표로 하지 않는다.

v0에서 명령이 아직 구현되지 않았더라도 전체 Graph는 저장되어야 한다. story 또는 context에서
생략했다는 이유로 원본을 잃어서는 안 된다.

---

## 7. 구현 단계별 Context

### 7.1 M2에서의 최소 Context

M2에는 Chain과 Artifact snapshot이 아직 없다(Artifact는 M3에서 들어온다 —
`GIL Artifact Model v0.1`). 따라서 첫 `gil context`는 다음으로 제한한다.

```text
[이전 Cycle]
  현재 Cycle의 ancestor를 Cycle 해상도로 선택적 투영
  Define에서 실험 목적과 성공 기준을 읽음
  outcome_ref가 가리키는 Outcome에서 판정의 교훈을 읽음
  Cycle Report에서 verdict, handoff, next_direction을 읽음
  ancestor Cycle의 Step Graph는 펼치지 않음

[현재 Cycle]
  현재 Cycle의 Step Report

[현재 위치]
  Current Cycle과 Step
  허용된 다음 행동
```

검사 가능한 핵심 불변식:

```text
previous_cycle_step_graph_expansions_in_context == 0
previous_cycle_projections_in_context == ancestor_count
current_cycle_step_occurrences_in_context == current_cycle_step_count
```

현재 Cycle이 첫 Cycle이라면 이전 Cycle 절은 없다.

여기서 "Cycle Report 해상도"는 Cycle Report에 물리적으로 저장된 필드만 출력한다는 뜻이
아니다. Cycle을 대표하는 정보를 원본 Graph와 구조적 참조에서 읽되, 내부 Step의 시간순
전개를 다시 보여주지 않는다는 뜻이다.

이전 Cycle의 선택적 투영은 다음 원본만 읽는다.

```text
실험 목적과 성공 기준 → 그 Cycle의 유일하고 immutable한 Define
판정의 교훈           → Cycle Report.outcome_ref가 가리키는 Outcome
판정과 인수인계       → Cycle Report.verdict, handoff_summary, next_direction
```

이 투영은 Define이나 Outcome의 내용을 Cycle Report에 복제하여 저장하지 않는다. Step ID,
Hypothesis, Verify, Analysis와 내부 전환 과정을 펼치지 않으므로 Step Graph 확장이 아니다.
`handoff_summary`는 다음 Cycle이 반드시 받아야 할 지식에 집중하며, 실험 목적·성공 기준·판정
이유를 모두 다시 서술할 책임을 지지 않는다.

### 7.2 M3 Artifact Context

M3의 `gil context`는 전체 Snapshot registry나 파일 목록을 반복하지 않는다. 새 Agent가 지금
행동을 이어 가는 데 필요한 세계 정보만 현재 위치 해상도로 투영한다.

```text
[현재 세계]
  현재 위치에서 유도한 공개 SnapshotRef
  작업 폴더가 그 세계와 같은지(clean / dirty)
  현재 열린 Node가 변경을 확정할 수 있는 Verify인지
  dirty인 비-Verify 자리라면 gil restore로 되돌릴 수 있다는 다음 행동
```

내부 manifest·blob 주소, Snapshot registry 전체, 모든 파일의 경로와 변경 목록, 이전 Cycle마다
반복되는 Artifact 세부는 출력하지 않는다.

`gil context`는 명시적으로 요청될 때 현재 폴더를 한 번 관측할 수 있다. 그러나 모든 `open`과
`close`가 전체 Context를 되풀이하지는 않는다. 일상 명령은 현재 행동에 필요한 짧은 nudge를
주고, 전체 onboarding은 새 세션이나 사용자가 요구한 때에만 `gil context`가 맡는다.

---

## 8. Story와 Context의 차이

두 투영은 비슷한 정보를 읽을 수 있지만 독자와 책임이 다르다.

| | story | context |
|---|---|---|
| 독자 | 인간 | 새 Agent 세션 |
| 목적 | 현재 상황 이해 | 작업 재개 |
| 표현 | 자연어 중심 | 구조적이고 빠짐없는 onboarding |
| 문법 정보 | 필요한 만큼 | 현재 행동에 필요한 규칙 포함 |
| 과거 세부 | 중요한 전환만 | 계층별 Report 해상도 |
| 전체 감사 | 하지 않음 | 하지 않음 |

두 투영 모두 과거 범위의 내부 Step 전체를 기본으로 반복하지 않는다.

---

## 9. Node Open의 출력

Node Open은 전체 context 재전송 사건이 아니다.

최소 delta만 보여준다.

```text
- 새 Node의 Kind와 상태
- 이 Node가 답해야 하는 핵심 질문
- Close에 필요한 Report 필드
- Current Will의 delta 또는 Active Will이 없다는 사실
- 작업 완료 뒤 허용되는 구조적 행동
```

새 세션 여부를 GIL이 추측하여 자동으로 전체 context를 출력하지 않는다. Agent 또는 host가
세션 경계에서 `gil context`를 명시적으로 호출한다.

---

## 10. Renderer

story, context와 history는 read model이며 renderer와 분리한다.

```text
Read Model
├─ plain text
├─ Markdown
├─ HTML
└─ structured data
```

renderer가 바뀌어도 포함되는 지식의 해상도와 의미가 바뀌어서는 안 된다. Monitor는 같은 read
model을 사용하되 사람이 필요할 때 상위 Report에서 내부 Graph로 점진적으로 펼칠 수 있게 한다.

---

## 11. 현재 결정하지 않는 것

- `gil context`의 Markdown·JSON 출력 schema
- context token budget과 자동 절단 정책
- relevance scoring
- 오래된 Chain Report를 Project 수준으로 다시 압축하는 규칙
- 분산 Agent 사이의 context 전송 형식
- `gil history`의 필터와 검색 문법
- Monitor의 접기·펼치기 UI
- 시각 자료를 context에 포함하는 조건
- Journey 구성 요소별 context 투영과 token budget
- 특정 provenance reference를 명시적으로 펼치는 조회 문법

---

## 12. 핵심 문장

> **GIL은 기억을 무조건 많이 전달하지 않는다. 현재 위치와 계층적 거리에 따라 필요한
> 해상도로 지식을 전달한다.**

> **story는 인간이 현재를 이해하기 위한 것이고, context는 새 Agent가 현재에서 다시 시작하기
> 위한 것이며, history는 전체 경로를 감사하기 위한 것이다.**

> **압축은 삭제가 아니다. 상위 Report 뒤에 있는 내부 Graph는 필요할 때 다시 읽을 수 있다.**
