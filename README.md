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
Interview Cycle을 열고, 사용자 Relation과 프로젝트 목표는 그 Interview 안에서 처음 형성한다.
이때 사용자와 Existence는 소유자와 도구가 아니라 프로젝트를 함께 만드는 동등한 협력자로
기록된다.

현재 구현은 초기 dogfood 단계다. Step 기반 사고 엔진과 단일 Experiment Cycle이 동작하며,
여러 Cycle, Artifact snapshot, Cycle revisit, Interview와 Monitor는 순차적으로 구현한다.

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

실패한 Cycle은 자식을 만들지 않는다. 유효한 Closed ancestor로 revisit한 뒤 새로운 형제 가지를
연다. 실패 Report와 Knowledge는 이후 Journey에 남아 같은 시도를 반복하지 않게 한다.

### 두 개의 시간선

```text
Revisit
├─ Artifact timeline → 과거 snapshot을 checkout
└─ Journey timeline  → 현재까지의 경험과 지식을 유지
```

GIL에서 과거로 돌아간다는 것은 과거의 세계를 다시 선택하는 것이지, 과거의 Agent로 돌아가는
것이 아니다.

### 인간의 의도는 인간이 확정한다

향후 Interview Cycle은 모호한 사용자 요청을 작은 명제로 나누고 AI의 해석을 인간에게 다시
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
- 단일 Experiment Cycle
- Cycle Report와 `gil cycle close`
- 마지막 Outcome만 Cycle 판정 근거로 허용
- 사람이 읽는 `gil status`와 `gil story`
- 새 Agent 세션이 이어받는 계층적 `gil context`
- Define·Outcome을 선택적으로 투영하는 협업자용 Cycle story
- 제목·개행·indentation으로 구분되는 plain text Cycle Report
- 이전 저장 형식을 조용히 무시하지 않는 복원 검사

### 진행 중

- 성공한 Cycle에서 다음 Experiment Cycle 열기
- Cycle 간 parent, lineage와 handoff
- 인간용 story와 전체 감사 history의 역할 분리

### 다음

- 여러 Cycle과 handoff
- Verify 경계의 Artifact snapshot
- dirty 검사와 `gil restore`
- Cycle-level revisit과 실패 형제 분기
- read-only Monitor
- Interview Cycle과 Chain
- 백엔드·데이터 분석·프론트엔드·기획서 작성 시나리오

상세 진행 상황과 합격 조건은 [GIL Living Roadmap](spec/GIL_Roadmap.md)에서 추적한다.

GIL은 누적된 기록을 모든 독자에게 같은 해상도로 반복하지 않는다.

```text
gil story    인간이 현재 상황을 이해한다.
gil context  새 Agent 세션이 계층별로 압축된 지식을 이어받는다.
gil history  전체 실행 경로를 감사한다.
```

이전 Chain은 Chain Report, 현재 Chain의 이전 Cycle은 Cycle Report, 현재 Cycle은 Step Report
해상도로 읽는 것을 원칙으로 한다. 압축된 내부 Graph는 삭제되지 않으며 필요할 때 다시 조회한다.

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
gil open define
```

Report는 stdin으로 전달한다.

```bash
gil close <<'EOF'
problem: 협업자가 Cycle 절만 읽고 실험의 목적을 이해할 수 있는가
success_condition: Step 기록을 펼치지 않고 목적, 판정과 다음 방향을 설명할 수 있다
EOF
```

현재 알고 있는 Step Kind:

```text
define
hypothesis
verify
analysis
outcome
```

명령과 Report 형식은 아직 변경될 수 있다. 기존 `.gil/walk.yaml` 형식은 새
`.gil/state.yaml` 형식으로 자동 변환하지 않으며, 발견하면 기록을 보존한 채 이전 형식임을
알린다.

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
- [Machine-readable grammar](spec/gil-spec.yaml)
- [Living Roadmap](spec/GIL_Roadmap.md)

명세가 구현보다 앞선다. 구현과 명세가 충돌하면 조용히 맞추지 않고 충돌을 드러내고 다시
결정한다.

---

## Project status

**2026-08-21 — 처음부터 다시 짓는 중이다.**

앞선 Go 구현과 문서·릴리스는 이 저장소의 옛 branch와 commit history에 남아 있다. 현재 구현은
Rust로 작성하며, Git wrapper가 아니라 GIL의 개념과 불변식을 먼저 세우는 방향으로 진행한다.

MIT License.
