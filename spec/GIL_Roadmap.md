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

마지막 갱신: **2026-09-19**

```text
전체 이정표 10개

진행도  [x][x][~][x][x][x][~][ ][ ][L]
        M0 M1 M2 M3 M3.5 M4 M5 M6 M7 M8

완료     5  Step Core, 단일 Cycle 경계, Artifact 시간선, AI Manual Foundation, Failure Revisit
진행 중  2  Bootstrap 잔여(M2), Human Monitor(M5)
대기     2  Advanced Interview·Chain Closing(M6), Scenario Suite(M7)
Later    1  성공 가지 Merge
```

현재 한 문장:

> **사고의 시간선과 결과물의 세계는 format 4에서 연결됐고, 중단 후에도 복구 가능한 방식으로
> 되돌아갈 수 있다. 그리고 두 계열의 새 Agent 세션이 전체 명세 없이 `gil context`와 주소
> 가능한 Help Topic만으로 실제 작업과 Cycle을 완주했다. M3·M3.5·M4는 닫혔다.
> macOS Native Companion과 실제 Project 자동 갱신까지 동작한다. 이제 Monitor를 필수 인간 표면으로
> 고정하고 persistent Host PiP 우선·Native Companion fallback·비개발자 무터미널 설치를 배포
> 계약으로 닫는다.**

현재 초점:

- M5의 인간 판독·장시간 관찰 실험을 마친다.
- persistent Host PiP와 Native Companion을 같은 필수 Monitor의 두 adapter로 정렬한다.
- macOS·Windows 비개발자가 Plugin 설치에서 Monitor까지 terminal 없이 도달하는 배포 경로를 만든다.

바로 다음 목표:

> **M5-D의 capability 판정·Companion 설치 상태·승인 기반 설치 계약을 시험 가능한 adapter 경계로
> 만들고, Windows feasibility build로 macOS 전용 결합을 조기에 드러낸다.**

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
M3 Artifact Timeline                 완료
  ↓
M3.5 AI Manual Foundation            완료   ← GIL Manual Model v0.1
  ↓                                          M4는 M3-D Cycle Exit Snapshot에 의존한다
  ├─ 중첩 GIL 프로젝트 지원          Later  §7.4 미결 기능
  ├─ Managed Dataset                 Later  §7.5 결정 로그만 남긴다
  ↓
M4 Failure Revisit & Branching       완료
  ↓
M5 Human Monitor                     진행 중 ← GIL Monitor Model v0.1
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
- [x] `gil help <주제>` 점진적 도움말 — M3.5에서 구현

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

상태: `[x] 완료` — 남은 항목은 전부 **범위 밖으로 미룬 것**이거나 후속 Milestone 의 몫이다.

규범: **`GIL Artifact Model v0.1`** — Artifact·Snapshot·`gil restore`의 단일 진실 공급원이다.
이 체크리스트는 그 문서를 구현 순서로 옮긴 것이며, 규칙의 근거는 전부 거기 있다.

목표:

> GIL의 사고 Graph와 작업 결과물의 세계를 snapshot으로 연결하고, 이후 Cycle revisit이 세계를
> 복원할 수 있는 기반을 만든다.

### M3-A Artifact 정체성과 manifest

**완료.** 관측기와 format 4 결합까지 구현됐다.

- [x] Artifact 정체성 = **정규화된 상대 경로 + 실제 바이트** (Artifact Model §3.1)
- [x] mtime·생성 시각·소유자·권한은 정체성에 **넣지 않음**
- [x] 내용은 **바이트로 비교** — 줄바꿈·인코딩을 임의 변환하지 않음 (§3.2)
- [x] rename·이동은 **삭제 + 생성**으로 관측
- [x] 경로 계약: 상대 경로 · `/` 구분자 · UTF-8 · 절대경로와 `.`/`..` 금지 (§3.3)
- [x] 구성 요소에 `\` 를 담은 이름은 Artifact 경로가 아님 — 전체 관측 거절
- [x] 관측 경로와 문자열 parser 가 **같은 검사**를 지나 왕복이 성립
- [x] 프로젝트 루트는 `EntryPath` 가 아니라 별도 오류 자리로 표현
- [x] 대소문자와 Unicode 표기를 **관측한 그대로 보존** — NFC/NFD 임의 적용 없음
- [x] 표현할 수 없는 경로가 있으면 **조용히 제외하지 않고 전체 관측 거절**
- [x] 프로젝트 절대 위치는 manifest에 없음 — 폴더를 옮겨도 같은 세계
- [x] 정렬은 **경로 UTF-8 바이트 오름차순** 하나 — locale 비의존
- [x] 일반 파일만 기록 · 빈 디렉터리는 세계에 없음 (§3.4)
- [x] **프로젝트 루트 바로 아래의 `.gil/` 하나만** 제외
- [x] **더 깊은 곳의 `.gil` 디렉터리는 `NestedGilRepository`로 전체 관측 거절**
- [x] 중첩 `.gil` 내부를 탐색하지 않음 — 이름과 위치만으로 즉시 거절
- [x] `.gil` 이라는 이름의 **일반 파일**은 일반 파일 규칙 적용
- [x] `.gil` 이라는 이름의 **심볼릭 링크**는 `Symlink` 규칙으로 거절
- [x] 심볼릭 링크·특수 항목은 **전체 관측 거절** — 따라가지도 조용히 빼지도 않음
- [x] 거절 시 어떤 파일도 변경하지 않고 논리 상태도 확정하지 않음
- [x] 대용량 파일에 공개 상한 없음 · 스트리밍 관측 · 실패 시 전체 거절 (§3.5)
- [x] `SnapshotRef`(`snapshot:A1`) — 프로젝트 로컬 순차 ID이자 **세계의 정체성** (§13)
- [x] `gil start`가 **실제 프로젝트 상태**를 최초 불변 Snapshot으로 확정 (§4)
- [x] `gil start`가 최초 Snapshot·Project·Existence·Journey·뿌리 Cycle·그 Cycle의
      `entry_snapshot_ref`를 **하나의 논리적 초기화 트랜잭션**으로 확정
- [x] 최초 Snapshot 참조는 **뿌리 Cycle의 `entry_snapshot_ref`** 가 갖는다 (§4·§7.1)
- [x] `Project` 뿌리에 `baseline_snapshot_ref`를 **두지 않음**
- [x] 모든 `snapshot_ref`의 실재를 복원 시 검사

### M3-B 생성 권한과 변경 경계

- [x] Artifact 세계를 **확정할 권한**은 `gil start`와 Verify close에만 (§5)
- [x] Interview·Define·Hypothesis·Analysis·Outcome·Cycle close는 세계를 확정하지 않음
- [x] clean / dirty 판정은 관리 범위와 정규화 규칙으로 만든 **manifest 비교** (§6)
- [x] 권한·mtime 변경과 빈 디렉터리 생성·삭제는 **dirty가 아님**
- [x] **안정된 관측** — 확정 직전 재관측, 다르면 「관측 중 변경되었다」로 거절 (§6)
- [x] 읽는 동안 파일이 사라지거나 생기거나 읽기 오류가 나면 전체 거절
- [x] 관측 거절 시 Step·Will·Journey·Report·Graph·World Current 무변경
- [x] Verify에는 verdict가 없고 Snapshot 확정은 판정과 독립임을 보존
- [x] 비-Verify Action Step close에서 Artifact 변경이 있으면 거절 (§6)
- [x] **Cycle container close에서도** Artifact 변경이 있으면 거절
- [x] 거절 시 Step과 Active Will이 열린 채 남고 Journey revision·Done Will·Report가
      부분 저장되지 않음
- [x] 경고만 하고 닫거나 자동으로 변경을 버리는 경로 없음
- [x] `gil status`의 clean / dirty 표시 — **같은 read model 하나를 지남**
- [x] 관측 실패를 dirty 로 오판하지 않고 「확인하지 못했다」로 구분
- [x] dirty 일 때 Verify 는 「닫아 확정」, 그 밖은 「먼저 `gil restore`」
- [x] 내부 digest·객체 경로·전체 파일 목록 비노출 · status 는 읽기 전용

### M3-B1 객체 저장소와 canonical manifest codec  `[x]`

- [x] `.gil/artifacts/{blobs,manifests,tmp}/sha256/<2>/<나머지>` 경로 (Artifact Model §10.5)
- [x] blob = 원본 바이트 그대로 — 헤더·압축·암호화·변환 없음
- [x] blob 주소 = `SHA-256(파일 바이트)` · 같은 바이트는 blob 하나 공유
- [x] canonical manifest 이진 형식 — magic·version·algorithm·count·항목
- [x] 정수는 big-endian 고정 폭 — native endian·`usize` 비의존
- [x] 알고리즘 태그는 **머리에 한 번만** — 항목마다 되풀이하지 않음
- [x] 항목은 엄격한 오름차순 · 중복 경로 없음 · 비canonical 은 **정렬하지 않고 거절**
- [x] decoder 가 입력을 믿지 않음 — 길이 필드로 무제한 선할당하지 않음
- [x] manifest 주소 = `SHA-256(canonical bytes)` — 공개 `SnapshotRef` 가 아님
- [x] 임시 자리에 스트리밍 → 확정 · 기존 객체를 덮어쓰지 않음 (**B2a 에서 hard link 로 보정**)
- [x] 읽을 때 주소와 실제 내용을 다시 견줌 · 손상은 거절하고 고치지 않음
- [x] 첫 훑기가 지문과 blob 을 **한 스트림**으로 — 파일을 세 번 읽지 않음
- [x] 두 번째 관측이 다르면 논리 Snapshot 없음 · 미참조 객체는 손상이 아님
- [x] 시작 시 canonical 임시 일반 파일만 회수하고, 모르는 항목·링크·디렉터리는 거절

### M3-B2a append-only 확정과 registry 도메인 타입  `[x]`

**format 4 결합 전에 완성한 준비 조각이다.** 당시 `state.yaml`은 format 3이었으며,
현재는 M3-B2b에서 format 4로 올라갔다.

- [x] 확정을 **hard link** 로 — `rename` 은 이미 있는 최종 경로를 말없이 갈아 끼운다
- [x] 이미 있으면 **건드리지 않고 확인만** — 같으면 공유, 다르면 손상으로 거절
- [x] hard link 를 못 거는 파일 시스템에서 **rename 으로 물러서지 않음** — 거절한다
- [x] `flush` + 파일 `fsync` + 부모 디렉터리 `fsync`(Unix) — 보장의 실제 범위를 명세에 기록
- [x] 확정 직후 최종 객체를 **다시 열어** 지문 재검증 — 「썼으니 있다」를 믿지 않음
- [x] 실패한 확정은 제 임시 이름을 제 손으로 걷음 (죽은 프로세스의 잔해는 미결)
- [x] blob 과 manifest 가 **같은 확정 경로 하나**를 지남
- [x] `ManifestAddress` — manifest 전용 주소 타입 · blob 주소가 그 자리에 올 수 없음
- [x] `SnapshotRegistry` 도메인 타입 — `intern` · `resolve` · `find_by_manifest`
- [x] 같은 manifest 는 **기존 `SnapshotRef` 재사용** · `next_id` 와 records 불변 (§13)
- [x] `A0` 없음 · 이름 재발급 없음 · 한 세계에 이름 하나 · 오름차순 · 빈틈 없음
- [x] 이름이 바닥나면 **감싸 돌지 않고** 명시적 오류
- [x] `restore(next_id, records)` 구조 검증 — 위 불변식을 모두 거절 사유로
- [x] registry 는 **메모리 안에서만** — `state.yaml` 을 읽지도 쓰지도 않음

### M3-B2-lock 프로젝트 트랜잭션 잠금  `[x]`

**format 4보다 먼저다.** 두 명령이 같은 `next_snapshot_id` 를 읽으면 같은 이름을 서로 다른
세계에 준다 — registry 를 저장하기 전에 발급이 직렬화되어 있어야 한다(Artifact Model §10.6).

- [x] `.gil/project.lock` 에 건 **OS advisory lock** — 파일의 존재는 잠금 상태가 아님
- [x] 표준 라이브러리의 `File::try_lock` — 새 의존성 없음
- [x] `create_new` sentinel · lock 디렉터리 polling · PID 파일 추측을 쓰지 않음
- [x] 비정상 종료 시 운영체제가 해제 — 사람이 지울 stale lock 이 없음
- [x] **상태를 읽기 전에** 획득 · 명령 전체가 끝날 때까지 보유
- [x] RAII guard — 정상·오류·panic·프로세스 종료 어느 길로든 해제
- [x] 잠금이 걸린 파일 handle 의 수명과 guard 수명이 일치 · 임시 값으로 두지 않음
- [x] 같은 프로세스가 중복 획득하지 않음 — 명령 경계에서 한 번 잡고 안으로 넘김
- [x] non-blocking · 경쟁하면 즉시 거절 · 기다리거나 빼앗지 않음
- [x] 경쟁과 「잠글 수 없는 자리」를 구분해 말함
- [x] 상태 접근 CLI 전부가 같은 잠금 경계를 지남 (읽기 명령 포함)
- [x] `--version`·정적 help 는 프로젝트를 찾지 않으므로 잠그지 않음
- [x] `gil start` bootstrap — `.gil` 을 만들고 **잠근 뒤에** 기존 상태를 재검사
- [x] 초기화 가능한 내부 흔적(`project.lock`·`artifacts/`)과 거절할 상태를 구분
- [x] 저장 계층 내부 경로가 guard 없이는 **컴파일되지 않음** (`save_within`·`load_within`)
- [x] 별도 프로세스로 검증 — 정상 종료·강제 종료·잔해 파일·동시 `start`
- [ ] shared read lock — 모니터링 성능 문제가 실제로 확인되면 그때 검토
- [ ] timeout·retry·wait 옵션 — v0 에 만들지 않음

**남은 한계**: 공개 `load`/`save` 는 여전히 잠금 없이 부를 수 있다. CLI 는 전부 잠금을
지나므로 GIL 명령끼리는 보장되지만, 라이브러리를 직접 쓰는 코드까지 안전하다고 말하지
않는다(Artifact Model §10.6).

### M3-B2b format 4 결합  `[x]`

**format 4 는 처음부터 완전하다.** 「나중에 채울 null」을 만들지 않았다.

- [x] `state.yaml` 의 `artifacts` 블록 — `next_snapshot_id` + `snapshots[{id, manifest}]`
- [x] record 의 `id` 는 bare `A1`, 가리키는 자리는 typed `snapshot:A1`
- [x] manifest 주소는 `algorithm` + 소문자 canonical hex — 대문자·홀수 길이 거절
- [x] 모든 Cycle 에 `entry_snapshot_ref` · 열린 Cycle 에 Exit 없음 · 닫힌 Cycle 에 Exit 필수
- [x] 닫힌 Verify 에 `snapshot_ref` 필수 · 열린 Verify 와 그 밖의 Kind 에는 없음
- [x] 자식 Cycle 의 Entry = 부모의 Exit (고르지 않고 **읽는다**)
- [x] Cycle Exit = 마지막 Outcome 계보의 **가장 가까운 Verify**, 없으면 Entry
- [x] World Current 는 **유도값** — 캐시 필드 없음 · 계산은 한 함수에만
- [x] `gil start` 가 지금 폴더를 관측해 최초 세계를 확정 — 빈 세계로 만들지 않음
- [x] Verify close 트랜잭션 — 관측 → 객체 확정 → intern → 기록 → Will Done → 판 → 저장
- [x] 같은 세계면 **기존 `SnapshotRef` 재사용**, 처음 보는 세계면 새 이름
- [x] 비-Verify Step close dirty gate — 다르면 거절, 거절 시 전부 불변
- [x] Cycle container close dirty gate 와 Exit 확정
- [x] load 검증 ①registry 구조 → ②manifest 객체 → ③Graph 참조
- [x] blob 전수 해시 없음 — 보장의 경계를 명세와 시험에 못 박음
- [x] `tmp/` 회수 — canonical 이름의 일반 파일만, 모르는 것·링크·디렉터리는 거절
- [x] 창고 최상위 구조 검증 — `blobs`·`manifests`·`tmp` 만
- [x] 객체 내구성 → 상태 내구성 순서 · state 저장도 flush·fsync·rename·디렉터리 fsync
- [x] format 3 은 **변환하지 않고** 보존한 채 거절
- [ ] `gil fsck` — 범위 밖

### M3-C Verify close 트랜잭션  `[x]`

- [x] Report 검증 → 관측 → 세계 확정 → `snapshot_ref` → Will Done → Journey revision →
      Closed 를 하나의 원자적 동작으로 (§7)
- [x] 하나라도 실패하면 전체가 이전 상태
- [x] `snapshot_ref`는 Report가 아니라 Verify Node의 **구조 필드**
- [x] 다른 Closed Step은 lineage에서 가장 가까운 선행 Verify를, 없으면 Cycle Entry를 유도
- [x] **dirty일 때만** 새 `SnapshotRef` 발급 (Artifact Model §13)
- [x] **clean이면** 새 ID를 만들지 않고 기존 `SnapshotRef`를 Verify에 기록
- [x] 아무것도 바꾸지 않은 Verify도 정상적으로 닫힘 — Verify 에는 verdict 가 없다
- [x] 공개 `SnapshotRef`(`snapshot:A1`)와 내부 내용 주소를 분리 — receipt 에 hash 비노출
- [x] World Current Snapshot은 **유도값** — 캐시 필드를 두지 않음 (§7.6)
- [x] Snapshot 저장소(①)와 `state.yaml`(②)의 순서·비대칭 검사 (§10)

### M3-D Cycle Entry / Exit Snapshot  `[x]`

Entry — 전이가 정한다 (§7.1)

- [x] **모든 Cycle이 생성과 동시에 실재하는 `entry_snapshot_ref`를 지님** (`Option` 이 아니다)
- [x] Entry는 그 Cycle을 **연 전이가 출발한 세계**다
- [x] 뿌리 → `gil start`의 최초 SnapshotRef
- [x] `open_child` → 부모 Cycle의 `exit_snapshot_ref`
- [x] `open_child`는 부모가 닫혀 있고 실재하는 Exit을 가질 때만 허용
- [ ] `revisit` → **revisit 대상 Cycle의 `exit_snapshot_ref`** (M4가 밟는다 — 아직 없다)
- [x] `revisit`의 구조적 `parent`와 Entry 세계는 모두 대상 Cycle에서 받고,
      `revisit_from`만 실패 Cycle을 가리킴
- [ ] merge로 열린 Cycle의 Entry는 **미결로 남김** — 부모 Exit으로 미리 고정하지 않음
- [x] Cycle 생성 시·복원 시 Entry Snapshot의 **실재 검사**

Exit — lineage가 정한다 (§7.2·§7.5)

- [x] Cycle close는 새 Snapshot을 확정하지 않음
- [x] 마지막 Outcome의 **구조적 lineage**에서 가장 최근 Verify Snapshot을 Exit로 기록
- [x] 그 lineage에 Verify Snapshot이 없으면 **그 Cycle의 Entry**를 계승
- [x] 버려진 가지의 Snapshot을 고르지 않음
- [x] 이름이 가장 큰 Snapshot을 고르지 않음 — **살아남은 가지가 더 작은 이름**인 시험으로 고정
- [x] 열린 Cycle의 `exit_snapshot_ref`는 `null` · 닫힌 Cycle은 필수
- [x] 닫힌 Cycle 복원 시 Exit Snapshot의 **실재 검사**
- [x] Entry = Exit 허용 — Artifact를 바꾸지 않는 Interview Cycle이 그렇다

### M3-E `gil restore`  `[x]`

목표 유도 (§8.1)

- [x] **Snapshot 대상 인수를 두지 않음** — 추가 인수가 있으면 명확히 거절
- [x] 목표는 `Cycle::world_snapshot()` **한 함수**가 유도 — dirty gate·Cycle Exit 과 공유
- [x] 현재 위치의 **구조적 Step lineage**에서 가장 가까운 닫힌 Verify의 `snapshot_ref`
- [x] 없으면 **현재 Cycle의 `entry_snapshot_ref`** · 닫힌 Cycle 경계면 Exit
- [x] **부모 Cycle이나 `Project` 뿌리를 다시 순회하지 않음**
- [x] 버려진 가지 · 최대 ID · 사용자 지정을 쓰지 않음 — 살아남은 가지가 **더 작은 이름**인
      배치로 고정
- [x] 열린 Verify가 아직 확정하지 않은 변경도 직전 lineage 기준으로 되돌림

효과 (§8.2·§8.3)

- [x] 관리 대상 세계 **전체**를 목표 manifest와 정확히 같게 만듦
- [x] 교체 · 생성 · 삭제 · 무변경 네 갈래 · rename 은 삭제+생성으로 복원
- [x] 비게 된 폴더 제거 · rollback 은 **이번에 만든 폴더만** 거둠
- [x] `.gil/`은 절대 변경하지 않음
- [x] 현재 Step·Active Will·Journey·Done Will·Graph·Report·registry·기존 Snapshot 무변경
- [x] **`state.yaml` 바이트가 완전히 같은지** 시험으로 고정
- [x] **행동 취소가 아님** — 열린 Node는 열린 채로 남고 정상 Report로 닫음

원자성 (§8.4)

- [x] `preflight → prepare → apply → verify → commit → cleanup`, 실패는 rollback
- [x] 실행 전 완전 관측 · 링크/특수 항목/중첩 `.gil` 이면 **무변경** 거절
- [x] 목표 manifest와 **모든 blob 의 바이트를 전수 검증**한 뒤에만 진행
- [x] `.gil/restore/{preparing-*, active/, cleanup-*}` · `active` 는 잠금 덕에 최대 하나
- [x] `PLAN` 은 versioned 이진 형식 — 경로 검증·오름차순·중복/잘림/trailing 거절
- [x] 보관 이름은 **불투명한 서수** — 사용자 경로를 내부 파일 이름으로 쓰지 않음
- [x] 덮어쓰거나 지울 **현재 파일만** 보관 — 세계 전체를 복제하지 않음
- [x] rollback 자료는 registry 에 들어가지 않음 — 새 SnapshotRef 발급 없음
- [x] `preparing → active` 원자적 publish 이후에만 파일을 건드림
- [x] 목표 blob 과 **hard link 하지 않음** — 작업 파일 편집이 창고를 고치지 못하게
- [x] 적용 직전 before 상태 재확인 · 다르면 rollback (외부 writer)
- [x] 적용 후 **결과를 다시 관측**해 목표와 견줌 · 다르면 rollback
- [x] `COMMITTED` 를 backup 삭제 **전에** durable 하게 기록
- [x] **중단 → 다음 GIL 명령이 감지·복구한 뒤에만 다른 동작 허용**
- [x] 복구는 **state load 보다 먼저** · 잠금 안에서 · 실패하면 원래 명령 실행 금지
- [x] restore 영역의 모르는 항목·링크는 조용히 지우지 않고 거절
- [x] 내부 준비 영역은 사용자 상태가 아님 — 선택·참조·Git 용어 없음

권한과 receipt (§8.5·§8.6)

- [x] 내용만 교체할 때 **실행 전 권한 보존** · 새 파일은 시스템 기본 권한
- [x] 권한 때문에 실패하면 전체 거절 + rollback
- [x] **멱등** — 이미 같으면 오류가 아니라 성공적인 no-op
- [x] no-op 은 transaction·객체·저장 어느 것도 만들지 않음
- [x] receipt는 목표 ref · 교체/생성/삭제 수 · 유지된 Cycle·Step·Will만
- [x] 개별 파일 목록 전체와 raw digest 를 기본 출력에 내보이지 않음
- [x] 없는 현재 항목을 지어내지 않음

확인 계약 (§8.8)

- [x] **대화형 확인 없음** — 명령 실행 자체가 복원 의사다
- [x] `--force`·`--yes`·별도 confirm 명령을 만들지 않음
- [x] restore 전에 반드시 실행해야 하는 status/check 명령을 두지 않음
- [x] 비대화식 에이전트가 그냥 부를 수 있음

합격 조건 — **죽여서 잰다**

- [x] `prepared-not-armed` 중단 → 다음 명령이 잔해만 치움
- [x] `after-prepare`·`after-first-apply`·`before-commit` 중단 → 다음 명령이 rollback
- [x] `after-commit`·`before-cleanup` 중단 → **되돌리지 않고** 잔해만 정리
- [x] 복구가 state load 보다 먼저임을 **읽을 수 없는 `state.yaml`** 로 고정
- [ ] rollback 과 외부 writer 가 계속 경쟁할 때의 종결 전략 — 미결(§12)

### M3-F 시간선과 공개 어휘

- [x] Snapshot 복원이 Journey revision·Done Will·Report·Graph·Snapshot 객체를 지우지 않음 (§9)
- [x] 내부 준비 영역을 사용자 상태나 staging으로 노출하지 않음
- [x] 공개 개념과 오류 메시지에 Git 용어를 노출하지 않음 (§14)
- [x] `.gilignore` 공개 계약은 실제 필요가 확인된 뒤 결정 — 지금 만들지 않음
- [x] delta·chunk·pack·prune 은 **필요성이 확인된 뒤의 내부 최적화** — 공개 계약이 아님

합격 조건:

- [x] 이미 파일이 있는 폴더에서 `gil start` 한 번이 그 실제 상태를 기준 세계로 확정한다.
- [x] 현재 작업물이 어느 Verify와 어느 Cycle의 세계인지 구조에서 유도할 수 있다.
- [x] 비-Verify Step과 Cycle을 dirty 상태에서 닫으려 하면 거절되고, 거절 뒤 상태가 그대로다.
- [x] `gil restore`가 Artifact만 복원하고 Graph·Journey는 바꾸지 않는다.
- [x] snapshot 실패로 존재하지 않는 참조가 생기지 않는다.
- [x] 같은 세계를 두 번 확정해도 `SnapshotRef`가 하나다 — 이름이 바뀌면 세계가 바뀐 것이다.
- [x] 닫힌 Cycle의 Exit Snapshot이 버려진 가지가 아니라 마지막 Outcome의 lineage를 따른다.
- [x] 프로젝트 폴더를 다른 경로로 옮겨도 같은 Artifact 세계로 판정된다.
- [x] 관측이 만든 모든 경로를 같은 parser가 다시 읽는다.
- [x] 심볼릭 링크가 하나 있으면 관측이 거절되고 파일은 하나도 바뀌지 않는다.
- [x] 프로젝트 안에 다른 GIL 저장소가 있으면 관측이 거절되고 그 안을 읽지 않는다.
- [x] `gil restore`를 두 번 실행하면 두 번째는 성공적인 no-op이다.
- [x] restore 도중 프로세스를 죽여도 다음 명령이 실행 전 세계로 되돌린다.
- [x] `gil status` 하나로 기준 Snapshot·clean/dirty·지금 밟을 수 있는 수를 읽을 수 있다.
- [x] clean → dirty → `gil restore` → clean 전이가 status 만 보고 읽힌다.

**M3 에서 하지 않기로 한 것** — 미결이 아니라 결정이다.

- `gil fsck`·prune·pack·delta·chunk — 필요성이 확인된 뒤의 내부 최적화(§14)
- `.gilignore` — 공개 계약을 지금 만들지 않는다
- 파일별 diff·상세 목록·`gil history` — 기본 receipt 를 넘는 해상도는 별도 결정(§8.6·§12)
- Managed Dataset — Artifact 가 아니다(§7.5)
- Cycle-level revisit·merge — M4·M8 의 몫이다

**여전히 미결로 남은 것**(Artifact Model §12):

- merge 로 열린 Cycle 의 Entry 규칙
- rollback 과 외부 writer 가 계속 경쟁할 때의 종결 전략
- 미참조 내부 객체를 언제 거둘 것인가

권장 시나리오:

> 기존 파일이 있는 저장소에서 시작해, 한 Experiment Cycle이 실제로 파일을 고치고 그 세계가
> Cycle Exit에 남는 것을 확인한다.

---

## 7.4 M3 이후 — 중첩 GIL 프로젝트 (미결 기능)

상태: `Later` — **우선순위를 임의로 높이지 않는다.**

v0은 중첩 GIL 프로젝트를 지원하지 않는다. 프로젝트 안에서 다른 `.gil` 디렉터리를 발견하면
Artifact 관측 전체를 거절한다(`GIL Artifact Model v0.1` §3.4).

조용히 제외하는 것도, 일반 Artifact로 추적하는 것도 안 되기 때문이다.

```text
조용히 제외   바깥 restore가 안쪽 작업 파일만 과거로 되돌리고 안쪽 .gil은 현재에 남긴다
              → 안쪽 GIL의 기록과 실제 세계가 어긋난다
              → 숨은 ignore 영역이 생긴다
일반 추적     바깥 restore가 안쪽 Journey·Will·Report·Graph를 과거로 되돌린다
              → World restore가 Journey를 되돌리지 않는다는 불변식 위반
```

지원하려면 다음이 **하나의 별도 모델**로 설계되어야 한다.

- [ ] nested project 또는 subproject reference
- [ ] 안쪽 프로젝트 전체를 하나의 외부 경계로 취급
- [ ] 바깥 Graph가 안쪽의 특정 `SnapshotRef`를 참조
- [ ] 바깥 restore가 안쪽 Journey와 내부 저장소를 변경하지 않는 규칙
- [ ] 중첩 프로젝트 이동·삭제·복원 계약

**M3에서 이를 구현하거나 schema 자리를 미리 만들지 않는다.**

---

## 7.5 M3 이후 — Managed Dataset (결정 로그)

상태: `Later` — **이번 범위에서 만들지 않는다.**

Dataset schema·`DatasetRef`·CLI·저장소를 M3 Artifact Snapshot 구현과 섞지 않는다. **Dataset용
필드를 M3 저장 schema에 미리 만들지 않는다.** 여기 남기는 것은 이미 확정된 방향뿐이며, 전체
Dataset Model은 M3 이후 별도 명세로 설계한다.

### 확정된 결정

경계

- 외부 원본 자료실은 **반드시 GIL 프로젝트 밖에 있다.**
- 외부 원본 자료실은 GIL이 관리·복원·불변성 보장을 하지 않는다.
- GIL은 실험을 위해 **반입한 Managed Dataset만** 관리한다.

단위

- **Dataset 전체가 하나의 불변 추적 단위**다.
- Dataset 내부 항목은 독립적인 GIL Node·Artifact·시간선을 갖지 않는다.
- Dataset의 변화는 기존 Dataset의 수정이 아니라 **새로운 Dataset의 확정**이다.

시간선

- Dataset의 확정·파생·사용 이력은 **Journey Timeline을 따라 append-only로 누적**된다.
- **World restore와 Cycle revisit은 Dataset 객체와 그 Journey 기록을 지우거나 되돌리지
  않는다.** Artifact 세계를 과거로 투영해도 어떤 Dataset을 만들었고 썼는지는 남는다.

Artifact와의 관계

- 현재 Verify가 사용한 Dataset은 Verify 또는 Report가 `dataset_ref`로 참조한다.
- **Artifact Snapshot이 Dataset을 소유하지 않으며 그 실제 바이트를 반복 저장하지 않는다.**

책임의 경계

- Query·Filter·추출 명세는 **AI 또는 사용자가 생성한다.**
- GIL은 명세의 의미를 생성하거나 판단하지 않는다. **입력 Dataset · 실행 명세 · 출력 Dataset의
  관계만 추적한다.**
- 개인정보·저작권·반입 자격·민감도 판정은 **v0 범위 밖**이다.

---

## 8. M3.5 — AI Manual Foundation

상태: `[x] 완료` — 두 번의 dogfood 가 목표를 실측으로 통과했다(M3.5-D).
남은 항목은 전부 **범위 밖으로 미룬 것**이거나 필요성이 아직 관측되지 않은 것이다.

목표:

> 전체 명세나 긴 few-shot을 주지 않아도 Agent가 현재 상태와 오류에서 필요한 규칙 하나를
> 발견하고, 일상 GIL loop를 수행하며 실패에서 복구한다.

규범: `GIL Manual Model v0.1`

**M3.5 에서 하지 않기로 한 것** — 미결이 아니라 결정이다.

- 성공 receipt 의 Help 링크 — 두 dogfood 의 마찰 어느 것도 이것으로 막히지 않았다
- 읽은 Topic 이력 저장 — 세션의 작업 기억이지 프로젝트의 사실이 아니다
- Example registry 와 실체 검증 — inline 예제만 두고 미룬다
- 자연어·fuzzy·의미 검색 · embedding · vector database
- Agent Skill · `llms.txt` · MCP · GUI

### M3.5-A Manual 정보 구조

- [x] Manual·Context·Story·History의 독자와 책임 분리
- [x] 네 단계 공개: Bootstrap → Discovery → Topic → Reference/Example
- [x] `/` 구분 canonical Topic ID와 비재사용·alias 규칙
- [x] 행동과 실패 지점 중심의 Topic 경계
- [x] Topic metadata와 고정 본문 구조
- [x] Domain Specification·Grammar·Read Model·Manual의 진실 원천 순서
- [x] 자연어 검색보다 상태와 정확한 `help_ref`를 우선하는 선택 규칙
- [x] CLI·Agent Skill·`llms.txt`·MCP가 하나의 Manual read model을 공유하는 방향
- [x] Project content가 bundled Manual을 덮어쓰지 못하는 신뢰 경계

### M3.5-B 최소 구현

- [x] 검증 가능한 Manual Topic source와 index
- [x] `gil help <topic>` — canonical Topic 하나 조회
- [x] canonical Topic ID 타입 — 다듬지 않는 정확한 왕복, 경로·enum 으로 암묵 변환 없음
- [x] 최소 front matter parser — `---` YAML `---` + Markdown, 새 의존성 없음
- [x] 필수 `id`·`title`·`summary` · 선택 `applies_when`·`related`·`examples`·`aliases`
- [ ] **Example 실체 검증** — Topic 본문의 inline 예제만 있고 `manual/examples/` 객체 체계와
      registry 는 아직 없다. `examples` metadata 는 주소 검증만 지나고 실체는 확인되지 않는다.
- [x] `[이름]` 절 경계 인식 — 범용 Markdown AST 없이
- [x] help 조회의 완전한 읽기 전용성 — `.gil` 을 찾지도 잠그지도 않음
- [x] 깨진 link·중복 ID·순환/분기/가로채기 alias·비canonical ID의 test 거절
- [x] 「주소가 아니다」와 「그런 Topic 이 없다」를 구분
- [x] Grammar 필드와 Manual 본문의 정합성 — 손으로 복제하지 않고 **투영**
- [x] Project content 가 bundled Topic 을 덮지 못함 · 설치본만으로 조회
- [x] `gil help` — 현재 상태에 **관련된 것만**, 최대 5개 (0개도 1개도 정상)
- [x] 유한한 `applies_when` 표지 — 모르는 key·값·글자 아닌 값을 index 에서 거절
- [x] 필드 없음(모든 상태)과 `applies_when: {}`(실수) 를 가름
- [x] `ManualContext` — 상태를 **한 번만** 읽는 읽기 전용 투영
- [x] `artifact_confirmation` 은 코어의 Verify 판정 하나를 공유 (`can_confirm_artifact`)
- [x] 정렬은 (조건 수 ↓, 주소 ↑) 두 열쇠 — `relevance` 필드를 만들지 않았다
- [x] `unknown` 을 dirty 로 오판하지 않고 짧게만 말함
- [x] 정확 조회는 잠금 없음 · 상태 기반 조회는 잠금 → 복구 → 상태 읽기
- [x] 프로젝트 밖 help 가 `.gil` 도 잠금 파일도 만들지 않음
- [x] 오류의 안정된 `help_ref` — Router 는 도메인 밖에 살고 typed 구조만 본다
- [x] 대응표 한 자리 · 오류 하나에 Topic 최대 하나 · 빈 절 없음
- [x] Router 가 돌려줄 수 있는 모든 주소의 **실재를 시험이 확인**
- [x] 붙이지 않는 거절 목록 — 잠금 경쟁·손상·관측 실패·실행 실패·주소 오류
- [x] 링크를 고르며 관측·잠금·저장이 늘지 않음
- [ ] status·open·close receipt의 선택적 `help_ref` (다음 조각)
- [x] enum 허용값의 Manual 투영 — `close_contract:<cycle>` 이 `gil close --help` 와 같은
      renderer 로 허용값·좁혀진 갈래·「아직 없음」까지 낸다
- [ ] 성공 receipt 의 선택적 `help_ref` — **필요성이 아직 관측되지 않았다**(아래 dogfood)

**오류 → Topic 대응표**

```text
비-Verify dirty close (Step·Cycle 경계)   artifact/dirty/non-verify
Verify Report 계약 오류                    step/verify/close
gil restore 에 허용되지 않은 인수          artifact/restore
행동 계약 누락·빈 칸 (실행형 Step open)    action/open-contract
Experiment Cycle Report 계약 오류          cycle/experiment/close
```

**dogfood 에서 발견한 마찰과 이번 보정**

Receiver Agent 가 열린 Verify 를 인수해 과제와 Cycle 을 완주했으나 네 번의 탐색성 거절이
있었다. Verify Report 는 `gil close --help` 로 복구됐고, 실제로 비어 있던 Manual 지식은
둘이었다 — **행동 계약 작성법**과 **Experiment Cycle Report 작성법**. 그 둘만 Topic 으로
더하고 Router 를 연결했다. 새 기능은 늘리지 않았다.

**여섯 Topic 의 실제 `applies_when`**

```text
current                     (필드 없음 — 모든 상태)
step/verify/close           cycle_kind: experiment · step_kind: verify · step_status: open
artifact/restore            project: present · world_state: dirty
artifact/dirty/non-verify   project: present · world_state: dirty
                            artifact_confirmation: unavailable
action/open-contract        project: present · step_status: none
cycle/experiment/close      cycle_kind: experiment · cycle_status: open
                            step_kind: outcome · step_status: closed
```

새 표지를 만들지 않았다. Experiment 의 **끝 경계**는 「닫힌 Outcome 위에 서 있다」로
기존 key 만으로 정확히 말할 수 있고, 그것이 코어의 `at_exit()` 와 같은 자리다.
`action/open-contract` 는 **시작 경계**(아직 아무것도 열지 않은 자리)에서만 추천하고,
그 밖에서는 오류 Router 가 발견 경로다 — 모든 상태에 붙는 Topic 을 만들지 않는다.

**Topic source 와 배포**

```text
src/manual/topics/**.md      source — 이 경로는 공개 계약이 아니다
include_str!                 바이너리와 같은 버전으로 묶인다
front matter 의 id           공개 주소 — 폴더를 옮겨도 그대로다
```

파일을 찾지 않으므로 작업 폴더의 같은 이름 파일이 덮어쓸 길이 자체가 없다.

**최소 parser 계약**(구현 중 확정)

- `---\n` 로 시작하고 `\n---\n` 로 닫히는 YAML front matter 하나.
- 그 뒤는 Markdown 본문. 열 0 의 `[이름]` 줄이 절을 가른다.
- 첫 절 앞의 글은 어느 절에도 들어가지 않는다.
- 본문의 `{{close_requires:<cycle>/<kind>}}` 한 줄은 읽는 순간 `gil-spec.yaml` 이 채운다.
  채우지 못하면 **조용히 지우지 않고** 그 사실을 적는다.

### M3.5-C 최초 Topic

- [x] `current`
- [x] `step/verify/close`
- [x] `artifact/restore`
- [x] `artifact/dirty/non-verify`
- [x] `action/open-contract` — dogfood 마찰에서 필요성이 확인됨
- [x] `cycle/experiment/close` — 같은 근거
- [ ] `interview/approval`
- [ ] `report/observation-vs-interpretation`
- [ ] 실제 오류에서 필요성이 확인된 error Topic

여섯 Topic 은 **지금 명세와 실제 CLI 만** 말한다. 각 Topic 의 명령 예제가 gil 이 아는 명령인지,
Verify Topic 이 verdict 를 요구하지 않는지, restore Topic 이 대상 인수·`--force`·사전 확인을
요구하지 않는지, dirty Topic 이 밟을 수 없는 길을 안내하지 않는지를 시험이 잡는다.

### M3.5-D 자기 온보딩 dogfood  `[x]`

두 번 돌렸다. 기록은 `GIL Manual Model v0.1` §16에 있다.

- [x] Agent에게 전체 명세 대신 Bootstrap Capsule만 제공
- [x] 새 세션에서 `gil context`로 현재 행동 복원 — 열린 Verify와 Active Will까지
- [x] 같은 세션에서는 context 반복 없이 open·행동·close 진행 (두 실험 모두 `context` 1회)
- [x] 의도적으로 만든 비-Verify dirty 실패에서 **Topic 하나로** 복구 (실험 1)
- [x] 필수 Report·계약 누락에서 Topic 하나로 복구 (실험 2 — 두 Topic이 실제로 쓰였다)
- [x] 실제로 읽은 Topic과 불필요하게 읽은 Topic 수 기록 — Manual 조건은 헛된 조회 0
- [x] control과 manual 조건을 같은 기능 과제로 비교
- [x] 다른 모델·세션이 같은 bundled Manual로 같은 규칙을 복원 (실험 2)

합격 조건:

- [x] 전체 Specification을 주입하지 않고 Bootstrap만으로 시작한다.
- [x] 흔한 실패 하나를 오류가 가리킨 Topic 하나만 읽고 복구한다.
- [x] `gil help` 기본 출력이 현재 관련 Topic 3~5개를 넘지 않는다.
- [x] 도움말 조회 전후 Project state와 Artifact 저장소가 완전히 같다.
- [x] Manual이 현재 Grammar에 없는 필드·허용값·전이를 제시하지 않는다 — 투영이 보장한다.
- [ ] **입력량이 줄면서 기능 준수율이 유지되는가** — 절반만 확인됐다. 기능 준수율은
      유지됐고 최초 prompt는 짧아졌으나, **실행 전체의 토큰 사용량은 두 조건이 거의 같았다.**
      전체 토큰 절약은 입증되지 않았다.

**입증된 최소 명제**

> 새 Agent 세션이 전체 GIL 명세를 미리 읽지 않고도, `gil context`·명령 receipt·
> typed refusal·주소 가능한 Help Topic만으로 실제 작업과 GIL Cycle을 이어 수행할 수 있다.

**입증되지 않은 것** — 여기 적힌 것을 넘어 주장하지 않는다.

- 전체 토큰 절약
- 모든 모델·모든 작업에서의 일반성 (두 계열, 각 한 번, 작은 과제)
- 자연어·의미 검색 (두 실험 모두 정확한 주소만 썼다)

범위 밖:

- 자연어 검색·embedding·vector database
- LLM의 Topic 자동 생성·자동 수정
- 사용자·프로젝트별 Manual override
- 원격 Wiki와 Manual 배포
- MCP 서버 구현
- GUI Manual 탐색

---

## 9. M4 — Failure Revisit & Branching

상태: `[x] 완료`

**의존: M3.** Cycle revisit은 「대상 Cycle Exit의 세계로 돌아간다」는 동작이므로, M3-D가
Cycle Exit Snapshot을 확정하기 전에는 돌아갈 곳이 없다. M3-E의 `gil restore`가 그 복원의
기계이고, M3-B의 dirty 거절이 revisit의 clean 전제를 만든다.

```text
M3-D Cycle Exit Snapshot   →  M4 revisit target의 세계이자 새 Cycle의 Entry
M3-E restore               →  M4 세계 복원 기계
M3-B dirty 거절            →  M4 clean 전제
```

M3-D가 「Entry는 **연 전이가 출발한 세계**」로 일반화해 두었으므로, M4는 표에 새 줄을 만드는
것이 아니라 **이미 있는 `revisit` 줄을 밟기만** 하면 된다.

Experiment Cycle failure Report의 `revisit`은 **기록할 수 있고 실행할 수 있는** 방향이다
(`GIL Artifact Model v0.1` §11의 1번 상태). M4-B가 대상을 검증하고 M4-C가 내부 이동과 복구
경계를 세웠으며, M4-D가 새 Cycle Open과 공개 CLI를 연결했다.

목표:

> 실패한 세계를 지우지 않고 Closed ancestor의 세계에서 다른 Cycle을 시작한다.

체크리스트:

- [x] Cycle-level `next_direction: revisit`
- [x] revisit target은 현재 Cycle lineage의 Closed ancestor
- [x] target Cycle은 새 자식을 가질 수 있는 성공 Cycle
- [x] failure Report에서 `next_direction.target_cycle_ref` 조건부 필수, 그 밖의 방향에서는 금지
- [x] dirty 상태에서 revisit 거절
- [x] target Cycle Exit Snapshot으로 세계 복원
- [x] **새 Cycle의 `entry_snapshot_ref` = revisit 대상 Cycle의 `exit_snapshot_ref`**
      (Artifact Model §7.1 — v0에서는 구조적 부모인 revisit 대상의 Exit과 같다)
- [x] `.gil`과 Journey는 Artifact 복원의 영향 없음
- [x] 실패 Cycle의 Graph·Report·snapshot 보존
- [x] `pending_cycle_revisit`
- [x] `pending_cycle_revisit`은 format 4의 선택적 필드 — 기존 파일의 부재는 `None`, format bump 없음
- [x] revisit 직후 새 Cycle만 허용
- [x] 새 Cycle `parent = target ancestor`
- [x] 새 Cycle `revisit_from = failed Cycle`
- [x] target이 실패 Cycle의 직접 부모일 때 실패 Cycle과 새 Cycle이 형제 관계
- [x] 더 먼 ancestor를 target으로 삼으면 새 Cycle은 그 ancestor의 자식이며 "형제"를 일반 불변식으로 쓰지 않음
- [x] 같은 실패 Cycle에서는 revisit 한 번만 가능하되, 나중의 실패 Cycle은 같은 target을 다시 선택 가능
- [x] 강제 revisit 없음
- [x] 논리 상태(②)를 먼저 확정하고 작업 폴더(③)를 기존 restore transaction으로 수렴
- [x] Cycle Model·Artifact Model §11·Roadmap·`gil-spec.yaml`의 상태 2 문구를 함께 상태 1로 이동
- [x] Help Topic `cycle/revisit` · `cycle/revisit/target`과 typed Router 구현

합격 조건:

- [x] 실패한 Artifact는 현재 세계에서 제거되지만 snapshot으로 남는다.
- [x] 실패 지식과 Report는 새 가지 Cycle에 전달된다.
- [x] 과거 Cycle이나 snapshot을 수정하지 않는다.

권장 시나리오:

> 여러 가설이 실패하고 대안 실험으로 전환하는 데이터 분석 문제.

---

## 10. M5 — Human Monitor

상태: `[~] 진행 중 — M5-A 완료, M5-C는 실제 Project 자동 갱신까지 닫힘, M5-B의 filter·scope 이어받기와 판독 실험이 남음`

목표:

> 사용자가 터미널과 raw YAML 없이 AI의 현재 위치, 실패, 전환과 다음 방향을 이해한다.

상세 의미 계약은 `GIL Monitor Model v0.1`을 따른다. M5에서는 아직 존재하지 않는 Chain,
승인 mode와 시각 자료 schema를 UI가 먼저 지어내지 않는다.

### M5-A0 Monitor Snapshot

- [x] Monitor가 답해야 하는 인간의 질문과 다른 투영의 역할 분리
- [x] "하나의 read model"을 하나의 사실 Snapshot과 목적별 projection으로 정의
- [x] 아직 구현되지 않은 Chain을 v0 출력에서 제외
- [x] active lineage는 parent edge만 따르고 `revisit_from`은 별도 관계로 정의
- [x] pending revisit와 완료된 revisit 구분
- [x] world `clean / dirty / unknown`과 단일 관측 규칙
- [x] semantic read-only와 Storage recovery 구분
- [x] Report·Will·사용자 문자열을 신뢰하지 않는 renderer 입력으로 정의
- [x] typed `MonitorSnapshot` 구현 — active lineage를 Cycle 해상도 사실로 보강
- [x] 검증된 Project loader만 사용 — raw YAML·CLI 문자열 파싱 없음
- [x] 한 Snapshot당 Artifact 세계 관측 한 번
- [x] status와 current Cycle·Step·world state 정합성 시험
- [x] Monitor 조회 전후 Graph·Journey·Will·Snapshot registry·작업 파일 불변

### M5-A1a plain text reference renderer

- [x] 순수 함수 `render_monitor_text(&MonitorSnapshot)`
- [x] `gil monitor` read-only 명령
- [x] Snapshot 생성 뒤 lock을 놓고 renderer 실행
- [x] 현재 Cycle / Step
- [x] 현재 실험 목적과 성공 기준
- [x] active lineage와 inactive Cycle 구분
- [x] active ancestor의 종류·상태·판정·handoff 표시
- [x] 실패 verdict와 구조적 sibling 관계를 혼동하지 않음
- [x] revisit 출처와 대상
- [x] Cycle handoff
- [x] Current Will
- [x] 현재 clean / dirty / unknown
- [x] 현재 가능한 행동과 선택적 Help Topic
- [x] 색·terminal 폭·ANSI·Unicode 도형 없이도 구조가 읽힘
- [x] 여러 줄 값의 indentation 유지

### M5-A1b 안전한 HTML renderer

- [x] A1a와 같은 `MonitorSnapshot`만 입력으로 사용
- [x] 완전한 standalone HTML5 문서와 `gil monitor --html`
- [x] Report·Will·사용자 문자열 HTML escape
- [x] raw HTML·script·외부 resource 자동 로드 없음
- [x] 엄격한 CSP와 renderer 소유 inline CSS만 허용
- [x] 색만이 아닌 text·heading·list로 상태와 관계 구분
- [x] 작은 화면에서도 읽히는 responsive layout
- [x] renderer 사이에서 typed reference·판정·다음 행동이 같음

### M5-A2 지속 관찰

구현 순서: **A2a 갱신 상태기계 → A2b 안전한 loopback server → A2c OS 변화 감지와 실사용 검증**.
`gil monitor --serve`는 세 조각이 모두 닫힌 뒤 공개한다.

- [x] loopback server·주소·요청·cache의 의미 계약 확정
- [x] browser refresh와 Artifact 재관측 주기 분리
- [x] watcher는 hint, 전체 `monitor()` 조회만 사실이라는 규칙 확정
- [x] Current / Stale / Unavailable 상태 정의
- [x] `gil monitor --serve` — `127.0.0.1` 임의 port와 capability path
- [x] 내부 loopback server — `127.0.0.1` 임의 port와 capability path
- [x] exact Host·token 검증, GET/HEAD만, 요청 크기·시간 제한
- [x] CSP·no-store·nosniff·no-referrer·DENY 응답
- [x] change hint debounce와 느린 reconciliation
- [x] browser refresh마다 전체 Artifact를 다시 관측하지 않음
- [x] 상태 변경 시 완전한 새 Snapshot으로 자동 갱신
- [x] UI가 프로젝트 lock을 장시간 소유하지 않음
- [x] watcher event를 GIL 사건으로 오인하지 않고 전체 조회로 수렴
- [x] 갱신 실패 시 stale 상태와 오류 표시
- [x] stale 뒤 event가 없어도 재시도하여 Current로 회복
- [x] server 종료 뒤 Project와 작업 파일 불변
- [x] UI의 cache·표현 상태와 GIL의 의미 상태 분리
- [x] OS 파일 감시 — 루트 `.gil`은 `state.yaml`만, 그 밖의 내부 사건은 hint로 만들지 않음
- [x] 관측이 스스로 hint를 낳아 영구 재관측하지 않음
- [x] watcher가 서지 못하면 화면과 stdout이 그 사실을 명시하고 reconciliation만 사용
- [x] Ctrl-C가 시험과 같은 종료 경로로 listener·watcher·worker를 끝냄

### M5-A3 실제 사용 검증

- [ ] 참여하지 않은 사용자가 30초 안에 현재 실험과 성공 기준을 설명
- [ ] 실패 가지와 현재 활성 가지를 혼동하지 않음
- [ ] CLI를 보지 않고 다음 행동을 설명
- [x] 판독 실험 1 수행 — 세 조건 모두 실패, 정보 부족이 아닌 평평한 시각 우선순위가 원인
- [x] 초보자가 Graph를 글 목록이나 ASCII art로 이해한다고 가정하지 않는 원칙 확정
- [x] 같은 MonitorSnapshot에서 안전한 inline SVG Cycle Graph 렌더링
- [x] parent 실선·revisit 점선·active lineage·inactive branch를 공간적으로 구분
- [x] 현재 Cycle만 Step을 펼치고 현재 Step을 위치와 글로 표시
- [x] SVG 옆 focus panel을 `지금 / 지금 할 일 / 왜 여기 왔는가` 순서로 재구성
- [x] 작업 행동(Will)과 그 뒤의 GIL 명령을 분리해 표시
- [x] 과거 `next_direction`을 현재 행동보다 낮추고 `당시`의 방향으로 명시
- [x] 실패 이유·교훈·revisit·현재 가설을 하나의 전환 서사로 투영
- [x] desktop·작은 화면 screenshot에서 node·edge·label 겹침과 잘림 없음
- [x] 색 없이 shape·line·label만으로 상태와 관계를 구분
- [x] 판독 실험 1 시나리오를 fixture로 고정하고 다섯 물음의 회귀 시험으로 잠금
- [x] 2026-09-05 시각 검토 — Cycle 중심 자유 배치 Graph는 작은 예시에서도 선이 복잡해 폐기
- [x] Git Graph형 단방향 시간축·lane과 Step 중심 node 원칙 확정
- [x] SVG layout을 `Step = node`, `Cycle/Chain = group`, `branch = lane`으로 교체
- [x] 새 node가 한 방향으로만 자라고 revisit도 화면에서 과거 방향으로 역행하지 않음
- [x] Cycle은 내용 영역의 경계·배경 띠로, Journey lane은 독립된 왼쪽 영역으로 표시
- [x] Step 옆에 kind와 짧은 인간용 요약을 정렬하고 typed reference는 보조 정보로 낮춤
- [x] 현재 경로는 연속 lane, 실패한 시도는 옆 lane의 끝으로 읽힘
- [x] 정적 Graph를 먼저 검증하고 click 기반 접기·펼치기는 interaction 계약 뒤로 미룸
- [ ] 같은 시나리오로 판독 실험 2 수행

### M5-B Host-Embedded Interactive Monitor

기본 사용자는 별도 `GIL.app`이나 browser를 먼저 열지 않는다. Codex·Claude Desktop 같은 Agent
Host 안에서 대화와 같은 Project의 Monitor를 연다. loopback server와 standalone shell은 개발,
진단 또는 Host가 embedded UI를 지원하지 않을 때의 fallback이다.

- [x] 기본 인간 표면을 Agent Host 안의 panel 또는 inline UI로 결정
- [x] `MonitorSnapshot → Host UI adapter`의 읽기 경계 정의
- [x] presentation intent와 domain-changing GIL action 분리
- [x] Host 중립 `MonitorViewV1` 전달 계약 명세 — 내부 `MonitorSnapshot`은 직접 직렬화하지 않음
- [x] Host 중립 presentation intent 명세 — select·focus·collapse·filter
- [x] 선택한 Step의 `NodeDetailV1` on-demand 상세 계약
- [x] 내부 `MonitorSnapshot → MonitorViewV1` 순수 투영 구현
- [x] kind·state·relation·world·action을 View 전용 enum으로 분리하고 JSON 문자열 왕복 준비
- [x] 값을 지닌 `ActionKind`를 `kind` + nullable 대상 kind로 손실 없이 투영
- [x] canonical JSON encoder와 null·빈 목록·원문 보존 왕복 시험
- [x] Host UI v1의 어휘 범위를 bundled GIL Grammar v0.1로 한정하고 미지원 값은 명시적 거절
- [x] `StepRef → NodeDetailV1` read model과 이름순 Report 투영
- [x] Codex Host 안의 fixture 기반 클릭 가능한 UX prototype
- [x] Graph가 기본 표면이고 text는 선택한 대상의 detail·검색·접근성 역할만 맡는 UX 확정
- [x] Step 선택 → 인접 요약 카드 + 별도 detail inspector UX 확정
- [x] Cycle 접기·펼치기와 접힌 행의 재배치 UX 확정
- [ ] 현재 위치로 이동·현재 경로만 보기·실패 갈래 filter
- [ ] Project와 Current Existence를 현재 대화의 명시적 scope에서 이어받음
- [x] port·capability URL 없이 Codex inline prototype을 열 수 있음
- [x] fixture UI가 `.gil`을 직접 읽거나 수정하지 않음
- [x] write action은 Human Checkpoint domain 계약 전까지 노출하지 않음
- [x] Codex Plugin UI에서 버튼·초기 자동 PiP 요청을 실측하고 실제 모드가 `inline`임을 확인
- [x] 지속형 Host surface 부재 시 Tauri Companion을 v0 기준 fallback으로 확정
- [x] 같은 canonical fixture Snapshot을 Tauri Companion에 표시
- [ ] 처음 보는 사용자를 대상으로 판독·탐색 실험

M5-B 구현 순서는 다음과 같다.

```text
Host-neutral Snapshot/Intent contract
→ typed MonitorViewV1 순수 투영
→ next_actions와 canonical JSON
→ NodeDetailV1
→ fixture prototype
→ 인간 UX 검증
→ 실제 MonitorSnapshot 연결
→ 다른 Host adapter와 fallback
```

### M5-C Persistent Tauri Companion

목표:

> Agent session과 무관하게 하나의 읽기 전용 창을 계속 띄우고, 그 창에서 등록한 GIL Project를
> 명시적으로 전환하며 현재 여정을 실시간으로 관찰한다.

첫 구현 조각은 **Tauri shell + fixture + Project switcher**다. 실제 `.gil` 연결과 watcher를 한 번에
넣지 않는다.

2026-09-11 실제 macOS Tauri 창에서 Step DAG, 절대 방향 edge 문법, 선택 요약과 상세, Cycle
접기·펼치기와 재배치, Project별 표현 상태 복원, 밀도 fixture와 자동 scroll을 검수했다. 첫 fixture
조각은 닫혔다. 2026-09-12에는 실제 GIL Project를 OS folder picker로 열어 DAG·상세·수동
refresh를 확인했고, picker와 읽기를 비동기 경계로 옮긴 뒤 창이 멈추지 않는 것도 실측했다.
2026-09-14에는 Companion-local settings와 실행·수명 UX를 닫았다. 창은 닫아도 숨을 뿐이고
menu bar에 남으며, 설치된 app bundle을 터미널 없이 실행하고 Agent가 같은 창을 앞으로 가져온다.

2026-09-16에는 선택 Project watcher를 닫았다. 실제 GIL Project에서 파일을 만들고 지우자
`clean`과 `dirty`가 사람의 새로고침 없이 오갔다. hint는 완전한 View 재조회 하나만 부르며,
경로도 사건의 종류도 화면으로 나가지 않는다.

남은 것은 **인간 판독·장시간 관찰 실험**이다.

- [x] Tauri app shell과 공용 UI bundle 연결
- [x] 기존 `reading_one` fixture로 Cycle DAG·현재 Cycle·detail interaction 표시
- [x] Project switcher에서 두 fixture scope를 전환하고 Project별 선택·detail을 격리해 복원
- [x] 최근 Project 목록·마지막 선택·창 위치를 Companion 설정에만 저장
- [x] 앱 재시작 뒤 Project 목록을 복원하되 마지막 선택 하나만 foreground에서 읽음
- [x] 사라진 Project와 다른 identity를 unavailable로 남기고 다른 Project를 추측하지 않음
- [x] 같은 display name은 표시용 scope suffix로 구분하고 Host 요청에는 전체 scope 사용
- [x] 창 geometry를 현재 display의 보이는 영역 안으로 제한해 복원
- [x] 손상·미지원 settings를 보존하고 자동 덮어쓰기 없이 임시 상태로 실행
- [x] Project 제거가 Companion 설정만 바꾸고 Project 파일은 전혀 바꾸지 않음
- [x] `.gil`·Artifact·Journey를 쓰지 않는다는 증거
- [x] GIL read adapter로 실제 `MonitorViewV1`과 `NodeDetailV1` 연결
- [x] OS folder picker로 Project를 명시적으로 선택하고 취소 시 현재 상태 유지
- [x] 수동 refresh가 완전한 View만 다시 읽고 실패 시 마지막 검증 View와 오류를 구분
- [x] 실제 Project의 open·View·detail·refresh가 `.gil`·Artifact·Snapshot 창고를 쓰지 않음
- [x] 현재 선택 Project의 변화 hint → 완전한 View 재조회
- [x] Project별 server·port·capability URL 없이 동작
- [x] 앱 하나로 Project 추가·제거·전환
- [x] Codex 또는 Claude session이 종료되어도 창과 마지막 검증 View 유지
- [x] 창 닫기가 창을 파괴하지 않고 숨기며 tray·Dock·재실행이 같은 창을 되살림
- [x] `⌘Q`와 tray 종료만 process를 끝내고 그 전에 설정을 flush
- [x] menu bar 표식으로 숨은 Companion을 찾아 열고 현재 Project·새로고침·종료를 제공
- [x] 로그인 시 시작을 OS 정식 자리로 등록하고 실패를 성공으로 표시하지 않음
- [x] 터미널 없이 실행할 수 있는 macOS app bundle과 사용자 영역 dogfood 설치
- [x] Agent의 `show_gil_companion`이 native 창을 열거나 앞으로 가져오고 결과를 typed로 구분
- [x] 사용자에게 보이는 표식을 소문자 `gil` 워드마크로 통일

M5-C 구현 순서는 다음과 같다.

```text
Tauri shell + fixture          (닫힘)
→ Project scope switcher        (닫힘)
→ 실제 GIL read adapter          (닫힘)
→ Companion-local settings      (닫힘)
→ 실행·수명과 native packaging   (닫힘)
→ 선택 Project watcher와 reconciliation   (닫힘)
→ 인간 판독·장시간 관찰 실험
```

하지 않는 것:

- Companion에서 `gil open`·`close`·`revisit`·`restore` 실행
- 여러 Project의 Graph를 한 화면에 합성
- 모든 등록 Project를 항상 전체 해상도로 background 관측
- Tauri 전용 사실 schema 또는 Graph 의미 생성

### M5-D Monitor Availability & Zero-terminal Distribution

상태: `[~] 명세 확정 · 구현 대기`

목표:

> 비개발자가 Plugin 설치 뒤 terminal·port·설정 파일 없이 지속형 GIL Monitor를 열며, Host가 진짜
> persistent PiP를 제공하지 않으면 AI의 안내와 OS 승인만으로 Native Companion을 준비한다.

설치 완료 조건과 Host별 fallback의 규범은 `GIL Distribution Model v0.1`이 소유한다.

- [x] Monitor를 선택 기능이 아닌 설치 완료의 필수 인간 표면으로 확정
- [x] persistent Host surface 우선·Native Companion fallback 순서 확정
- [x] inline 카드와 text는 preview·진단이며 설치 완료가 아님을 확정
- [x] AI가 설치를 조율하되 사용자 승인과 OS 신뢰 경계를 우회하지 않는 원칙 확정
- [ ] `persistent_host | native_companion | unavailable` capability 판정 구현
- [ ] PiP 요청 뒤 실제 mode·수명 계약을 확인하는 Host adapter 시험
- [ ] Companion `missing | stopped | outdated | ready` handshake 구현
- [ ] 설치·업데이트 완료 재감지와 원래 Monitor 요청 자동 재개
- [ ] Companion 없이도 GIL text loop가 동작하는 degraded mode 시험
- [ ] macOS Developer ID 서명·공증 또는 Store sandbox feasibility 확정
- [ ] Windows 10/11 feasibility build — watcher·locking·tray·single-instance·autostart
- [ ] Windows Store/MSIX 또는 signed installer 기본 채널 확정
- [ ] Plugin·Core·Companion·wire compatibility와 update rollback 계약
- [ ] macOS·Windows clean-machine 설치·업데이트·제거 시험
- [ ] 처음 보는 비개발자가 한 문장 요청으로 3분 안에 Monitor를 여는 설치 실험

배포 순서:

```text
Host capability probe
→ persistent PiP 실측
→ Companion handshake
→ trusted installer handoff
→ install completion re-detection
→ original request resume
→ macOS·Windows clean-machine 검증
```

공개 Plugin/MCP 제출은 이 조각의 끝이 아니라 후속 release gate다. 원격 MCP가 기본인 Host에서도
사용자의 로컬 Project는 remote server가 대신 읽지 않는다. public HTTPS MCP, 인증·도메인 검증과
심사 자료는 GIL의 시나리오 일반성이 M7에서 확인된 뒤 제출한다.

### M5 후속 — 선행 domain 계약 뒤 수행

- [ ] 표·차트·이미지·화면 캡처의 안전한 resource reference schema
- [ ] 시각 자료 caption·alt text·provenance 표시
- [ ] milestone / stepwise / autonomous 승인 상태와 Checkpoint UI
- [ ] 갑작스러운 Chain 종료 제안 전 경로 요약 — M6 Chain Closing 이후

합격 조건:

- [ ] 사용자가 30초 안에 “무엇을 하고 있고 왜 여기 있는가”를 설명할 수 있다.
- [ ] 실패 가지와 현재 활성 가지를 혼동하지 않는다.
- [ ] UI가 CLI와 다른 진실 공급원을 만들지 않는다.

권장 시나리오:

> 화면 변화를 단계별로 확인하는 프론트엔드 개발.

---

## 11. M6 — Advanced Interview & Chain Closing

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

## 12. M7 — Scenario Suite

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

## 13. M8 — Successful Branch Merge

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

## 14. 로드맵 갱신 규칙

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

## 15. 결정 로그

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

### 2026-08-24

- M2H Constraint-aware Receipt 완료. 허용값의 뜻과 계층을 machine-readable Grammar가 소유하고
  Receipt·`--help`·거절이 같은 read model 하나를 투영한다.
- `GIL Artifact Model v0.1`을 Artifact·Snapshot·`gil restore`의 **규범 단일 진실 공급원**으로
  세우고, 다섯 문서에 흩어져 있던 중복 규범을 참조로 정리.
- Artifact Snapshot은 World Timeline에 속하고 Journey Timeline은 복원의 영향을 받지 않는다.
- Snapshot을 확정할 권한은 `gil start`와 Verify close 둘뿐. Verify에는 verdict가 없으며
  세계의 확정과 판정은 독립이다.
- 비-Verify Step **과 컨테이너 Cycle** 모두 Artifact 변경이 있으면 Close를 거절하고, 거절은
  아무것도 부분 저장하지 않는다.
- Cycle Exit Snapshot은 마지막 Outcome의 구조적 lineage를 따른다. 버려진 가지도, 이름이 가장
  큰 Snapshot도 아니다.
- `SnapshotRef`는 사건의 이름이 아니라 **하나의 불변 Artifact 세계의 정체성**이다. 같은 세계는
  기존 참조를 다시 가리키고, 새 세계가 처음 관측될 때만 새 ID를 발급한다. 공개 참조
  `snapshot:A1`과 내부 내용 주소는 다르다.
- Artifact 정체성은 **정규화된 상대 경로 + 실제 바이트**다. mtime·소유자·권한·빈 디렉터리는
  세계의 일부가 아니고, 내용은 바이트로 비교하며 줄바꿈·인코딩을 변환하지 않는다.
- 심볼릭 링크와 특수 항목은 조용히 제외하지 않고 **전체 관측을 거절**한다. 대용량 파일에는
  공개 상한을 두지 않고 스트리밍으로 관측한다.
- 확정 직전 **재관측**으로 동시 변경을 검사한다. 다만 외부 프로세스의 쓰기를 물리적으로
  금지한다고 주장하지 않는다.
- `gil restore`는 **목표 Snapshot 인수를 받지 않는다.** 목표는 현재 lineage에서 하나로
  유도되며, 멱등적이고 원자적이며 중단되면 다음 명령이 실행 전 세계로 되돌린다.
- Managed Dataset의 방향을 §7.5 결정 로그로 확정. M3 저장 schema에 Dataset 필드를 미리 만들지
  않는다.
- Cycle Entry Snapshot을 **「그 Cycle을 연 전이가 출발한 세계」**로 일반화. 뿌리는 최초
  Snapshot, `open_child`와 `revisit`은 구조적 parent의 Exit을 받고, 미래 merge는 별도 규칙이
  정한다. revisit에서 갈리는 것은 parent와 Entry가 아니라 대상 Cycle과 `revisit_from`이다.
  M4는 이미 있는 `revisit` 규칙을 밟기만 하면 된다.
- 최초 기준 Snapshot은 **뿌리 Cycle의 `entry_snapshot_ref`** 가 갖는다. `Project` 뿌리에
  `baseline_snapshot_ref`를 중복 저장하지 않는다.
- 모든 Cycle은 생성과 동시에 실재하는 `entry_snapshot_ref`를 지니고, 닫힐 때
  `exit_snapshot_ref`를 확정한다. 둘이 같은 참조일 수 있다.
- World Current Snapshot은 **유도값**이다. v0에 캐시 필드를 두지 않고, 조회 비용이 실제 문제가
  될 때 검토한다.
- `gil restore`는 현재 Cycle 밖을 순회하지 않는다. 목표는 「가장 가까운 닫힌 Verify」와
  「현재 Cycle의 Entry」 두 줄로 유도된다.
- `.gil` 제외 범위를 확정. **프로젝트 루트의 `.gil/` 하나만 제외**하고, 더 깊은 곳의 `.gil`
  디렉터리는 중첩 GIL 경계로 보아 **전체 관측을 거절**한다. 조용히 제외하면 숨은 ignore 영역이
  생기고 안쪽 기록이 실제 세계와 어긋나며, 일반 추적하면 바깥 restore가 안쪽 Journey를
  되돌려 불변식을 깬다. 중첩 프로젝트 지원은 §7.4의 후속 미결 기능으로 남긴다.
- M3-A 관측기 구현 완료. Artifact 정체성·경로 계약·`.gil` 경계·안정된 관측을 코드와 시험으로
  고정하고, 관측기는 crate 내부 API 로 유지(공개 계약으로 굳히지 않음).
- M3-B 를 셋으로 나눔: **B1** 객체 저장소와 canonical manifest codec, **B2a** append-only
  확정과 registry 도메인 타입, **B2b** `state.yaml` 결합. B1·B2a 는 `state.yaml` 을 건드리지
  않으므로 되돌리기 쉬운 자리에서 멈춘다.
- canonical manifest 이진 형식을 확정 — magic `GILMANIF` · version 1 · algorithm tag 1 ·
  big-endian 고정 폭. 알고리즘은 머리에 한 번만 적고 항목마다 되풀이하지 않는다.
- 내부 객체 주소(SHA-256)와 공개 `SnapshotRef` 를 분리. 저장 엔진을 바꿔도 공개 참조는
  바뀌지 않는다.
- delta·chunk·pack·prune·tmp 정리는 필요성이 확인된 뒤의 내부 최적화로 기록.
- 객체 확정을 **hard link 기반 no-clobber** 로 보정. `rename` 은 최종 경로가 이미 있으면
  말없이 갈아 끼우므로, 두 프로세스가 같은 주소를 동시에 확정하면 append-only 가 깨진다.
  hard link 를 못 거는 파일 시스템에서는 **보장을 약화하며 물러서지 않고 거절**한다.
  내구성 보장의 실제 범위(디렉터리 fsync 는 Unix 만, macOS `fsync` 는 드라이브 캐시까지
  비우지 않음, 동시 논리 갱신 잠금은 별개)를 Artifact Model §10.5 에 명시.
- **format 4 를 아직 만들지 않는다.** registry 만 먼저 저장하면 열린·닫힌 Cycle 이 필수
  `entry_snapshot_ref`·`exit_snapshot_ref` 를 갖지 않는 **과도기 저장 상태**가 생기고, 그
  상태를 읽는 복원 규칙을 나중에 다시 지워야 한다. 그래서 M3-B2 를 둘로 나눠 **B2a** 는
  저장 형식을 건드리지 않는 도메인 타입까지만 짓고, **B2b** 가 Cycle 필드와 함께 format 4 를
  한 번에 올린다.
- 프로젝트 단위 **단일 작성자 잠금**을 format 4 앞에 넣기로 결정. `state.yaml` 은 논리 상태
  전부를 통째로 쓰므로 두 명령이 겹치면 한쪽 변경이 조용히 사라지고, Snapshot 이름은 같은
  `next_id` 에서 두 번 발급된다. v0 은 shared/exclusive 를 나누지 않고 **읽기 명령까지 같은
  exclusive 잠금**을 짧게 쓴다 — 두 문법과 플랫폼 차이를 피하고, 향후 restore recovery 가
  먼저 실행될 자리를 확보한다.
- 잠금은 **OS advisory lock**(`std::fs::File::try_lock`)으로 걸고 `.gil/project.lock` 에 둔다.
  파일의 존재는 잠금 상태가 아니다 — 그래야 비정상 종료 뒤 사람이 지울 stale lock 이 없다.
  새 의존성을 들이지 않았다.
- 경쟁하면 **기다리지 않고 즉시 거절**한다. 무기한 대기는 Agent 의 턴을 삼키고, 얼마나
  기다릴지는 도구가 몰래 정할 일이 아니다. timeout·retry·wait 옵션은 v0 에 없다.
- **format 4 를 한 번에 올렸다.** registry·Cycle Entry/Exit·Verify Snapshot·최초 Snapshot·
  dirty gate 를 함께 넣어, 필수 필드가 비어 있는 과도기 저장 상태를 만들지 않았다.
- **format 3 자동 migration 을 만들지 않는다.** format 3 에는 관측된 세계가 없어
  `entry_snapshot_ref` 를 채울 근거가 없다. 지어내면 그것은 **일어나지 않은 관측**이고,
  그 거짓 위에서 첫 Verify 가 「전부 새로 생겼다」를 보게 된다. 앞 형식 파일은 보존한 채
  거절하고, 새 프로젝트에서 시작하도록 안내한다.
- Artifact 관측기의 내부 주소 타입 `ManifestAddress` **하나만** 공개 표면으로 연다. 세계를
  여는 문(`Project::start`)이 세계의 주소를 받아야 하기 때문이다. 창고·codec·registry·
  manifest 는 안에 남는다. 이 주소는 **사람이 보는 이름이 아니다** — 공개 표면은 `snapshot:A1`.
- **restore transaction 의 계획을 이진 형식으로** 적기로 결정. 이것은 죽은 프로세스가 남긴
  자료라 반쯤 쓰인 것을 반쯤 읽으면 안 되고, 들여쓰기 하나가 다른 계획이 되면 그 계획이
  남의 파일을 지운다. manifest codec 과 같은 규율(magic·version·big-endian 고정 폭)을 쓰고,
  경로는 디코더가 정규화 검증을 다시 한다.
- **작업 파일을 목표 blob 과 hard link 하지 않기로** 확정. link 하면 다음 편집이 창고 안의
  immutable 객체를 함께 고치고, 그 순간 그 주소의 내용이 주소와 달라진다.
- **rollback 자료는 역사가 아니다.** 새 SnapshotRef 를 발급하지 않고 registry 에도 넣지
  않는다 — 사람이 확정한 적 없는 세계에 이름을 주지 않는다.
- 비-Verify dirty 오류의 안내를 **밟을 수 있는 길**로 보정. Interview 안에서는 verify 로 갈
  방법이 없으므로 「Experiment 로 가라」가 아니라 「`gil restore` 로 되돌린 뒤 닫아라」가
  먼저 온다.
- `gil restore`의 확인 절차를 확정. **명령 실행 자체가 복원 의사**이며 대화형 확인·`--force`·
  `--yes`·별도 confirm 명령을 만들지 않는다. 안전성은 구조적 유도와 원자성에서 온다.
- selftest 장치의 Host 기준점을 **module 평가 시 한 번만** 고정한다. 검사마다 다시 잡으면
  앞선 검사가 남긴 스텁이 기준점이 되어 스텁이 스스로에게 위임한다.

### 2026-09-19

- GIL의 주 사용자를 비개발자로 다시 고정하고, **지속형 Monitor를 선택 기능이 아니라 설치 완료의
  필수 인간 표면**으로 확정했다.
- Agent Host가 실제 persistent panel·PiP 수명 계약을 만족하면 그 표면을 우선하고, 요청 뒤
  `inline`에 머물거나 계약을 확인할 수 없으면 같은 UI의 Native Companion으로 물러난다.
- AI는 Companion 없음·꺼짐·낡음·호환됨을 구분하고 설치를 끝까지 조율하지만, 사용자 승인과
  macOS·Windows의 서명·공증·Store 신뢰 경계를 우회하지 않는다.
- 설치 뒤 사용자가 완료를 다시 보고하지 않는다. adapter가 재감지하고 원래 Monitor 요청을
  자동으로 이어간다.
- 이 계약의 단일 소유자를 `GIL Distribution Model v0.1`로 두고 M5-D를 새 실행 조각으로 열었다.
