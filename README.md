# Ariadne

> **GIL은 인간과 AI의 문제 해결을 검증 가능한 실험 그래프로 만드는 local-first 실행
> 프로토콜이다.**

AI가 무엇을 했는지 나중에 추적하는 것만으로는 충분하지 않다.

GIL은 AI가 다음 행동으로 넘어가기 전에 무엇을 정의하고, 실행하고, 관측하고, 해석하고,
보고해야 하는지를 구조적으로 제한한다. 실패한 접근은 삭제하지 않으며, 과거의 Artifact 상태로
돌아가더라도 그 실패에서 얻은 지식은 잃지 않는 것을 목표로 한다.

```text
Artifact는 되돌릴 수 있다.
Journey는 되돌아가지 않는다.
```

v0의 지속적 Existence와 Journey는 프로젝트 로컬 `.gil`에 저장한다. 모델이나 세션이 바뀌어도
같은 프로젝트의 Current Existence를 읽어 동일한 존재로 작업을 이어간다. `gil start`는 최초
Interview Cycle을 연다. 설계상 사용자 Relation과 프로젝트 목표는 설정값으로 미리 지어내지
않고 그 Interview 안에서 형성하며, 사용자와 Existence는 소유자와 도구가 아니라 프로젝트를
함께 만드는 동등한 협력자다.

현재 구현은 dogfood 단계다. Bootstrap Interview, 여러 Cycle, 지속되는 Existence와 Will,
format 4 Artifact Snapshot, dirty gate, 중단 복구 가능한 `gil restore`, 그리고 필요한 규칙
하나만 조회하는 bundled Manual이 동작한다.

전체 명세를 미리 읽지 않은 새 Agent 세션이 `gil context`와 주소 가능한 Help Topic만으로
실제 작업과 GIL Cycle을 완주하는 것을 Claude와 Codex 계열에서 각각 확인했다. 실패한 Cycle에서
유효한 Closed ancestor로 돌아가 그 아래에 새 시도를 여는 **Cycle-level revisit**도 CLI와
Artifact 복구까지 연결되어 있다.

---

## 왜 만드는가

장시간 실제 프로젝트를 수행하는 AI에게는 다음 문제가 생긴다.

- 무엇을 해결하려 했는지보다 마지막 출력만 남는다.
- 실패한 접근과 방향 전환의 이유가 사라진다.
- 파일을 과거 상태로 되돌리면 이후에 얻은 지식까지 잃기 쉽다.
- 실행 trace는 많지만 다음 협업자가 무엇을 이어받아야 하는지 알기 어렵다.
- 인간은 Agent가 너무 멀리 진행한 뒤에야 잘못된 문제를 풀고 있었다는 사실을 발견한다.

GIL은 문제 해결을 **Step → Cycle → Chain**의 재귀적 Graph로 구성하여 이 문제를 다룬다.

```text
Project
└─ Chain Graph
   └─ Chain
      └─ Cycle Graph
         └─ Cycle
            └─ Step Graph
               └─ Step
```

- **Step** — 지금 수행할 하나의 원자적 사고 또는 행동
- **Cycle** — 고정된 문제와 성공 조건 아래 수행하는 하나의 실험
- **Chain** — 인간의 큰 질문에서 시작해 여러 실험을 묶는 탐색 범위

---

## 핵심 설계

### Trace가 아니라 Protocol

Observability 도구는 Agent가 무엇을 했는지 기록한다.

GIL은 그보다 앞에서 **어떤 기록과 상태가 있어야 다음 행동이 허용되는지**를 정의한다.

```text
Define → Hypothesis → Verify → Analysis → Outcome
```

- Report 없이는 Step을 닫을 수 없다.
- 열린 Step을 둔 채 허용되지 않은 다음 Step으로 갈 수 없다.
- Artifact를 변경하고 snapshot을 확정할 수 있는 Step은 Verify뿐이다.
- Cycle은 마지막 Outcome과 일치하는 Cycle Report가 있어야 닫힌다.

### 실패는 Graph를 성장시키는 사건

실패는 삭제하거나 성공으로 포장할 예외가 아니다.

```text
Cycle A (success)
├─ Cycle B (failure)
└─ Cycle C (new attempt)
```

실패한 Cycle은 자식을 만들지 않는다. 유효한 Closed ancestor로 revisit한 뒤 그 아래에 새로운
가지를 연다. 대상이 실패 Cycle의 직접 부모일 때 새 가지는 실패 Cycle의 형제가 된다. 실패
Report와 Knowledge는 이후 Journey에 남아 같은 시도를 반복하지 않게 한다.

### 두 개의 시간선

```text
Revisit
├─ Artifact timeline → 구조가 가리키는 snapshot으로 복원
└─ Journey timeline  → 현재까지의 경험과 지식을 유지
```

GIL에서 과거로 돌아간다는 것은 과거의 세계를 다시 선택하는 것이지, 과거의 Agent로 돌아가는
것이 아니다.

### 인간의 의도는 인간이 확정한다

Interview Cycle은 모호한 사용자 요청을 작은 명제로 나누고 AI의 해석을 인간에게 다시
확인한다.

- AI는 사용자의 응답보다 넓은 의도를 확정하지 않는다.
- Interview는 인간이 승인한 Synthesis를 근거로 성공한다.
- Chain의 최종 success 또는 failure는 Closing Interview에서 인간이 승인한다.

### Report는 인수인계 문서다

모든 Step, Cycle과 Chain Report는 다음 원칙을 따른다.

- 정의되지 않은 약어와 내부 코드명만으로 대상을 표현하지 않는다.
- 관측과 해석을 구분한다.
- 성공·실패를 기준과 증거로 추적할 수 있게 쓴다.
- 해당 Node에 참여하지 않은 협업자도 독립적으로 이해할 수 있게 쓴다.
- 세부 기록 전체를 복제하지 않고 다음 계층이 반드시 받아야 할 내용을 압축한다.

GIL은 모델의 비공개 chain-of-thought를 저장하려는 시스템이 아니다. 협업을 위해 제출 가능한
가설, 실행, 관측, 해석, 판정, 근거와 다음 방향을 기록한다.

---

## 현재 구현 상태

### 동작함

- Define → Hypothesis → Verify → Analysis → Outcome Step Grammar
- Step Open / Close와 Kind별 Report 검증
- Step-level revisit과 형제 Hypothesis
- 프로세스를 넘는 local persistence
- Bootstrap Interview와 승인된 Synthesis
- 여러 Cycle의 parent, lineage와 handoff
- 지속되는 Existence, Journey와 Active/Done Will
- Cycle Report와 기본 경로인 `gil close` (`gil cycle close`는 호환 명령)
- 마지막 Outcome만 Cycle 판정 근거로 허용
- 사람이 읽는 `gil status`와 `gil story`
- 새 Agent 세션이 이어받는 계층적 `gil context`
- Define·Outcome을 선택적으로 투영하는 협업자용 Cycle story
- 제목·개행·indentation으로 구분되는 plain text Cycle Report
- 이전 저장 형식을 조용히 무시하지 않는 복원 검사
- format 4 Snapshot registry와 내용 주소 객체 저장소
- `gil start`의 실제 프로젝트 세계 확정
- Verify close의 Snapshot 확정과 비-Verify dirty gate
- Cycle Entry/Exit Snapshot과 World Current 유도
- 프로젝트 단위 잠금과 중단 뒤 임시 객체 회수
- 현재 Snapshot과 clean/dirty를 보여 주는 `gil status`
- 중단 뒤 rollback 가능한 `gil restore`
- 바이너리에 함께 실리는 Manual과 `gil help <주제>` 조회
- 현재 상태에 맞는 Topic만 보여 주는 `gil help`
- 거절이 복구 Topic 하나를 가리키는 오류 Router
- Cycle-level `gil revisit`과 대상 Exit 세계 복원
- `parent = target`, `revisit_from = failure`, `entry = target.exit`인 새 Cycle 가지
- 실패 Report를 유지하는 pending·story·context와 `cycle/revisit` Help Topic

### 확인됨

- 전체 명세 없이 Bootstrap만 받은 Agent가 오류가 가리킨 Topic 하나로 복구하고 완주
- 다른 모델 계열의 새 세션이 `gil context`만으로 열린 Verify와 Active Will을 인수인계

아직 확인되지 않은 것: 전체 토큰 절약, 모든 모델·작업에서의 일반성.

### 다음

- read-only Monitor
- Interview Cycle과 Chain
- 백엔드·데이터 분석·프론트엔드·기획서 작성 시나리오

상세 진행 상황과 합격 조건은 [GIL Living Roadmap](spec/GIL_Roadmap.md)에서 추적한다.

GIL은 누적된 기록을 모든 독자에게 같은 해상도로 반복하지 않는다.

```text
gil story    인간이 현재 상황을 이해한다.
gil context  새 Agent 세션이 계층별로 압축된 지식을 이어받는다.
gil help     Agent가 지금 필요한 규칙 하나를 배운다.
```

현재 구현은 이전 Cycle을 Cycle Report, 현재 Cycle을 Step Report 해상도로 읽는다. 미래 Chain
계층에서는 이전 Chain을 Chain Report 해상도로 읽는 같은 원칙을 적용한다. 압축된 내부 Graph는
삭제되지 않으며, 전체 경로 감사 명령은 아직 구현하지 않았다.

---

## 현재 CLI 사용

아직 정식 릴리스가 아니다. 저장소의 현재 작업 트리를 직접 설치한다.

```bash
cargo install --path . --force
```

빈 작업 폴더에서 시작한다.

```bash
gil start
gil status
gil context
```

막혔을 때는 그 자리의 규칙 하나만 읽는다. 거절이 읽을 주소를 함께 알려 준다.

```bash
gil help                            # 지금 상태에 관련된 주제만
gil help artifact/dirty/non-verify  # 그 주제 하나
```

`gil start`는 먼저 Interview Cycle을 연다. 현재 자리에서 가능한 명령과 필요한 Report 필드는
`gil status`와 상태에 민감한 도움말이 안내한다. Report와 Action Context는 stdin으로 전달한다.

```bash
gil open --help
gil close --help
```

실패한 Experiment Cycle Report가 유효한 Closed ancestor를 `target_cycle_ref`로 확정하면,
대상을 명령 인수로 다시 고르지 않고 두 단계로 새 가지를 연다.

```bash
gil revisit
gil open experiment  # 또는 gil open interview
```

첫 명령은 대상 Cycle의 Exit 세계로 Artifact를 복원하되 실패 Report와 Journey를 남긴다. 두 번째
명령은 그 대상 아래에 새 Cycle을 연다.

Experiment Cycle의 Step Kind:

```text
define
hypothesis
verify
analysis
outcome
```

명령과 Report 형식은 아직 변경될 수 있다. 기존 `.gil/walk.yaml`과 format 3
`.gil/state.yaml`은 format 4로 자동 변환하지 않으며, 발견하면 기록을 보존한 채 이전
형식임을 알린다.

---

## 관련 영역과 차이

GIL은 다음 연구·제품 영역과 맞닿아 있다.

| 영역 | 대표적인 중심 | GIL이 집중하는 것 |
|---|---|---|
| Agent orchestration | durable execution, checkpoint, human-in-the-loop | 실험의 의미와 허용되는 다음 행동 |
| Agent observability | trace, 비용, 지연, 사후 디버깅 | 실행 전에 강제되는 Report와 판정 문법 |
| Agent evaluation | 데이터셋, scorer, 실행 비교 | 실제 작업 안의 가설·실패·전환과 handoff |
| Version control | 파일 변경과 복원 | Artifact 상태와 의미 있는 실험 Graph의 연결 |
| Reflective agents | 언어적 자기 피드백 | 인간과 다음 Agent가 검증하는 불변의 실패 기록 |

인접한 프로젝트와 연구:

- [LangGraph](https://langchain-ai.github.io/langgraph/index.html) — stateful Agent orchestration과 durable execution
- [LangSmith](https://www.langchain.com/langsmith-platform) — Agent observability와 evaluation
- [MLflow Tracing](https://mlflow.org/docs/latest/genai/tracing) — framework-agnostic Agent trace와 feedback
- [Weights & Biases Weave](https://docs.wandb.ai/weave/tutorial-eval) — 모델·Agent 버전과 evaluation
- [Reflexion](https://arxiv.org/abs/2303.11366) — 언어적 reflection을 이용한 Agent 학습

GIL은 이들과 같은 tracing dashboard나 범용 Agent framework가 되는 것을 우선 목표로 삼지
않는다. 어떤 Agent든 실제 프로젝트에서 검증 가능한 실험 문법을 따르게 하는 local execution
layer를 목표로 한다.

---

## 연구 질문

로드맵의 dogfood 시나리오는 다음 질문을 검증하기 위한 실험이기도 하다.

1. onboarding만으로 Agent가 GIL의 Step과 Cycle Grammar를 지키는가?
2. GIL을 사용하면 실패한 접근을 반복하는 빈도가 줄어드는가?
3. Cycle Report가 raw trace보다 협업자의 인수인계 이해도를 높이는가?
4. Artifact를 복원하면서 Knowledge를 유지하는 revisit이 다음 시도의 품질을 높이는가?
5. Interview가 모호한 사용자 의도를 더 정확한 실험 명제로 만드는가?
6. 인간은 Monitor만 보고 현재 실험, 실패 이유와 다음 방향을 이해할 수 있는가?
7. 구조적 제약이 만드는 비용은 어떤 종류의 작업에서 정당화되는가?

---

## 명세

- [GIL Specification v0.1](spec/GIL%20Specification%20v0.1.md)
- [GIL Node Model v0.1](spec/GIL_Node_Model_v0.1.md)
- [GIL Time Model v0.2](spec/GIL_Time_Model_v0.2.md)
- [GIL Cycle Model v0.1](spec/GIL_Cycle_Model_v0.1.md)
- [GIL Context Model v0.1](spec/GIL_Context_Model_v0.1.md)
- [GIL Agent UX Model v0.1](spec/GIL_Agent_UX_Model_v0.1.md)
- [GIL Existence Model v0.1](spec/GIL_Existence_Model_v0.1.md)
- [GIL Will Model v0.1](spec/GIL_Will_Model_v0.1.md)
- [GIL Manual Model v0.1](spec/GIL_Manual_Model_v0.1.md)
- [GIL Storage Model v0.1](spec/GIL_Storage_Model_v0.1.md)
- [Machine-readable grammar](spec/gil-spec.yaml)
- [Living Roadmap](spec/GIL_Roadmap.md)

명세가 구현보다 앞선다. 구현과 명세가 충돌하면 조용히 맞추지 않고 충돌을 드러내고 다시
결정한다.

---

## Project status

**2026-08-31 — Rust dogfood 구현을 진행 중이다.**

앞선 Go 구현과 문서·릴리스는 이 저장소의 옛 branch와 commit history에 남아 있다. 현재 구현은
Rust로 작성하며, Git wrapper가 아니라 GIL의 개념과 불변식을 먼저 세우는 방향으로 진행한다.

MIT License.
