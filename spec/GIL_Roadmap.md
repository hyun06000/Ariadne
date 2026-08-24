# GIL Living Roadmap

> GIL이 지금 어디에 있고, 무엇을 통과했으며, 다음에 무엇을 정복해야 하는지 기록하는
> 수정 가능한 실행 문서다.

이 문서는 규범 명세가 아니다. 구조와 불변식의 근거는 각 Specification에 있으며, 이 문서는
그 명세를 실제 구현·dogfood·사용 예시로 옮기는 순서와 현재 상태를 추적한다.

---

## 1. 상태 표기

- `[x]` 완료 — 구현과 검증이 끝났고 다음 단계가 의존해도 된다.
- `[~]` 진행 중 — 현재 작업 중이거나 dogfood 판정을 기다린다.
- `[ ]` 대기 — 아직 시작하지 않았다.
- `[!]` 재검토 — 구현됐지만 실제 사용에서 문제가 발견됐다.
- `Later` — 필요 사례가 나타날 때 시작한다.

완료는 코드가 존재한다는 뜻만이 아니다. 해당 단계의 **합격 조건을 실제 테스트 또는
dogfood로 통과**해야 `[x]`가 된다.

---

## 2. 현재 위치

마지막 갱신: **2026-08-24**

```text
전체 이정표 9개

진행도  [x][x][~][ ][ ][ ][ ][ ][L]
        M0 M1 M2 M3 M4 M5 M6 M7 M8

완료     2  Step Core, 단일 Cycle 경계
진행 중  1  여러 Cycle의 연속성 (M2A~M2H 완료, M2B 잔여)
대기     5  Artifact 시간선 이후 — M3 계약은 확정됐고 구현이 남았다
Later    1  성공 가지 Merge
```

현재 한 문장:

> **사고의 시간선(Graph·Will·Journey)은 프로세스를 넘어 이어지고, 값의 뜻은 오류 전에 설명된다.
> 이제 남은 것은 그 사고가 실제로 만든 **결과물의 세계**를 시간선에 연결하는 일이다.**

현재 초점:

- `gil start`가 이미 있는 프로젝트 상태를 최초 기준 세계로 확정한다.
- 세계를 바꿀 수 있는 자리를 Verify 하나로 좁히고, 그 밖의 Close는 변경을 거절한다.
- Cycle Exit이 마지막 Outcome의 lineage를 따라 확정된 세계를 가리킨다.

바로 다음 목표:

> **어떤 Node에 서 있든 "지금 이 폴더가 어느 Verify의 세계인가"에 답할 수 있고, 허용되지 않은
> 변경으로 막힌 자리를 `gil restore` 하나로 되돌릴 수 있게 한다.**

---

## 3. 전체 경로

```text
M0 Step Core                         완료
  ↓
M1 Single Cycle Boundary             완료
  ↓
M2A Multi-Cycle + Existence/Will     진행 중
  ↓
M2B Bootstrap Interview Kernel       진행 중
  ↓
M2C Action Context Dogfood           완료
  ↓
M3 Artifact Timeline                 대기   ← 계약 확정됨 (GIL Artifact Model v0.1)
  ↓                                          M4는 M3-D Cycle Exit Snapshot에 의존한다
  ↓
M4 Failure Revisit & Branching       대기
  ↓
M5 Human Monitor                     대기
  ↓
M6 Advanced Interview & Chain Close  대기
  ↓
M7 Scenario Suite                    대기
  ↓
M8 Successful Branch Merge           Later
```

Monitor는 M5에서 갑자기 시작하지 않는다. M2에서 read model을 준비하고, M4의 Cycle Graph가
생기면 사람이 보는 로컬 UI로 확장한다.

---

## 4. M0 — Step Core

상태: `[x] 완료`

목표:

> AI가 한 번에 하나의 원자적 Step만 수행하고, Report 없이 다음 사고로 넘어가지 못한다.

체크리스트:

- [x] Define → Hypothesis → Verify → Analysis → Outcome 문법
- [x] Step Open / Close
- [x] Kind별 필수 Report
- [x] success / failure 판정
- [x] Step-level revisit
- [x] `parent`와 `revisit_from` 구분
- [x] Report와 Knowledge 보존
- [x] 프로세스를 넘는 persistence
- [x] `gil status`
- [x] `gil story`
- [x] 이전 저장 형식을 조용히 무시하지 않음

합격 조건:

- [x] 여러 CLI 프로세스에 걸쳐 한 Walk를 끝낼 수 있다.
- [x] 실패 후 과거 Step에서 새 Hypothesis 형제 가지를 만들 수 있다.
- [x] story만 읽고 Step 수준의 시도와 판정을 이해할 수 있다.

---

## 5. M1 — Single Cycle Boundary

상태: `[x] 완료`

목표:

> 한 Experiment 전체를 Cycle로 닫고, 참여하지 않은 협업자도 Cycle 절만으로 그 실험을
> 이해한다.

구현 체크리스트:

- [x] 단일 `kind: experiment` Cycle
- [x] Cycle이 Walk를 소유
- [x] Cycle Open / Closed
- [x] `Walk.finished` 제거, `Cycle.status`로 단일화
- [x] Cycle Report
- [x] `gil cycle close`
- [x] Cycle Exit을 Step으로 열 수 없음
- [x] `outcome_ref`는 마지막 Outcome만 허용
- [x] Cycle verdict와 Outcome verdict 일치 검사
- [x] verdict별 next direction 제한
- [x] `.gil/state.yaml` format 1
- [x] 닫힌 Cycle 불변
- [x] Cycle Report를 story 마지막 절에 표시
- [x] Define·Outcome을 선택적으로 투영하는 협업자용 Cycle story
- [x] plain text Cycle 절의 개행·indentation·블록 구분 개선

dogfood 체크리스트:

- [x] 설치본에서 단일 Cycle을 끝까지 수행
- [x] Cycle Report 입력과 Close 동작 확인
- [x] 현재 참여자는 기존 Cycle 절을 이해할 수 있음
- [!] 참여하지 않은 협업자는 기존 Cycle 절만으로 전체 실험과 실패 이유를 이해하기 어려웠음
- [x] 개선된 Cycle 절로 같은 닫힌 상태를 다시 읽음
- [x] 사용자가 선택적 투영 형식에서 목적을 이해함
- [x] 사용자가 선택적 투영 형식에서 성공·실패 이유를 이해함
- [x] 사용자가 다음 방향을 이해함
- [!] 실제 dogfood Report에 정의되지 않은 내부 단계명 `S1`이 남음
- [x] 모든 Report에 객관적·자립적 글쓰기 원칙을 명세 불변식으로 확정
- [x] 개선된 plain text layout을 실제 닫힌 Cycle로 재확인

합격 조건:

- [x] Step 절을 펼치지 않아도 실험 목적, 성공 기준, verdict, 이유, handoff, 다음 방향을 안다.
- [x] Cycle Report가 Define·Outcome 내용을 중복 저장하지 않는다.
- [x] 선택적 투영은 immutable Define과 마지막 Outcome 원본에서 읽는다.

M1이 끝나면:

> S1 구현과 명세를 하나의 안정된 checkpoint로 만들고 M2로 이동한다.

---

## 6. M2 — Multi-Cycle Continuity

상태: `[~] 진행 준비`

목표:

> 성공한 Cycle에서 다음 Cycle을 열고, 전체 Step 기록을 복사하지 않고 handoff로 이어간다.

체크리스트:

- [ ] `gil cycle open experiment`
- [ ] 둘째 Cycle 생성
- [ ] Cycle `parent`
- [ ] Cycle lineage
- [ ] 성공한 Cycle만 자식 Cycle의 부모가 됨
- [ ] 실패한 Cycle 아래에서 child open 거절
- [ ] 새 Cycle은 새 immutable Define을 가짐
- [ ] 부모 Cycle Report 전달
- [ ] 누적된 실패 Cycle Report 전달
- [ ] `executed_cycles`
- [ ] `pending_exploration`
- [ ] 여러 Cycle을 구분하는 status / story
- [ ] 한 번에 하나의 active Cycle

read model 준비:

- [x] story / context / history의 독자와 역할 분리
- [x] 현재 위치와 계층적 거리에 따른 Context Resolution Rule 명세
- [x] `gil context` 구현
- [x] 이전 Cycle은 Define·참조된 Outcome·Cycle Report에서 Cycle 해상도로 선택적 투영
- [x] 현재 Cycle은 Step Report 해상도로 context에 포함
- [x] 과거 Cycle의 Step Graph가 context에 펼쳐지지 않음
- [x] Node Open은 전체 context가 아니라 delta만 출력
- [x] Context / Will / Grammar의 책임 분리 명세
- [x] 일상 Agent loop를 `start / open / close`와 명령별 nudge로 확정
- [x] `gil context`를 매 행동이 아닌 cold start·handoff·recovery 용도로 확정
- [x] 명령 출력을 State delta + Current Will + 적용 Grammar + 선택적 Help ref로 정의
- [x] 오류를 이유·복구 행동·다음 명령·도움말을 주는 국소 안내서로 정의
- [x] 전체 명세 대신 주제별로 읽는 점진적 `gil help` 방향 확정
- [x] Will을 Journey Timeline의 첫 구체적 축으로 명세
- [x] 런타임 모델과 지속적 Existence identity 분리 명세
- [x] World Current / Existence Current의 독립성 명세
- [x] Closed Node provenance를 `existence_ref` + `journey_ref`로 분리
- [x] provenance ref를 기본 context에서 재귀적으로 펼치지 않음
- [x] v0 Existence와 Journey의 저장 범위를 프로젝트 로컬 `.gil`로 확정
- [x] World와 Existence/Journey를 단일 `.gil/state.yaml` format 3에 저장하기로 확정
- [x] Journey revision과 Node Close provenance의 단일 save transaction 명세
- [x] `gil start`가 최초 Existence와 초기 Journey를 만들도록 bootstrap 명세
- [x] `gil start`가 최초 Interview Cycle을 열도록 확정
- [x] 사용자 Relation과 목표를 설정이 아니라 Interview 안에서 형성
- [x] 사용자와 Existence를 프로젝트의 동등한 Participant로 확정
- [x] 최초 Relation은 `with`와 자연어 `description`만 가진 최소 기억으로 확정
- [x] 추가 Existence는 빈 Journey에서 가볍게 초기화하고 명시적으로 선택
- [x] Node를 Open한 Existence와 Close한 Existence가 같아야 한다고 확정
- [x] Open Step·Cycle·Chain이 있으면 Existence 전환 금지
- [x] Current Will은 가장 깊은 실행형 Open Node 하나에만 대응
- [x] Chain·Cycle 컨테이너 Close는 별도의 Will Done을 요구하지 않음
- [x] Action Node Open과 Active Will 생성을 단일 transaction으로 확정
- [x] 공개 traversal 문법을 `gil open` / `gil close`로 최소화
- [x] `gil close`가 Will Done·Journey revision·Report·Node Close를 원자적으로 확정
- [x] 프로젝트 로컬 typed reference와 종류별 안정적·비재사용 ID 확정
- [x] Cycle ID는 프로젝트 전역, Step ID는 Cycle 로컬이며 Step ref에 Cycle ID 포함
- [x] 화면의 `#3` 축약과 영구 `step:C2/S3` reference 분리
- [x] 최초 Existence와 빈 ES0을 함께 만들고 J0이 `state:ES0`을 가리키도록 확정
- [x] 모든 Journey revision의 `existence_state_ref`를 필수로 확정
- [x] Node Open 시 immutable `existence_ref` 기록
- [ ] Node Close 시 Current Existence·Active Will 일치와 통합 transaction 검사
- [x] Current Existence indicator 저장과 복원
- [ ] 같은 Existence를 다른 세션·모델에서 복원하는 dogfood
- [ ] 다른 Existence를 선택했을 때 별도 Journey가 복원되는 dogfood
- [ ] Active Will register와 Done Will append-only Timeline 저장
- [ ] Node Open에서 Current Will 확정
- [ ] 실행형 Node Close에서 Active Will Done을 함께 확정
- [ ] onboarding에서 Context / Current Will / Applicable Grammar를 분리해 전달
- [ ] `gil start` 출력이 최초 행동으로 nudge
- [ ] `gil open` 출력이 현재 행동·완료 조건·필수 Report만 투영
- [ ] `gil close` 출력이 state delta와 다음 nudge만 투영
- [ ] 오류만 읽고 올바른 다음 행동으로 복구하는 dogfood
- [ ] 같은 세션에서 매번 `gil context` 없이 진행하는 dogfood
- [ ] `gil story`를 현재 Journey 중심의 인간용 투영으로 축소
- [ ] 전체 감사 기록을 위한 `gil history` 구현 또는 명시적 조회 경로
- [ ] UI와 CLI가 함께 읽을 안정된 상태 투영 정의
- [ ] Cycle ID, kind, status, parent, verdict, handoff 노출
- [ ] 현재 가능한 다음 행동 노출
- [ ] 기계가 읽을 수 있는 출력 형식 후보 검토

### M2B — Bootstrap Interview Kernel

- [ ] `gil start`가 X1 + 빈 ES0 + J0 + Current ref + Interview Cycle을 한 save로 생성
- [ ] J0의 `existence_state_ref == state:ES0`과 State 실재 복원 검사
- [ ] 초기 Knowledge·Memory·Relations·Will head만 `null` 허용하고 복원 검사
- [x] Interview `question / interpretation / synthesis / outcome` Grammar
- [x] Question에 질문·선택지·인간 원문 응답을 함께 저장
- [ ] 프로젝트 로컬 Human Participant `U1`과 사용자가 제공한 호칭 저장
- [ ] X1 Journey에 `with: participant:U1`과 관계 설명을 가진 최초 Relation
- [ ] 사용자의 큰 질문 수집
- [x] 작은 명제의 yes/no 승인과 no 이유 재질문
- [ ] 승인된 최초 탐색 체크리스트 Synthesis
- [x] 승인된 Synthesis 전 Experiment Cycle Open 거절

### M2D — Agent UX Correction 1

실제 인수인계 dogfood 에서 드러난 공개 표면의 불일치를 고친 자리.

- [x] Cycle Report 의 `outcome_ref` 를 typed `StepRef` 로 정합화
- [x] `gil open` 통합 dispatcher — Step 과 Cycle 경계를 GIL 이 판정
- [x] 가능한 종류가 하나면 Kind 입력 없이 진행
- [x] 가능한 종류가 여럿이면 그 종류만 보여 주고 명시적 선택을 요구
- [x] `gil close` 통합 dispatcher — 가장 깊은 열린 경계를 GIL 이 판정
- [x] Open Receipt 에 닫는 데 필요한 칸과 다음 명령
- [x] Close Receipt 에 delta 와 다음 nudge
- [x] 오류에 무엇·왜·지금 할 일·다음 명령
- [x] 빈 `gil close` 가 **그 Node 의** 골격을 보여 줌
- [x] `close_chain` 을 실행 가능한 값에서 내리고 까닭을 안내
- [x] Synthesis 의 `approved` 가 다음 자리를 가름 (yes → 판정 · no → 질문)
- [x] `gil --help` 를 Interview-first 와 typed `outcome_ref` 로 정합화
- [x] `gil cycle open/close` 는 호환으로만 남기고 기본 경로에서 비홍보
- [ ] `gil help <주제>` 점진적 도움말

### M2E — Agent UX Correction 2

- [x] Step revisit의 `next_direction.target_node_ref`를 typed `StepRef`로 정합화
- [x] bare `target_node_id` 저장·입력 거절
- [x] `basis_refs`를 block scalar의 한 줄당 하나의 StepRef로 파싱
- [x] `basis_refs`의 같은 Interview Cycle·선행 Closed Question/Interpretation·중복 금지 검사
- [x] Cycle Kind의 짧은 선택 설명을 machine-readable Grammar가 소유
- [x] 선택지가 여러 개인 자리에서만 Grammar 설명을 투영
- [x] Open Receipt는 실제 작업 전에 `gil close`를 `실행` 명령으로 강조하지 않음

### M2F — Interview Reference Lineage

- [x] `basis_refs`의 유효성을 ID·시간 순서가 아니라 현재 Synthesis의 Lineage로 검사
- [x] `synthesis_ref`가 현재 Outcome의 Lineage에 속한 Closed Synthesis인지 검사
- [x] `basis_refs` 없음과 빈 block scalar를 같은 유효 근거 없음으로 거절
- [x] Report 입력은 dotted·nested를 모두 허용하고 출력은 dotted를 canonical로 사용

### M2G — Current Will Transaction

- [x] Project root의 전역 `next_will_id` allocator
- [x] Active Will을 Existence Journey의 inline 객체로 저장
- [x] 실행형 `gil open`이 Action Contract 세 필드를 stdin으로 받음
- [x] Action Node와 Active Will을 한 save로 Open
- [x] `gil open` Receipt가 `next_action`·`done_when`을 국소 투영
- [x] 실행형 `gil close`가 같은 Will 객체를 Done 목록 끝으로 이동
- [x] Close에서 Journey revision 생성·current ref 이동·`will_head_ref` 확정
- [x] Node `journey_ref`·Report·Closed와 Will Done을 한 save로 확정
- [x] Done Will 객체의 immutable·append-only 복원 검사
- [x] 컨테이너 Cycle Open·Close는 Will을 만들거나 완료하지 않음

### M2H — Constraint-aware Receipt

- [x] machine-readable Grammar가 각 허용 enum 값의 짧은 의미를 소유(`value_descriptions`)
- [x] 허용값 설명은 해당 값이 움직이는 Step·Cycle 계층을 밝힘
- [x] Open Receipt가 현재 Close 필드의 허용값·조건부 허용값을 사전에 투영
- [x] `gil close --help`가 현재 Close 계약을 읽기 전용으로 출력
- [x] `gil open --help`가 현재 Kind 선택과 Action Contract 골격을 읽기 전용으로 출력
- [x] 상태별 help 호출 전후 저장 파일이 바뀌지 않음(바이트 동일)
- [x] 아직 구현하지 않은 enum 값은 실행 가능한 값과 분리(`not_yet`)
- [x] Outcome `close_cycle`과 Cycle Report `open_child`의 계층 차이를 자연어로 안내
- [x] Receipt·help·거절이 같은 Grammar read model 하나를 투영

합격 조건:

- [x] 새 Agent가 Open Receipt와 help만 읽고 `close_cycle`·`open_child`를 첫 시도에 제출한다.
- [x] enum 값을 알아내기 위한 실패 명령이 0회다.
- [x] `open --help`·`close --help` 전후 저장 파일 hash가 같고 Active Will과 Open Step이 남는다.

미결로 넘긴 것:

- [ ] 「기록은 되지만 지금 실행할 수 없는 값」(Artifact Model §11의 2번 상태)을 Grammar가
  `not_yet`과 구분되는 표식으로 갖는다. 현재는 `value_descriptions` 산문으로만 구분한다.

### M2C — Action Context Dogfood

- [x] 다른 모델·세션이 같은 Existence와 Journey를 복원
- [x] context + Current Will + Grammar로 열린 Action Node 이어가기
- [x] 실제 작업을 수행한 뒤 통합 `gil close`

합격 조건:

- [ ] 두 번째 Cycle이 첫 Cycle의 Step을 펼치지 않고 작업을 이어간다.
- [ ] 협업자가 Cycle별 목적과 handoff를 구분할 수 있다.
- [ ] 실패 Cycle을 부모로 새 Cycle을 열 수 없다.
- [x] 과거에는 Current Will이 없어 새 Agent가 Verify를 실제 검증 전에 닫았으나, M2C 재실험에서
  저장된 Will의 실패 재현 → 수정 → 재검증 순서를 먼저 수행한 뒤 Verify를 닫음.
- [x] 새 Agent가 Action Context로 실제 작업을 먼저 수행한 뒤 Node를 닫는다.
- [x] 매 Node Open에서 과거 context가 중복 출력되지 않는다.
- [x] enum 허용값이 Open Receipt에 보이지 않아 오류로 값을 발견하던 문제는 M2H가 해소했다.
- [x] `gil close --help`가 빈 Close 요청으로 처리되던 문제는 M2H가 해소했다.

첫 권장 시나리오:

> 테스트로 판정 가능한 작은 백엔드 버그 수정.

---

## 7. M3 — Artifact Timeline

상태: `[ ] 대기`

규범: **`GIL Artifact Model v0.1`** — Artifact·Snapshot·`gil restore`의 단일 진실 공급원이다.
이 체크리스트는 그 문서를 구현 순서로 옮긴 것이며, 규칙의 근거는 전부 거기 있다.

목표:

> GIL의 사고 Graph와 작업 결과물의 세계를 snapshot으로 연결하고, 이후 Cycle revisit이 세계를
> 복원할 수 있는 기반을 만든다.

### M3-A 관리 범위와 최초 기준 세계

- [ ] 프로젝트 루트 아래 일반 파일을 관리 대상으로 관측 (Artifact Model §3)
- [ ] `.gil/`·특수 파일·내부 임시 파일 제외
- [ ] 불투명한 `SnapshotRef`(`snapshot:A1`)
- [ ] `gil start`가 **실제 프로젝트 상태**를 최초 불변 Snapshot으로 확정 (§4)
- [ ] 최초 Snapshot 참조의 저장 위치 확정 — Cycle entry 필드인가 Project 뿌리 필드인가
- [ ] `gil start`가 최초 Snapshot·Existence·Journey·Interview Cycle을 **한 저장 트랜잭션**으로 확정
- [ ] 모든 `snapshot_ref`의 실재를 복원 시 검사

### M3-B 생성 권한과 변경 경계

- [ ] 새 Snapshot은 `gil start`와 Verify close에서만 생성 (§5)
- [ ] Interview·Define·Hypothesis·Analysis·Outcome·Cycle close는 Snapshot을 만들지 않음
- [ ] Verify에는 verdict가 없고 Snapshot 확정은 판정과 독립임을 보존
- [ ] 비-Verify Action Step close에서 Artifact 변경이 있으면 거절 (§6)
- [ ] **Cycle container close에서도** Artifact 변경이 있으면 거절
- [ ] 거절 시 Step과 Active Will이 열린 채 남고 Journey revision·Done Will·Report가
      부분 저장되지 않음
- [ ] 경고만 하고 닫거나 자동으로 변경을 버리는 경로 없음
- [ ] `gil status`의 clean / dirty 표시

### M3-C Verify close 트랜잭션

- [ ] Report 검증 → 관측 → Snapshot 확정 → `snapshot_ref` → Will Done → Journey revision →
      Closed 를 하나의 원자적 동작으로 (§7)
- [ ] 하나라도 실패하면 전체가 이전 상태
- [ ] `snapshot_ref`는 Report가 아니라 Verify Node의 **구조 필드**
- [ ] 다른 Closed Step은 lineage에서 가장 가까운 선행 Verify를, 없으면 Cycle Entry를 유도
- [ ] 관측 결과가 기존 Snapshot과 같을 때 이름을 재사용할지 확정 (Artifact Model §13)
- [ ] World Current Snapshot을 유도값으로 둘지 캐시할지 확정
- [ ] Snapshot 저장소(①)와 `state.yaml`(②)의 순서·비대칭 검사 (§10)

### M3-D Cycle Exit Snapshot

- [ ] Cycle close는 새 Snapshot을 만들지 않음 (§7)
- [ ] 마지막 Outcome의 **구조적 lineage**에서 가장 최근 Verify Snapshot을 Exit로 기록
- [ ] 그 lineage에 Verify Snapshot이 없으면 Entry Snapshot을 계승
- [ ] Entry Snapshot = 부모 Cycle의 Exit, 뿌리 Cycle이면 최초 기준 Snapshot
- [ ] 버려진 가지의 Snapshot을 고르지 않음
- [ ] 이름이 가장 큰 Snapshot을 고르지 않음
- [ ] Artifact를 바꾸지 않는 Interview Cycle은 Entry = Exit

### M3-E `gil restore`

- [ ] 현재 Cycle에서 이용 가능한 가장 최근 확정 Snapshot으로 Artifact만 복원 (§8)
- [ ] Graph·Report·Current Node·Active Will·Journey·Existence를 바꾸지 않음
- [ ] 복원 전에 덮어쓰게 될 변경과 복원 대상을 보여 줌
- [ ] 현재 변경을 자동 보존하거나 새 Snapshot으로 만들지 않음
- [ ] 확인 절차와 비대화식 사용법 확정 — 임의의 강제 옵션을 만들지 않음
- [ ] 강제 restore + close를 한 동작으로 묶는 경로 없음

### M3-F 시간선과 공개 어휘

- [ ] Snapshot 복원이 Journey revision·Done Will·Report·Graph·Snapshot 객체를 지우지 않음 (§9)
- [ ] staging을 사용자에게 노출하지 않음
- [ ] 공개 개념과 오류 메시지에 Git 용어를 노출하지 않음 (§14)
- [ ] `.gilignore` 공개 계약은 실제 필요가 확인된 뒤 결정 — 지금 만들지 않음

합격 조건:

- [ ] 이미 파일이 있는 폴더에서 `gil start` 한 번이 그 실제 상태를 기준 세계로 확정한다.
- [ ] 현재 작업물이 어느 Verify와 어느 Cycle의 세계인지 설명할 수 있다.
- [ ] 비-Verify Step과 Cycle을 dirty 상태에서 닫으려 하면 거절되고, 거절 뒤 상태가 그대로다.
- [ ] `gil restore`가 Artifact만 복원하고 Graph·Journey는 바꾸지 않는다.
- [ ] snapshot 실패로 존재하지 않는 참조가 생기지 않는다.
- [ ] 닫힌 Cycle의 Exit Snapshot이 버려진 가지가 아니라 마지막 Outcome의 lineage를 따른다.

권장 시나리오:

> 기존 파일이 있는 저장소에서 시작해, 한 Experiment Cycle이 실제로 파일을 고치고 그 세계가
> Cycle Exit에 남는 것을 확인한다.

---

## 8. M4 — Failure Revisit & Branching

상태: `[ ] 대기`

**의존: M3.** Cycle revisit은 「대상 Cycle Exit의 세계로 돌아간다」는 동작이므로, M3-D가
Cycle Exit Snapshot을 확정하기 전에는 돌아갈 곳이 없다. M3-E의 `gil restore`가 그 복원의
기계이고, M3-B의 dirty 거절이 revisit의 clean 전제를 만든다.

```text
M3-D Cycle Exit Snapshot   →  M4 revisit target의 세계
M3-E restore               →  M4 checkout 기계
M3-B dirty 거절            →  M4 clean checkout 전제
```

현재 Experiment Cycle failure Report의 `revisit`은 **유효하게 기록되지만 실행할 수 없는**
방향이다(`GIL Artifact Model v0.1` §11의 2번 상태). M4가 그것을 1번으로 옮긴다.

목표:

> 실패한 세계를 지우지 않고 Closed ancestor의 세계에서 다른 Cycle을 시작한다.

체크리스트:

- [ ] Cycle-level `next_direction: revisit`
- [ ] revisit target은 현재 Cycle lineage의 Closed ancestor
- [ ] target Cycle은 새 자식을 가질 수 있는 성공 Cycle
- [ ] dirty 상태에서 revisit 거절
- [ ] target Cycle Exit snapshot checkout
- [ ] `.gil`과 Journey는 checkout 영향 없음
- [ ] 실패 Cycle의 Graph·Report·snapshot 보존
- [ ] `pending_cycle_revisit`
- [ ] revisit 직후 새 Cycle만 허용
- [ ] 새 Cycle `parent = target ancestor`
- [ ] 새 Cycle `revisit_from = failed Cycle`
- [ ] 실패 Cycle과 새 Cycle이 형제 관계
- [ ] 강제 revisit 없음

합격 조건:

- [ ] 실패한 Artifact는 현재 세계에서 제거되지만 snapshot으로 남는다.
- [ ] 실패 지식과 Report는 새 형제 Cycle에 전달된다.
- [ ] 과거 Cycle이나 snapshot을 수정하지 않는다.

권장 시나리오:

> 여러 가설이 실패하고 대안 실험으로 전환하는 데이터 분석 문제.

---

## 9. M5 — Human Monitor

상태: `[ ] 대기`

목표:

> 사용자가 터미널과 raw YAML 없이 AI의 현재 위치, 실패, 전환과 다음 방향을 이해한다.

### M5-A Read-only Monitor

- [ ] `.gil`을 안전하게 읽는 read model
- [ ] 현재 Chain / Cycle / Step
- [ ] 현재 실험 목적과 성공 기준
- [ ] active lineage
- [ ] 실패한 형제 Cycle
- [ ] revisit 출처와 대상
- [ ] Cycle handoff
- [ ] 현재 clean / dirty
- [ ] 현재 가능한 행동
- [ ] 상태 변경 시 자동 갱신
- [ ] GIL 상태를 변경하지 않는 read-only UI
- [ ] 하나의 read model에서 plain text / Markdown / HTML renderer 제공
- [ ] renderer 사이에서 의미와 판정이 달라지지 않음
- [ ] Report의 표·차트·이미지·화면 캡처 참조 표시
- [ ] 시각 자료 caption·alt text·provenance 표시
- [ ] Markdown·HTML의 안전한 렌더링 정책

### M5-B Human Checkpoints

- [ ] milestone 승인 표시
- [ ] stepwise 승인 표시
- [ ] autonomous 진행 설명
- [ ] 갑작스러운 Chain 종료 제안 전에 경로 요약

합격 조건:

- [ ] 사용자가 30초 안에 “무엇을 하고 있고 왜 여기 있는가”를 설명할 수 있다.
- [ ] 실패 가지와 현재 활성 가지를 혼동하지 않는다.
- [ ] UI가 CLI와 다른 진실 공급원을 만들지 않는다.

권장 시나리오:

> 화면 변화를 단계별로 확인하는 프론트엔드 개발.

---

## 10. M6 — Advanced Interview & Chain Closing

상태: `[ ] 대기`

목표:

> Bootstrap Interview Kernel을 일반적인 재인터뷰, 탐색 계획 변경과 Chain Closing으로 확장한다.

체크리스트:

- [ ] Bootstrap 이후 새 Interview Cycle
- [ ] 실험 중 발견한 의문을 다시 Interview로 확인
- [ ] Interpretation: 응답보다 넓은 의도를 확정하지 않음
- [ ] 인간 응답을 AI 대필과 구분하는 통로
- [ ] `pending_exploration` 변경 승인
- [ ] Interview는 success로만 닫힘
- [ ] Closing Interview
- [ ] Chain success / failure 인간 승인
- [ ] Chain Report
- [ ] `closing_synthesis_ref`
- [ ] Chain `handoff_summary`

합격 조건:

- [ ] 사용자는 객관식 중심의 작은 질문으로 모호한 의도를 명확히 할 수 있다.
- [ ] AI는 사용자가 답한 범위보다 큰 의도를 확정하지 않는다.
- [ ] Chain failure도 성공한 Closing Interview에서 인간이 승인한다.

권장 시나리오:

> 모호한 프로젝트 아이디어를 실행 가능한 기획서로 만드는 작업.

---

## 11. M7 — Scenario Suite

상태: `[ ] 대기`

목표:

> GIL의 기능을 정적 테스트가 아니라 서로 다른 실제 작업 유형으로 반복 검증한다.

공통 구조 후보:

```text
scenario/
├─ task.md
├─ initial-artifacts/
├─ expected-capabilities.md
├─ human-checkpoints.md
├─ acceptance.md
└─ reference-story.md
```

### Backend

- [ ] 테스트로 판정 가능한 작은 버그
- [ ] 여러 Cycle handoff
- [ ] Verify snapshot
- [ ] 실패 후 수정 방향 전환
- [ ] 자동화된 acceptance

### Data Science

- [ ] 실패 가능한 가설 여러 개
- [ ] milestone 중심 인간 참여
- [ ] 실패 Cycle 보존
- [ ] ancestor revisit과 형제 실험
- [ ] 결과 중심 handoff

### Frontend

- [ ] 시각 Artifact 변화
- [ ] stepwise 인간 검수
- [ ] 이전 화면 snapshot 복원
- [ ] Monitor에서 변화 이유 확인
- [ ] 최종 UI acceptance

### Planning Document

- [ ] Opening Interview
- [ ] 사용자 의도 원자화
- [ ] 탐색 체크리스트
- [ ] 여러 Experiment Cycle
- [ ] Closing Interview
- [ ] 인간이 승인한 Chain verdict

합격 조건:

- [ ] 네 시나리오가 서로 다른 GIL 기능을 실제로 요구한다.
- [ ] 단순히 정답을 얻는 것과 GIL 구조를 지키는 것을 따로 평가한다.
- [ ] control과 GIL 실험을 반복할 수 있다.

---

## 12. M8 — Successful Branch Merge

상태: `Later`

시작 조건:

> 독립적으로 성공한 두 Cycle의 Artifact와 지식을 실제로 합쳐야 하는 사례가 반복해서 나타난다.

후보 체크리스트:

- [ ] 독립 성공 형제 Cycle
- [ ] 다중 부모 Cycle
- [ ] Report 합류
- [ ] Artifact 충돌 탐지
- [ ] Merge Cycle
- [ ] 인간 또는 AI의 충돌 판단
- [ ] 합류 후 lineage와 Journey 의미

지금 하지 않는 이유:

- 실패 후 revisit은 하나의 과거 snapshot을 선택하므로 Merge가 아니다.
- 실제 성공 가지 합류 사례 없이 설계하면 불필요한 복잡성을 먼저 만들 가능성이 크다.

---

## 13. 로드맵 갱신 규칙

작업을 시작할 때:

1. 현재 이정표를 `[~]`로 표시한다.
2. 이번 Step의 정확한 완료 조건을 체크리스트에 추가한다.
3. 범위 밖 항목을 명시한다.

작업을 마칠 때:

1. 테스트만 통과하면 구현 항목을 `[x]`로 표시한다.
2. dogfood가 필요한 항목은 사용자 판정 전까지 `[~]`로 둔다.
3. 실제 사용에서 문제가 발견되면 `[!]`로 되돌린다.
4. 새 기능을 즉시 끼워 넣지 말고 어느 이정표에 속하는지 먼저 정한다.
5. `마지막 갱신`, `현재 한 문장`, `바로 다음 목표`를 갱신한다.

명세가 바뀔 때:

- Roadmap보다 Specification이 우선한다.
- 변경된 불변식이 영향을 주는 이정표와 합격 조건을 함께 수정한다.
- 과거 완료 표시가 더 이상 사실이 아니면 주저하지 않고 `[!]`로 되돌린다.

---

## 14. 결정 로그

### 2026-08-21

- Living Roadmap 최초 작성.
- M1 Single Cycle Boundary의 선택적 투영과 plain text renderer dogfood 통과.
- M1을 완료하고 현재 위치를 M2 Multi-Cycle Continuity 준비로 이동.
- 과거 dogfood Report의 `S1` 약어를 계기로 전 계층 Report 작성 불변식을 확정.
- story, context, history를 서로 다른 해상도 투영으로 분리.
- 이전 Chain은 Chain Report, 이전 Cycle은 Cycle Report, 현재 Cycle은 Step Report로 전달하는
  Context Resolution Rule을 확정.
- 이전 Cycle의 해상도는 Report의 저장 필드만 뜻하지 않는다. 유일한 Define과 참조된 Outcome,
  Cycle Report 원본에서 Cycle 대표 정보를 선택적으로 투영하고 Step Graph는 펼치지 않는다.
- Context의 이전 Cycle 투영 수는 `ancestor_count`와 같아야 한다.
- Monitor를 M2 read model 준비와 M5 UI 구현으로 분리.
- 시나리오 순서를 Backend → Data Science → Frontend → Planning Document로 둠.
- 실패 revisit은 M4, 성공 가지 Merge는 실제 필요가 생기는 M8로 분리.
- 실제 새 Agent 인수인계 dogfood에서 이전 Cycle의 지식, 현재 가설과 위치 복원은 성공.
- 같은 dogfood에서 `next_moves`가 실제 다음 작업으로 오인되어 증거 없는 Verify Close가 발생.
- Context는 상태, Will은 현재 실제 행동, Grammar는 구조적 허용 행동을 담당한다고 분리.
- 평상시 Agent loop는 `gil start / gil open / 실제 작업 / gil close`이며 각 명령의 작은 nudge가
  다음 행동을 안내. `gil context`는 cold start·handoff·recovery 때만 사용.
- 명령 출력은 전체 context가 아니라 State delta, Current Will, 지금 적용되는 Grammar와 선택적
  help reference를 투영. 오류는 전체 명세 없이 복구할 수 있는 국소 안내서 역할을 함.
- GIL 내부 개념이 늘어나도 공개 명령을 같은 비율로 늘리지 않고, 주제별 `gil help`를 필요할
  때만 읽는 점진적 Agent UX 방향을 확정.
- Synthesis의 `basis_refs`는 block scalar에 canonical StepRef를 한 줄씩 적고, 같은 Interview
  Cycle의 앞선 Closed Question·Interpretation만 중복 없이 참조하도록 확정.
- Open Receipt는 CLI를 재촉하지 않고 실제 작업으로 제어권을 넘김. 여러 Kind의 설명은 renderer
  하드코딩이 아니라 machine-readable Grammar가 소유하며 선택이 필요할 때만 투영.
- Interview의 근거 참조는 ID나 닫힌 시각이 아니라 구조적 Lineage로 판정. `basis_refs`는 현재
  Synthesis의 조상 Question·Interpretation을, `synthesis_ref`는 Outcome의 조상 Synthesis를
  가리키며 Report 입력은 dotted·nested 둘을 받고 dotted를 canonical 출력으로 사용.
- Active Will은 Existence Journey 안의 inline 객체로 저장하고, 실행형 Close에서 같은 객체를
  immutable `done_wills` 끝으로 이동. Will ID는 프로젝트 전역 `next_will_id`가 발급하며
  revision의 `will_head_ref`가 마지막 Done 객체를 가리킴.
- 실행형 `gil open`은 stdin에서 `objective`·`next_action`·`done_when`을 받아 Node와 Will을 한
  save로 열고, Receipt는 실제 작업과 완료 조건만 국소 투영.
- M2C Will 인수인계 dogfood 통과. 새 Agent는 최초 `gil context` 한 번만 읽고 열린 Verify의
  실패 재현, 코드 수정, 재검증과 불변성 증거 확보를 마친 뒤에만 Close했으며 4개 테스트가 통과.
- 같은 dogfood에서 `gil close --help` 처리와 enum 허용값의 사전 비노출이 새 UX 문제로 발견됨.
  Step Outcome의 `close_cycle`과 Cycle Report의 `open_child`는 서로 다른 계층의 방향이지만 raw
  enum만으로는 의미 차이가 충분히 설명되지 않음.
- Active Will은 구체화하는 동안 덮어쓰고 Done Will만 시간순 Journey Timeline에 확정.
- Existence는 모델·프로세스·세션이 아니라 GIL에 저장되는 지속적 행동 주체로 확정.
- World Current는 위치를, Existence Current는 행동하는 존재를 선택하며 서로 자동 변경하지 않음.
- 동일한 Existence를 읽으면 어떤 모델과 세션에서도 동일한 Journey와 Will을 이어감.
- Closed Node는 지속적 identity와 Close 시점 Journey revision을 별도 provenance로 기록.
- 기본 context는 provenance ref를 재귀적으로 펼치지 않고 현재 필요한 해상도만 투영.
- v0 Existence와 Journey는 프로젝트의 `.gil`을 단일 진실 원천으로 사용하고 프로젝트 간
  공유와 전역 registry는 이후로 미룸.
- v0 저장은 `.gil/state.yaml` format 3 하나를 사용하며 Journey revision과 Node Close를 한
  번의 원자적 파일 교체로 확정. format 2 자동 migration과 object 분리는 이후로 미룸.
- `gil start`는 최초 Existence와 빈 초기 Journey를 Current로 만들고 최초 Interview Cycle을
  Open. 사용자 Relation·목표·탐색 Synthesis는 Interview 안에서 처음 형성.
- Bootstrap Interview Kernel을 M6에서 M2B로 앞당기고, M6는 재인터뷰와 Chain Closing 확장으로
  좁힘.
- 추가 Existence는 기존 Journey를 복사하지 않고 최소 상태로 만들며 명시적 전환 전에는
  Current가 되지 않음.
- 하나의 Node는 시작한 Existence가 끝내며, 재귀적 Open Node가 하나라도 있으면 v0에서
  Existence 전환을 거절. 명시적 ownership handoff는 이후로 미룸.
- Existence ownership은 모든 Node에 적용하지만 Current Will은 가장 깊은 실행형 Open Node
  하나에만 대응. Chain·Cycle은 내부 Graph의 컨테이너로서 장기 Active Will을 점유하지 않음.
- 실행형 Node와 Active Will은 함께 Open되고, `gil close`가 Will Done·Journey revision·Report·
  Node Close를 하나의 transaction으로 확정. 별도 ready-to-close와 Will traversal 명령은 두지 않음.
- 기존 Specification이 `Will`이라 부르던 「미래 조건에서 기억해야 하는 지속적 규약」을
  Prospective Memory로 재분류. `Will`이라는 이름은 Will Model의 현재 행동 단위에만 쓴다.
- Memory를 Retrospective / Prospective로 구분. Journey의 최상위 구성 요소 수는 늘리지 않는다.
- Prospective Memory는 `done`으로 소비되지 않으며, 조건이 충족되면 새 Current Will의 근거가
  될 수 있다. 조건 판정과 Will 생성 trigger는 아직 정하지 않는다.
- 사용자와 Existence는 프로젝트를 함께 만드는 동등한 Participant. 최초 Interview는 사용자를
  프로젝트 로컬 `U1`으로 식별하고 X1 Journey에 최소 Relation 기억을 형성한다.
- 인간의 내적 Journey는 추측해 만들지 않지만, 이는 저장 구조의 차이일 뿐 협력 관계의 위계가
  아니다. 역할과 권한 차이는 후속 Interview의 명시적 합의 없이는 추론하지 않는다.
- v0 Relation은 `with`와 자연어 `description`만 다루고 방향성·Kind enum·권한·다자 관계와
  프로젝트 전역 관계 Graph는 실제 필요가 생길 때까지 미룬다.
- U2A 경계를 넓혀 Bootstrap Interview의 최소 실행 문법을 함께 구현. 최초 Cycle을 Interview로
  강제하면서 그것을 걸을 문법을 빼면 유효한 다음 상태가 없어지기 때문.
- Step Grammar를 Cycle Kind 안으로 옮김. 같은 `outcome`도 Interview와 Experiment가 요구하는
  Report가 다르고, 서로의 Step을 열 수 없어야 하므로 평평한 목록으로는 가를 수 없다.
- 구조적 reference 를 전부 typed 로 통일. `outcome_ref` · `synthesis_ref` · `target_node_ref` 가
  같은 파싱·오류 규율을 쓰고, 거절할 때마다 올바른 전체 주소를 함께 말한다.
- `basis_refs` 는 block scalar 한 줄에 하나. 범용 list 문법을 만들지 않는다.
- Cycle Kind 의 한 줄 설명은 `gil-spec.yaml` 이 갖는다 — renderer 에 흩어 적지 않는다.
- Open Receipt 는 `실행` 블록 없이 실제 작업으로 제어권을 넘긴다.
- 공개 표면을 `start · open · close` 셋으로 좁힘. Step 과 Cycle 경계는 GIL 이 판정하고 AI 가
  외우지 않는다. `gil cycle open/close` 는 호환으로만 남긴다.
- `outcome_ref` 를 typed `StepRef` 로 정합화. bare 와 화면 축약은 저장 reference 가 아니다.
- `close_chain` 은 명세에 남기되 실행 가능한 값에서 내리고, 적으면 아직인 까닭을 말한다.
- 영구 ID는 프로젝트 로컬에서 종류별로 유일하고 재사용하지 않으며 typed reference로 저장.
  Cycle은 `cycle:C2`, Step은 소속을 포함한 `step:C2/S3`; `#3`은 현재 화면의 축약에만 사용.
- 최초 Existence는 내용이 빈 ES0과 함께 생성되고 J0은 항상 `state:ES0`을 참조. 모든 Journey
  revision은 실재하는 Existence State를 반드시 가리키며 State ref는 null일 수 없음.
