# GIL Agent UX Model v0.1

> AI가 GIL 전체 명세를 매번 읽지 않고도 현재 행동을 시작하고, 기록하고, 다음 행동으로
> 이동할 수 있게 하는 공개 상호작용 원칙

## 1. 목적

GIL의 내부 모델은 Graph, Cycle, Journey, Existence, Will과 Grammar를 포함한다. 그러나 이
내부 복잡도를 AI의 일상적인 명령 표면에 그대로 노출하지 않는다.

> **GIL을 올바르게 사용하기 위해 GIL 전체를 이해할 필요가 없어야 한다.**

긴 few-shot, 전체 명세와 반복되는 전체 context는 LLM의 입력을 불필요하게 키운다. v0의 Agent
UX는 작은 명령 표면, 명령 결과의 국소적 nudge, 필요할 때만 읽는 도움말과 명시적 복원을
사용한다.

---

## 2. 공개 상호작용의 중심

AI가 평상시에 반복하는 동작은 셋이다.

```text
gil start
gil open
gil close
```

- `gil start` — 프로젝트의 GIL 여정을 만들고 최초 방향을 제시한다.
- `gil open` — 지금 수행할 하나의 행동 계약을 열어 준다.
- `gil close` — Report를 기록하고 행동을 끝낸 뒤 바로 다음 방향을 제시한다.

`gil context`는 이 반복문에 항상 들어가는 명령이 아니다. 새 세션의 복원, 인수인계와 맥락
상실 복구를 위한 별도 명령이다.

```text
평상시:  start → open → 실제 작업 → close → open → ...
복구 시: context → 현재 열린 행동을 이어감
```

내부 Node Kind와 전이 규칙이 늘어나더라도 공개 명령 수를 같은 비율로 늘리지 않는다. 현재
상태에서 가능한 Kind가 하나라면 GIL이 유도한다. 선택이 필요한 경우에도 새 명령을 만들기보다
현재 명령의 작은 입력이나 안내로 표현한다.

---

## 3. 대화의 연속성을 기본값으로 본다

같은 채팅 세션에는 직전 명령 출력, 사용자 응답과 실제 작업의 맥락이 이미 남아 있다. GIL은
매 명령마다 전체 과거를 다시 투영하지 않는다.

일상 명령 출력은 다음 합성이다.

```text
Command Receipt
  = 방금 확정된 State delta
  + 지금 필요한 Current Will
  + 바로 적용되는 Grammar
  + 필요할 때만 읽는 Help reference
```

출력은 전체 Journey, 전체 Cycle Graph 또는 이전 Report를 반복하지 않는다. 명령 사이의 대화
연속성이 끊어졌을 때만 `gil context`가 필요한 해상도의 인수인계 패킷을 만든다.

---

## 4. 명령별 출력 계약

### 4.1 `gil start`

최초 상태 전체를 설명하지 않는다. 시작된 범위, 지금의 목적과 최초 행동으로 가는 길만 준다.

```text
프로젝트를 시작했다.
현재: 최초 Interview

다음
  사용자가 무엇을 원하는지 확인한다.

실행
  gil open
```

저장 경로, format 번호와 내부 ID는 진단에 필요하면 별도 줄로 표시할 수 있지만 nudge보다 앞에
두지 않는다.

### 4.2 `gil open`

`gil open`은 실행형 Node와 Active Will을 함께 여는 동작이다. 출력은 AI가 실제 세계에서 무엇을
해야 하는지 알려 주는 **행동 계약**이다.

Agent는 Open 입력에서 세 필드의 Action Contract를 한 번 명시한다.

```bash
gil open <<'EOF'
objective: 사용자의 프로젝트 목표를 확인한다
next_action: 목표의 종류를 선택지와 함께 질문한다
done_when: 사용자의 원문 응답을 얻는다
EOF
```

GIL은 이를 저장한 뒤 Receipt에서 전체를 장황하게 반복하지 않고 `next_action`과 `done_when`을
각각 `지금 할 일`과 `완료 조건`으로 투영한다. `objective`는 Active Will과 context에 보존하되
현재 행동을 이해하는 데 필요할 때만 Receipt에 추가한다.

```text
열었다: step:C1/S1 · Question

지금 할 일
  사용자가 원하는 호칭을 확인한다.

완료 조건
  사용자의 원문 응답을 얻는다.

닫을 때 필요한 것
  question
  choices
  response
```

다음을 지킨다.

- 구조 명령만을 `지금 할 일`로 제시하지 않는다.
- `objective`, `next_action`, `done_when`을 그대로 장황하게 중복하지 않고 행동 계약으로
  투영한다.
- Report 필드는 현재 Node를 닫는 데 필요한 것만 보여 준다.
- 필드에 유한한 허용값이나 조건부 허용값이 있으면 오류를 기다리지 않고 함께 보여 준다.
- 조상 Cycle과 과거 Step을 자동으로 펼치지 않는다.

`gil open` 성공 뒤의 다음 행동은 대개 CLI 명령이 아니라 사용자와의 대화, Artifact 수정 또는
검증이다. 따라서 `start`·`close`처럼 별도의 `실행` 블록으로 `gil close`를 즉시 강조하지 않는다.
실제 작업을 먼저 수행하고 완료 조건을 충족한 뒤 닫으라고 안내한다. 이는 Agent가 작업 전에
Node부터 닫는 오류를 막는다.

여러 Node 또는 Cycle Kind 중 선택해야 할 때 GIL은 각 선택지의 짧은 설명을 보여 준다. 설명은
renderer 코드에 흩어 쓰지 않고 machine-readable Grammar에서 읽는다. 선택지가 하나면 설명을
반복하지 않고 자동으로 연다.

허용값의 설명도 같은 원칙을 따른다. `close_cycle`, `open_child`, `revisit` 같은 raw enum만
보여 주지 않고 그것이 어느 계층에서 무엇을 움직이는지 짧게 설명한다. 허용값과 설명의 단일
진실 원천은 machine-readable Grammar다.

### 값의 세 상태를 구분해서 말한다

명세가 정의한 값이라고 해서 지금 밟을 수 있는 것은 아니다. GIL은 셋을 구분한다
(`GIL Artifact Model v0.1` §11).

```text
1. 기록할 수 있고 실행할 수 있다          허용값으로 보여 준다
2. 유효하게 기록할 수 있지만 지금은 실행할 수 없다
                                           허용값으로 보여 주되, 그 사실을 설명에 담는다
3. 아직 문법으로 제공되지 않는다          `아직 없음`으로 따로 세운다
```

2번은 **잘못된 값이 아니다.** Experiment Cycle failure Report의 `revisit`이 지금 그 상태다.
사용자와 에이전트에게 잘못 적었다고 말하지 않는다 — 방향은 정상적으로 기록되었고 후속
전이가 아직 구현되지 않았다고 설명한다. 3번(`close_chain`)만 허용값 목록에서 분리한다.

### 4.3 `gil close`

`gil close`는 저장된 결과와 다음 nudge를 보여 준다. 방금 제출한 Report 전체를 그대로 되풀이하지
않는다.

```text
닫았다: step:C1/S1 · Question
기록됨: journey:X1@J1

다음
  응답에서 확정된 것과 아직 모르는 것을 구분한다.

실행
  gil open
```

Cycle 또는 Chain 경계에서는 다음 계층이 반드시 받아야 할 handoff만 추가할 수 있다. 내부
Step Graph 전체를 명령 출력에 투영하지 않는다.

### 4.4 상태에 민감한 `--help`

`gil open --help`와 `gil close --help`는 일반 도움말이 아니라 **현재 자리의 계약**을 읽기
전용으로 보여 준다. 상태를 변경하거나 stdin이 없는 실제 Open·Close 요청으로 해석하지 않는다.

```text
gil close --help

닫을 대상
  step:C2/S5 · outcome

필요한 Report
  verdict
    success | failure

  next_direction.action
    success이면 close_cycle — Step Graph를 끝내고 현재 Cycle Report로 이동
    failure이면 revisit — 현재 Cycle 안의 유효한 조상에서 새 형제 시도
```

- help는 현재 Node·Cycle의 필수 필드, 허용값, 조건부 필드와 짧은 의미를 보여 준다.
- help 호출 전후의 저장 상태는 바이트 단위로 같아야 한다.
- `gil open --help`는 현재 열 수 있는 Kind와 Action Contract 골격을 보여 준다.
- 일반 `gil --help`는 명령 표면을, 상태별 `open/close --help`는 현재 계약만 다룬다.
- 아직 **문법으로 제공되지 않는** 값(3번 상태)은 허용값처럼 제시하지 않고 별도 `아직 없음`으로
  설명한다. 기록은 되지만 실행이 아직인 값(2번 상태)은 허용값에 남기고 그 사실을 설명에 담는다.

---

## 5. `gil context`의 역할

`gil context`는 **cold start, handoff, recovery** 명령이다.

다음 때 사용한다.

- 새로운 모델이나 세션이 같은 Existence의 작업을 이어받을 때
- Agent가 현재 목적, 근거 또는 위치를 잃었을 때
- 협업자에게 명시적으로 인수인계할 때
- 채팅 맥락과 저장된 GIL 상태가 어긋났다고 의심할 때

다음 이유만으로 사용하지 않는다.

- 모든 `open` 직전이기 때문에
- 모든 `close` 직후이기 때문에
- 현재 채팅에 같은 내용이 이미 있는데 안전하다는 막연한 이유 때문에

`gil context`는 기존 Context Resolution Rule에 따라 이전 Cycle은 Cycle 해상도, 현재 Cycle은
Step 해상도, 현재 자리는 Will과 적용 Grammar 해상도로 투영한다. 전체 history 조회를 대신하지
않는다.

새 Agent에게 필요한 최소 온보딩 규칙은 다음 한 줄로 줄일 수 있어야 한다.

> **새 세션이면 먼저 `gil context`를 읽고, 그 뒤에는 각 명령이 돌려주는 다음 nudge를 따른다.**

---

## 6. 오류는 복구 안내서다

오류는 내부 enum 이름이나 금지 사실만 말하지 않는다. AI가 전체 명세를 찾아 읽지 않고 바로
복구할 수 있게 한다.

```text
GIL-E104 · 이 Interview는 아직 닫을 수 없다.

이유
  승인된 Synthesis가 없다.

지금 해야 할 일
  사용자의 응답을 Interpretation으로 정리한다.

다음
  gil open

더 알아보기
  interview/approval
```

오류는 가능하면 다음 네 가지를 가진다.

1. 무엇이 거절됐는가
2. 왜 거절됐는가
3. 지금 무엇을 해야 하는가
4. 필요할 때만 읽을 도움말 reference

오류가 전체 context를 자동 첨부하지 않는다. 복구에 필요한 국소 정보만 제공한다.

---

## 7. 점진적 도움말

긴 단일 매뉴얼 대신 안정된 주제 주소를 가진 작은 도움말을 제공한다.

```text
gil help current
gil help interview/approval
gil help report/observation-vs-interpretation
gil help revisit/failure
```

`help`는 하나의 명령이며 주제마다 새 CLI 명령을 만들지 않는다. context와 오류가 관련 주제를
직접 가리켜 AI가 목차 전체를 탐색하지 않게 한다.

각 도움말 주제는 다음만 포함한다.

- 개념 한 문장
- 언제 필요한가
- 반드시 지킬 불변식
- 올바른 예시 하나
- 흔한 실패 하나

도움말 저장 형식, 검색·색인 방식과 내장 또는 외부 resource 여부는 구현 직전에 정한다. v0의
핵심 계약은 **필요한 개념만 요청해서 읽을 수 있다**는 점이다.

---

## 8. 독자별 출력의 분리

```text
gil story    인간이 현재 여정을 이해한다.
gil context  새 Agent가 작업을 복원한다.
gil help     Agent가 필요한 개념 하나를 배운다.
gil history  전체 실행 경로를 감사한다.
```

이 네 출력은 서로를 그대로 복제하지 않는다. 특히 `story`는 인간용이고, `context`는 매 행동마다
호출하는 상태 조회가 아니며, `history`는 자동 온보딩 자료가 아니다.

---

## 9. 토큰 경제성 원칙

- 같은 세션에 이미 있는 내용을 일상 명령마다 반복하지 않는다.
- 전체 문법 대신 현재 Node에 적용되는 문법만 보여 준다.
- 전체 Report 대신 저장 성공과 의미 있는 state delta를 보여 준다.
- 도움말은 오류와 현재 상태에서 직접 연결된 한 주제만 읽는다.
- 긴 설명보다 안정된 필드명, 구조와 짧은 예시를 우선한다.
- 짧게 만들기 위해 복구에 필요한 이유나 완료 조건을 생략하지 않는다.

출력 길이 자체보다 **다음 행동에 필요하지 않은 정보가 포함됐는가**를 기준으로 평가한다.

---

## 10. 검사 가능한 불변식

```text
normal_loop_does_not_require_context
start_output_points_to_first_action
open_output_contains_action_and_done_condition
open_output_contains_only_current_close_requirements
close_output_reports_delta_and_next_nudge
command_receipt_does_not_expand_history
context_is_for_bootstrap_handoff_or_recovery
error_explains_reason_and_recovery
help_is_topic_scoped
new_node_kinds_do_not_require_new_public_commands
```

Dogfood에서는 다음을 확인한다.

1. 새 Agent가 짧은 온보딩 한 줄과 `gil context`만으로 작업을 복원하는가.
2. 같은 세션에서는 이후 `context` 없이 `open`·실제 작업·`close`를 반복할 수 있는가.
3. 잘못된 동작을 했을 때 오류만 읽고 올바른 경로로 복귀하는가.
4. 전체 명세를 제공하지 않아도 필요한 도움말 한 주제로 문제를 해결하는가.
5. 명령 출력에 같은 과거 내용이 반복 누적되지 않는가.

---

## 11. 아직 결정하지 않는 것

- `gil help` 주제의 영구 저장 형식과 배포 방식
- 자연어 검색, embedding 또는 LLM 위키 색인
- 명령 출력의 JSON 또는 다른 machine-readable renderer
- 출력별 구체적인 최대 token 수
- 현재 가능한 Node Kind가 여러 개일 때의 선택 UI
- 오류 code의 namespace와 안정성 정책
- GUI Monitor에서 같은 nudge를 표현하는 방식

---

## 12. 핵심 문장

> **평상시에는 명령 출력이 다음 행동을 가르치고, 연속성이 끊겼을 때만 `gil context`가 작업을
> 복원한다.**

> **GIL의 내부 개념 수가 늘어나도 AI가 외워야 하는 공개 명령 수는 함께 늘어나지 않는다.**
