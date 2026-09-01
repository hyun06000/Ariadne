# GIL Cycle Model v0.1

> Chain의 Cycle Graph, Cycle의 공통 수명, Interview Cycle의 최소 문법을 정의한다.

## 1. 목적

이 문서는 `GIL Specification v0.1`과 `GIL Node Model v0.1`이 열어 둔 다음 영역을
구체화한다.

- Chain 안에서 Cycle이 형성하는 Graph
- Cycle의 Open / Close와 Report
- Cycle 수준의 success / failure와 revisit
- Interview Cycle과 Experiment Cycle의 역할
- Interview Cycle의 최소 Step Grammar
- Chain의 시작과 종료에서 인간이 맡는 역할

이 문서는 구현 형식, 저장 엔진, 다중 부모 Merge를 정의하지 않는다. Artifact Snapshot의 계약은
`GIL Artifact Model v0.1`이 갖는다.

---

## 2. 재귀적 계층

GIL의 Reasoning 구조는 재귀적이다.

```text
Project
└── Chain Graph
    └── Chain
        └── Cycle Graph
            └── Cycle
                └── Step Graph
                    └── Step
```

각 계층에서 같은 원칙이 반복된다.

- 성공한 Node는 다음 자식 Node의 기반이 될 수 있다.
- 실패한 Node는 자식을 만들지 않는다.
- 실패는 삭제되지 않고 Report와 Knowledge로 Journey에 남는다.
- 실패 뒤에는 과거의 유효한 분기점으로 revisit하여 그 아래에 새 가지를 만든다. 직접 부모로
  돌아간 경우에만 실패 가지와 새 가지가 형제다.
- revisit은 과거 Node를 다시 열거나 수정하지 않는다.

failure는 막다른 오류가 아니다.

> **failure는 현재 가지의 가설이 충족되지 않았음을 나타내며, 지식을 유지한 채 다른 가지를
> 시도하기 위한 논리적 발판이다.**

---

## 3. Cycle Graph

Chain은 Cycle Graph를 포함한다.

Cycle Graph는 DAG를 형성할 수 있으며 부모·자식과 형제 관계를 가진다.

```text
Chain
└─ Cycle A
   ├─ Cycle B
   └─ Cycle C
```

Cycle B와 Cycle C는 Cycle A를 부모로 하는 형제다.

Cycle ID는 프로젝트 전체에서 유일하며 `cycle:C2`처럼 참조한다. Step은 Cycle 안에서 번호를
부여받고 `step:C2/S3`처럼 소속 Cycle을 포함해 참조한다. 현재 Cycle이 자명한 story나 status의
`#3`은 인간용 축약일 뿐 저장 reference가 아니다. 상세 규칙은 `GIL Node Model v0.1` §2.1을
따른다.

### 실패한 Cycle은 자식을 만들지 않는다

```text
Cycle A
└─ Cycle B (failure)
   └─ Cycle C              허용하지 않음
```

Cycle B가 실패한 뒤 새로운 시도를 하려면 유효한 Closed ancestor로 revisit한다.

```text
Cycle A
├─ Cycle B (failure)
└─ Cycle C
```

Graph에서 B와 C는 형제지만 Journey에는 B의 실패 경험이 남는다.

```text
A → B의 실패 경험 → A revisit → C
```

---

## 4. Cycle Kind

Cycle에는 최소 두 Kind가 있다.

```text
cycle.kind:
- interview
- experiment
```

두 Kind는 같은 Cycle 수명을 공유한다.

- Entry / Exit Boundary
- Open / Closed 상태
- 내부 Step Graph
- Cycle Report
- Artifact Exit 상태 (`GIL Artifact Model v0.1` §7)
- Kind에 따른 verdict
- revisit

차이는 내부 Step Grammar와 역할이다.

### Interview Cycle

사용자의 모호한 의도를 작은 문장으로 만들고, AI의 이해가 맞는지 인간에게 확인한다.

### Experiment Cycle

고정된 Define과 성공 조건 아래에서 하나의 실험 가설을 검증한다.

> **하나의 Experiment Cycle은 하나의 실험에 대응한다.**

---

## 5. Chain의 첫 Cycle

Chain의 첫 Cycle은 반드시 Interview Cycle이다.

프로젝트 최초 `gil start`도 같은 규칙을 따른다. 최초 Existence와 빈 Journey를 만든 뒤 그
Existence가 소유한 Interview Cycle을 첫 Cycle로 연다. 사용자 Relation과 목표를 CLI 설정값으로
미리 받지 않고 이 Interview 안에서 처음 형성한다.

```text
Chain Entry
    ↓
Interview Cycle
    ↓
Experiment Cycle
```

Chain은 사용자의 자연어 요청을 곧바로 실험하지 않는다.

먼저 심층 인터뷰를 통해 다음을 수행한다.

- 사용자의 큰 질문을 명확한 문장으로 만든다.
- 사용자의 의도와 제약을 확인한다.
- 큰 문제를 실험 가능한 작은 명제로 분할한다.
- 사용자가 그 이해와 탐색 범위를 승인하게 한다.

프로젝트 bootstrap Interview에는 다음 최소 범위가 반드시 포함된다.

- 사용자가 원하는 이름·별칭·호칭을 물어 프로젝트 로컬 Human Participant를 식별한다.
- 최초 Existence의 Journey에 Human Participant와 어떤 관계인지 자립적인 자연어로 기록한다.
  소유자·도구 또는 명령자·하위 실행자 관계를 추론하지 않는다.
- 사용자가 무엇을 하고 싶은지 큰 질문을 수집한다.
- AI가 이해한 의도를 작은 명제로 제안한다.
- 사용자가 yes/no로 명제를 승인하며 no이면 이유를 다시 묻는다.
- 승인된 Synthesis가 최초 탐색 체크리스트를 만든다.

승인된 Synthesis 전에는 Experiment Cycle을 열 수 없다.

Chain Open Report는 두지 않는다. Chain 생성 시에는 구조적 Open 상태만 존재하고, 첫 Interview
Cycle의 승인된 Synthesis가 Chain의 최초 탐색 범위를 만든다.

이 Synthesis는 큰 질문을 실험 가능한 작은 항목으로 원자화한 탐색 체크리스트를 소유한다.
체크리스트의 각 항목은 아직 Cycle Node가 아니라 앞으로 열 수 있는 Cycle 후보다.

v0에서는 체크리스트 후보를 독립적인 형제 가지로 미리 펼치거나 다중 부모로 합류시키지 않는다.
정상 진행에서는 체크리스트와 Interview 결과를 다음 Cycle로 직렬 전파하고, 현재 항목을 수행한
Cycle이 다음 항목의 Cycle로 이어진다.

```text
Opening Interview
        ↓ checklist: [A, B, C]
Experiment A
        ↓
Experiment B
        ↓
Experiment C
```

다만 Experiment가 실패하면 v0부터 Closed ancestor로 revisit하고, 그 ancestor 아래에 새 형제
Cycle을 열 수 있다. 이 실패 분기는 단일 Artifact 상태를 선택하여 되돌아가는 동작이며, 성공한
여러 Artifact를 결합하는 Merge가 아니다.

독립 체크리스트 후보들의 병렬 형제 실행, 성공 가지의 합류와 Artifact Merge는 v0에서 다루지
않는다.

---

## 6. Cycle Kind 사이의 연결

Chain의 첫 Cycle이 Interview여야 한다는 시작 규칙과, 성공한 Cycle의 자식 규칙은 구분한다.

```text
Interview(success)  → Interview | Experiment
Experiment(success) → Interview | Experiment
Experiment(failure) → 자식 없음
```

Interview Cycle은 `failure`로 닫히지 않는다. 인간이 승인한 Synthesis를 얻으면 `success`로
닫히고, 아직 얻지 못했다면 Open 상태로 남는다.

성공한 Experiment Cycle 뒤에 Interview Cycle을 열 수 있어야 한다.

```text
Interview A
└─ Experiment B (success, Artifact v2)
   └─ Interview C (Artifact v2 유지)
      └─ Experiment D
```

이는 실험 결과를 보존한 채 사용자에게 새로운 의문이나 Chain의 판정을 물을 수 있게 한다.

### Interview Cycle의 Artifact

Interview Cycle은 일반적으로 Artifact를 변경하지 않는다.

그러나 Artifact가 없다는 뜻은 아니다. Entry Snapshot 계승 규칙(`GIL Artifact Model v0.1`
§7.1·§7.5)에 따라 Interview Cycle은 저를 연 전이가 준 Artifact 상태를
그대로 상속하고, 변경하지 않았다면 같은 상태를 자신의 Exit로 전달한다.

```text
Interview Entry: Artifact v2
Interview Exit:  Artifact v2
```

Interview Cycle은 Artifact 관점에서 투명할 수 있다.

### 실패한 Experiment 뒤의 Interview

실패한 Cycle은 자식을 만들 수 없으므로 그 아래에 Interview를 열지 않는다. 과거의 유효한
Closed ancestor로 revisit한 뒤 그 아래에 새 Interview 가지를 만든다. 대상이 실패 Cycle의
직접 부모일 때 그 Interview가 실패 Cycle의 형제가 된다.

이때 실패한 Experiment의 Artifact 상태는 현재 상태로 채택되지 않지만, Report와 Knowledge는
Journey에 남아 새 Interview에 전달된다.

---

## 7. Experiment Cycle의 Define

하나의 Experiment Cycle에는 정확히 하나의 Define만 존재한다.

Cycle도 공통 Node이므로 Cycle을 Open한 Existence와 Close한 Existence는 같아야 한다. Cycle이
Open인 동안 다른 Existence로 전환할 수 없다. v0에서 하나의 실험을 여러 Existence가 나누어
소유하거나 진행하지 않는다.

Cycle은 내부 Step Graph를 담는 컨테이너 Node이므로 Cycle 자체가 장기 Active Will을 점유하지
않는다. Current Will은 Cycle 안에서 현재 실제 행동을 수행하는 가장 깊은 Step에 대응한다.
Cycle Close는 별도의 Cycle Will Done이 아니라 모든 내부 Step의 Close와 Cycle Report 조건을
검사한다.

Define이 닫히면 다음 두 항목은 바꿀 수 없다.

- Problem
- Success Condition

> **새로운 Define은 새로운 실험이며, 따라서 반드시 새로운 Experiment Cycle을 시작한다.**

같은 Cycle에서 바꿀 수 있는 것은 가설과 접근 방법이다.

```text
Define
├─ Hypothesis A
└─ Hypothesis B
```

Define이 잘못됐거나 성공 조건이 부족하다는 사실을 발견했다면 현재 Cycle은 `failure`로
닫는다. 실패 이유는 Report에 기록하고, 새로운 Define은 새 Cycle에서 작성한다.

---

## 8. Cycle Verdict

Cycle의 verdict는 정확히 두 값뿐이다.

```text
success
failure
```

별도의 `invalidated`, `inconclusive`, `aborted` verdict를 추가하지 않는다. 구체적인 이유는
Report에 기록한다.

### Experiment Cycle의 판정

Experiment Cycle의 verdict는 실험을 통해 가설과 성공 조건이 충족되었는지만 말한다.

```text
가설과 성공 조건 충족     → success
가설 또는 성공 조건 불충족 → failure
검증 불가능               → failure
실험 설계가 잘못됨         → failure
```

실험이 명제의 참·거짓을 알아내는 데 유용한 정보를 주었다는 이유만으로 success가 되지는 않는다.
가설이 충족되지 않았다면 failure다.

### Interview Cycle의 판정

Interview Cycle은 `success`로만 닫힐 수 있다. 인간이 Synthesis를 명시적으로 승인해야만
그 success가 성립한다.

따라서 Success의 근거는 Cycle Kind에 따라 분리된다.

```text
Experiment success → 해당 Cycle의 고정된 Define과 Success Condition
Interview success  → 인간이 yes로 승인한 Synthesis
```

Define에 근거해야 한다는 기존 Success 불변식은 Experiment에 적용된다. Define이 없는
Interview에 그 규칙을 확장하지 않는다.

Interview의 `no` 응답은 곧바로 Cycle failure가 아니다. AI의 현재 이해가 맞지 않다는 관측이며,
질문을 더 이어가야 한다.

사용자가 현재 방향의 탐색을 중단하거나 Chain의 대주제 자체가 잘못됐다고 확인한 경우에도,
AI가 그 의도를 정확한 Synthesis로 제시하고 사용자가 승인했다면 Interview는 성공한 것이다.
그 Synthesis가 Chain 종료를 제안한다면 `chain_verdict`가 `failure`일 수 있다.

필요한 인간 응답이나 승인을 아직 얻지 못했다면 논리적 failure를 만들지 않는다. Question 또는
Synthesis가 Open인 채로 남고, 따라서 Interview Cycle도 Open 상태로 남는다. 실행 오류나 연결
중단 역시 이 문서가 정의하는 Interview verdict가 아니다.

---

## 9. Cycle-level Revisit

### Artifact snapshot 경계 — 규범은 다른 문서가 갖는다

Cycle-level revisit은 **과거 Cycle Exit의 Artifact 상태로 돌아가는 동작**이므로 Artifact
Timeline 위에 선다. 그 계약의 규범 단일 진실 공급원은 `GIL Artifact Model v0.1`이다.

| 무엇 | 어디 |
|---|---|
| **Artifact 정체성** (경로 + 바이트) · 경로 정규화 · 관리 대상 종류 | Artifact Model §3 |
| 최초 기준 세계와 `gil start` | Artifact Model §4 |
| Snapshot 확정 권한 (start와 Verify close 둘뿐) | Artifact Model §5 |
| 비-Verify Step·Cycle close의 변경 거절 · manifest 비교 · 안정된 관측 | Artifact Model §6 |
| **Cycle의 `entry_snapshot_ref`·`exit_snapshot_ref` 저장 계약** | Artifact Model §7.1·§7.2 |
| Verify close 트랜잭션과 `snapshot_ref` 유도 | Artifact Model §7.3·§7.4 |
| World Current Snapshot 유도 | Artifact Model §7.6 |
| **Cycle Exit Snapshot 선택 규칙** | Artifact Model §7.5 |
| `gil restore` — 목표 유도 · 원자성 · 멱등성 · 확인 계약 | Artifact Model §8 |
| 저장과 원자성 경계 | Artifact Model §10 |

여기서는 **Cycle Graph가 지는 몫**만 적는다 — 어느 전이가 어느 세계에서 출발하는가.

### 전이가 Entry Snapshot을 정한다

모든 Cycle은 생성과 동시에 실재하는 `entry_snapshot_ref`를 지닌다. 그 값은 **그 Cycle을 연
전이가 출발한 세계**다.

| Cycle을 연 전이 | Entry Snapshot |
|---|---|
| 뿌리 (`gil start`) | 최초 기준 Snapshot |
| `open_child` | 부모 Cycle의 Exit |
| `revisit` | **revisit 대상 Cycle의 Exit** |
| merge (미래) | 별도 merge 규칙 — 아직 없다 |

> **구조적 `parent`와 갈래의 출처인 `revisit_from`을 같은 것으로 취급하지 않는다.**

`open_child`에는 `revisit_from`이 없다. revisit으로 열린 Cycle의 구조적 부모와 Artifact
세계의 출발점은 모두 revisit 대상이고, `revisit_from`만 버려진 실패 Cycle을 가리킨다. 이
셋을 각자 제자리에 두어야 "누구의 사고와 세계를 이어받았는가"와 "어느 실패가 이 새 갈래를
낳았는가"를 함께 답할 수 있다. 미래의 merge에서는 구조적 부모와 Entry 세계의 관계를 별도
규칙으로 다시 정한다.

### Cycle Exit

```text
Verify Closed   → 세계를 확정한다 (Artifact Model §5 — 바꿀 수 있는 유일한 경계).
                  바뀐 세계면 새 SnapshotRef, 그대로면 기존 것을 다시 가리킨다
Cycle Exit      → 새 Snapshot을 만들지 않는다.
                  마지막 Outcome의 구조적 lineage에서 가장 최근에 확정된 Verify
                  Snapshot을 기록하고, 없으면 그 Cycle의 Entry Snapshot을 계승한다.
```

버려진 가지의 Snapshot이나 이름이 가장 큰 Snapshot을 고르지 않는다. 이는 `basis_refs`(§16)와
`synthesis_ref`(§17)가 따르는 것과 **같은 계보 규칙**이다.

Entry와 Exit이 같은 `SnapshotRef`일 수 있다 — 그 Cycle이 세계를 바꾸지 않았다는 뜻이며,
Artifact를 건드리지 않는 Interview Cycle이 늘 그렇다.

### Staging은 GIL 상태가 아니다

GIL은 사용자에게 staging 상태나 `add` 동작을 노출하지 않는다. Verify Close가 현재 Artifact
tree 전체를 하나의 immutable snapshot으로 원자적으로 확정한다. 내부 저장 기법이 무엇이든
GIL Graph나 사용자 작업 흐름에 staging Node 또는 staging lifecycle을 추가하지 않는다.

### Revisit의 시간 규칙

Cycle revisit은 Step revisit과 같은 시간 규칙을 따른다.

- 대상은 현재 Cycle Lineage 위의 Closed ancestor여야 한다.
- 대상은 새 자식 Cycle을 가질 수 있는 유효한 분기점이어야 한다.
- 대상 Cycle 자체를 다시 열거나 수정하지 않는다.
- 대상 Cycle의 Exit에서 확정된 Artifact 상태로 돌아간다.
- Knowledge와 Journey는 되돌아가지 않는다.
- 이미 생성된 Cycle의 존재와 실패 기록은 사라지지 않는다.

```text
되돌아가는 것
- Current
- 대상 Cycle Exit의 Artifact 상태

되돌아가지 않는 것
- Knowledge
- Journey
- 실패 경험
- 이미 생성된 Cycle의 존재
```

revisit 뒤에 여는 새 Cycle의 구조적 부모는 **revisit 대상 Cycle**이다. 대상이 실패 Cycle의
직접 부모라면 새 Cycle과 실패 Cycle은 형제 관계가 된다. 더 먼 조상을 대상으로 삼으면 새
Cycle은 실패 Cycle의 형제가 아닐 수 있으므로, "형제"는 흔한 모양의 이름이지 일반 불변식이
아니다.

새 Cycle의 `entry_snapshot_ref`는 **revisit 대상 Cycle의 Exit Snapshot**이다. 실패 Cycle의
Exit을 계승하지 않는다. 실패 Cycle이 확정한 Snapshot 객체와 Report·Knowledge·Done Will은
그대로 남지만, 그 Artifact 모습은 새 시도의 현재 세계로 채택하지 않는다. 실패가 남긴 일부
Artifact를 선택적으로 가져오는 일은 revisit이 아니라 미래의 명시적 이월 또는 merge의 몫이다.

### Revisit의 상태 경계

revisit은 두 시간선을 구분한다.

```text
Artifact timeline
  대상 Cycle Exit에 새겨진 Snapshot을 현재 폴더에 다시 투영한다.

Journey timeline
  계속 전진한다. revisit 이전 상태로 복원하지 않는다.
```

복원은 개별 파일별 판단이 아니라 Snapshot 단위로 수행한다. 파일의 생성·수정·삭제는
snapshot 사이의 차이일 뿐, Cycle Graph가 파일별 규칙을 소유하지 않는다.

다음과 같은 GIL의 전역 상태는 Journey 시간선을 따르며 revisit의 영향을 받지 않는다.

- Cycle과 Step Graph
- Report와 Knowledge
- 실패 경험과 revisit 사건
- Existence와 현재까지 누적된 상태
- 실행된 Cycle 기록과 승인된 Synthesis

프로젝트 루트의 `.gil` 이 Artifact tree에서 제외된다는 것, 복원이 그 안을 건드릴 수 없다는
것, 그리고 더 깊은 곳의 `.gil` 이 중첩 GIL 경계로 거절된다는 것은
`GIL Artifact Model v0.1` §3.4가 정한다.

### Clean 세계 불변식

revisit은 현재 Artifact tree가 현재 경계의 `snapshot_ref`와 정확히 일치할 때만 실행할 수 있다.
기록되지 않은 생성·수정·삭제가 하나라도 있으면 dirty 상태이며 revisit을 거부한다.

```text
current Artifact tree == current snapshot_ref
  → revisit 허용

current Artifact tree != current snapshot_ref
  → revisit 거부
```

v0에는 dirty 상태를 덮어쓰는 강제 revisit을 두지 않는다. 현재 접근을 버리더라도 허용된 Step을
통해 변경 상태를 snapshot으로 확정하고, Analysis·Outcome과 Cycle Report를 작성하여 현재
실패 경로를 먼저 닫아야 한다. 실패의 Artifact snapshot과 Report는 Graph에 남는다.

Cycle revisit의 정당한 순서는 다음과 같다.

```text
1. 현재 Verify snapshot 확정
2. Analysis와 Outcome 작성
3. Cycle Report 작성, 실패 Cycle 종료
4. `gil revisit`으로 대상 Closed ancestor를 Current로 삼고 그 Exit Snapshot 복원
5. `pending_cycle_revisit`에 방금 닫은 실패 Cycle을 기록
6. 별도의 `gil open <kind>`로 대상 ancestor 아래에 새 Cycle 시작
```

Cycle-level revisit은 Step-level revisit과 같은 두 단계 구조를 따른다. `gil revisit` 자체는 새
Cycle의 Kind를 고르거나 새 Cycle ID를 발급하지 않는다. 다음 `gil open <kind>`가 새 Cycle을
만들며, 그때 `parent = revisit 대상`, `revisit_from = 실패 Cycle`,
`entry_snapshot_ref = revisit 대상의 exit_snapshot_ref`를 기록하고 pending 상태를 비운다.

같은 실패 Cycle에서 `gil revisit`을 두 번 실행할 수는 없다. 첫 실행 뒤 Current가 대상
ancestor로 옮겨졌기 때문이다. 그러나 그 뒤 열린 새 Cycle도 실패하면, 그 **새 실패 Cycle**의
Report가 같은 ancestor를 다시 대상으로 삼을 수 있다. 별도의 사용 횟수나 소진 플래그를 두지
않는다.

Step-level revisit도 같은 재귀 원리를 따른다. 현재 Step을 Report로 닫고 과거의 유효한 Step
경계의 세계로 복원한 뒤 새 Hypothesis 형제 가지를 연다.

내부 저장 엔진이 어떤 분기 기법을 쓰더라도 그것은 사용자가 직접 관리하는 별도 개념이 아니다.
새 Hypothesis 또는 새 Cycle 가지가 열릴 때 GIL Graph의 분기에 귀속되어 자동으로
생성되는 구현 세부이며, 그 어휘를 공개 표면에 노출하지 않는다
(`GIL Artifact Model v0.1` §14).

### 실행 경계

Cycle Report의 `revisit`은 **기록할 수 있고 실행할 수 있는** 방향이다(`GIL Artifact Model
v0.1` §11의 1번 상태).

`gil revisit`은 선언된 Closed ancestor로 Current와 Artifact 세계를 옮기고
`pending_cycle_revisit`을 남긴다. 이 명령만으로 새 Cycle을 만들지는 않는다. 이어지는
`gil open <interview|experiment>`가 새 Cycle을 열고 pending을 `revisit_from`으로 옮긴다.

둘 중 어느 단계에서도 대상 Cycle이나 실패 Cycle을 다시 열거나 수정하지 않는다.

---

## 10. 새 Cycle이 받는 것

새 Cycle은 부모의 세계에서 시작하지만 현재 Journey가 이미 배운 것을 가지고 시작한다.

최소 입력은 다음과 같다.

1. 현재 Chain의 승인된 방향
2. 구조적 부모 Cycle의 Cycle Report
3. 부모 이후 현재 Journey에서 닫힌 실패 Cycle Report들
4. 그 Cycle을 연 전이가 출발한 Artifact 세계 — 새 Cycle의 `entry_snapshot_ref`가 된다.
   `open_child`면 구조적 부모의 Exit이고, `revisit`이면 revisit 대상의 Exit이다
   (`GIL Artifact Model v0.1` §7.1)

실패 Cycle Report는 항상 전달한다. 같은 실패를 반복할 수 있기 때문이다.

실패 Cycle 내부의 모든 Step Report를 기본 Context에 넣지는 않는다. 압축된 Cycle Report를
전달하고, 세부 근거가 필요할 때 해당 Cycle 내부 Graph를 조회한다.

---

## 11. Cycle Close와 Cycle Report

내부 Outcome이 닫혀도 Cycle은 아직 Open이다.

```text
내부 Outcome 닫힘
        ↓
Cycle Report 작성
        ↓
Cycle Closed
        ↓
Cycle Exit
```

Cycle Report는 Cycle Close의 필수 조건이다. Cycle Exit은 Boundary이므로 자신의 Report를
갖지 않는다.

### Cycle Report의 최소 schema

```text
verdict
outcome_ref
handoff_summary
next_direction.action
next_direction.reason
next_direction.target_cycle_ref  (revisit일 때만, 예: cycle:C2)
```

#### verdict

Cycle Node 자신의 판정이다. 정확히 `success | failure` 중 하나다.

Cycle Report가 가리키는 Outcome도 Step Graph의 판정을 소유하지만, 두 verdict는 서로 다른
계층에 귀속된다. Cycle을 닫을 때 두 값이 같은지 검사한다.

```text
cycle_report.verdict == outcome_ref.verdict
```

두 값이 어긋나면 Cycle을 닫을 수 없다.

#### outcome_ref

내부 Step Graph의 마지막 Outcome Report를 가리킨다. verdict, lesson과 Step 수준의 방향을
근거로 연결한다. Outcome의 lesson과 Step 수준의 방향을 Cycle Report에 복제하지 않는다.
값은 `step:C2/S5` 형태의 StepRef다. `#5` 같은 화면 축약은 저장하지 않는다.

#### handoff_summary

다음 Cycle이 받아야 하는 현재 Cycle 내부 기록의 압축이다. 전역 Agent-side state인 Journey
전체를 요약하는 필드가 아니다.

다음을 중심으로 작성한다.

- 중요했던 실패
- 반증된 접근
- 중요한 전환점
- 반복하면 안 되는 시도
- 다음 Cycle이 반드시 알아야 할 미해결 위험

내부 Step Report 전체를 자동 투영하지 않는다.

### Cycle story의 선택적 투영

Cycle Report의 필드만 나열해서는 해당 Cycle에 참여하지 않은 협업자가 전체 실험을 이해하지
못할 수 있다. 그렇다고 Define과 Outcome의 내용을 `handoff_summary`에 복제하지 않는다.

`gil story`는 Cycle의 구조적 참조를 따라 인수인계에 필요한 최소 맥락을 선택적으로 투영한다.
Experiment Cycle의 닫힌 story 절에는 최소한 다음을 보여준다.

```text
실험한 것      ← 유일한 Define.problem
성공 기준      ← 유일한 Define.success_condition
결과           ← Cycle Report.verdict
성공·실패 이유 ← outcome_ref가 가리키는 Outcome.lesson
다음에 넘길 것 ← Cycle Report.handoff_summary
다음 방향      ← Cycle Report.next_direction
```

이 투영은 Step Report 전체를 펼치는 것이 아니다. Cycle을 식별하고 판정을 이해하는 데 필요한
시작점과 끝점만 읽는다.

```text
이 Cycle이 남긴 것  [experiment · 닫힘]
  실험한 것: ...
  성공 기준: ...
  결과: ...
  실패한 이유: ...
  다음 Cycle에 넘길 것: ...
  다음 방향: ...
```

Cycle Report schema에는 `problem`, `success_condition`, `lesson`을 다시 추가하지 않는다. 원본은
각각 immutable Define과 마지막 Outcome이며, story는 그 원본에서 읽는다.

### Story의 저장과 표현 분리

Report의 구조화된 원본과 Graph의 참조가 진실 공급원이다. plain text, Markdown과 HTML은 같은
read model을 서로 다른 방식으로 표현하는 renderer이며 별도의 판정을 소유하지 않는다.

```text
Graph + Reports + Artifact references
               ↓
           Read Model
          ┌────┼─────┐
          ↓    ↓     ↓
        text markdown html
```

v0 CLI의 기본 renderer는 plain text다. plain text도 제목, 빈 줄과 일관된 indentation으로 다음
블록을 시각적으로 구분해야 한다.

- 실험 정의
- 판정과 근거
- handoff
- 다음 방향

향후 Monitor는 같은 read model을 Markdown 또는 안전하게 제한된 HTML로 렌더링할 수 있다.
HTML 문자열을 Report의 진실 공급원으로 저장하거나, renderer마다 별도의 의미를 만들지 않는다.

### 시각 자료

모든 Node Report는 필요할 때 표, 차트, 이미지, 화면 캡처와 같은 시각 자료를 증거로 연결할 수
있어야 한다. 큰 바이너리나 임의의 HTML을 Report 본문에 직접 복제하지 않고 안정된 참조로
연결한다.

시각 자료 참조는 향후 최소한 다음 의미를 표현할 수 있어야 한다.

```text
kind
artifact_ref
caption
alt_text
provenance
```

- `artifact_ref`는 해당 자료가 속한 Artifact snapshot 또는 안정된 리소스를 가리킨다.
- `caption`은 이 자료가 어떤 주장이나 관측을 뒷받침하는지 설명한다.
- `alt_text`는 자료를 직접 볼 수 없는 독자에게 핵심 정보를 전달한다.
- `provenance`는 생성 또는 관측 출처를 추적한다.

정확한 schema, 저장 방식과 허용 media type은 시각 자료를 구현하기 전에 별도로 정한다. 첫
Monitor 구현은 이 결정을 기다리지 않고 구조적 사실과 신뢰하지 않는 텍스트만 표시한다. 그 전에도
Report의 추가 필드로 증거 참조를 기록할 수 있지만, renderer가 이해하지 못하는 참조를 임의로
실행하거나 삽입해서는 안 된다. HTML renderer의 기본 안전 경계는 `GIL Monitor Model v0.1`을
따른다.

#### next_direction

Cycle Graph에서 다음에 어디로 갈지 구조적으로 기록한다.

```text
next_direction.action:
  open_child | revisit | close_chain

next_direction.reason:
  비워 둘 수 없음

next_direction.target_cycle_ref:
  action이 revisit일 때 필수인 CycleRef
```

`next_direction.target_cycle_ref`는 `action`에 따른 **조건부 필드**다. 따라서 모든 Cycle
Report의 무조건적인 `close_requires`에는 넣지 않는다.

```text
action == revisit  → target_cycle_ref 필수
action != revisit  → target_cycle_ref 금지
```

값은 반드시 `cycle:C2` 형태의 typed `CycleRef`여야 한다. bare ID·화면 축약·StepRef·SnapshotRef는
받지 않는다. 대상을 기록할 때와 저장 상태를 복원할 때 다음을 모두 검사한다.

- 같은 Project의 Cycle Graph에 실재한다.
- Closed다.
- 현재 실패 Cycle 자신의 구조적 Lineage 위에 있으며 자기 자신이 아니다.
- 새 자식 Cycle을 가질 수 있는 유효한 분기점이다.
- Lineage는 구조적 `parent`만 따르며 `revisit_from`을 따라가지 않는다.

`target_cycle_ref`는 실패 Cycle을 닫는 순간에 방향의 근거와 함께 확정된다. 이후
`gil revisit`은 Cycle ID나 Snapshot ID를 인수로 받지 않고 이 참조를 읽는다.

Cycle Kind, verdict와 action은 다음처럼 맞물린다.

```text
Experiment success → open_child
Experiment failure → revisit
Interview success  → open_child | close_chain
```

`open_child`는 Cycle Graph 계층의 방향이다. 현재 Cycle이 이미 닫힌 뒤 그 Cycle을 부모로 다음
Cycle을 연다는 뜻이다. Step Outcome의 `close_cycle`과 반대되는 값이 아니다. 정상적인 성공
경로는 두 방향을 순서대로 사용한다.

```text
Outcome.next_direction.action = close_cycle
  → 현재 Cycle의 Step Graph를 끝냄

CycleReport.next_direction.action = open_child
  → 닫힌 Cycle을 부모로 다음 Cycle을 엶
```

`close_chain`은 성공한 Interview Cycle에서만 선택할 수 있다. 이때 해당 Interview가 참조하는
승인된 Synthesis에 `chain_verdict`가 있어야 한다. Experiment Cycle은 Chain을 직접 닫을 수 없다.

`open_child`는 다음 Cycle을 즉시 생성한다는 뜻이 아니다. 현재 성공 Cycle을 부모로 새 Cycle을
열 방향을 확정한다는 뜻이다.

---

## 12. Interview Cycle의 목적

인간은 자신이 원하는 것을 처음부터 정확한 문장으로 설명하지 못할 수 있다.

Interview Cycle의 기능은 모호한 생각을 잘게 나누어 문장으로 만들고, AI가 이해한 내용을
사용자에게 다시 제안하여 확인하는 것이다.

> **AI는 “이렇게 이해했다”고 제안하고, 사용자는 “그것이 내가 원한 것이다”라고 확정한다.**

Interview Cycle은 실험 계획을 고정하지 않는다.

- 하나의 Interview Cycle은 여러 Experiment 후보를 만들 수 있다.
- v0에서 후보들은 하나의 활성 경로를 따라 순차적으로 Cycle이 된다.
- 실패 후 revisit이 발생하면 대안 Cycle이 기존 실패 Cycle의 형제가 될 수 있다.
- 독립 후보들의 형제 실행과 성공 가지의 합류는 이후 버전에서 다룬다.
- 승인된 문제 분할은 변경 가능한 탐색 계획이다.
- 실제 Cycle DAG는 실험 결과에 따라 점진적으로 형성된다.
- 승인된 사용자 의도와 제약을 벗어나는 질문은 새로운 Interview Cycle에서 확인한다.

> **Interview는 고정된 DAG를 승인하는 것이 아니라, DAG가 자랄 수 있는 사용자 의도의 경계를
> 승인한다.**

---

## 13. Interview Cycle의 최소 Step Grammar

Interview Cycle v0의 내부 Step Kind는 네 가지다.

```text
question
interpretation
synthesis
outcome
```

최소 Grammar는 다음과 같다.

```text
Interview Entry
      ↓
Question
      ↓
Interpretation
   ┌──────┴──────┐
   ↓             ↓
Question      Synthesis
           │
      ┌────┴────┐
      ↓         ↓
 approved:no  approved:yes
      ↓         ↓
  Question   Outcome(success)
```

### 전이 의미

- `Entry → Question`: Interview는 사용자 질문으로 시작한다.
- `Question → Interpretation`: 응답을 받은 뒤에만 해석한다.
- `Interpretation → Question`: 중요한 모호성이 남았다.
- `Interpretation → Synthesis`: 사용자의 의도를 문장으로 제안할 준비가 됐다.
- `Synthesis(no) → Question`: 왜 아닌지 다시 묻는다.
- `Synthesis(yes) → Outcome(success)`: 인간 승인을 근거로 성공한다.

---

## 14. Question

Question은 질문 문장 하나가 아니라 질문과 인간 응답으로 완성되는 원자적 상호작용이다.

```text
Question OPEN
- AI가 질문과 보기를 제시
- 인간 응답 대기

Question CLOSED
- 질문과 응답이 함께 확정
```

질문만 있는 Question과 대답만 있는 Response는 존재하지 않는다. 별도의 Response Step Kind를
두지 않는다.

### Required Report

```text
question
choices
response
```

#### question

사용자에게 실제로 물은 문장이다. `prompt`라는 용어는 AI 실행 지시와 혼동될 수 있으므로
사용하지 않는다.

#### choices

가능한 한 사용자가 쉽게 답할 수 있는 객관식 보기를 제공한다.

모든 Question에는 다음 경로를 제공한다.

- `아직 잘 모르겠음 — 더 작은 질문 필요`
- `직접 입력`

보기는 사용자의 생각을 제한하는 정답 목록이 아니라 생각을 시작하기 위한 발판이다.
복수 선택 가능 여부를 명시한다. 적절한 보기를 만들 수 없다면 억지 객관식을 만들지 않는다.

#### response

선택 번호만 저장하지 않고 사용자의 원문 응답을 보존한다.

Question은 인간 응답이 오기 전에는 닫을 수 없다. AI의 해석은 Question Report에 섞지 않고
다음 Interpretation에 기록한다.

---

## 15. Interpretation

Interpretation은 직전 Question의 응답이 무엇을 의미하는지 해석한다.

### Required Report

```text
interpretation
unresolved
```

#### interpretation

사용자의 응답으로부터 정당하게 이해한 범위를 기록한다.

#### unresolved

사용자가 말하지 않아 아직 확정할 수 없는 중요한 범위를 기록한다. 중요한 unresolved가 남으면
다음 Question으로 묻는다. 충분히 해소되면 Synthesis로 갈 수 있다.

### Interpretation 불변식

> **Interpretation은 사용자의 응답을 더 큰 의도로 확장하지 않는다.**

응답을 정리하거나 좁힐 수는 있다. 그러나 응답 범위를 넘어선 의도를 사실로 추가하지 않는다.
새로운 의도가 필요하다면 반드시 다음 Question에서 확인한다.

---

## 16. Synthesis

Synthesis는 여러 Interpretation을 결합해 사용자의 의도를 명시적인 문장으로 제안하고,
같은 Node 수명 안에서 인간의 yes/no 승인을 받는다.

별도의 Approval Step Kind를 두지 않는다.

```text
Synthesis OPEN
- AI가 이해한 내용을 제시
- “이것이 맞는가?”라고 질문
- 인간의 yes/no 대기

Synthesis CLOSED
- statement와 approved가 함께 확정
```

### Required Report

```text
statement
basis_refs
approved
chain_verdict   (Chain 종료를 제안하는 Synthesis일 때만)
exploration_checklist   (Opening Interview의 Synthesis일 때)
```

#### statement

AI가 사용자에게 확인받으려는 명시적인 이해 또는 문제 분할이다.

사용자가 단순한 yes/no로 답하기 어렵다면 statement가 충분히 작고 명확하지 않은 것이다.

#### basis_refs

statement의 근거가 된 Interview Node들을 가리킨다. Synthesis는 근거 없는 새로운 목표나 제약을
추가할 수 없다. 먼저 Question으로 확인해야 한다.
각 값은 `step:C1/S1` 형태의 StepRef다. Report 문법에서는 block scalar 안에 한 줄에 하나씩
적는다.

```yaml
basis_refs: |
  step:C1/S1
  step:C1/S2
```

다음 불변식을 모두 만족해야 한다.

- 빈 줄을 제외한 각 줄은 canonical StepRef다.
- 참조 대상은 현재 Synthesis와 같은 Interview Cycle에 있다.
- 참조 대상은 Closed된 Question 또는 Interpretation이며 현재 Synthesis의 구조적 Lineage에
  속한다. ID 크기, 발급 순서나 닫힌 시각으로 선후를 추정하지 않는다.
- 같은 StepRef를 중복해서 적지 않는다.
- bare ID, `#1`과 쉼표로 이어 붙인 목록은 허용하지 않는다.
- 필드가 없거나 block scalar가 비어 있으면 모두 유효한 근거가 없는 같은 실패로 거절한다.

#### approved

정확히 다음 두 값 중 하나다.

```text
yes
no
```

`yes`만 명시적 승인이다.

- `yes` → Outcome(success)
- `no` → 왜 아닌지 묻는 Question

`no`는 Interview Cycle failure가 아니다.

#### chain_verdict

Synthesis가 Chain 종료를 제안할 때, 사용자가 승인하는 Chain 수준의 판정을 명시한다.

```text
success
failure
```

Closing Interview Cycle 자신의 verdict와 Chain verdict는 서로 다른 판정이다. 예를 들어
사용자가 Chain을 failure로 닫는 Synthesis를 승인했다면 Closing Interview Cycle은 인간 승인에
성공했으므로 `success`이고, Synthesis의 `chain_verdict`는 `failure`다.

#### exploration_checklist

Opening Interview의 Synthesis가 승인받으려는 원자화된 탐색 항목들의 순서 있는 목록이다.
각 항목은 아직 Cycle이 아니라 Cycle 후보다. v0에서는 이 순서를 따라 Interview 결과와 함께
다음 Cycle로 직렬 전파한다.

체크리스트는 고정 계약이 아니다. 실험 중 새 탐색 범위를 발견하면 이후 Interview에서 사용자에게
확인하여 남은 탐색 순서에 반영할 수 있다.

새 Interview Synthesis는 이전 Synthesis나 완료된 Cycle을 대체하지 않는다. 다음 두 상태를
구분한다.

```text
executed_cycles
  이미 실행된 Cycle과 그 Report. 불변이며 삭제하거나 덮어쓰지 않는다.

pending_exploration
  아직 Cycle로 열리지 않은 승인된 후보들의 현재 직렬 순서.
```

새 Synthesis는 승인된 변경을 `pending_exploration`에 누적한다. 항목을 추가하거나 순서를
조정하더라도 이미 실행된 항목과 그 결과는 `executed_cycles`에 그대로 남는다. 현재 남은
탐색 순서는 지금까지 승인된 Synthesis들을 순서대로 적용한 투영이다.

```text
Opening Synthesis: [A, B, C]
Experiment A:      completed
New Synthesis:     D를 다음 탐색으로 승인

executed_cycles:    [A]
pending_exploration:[D, B, C]
```

---

## 17. Interview Outcome

Interview Outcome은 기존 Outcome schema를 재사용한다.

```text
verdict
lesson
next_direction.action
next_direction.reason
next_direction.target_node_ref   (revisit일 때만인 StepRef)
```

Interview Outcome에는 다음 필드가 추가로 필요하다.

```text
synthesis_ref
```

규칙은 다음과 같다.

- Interview Outcome의 verdict는 항상 `success`다.
- `synthesis_ref`가 필수다.
- `synthesis_ref`는 같은 Interview Cycle에서 Closed되었고 현재 Outcome의 구조적 Lineage에
  속하는 Synthesis를 가리키는 StepRef다.
- 참조한 Synthesis의 `approved`는 `yes`여야 한다.
- 승인되지 않은 Synthesis를 근거로 success를 닫을 수 없다.

```text
success → close_cycle
```

응답이나 승인을 얻지 못한 Interview에는 Outcome을 만들지 않는다. 마지막 Question 또는
Synthesis와 Interview Cycle을 Open 상태로 둔다.

---

## 18. Chain의 성공과 실패

Chain의 큰 질문은 자연어 수준의 사용자 의도다. Experiment 결과만으로 Chain verdict를 자동
판정하지 않는다.

실험 Journey를 바탕으로 Interview Cycle을 열어 사용자에게 Chain의 큰 질문을 다시 제시한다.

Chain은 성공한 Closing Interview Cycle을 통해서만 닫을 수 있다. Closing Interview의
Synthesis가 승인되었다는 점에서 Interview verdict는 항상 `success`이며, 그 Synthesis가 승인한
Chain verdict는 `success | failure` 중 하나다.

```text
Opening Interview
        ↓
Experiment Cycles
        ↓
Closing Interview
        ↓
인간 승인
```

### Chain success

Closing Interview가 실험 결과를 큰 질문에 연결한 Synthesis를 제시하고, 사용자가 Chain을
success로 닫는 문장에 `yes`로 승인해야 한다. 이 Synthesis의 `chain_verdict`는 `success`다.

### Chain failure

현재 탐색 경로의 Experiment들이 계속 실패해 더 할 일이 없어 보이더라도 자동으로 Chain을
닫지 않는다.

Closing Interview는 다음을 사용자에게 설명한다.

- 어떤 Cycle 경로를 탐색했는가
- 어떤 가설들이 실패했는가
- 어디서 방향을 전환했는가
- 현재 남아 있는 새 아이디어가 있는가

그 뒤 사용자에게 다음 방향을 묻는다.

```text
1. 현재 Chain에서 새 아이디어를 더 실험한다
2. 문제를 다시 인터뷰하고 현재 Chain을 계속한다
3. 별도의 새 Chain을 Opening Interview로 시작한다
4. 현재 결론으로 이 Chain을 닫는다
5. 아직 잘 모르겠음
6. 직접 입력
```

선택은 Question에서 얻는다. AI는 선택을 작은 Synthesis로 명확히 만들고 최종 yes/no 승인을
받는다. 사용자가 현재 Chain을 failure로 닫는 문장에 `yes`로 승인해야 Chain failure가 된다.
이 Synthesis의 `chain_verdict`는 `failure`다.

---

## 19. Chain Report

Chain을 닫으려면 Chain Report가 필요하다.

최소 schema는 다음과 같다.

```text
verdict
closing_synthesis_ref
handoff_summary
```

### verdict

Chain Node 자신의 판정이다. 정확히 `success | failure` 중 하나다.

Closing Interview Cycle의 verdict를 그대로 사용하지 않는다. Closing Interview Cycle의
`success`는 인간 승인을 얻는 인터뷰가 성공했다는 뜻이며, 사용자가 승인한 Chain verdict는
`success`일 수도 `failure`일 수도 있다.

Chain을 닫을 때 다음 값이 같은지 검사한다.

```text
chain_report.verdict
==
closing_synthesis_ref가 가리키는 synthesis.chain_verdict
```

두 값이 어긋나면 Chain을 닫을 수 없다.

### closing_synthesis_ref

Chain success 또는 failure를 인간이 승인한 정확한 Synthesis를 직접 가리킨다. 중간의 Interview
Cycle이나 Outcome을 Chain Report에서 다시 참조하지 않는다.
값은 해당 Synthesis를 가리키는 StepRef다.

참조 대상은 다음 조건을 모두 만족해야 한다.

- 현재 Chain의 성공한 Closing Interview Cycle 안에 존재한다.
- `approved`가 `yes`다.
- `chain_verdict`가 존재한다.
- `chain_verdict`가 Chain Report의 `verdict`와 같다.

### handoff_summary

다음 Chain이 받아야 하는 중요한 Cycle 경로, 실패, 전환점과 남은 의문을 압축한다.

전역 Agent-side state인 Journey 전체를 요약하는 필드가 아니다. 현재 Chain 내부에서 다음
Chain으로 넘겨야 할 내용만 선별한다.

전체 Cycle Report를 자동 투영하지 않는다. 세부 기록은 Graph에 남아 있으며 필요할 때 조회한다.

---

## 20. 실행 모드에 관한 비규범적 예시

인간이 Journey에 참여하는 밀도는 작업에 따라 달라질 수 있다.

```text
autonomous
milestone
stepwise
```

- 프론트엔드 개발처럼 화면 변화를 하나씩 확인해야 하는 작업에는 `stepwise`가 적합할 수 있다.
- 데이터 분석처럼 개별 실험보다 큰 결과와 방향 전환이 중요한 작업에는 `milestone`이 적합할 수 있다.
- 하이퍼파라미터 튜닝처럼 최종 결과가 중요한 반복 작업에는 `autonomous`가 적합할 수 있다.

이 구분은 현재 Cycle Grammar의 일부가 아니다. 향후 GIL 사용 예시와 UI를 설계할 때 다룬다.
어떤 모드에서도 Chain의 최종 success / failure는 인간이 Interview에서 승인한다.

---

## 21. 현재 결정하지 않는 것

이 문서는 다음을 의도적으로 결정하지 않는다.

- Interview 질문 선택지를 생성하는 알고리즘
- 사용자의 자연어 응답을 구조화하는 구현 방식
- 실험 후보 계획의 저장 schema
- 탐색 체크리스트 항목의 식별자·상태·의존 관계 schema
- Chain Report 이후 Project 수준의 `next_direction`
- Chain-level revisit의 구체적인 명령과 상태 머신
- 다중 부모 Cycle과 Artifact Merge
- 독립 체크리스트 항목의 형제 실행과 합류 규칙
- 동시에 진행되는 Cycle들의 Merge
- Artifact Snapshot 저장 엔진
- `.gilignore`의 형식, 기본 제외 목록과 기존 ignore 파일 호환 정책
- 실행 모드의 전환 명령과 승인 정책
- 인간 부재·연결 중단 시 Interview의 timeout 정책
- 장기간 Open인 Question, Synthesis와 Interview Cycle의 운영·정리 정책

다중 부모 Merge는 서로 다른 성공 Artifact 가지를 실제로 결합해야 하는 사례가 나타날 때
별도로 설계한다. 성공한 Experiment의 Artifact를 유지한 채 Interview를 여는 문제는 단일
부모-자식 연결로 해결하며 Merge를 요구하지 않는다.

### 단계별 구현 범위

구조 전체를 한 번에 구현하지 않는다.

```text
v0
  한 번에 하나의 활성 Cycle 경로
  실행된 Cycle과 Journey 보존
  승인된 남은 탐색 순서의 직렬 전파
  실패 Cycle에서 Closed ancestor로 revisit
  형제 Cycle을 통한 분기 표현
  대상 ancestor Exit의 Artifact 상태 복원

later
  독립적으로 성공한 형제 Cycle들의 합류
  다중 부모 Report 전달과 Artifact Merge
```

v0의 형제 Cycle은 실패 후 revisit으로 생기는 대안 가지다. 동시에 여러 성공 가지를 활성화하거나
합치는 기능은 아니다. 이 단계 구분은 이후 구조의 가능성을 부정하지 않으면서, Artifact Merge를
요구하지 않는 분기부터 먼저 구현하기 위한 순서다.

---

## 22. 핵심 문장

> **Chain은 Interview로 시작하고 Interview로 판정된다.**

> **Interview Cycle은 성공으로만 닫힌다. Chain의 failure도 성공한 Closing Interview에서
> 인간이 승인한다.**

> **Interview는 실험 계획을 구속하지 않고, 실험 DAG가 자랄 수 있는 사용자 의도의 경계를
> 승인한다.**

> **하나의 Experiment Cycle에는 하나의 고정된 Define이 있고, 새로운 Define은 새로운
> Cycle을 시작한다.**

> **새 Cycle은 부모의 세계에서 시작하지만, 현재 Journey가 이미 배운 실패를 모두 가지고
> 시작한다.**

> **Question은 질문과 응답의 쌍이고, Synthesis는 명제와 인간 승인의 쌍이다.**

> **Interpretation은 사용자의 응답보다 더 큰 의도를 확정하지 않는다.**

> **failure는 끝이 아니라, 재귀적 Graph에서 다른 가지를 만들기 위한 논리적 발판이다.**
