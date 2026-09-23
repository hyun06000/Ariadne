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

`gil context`를 읽는 자리는 넷뿐이다.

```text
새로운 세션
새로운 Agent
현재 위치나 의도를 잃은 경우
명시적으로 전체 작업 맥락이 필요한 경우
```

명령마다 되풀이하는 것이 아니다. 되풀이하면 매 걸음이 전체 인수인계 비용을 치르고, 정작
직전 명령이 준 다음 수는 읽히지 않는다.

### 한 걸음의 전체 모양

```text
명령 실행
→ 성공 receipt 또는 typed 거절
→ 즉시 밟을 수 있는 다음 행동
→ 그 규칙이 낯설 때만 정확한 Help Topic 하나
→ 다시 명령 실행
```

**넷째 칸은 대개 건너뛴다.** 거절은 그 자체로 다음 행동을 말하므로, Topic은 그 규칙을 처음
만났을 때만 읽는다. 같은 세션에서 이미 이해한 Topic은 불확실할 때만 다시 읽는다 — 무엇을
읽었는지는 세션의 작업 기억이지 프로젝트의 사실이 아니므로 GIL은 그것을 저장하지 않는다.

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

### 4.4 `gil restore`

`gil restore`는 사용자가 Snapshot을 고르는 명령이 아니다. 현재 구조적 lineage에서 목표가
하나로 유도되므로 대상 인수, 사전 확인, `--force`를 두지 않는다.

성공 receipt는 복원한 공개 `SnapshotRef`, 교체·생성·삭제한 항목 수, 현재 Step과 Active
Will이 그대로 열려 있다는 사실과 다음 행동을 말한다. 내부 hash, 객체 경로와 전체 파일
목록은 기본 출력에 넣지 않는다. 이미 clean이면 성공적인 no-op으로 짧게 알린다.

실패나 중단을 발견하면 다른 명령을 진행하기 전에 복구 여부와 사용자가 취할 수 있는 한 가지
다음 행동을 말한다.

### 4.4b `gil status`의 현재 세계

`gil status`는 **지금 자리의 짧은 nudge**다. `gil context`가 하는 온보딩을 되풀이하지 않는다
(Context Model이 정의한 Context 해상도는 그대로 둔다).

거기에 Artifact 한 절을 더한다. 그 절이 네 물음에 답한다.

```text
지금 구조가 가리키는 Snapshot 은 무엇인가
작업 폴더는 그것과 같은가 다른가
다르다면 여기서 확정할 수 있는가
없다면 지금 실제로 밟을 수 있는 수는 무엇인가
```

clean:

```text
현재 세계
  snapshot:A3 · clean
```

dirty이고 Verify가 열려 있으면 — **확정이 정상적인 길이다.**

```text
현재 세계
  기준: snapshot:A3
  상태: dirty

이 Verify 를 닫으면 바뀐 세계를 관측해 Snapshot 으로 확정한다.
```

dirty이고 그 밖의 자리면 — **먼저 되돌리는 수뿐이다.**

```text
현재 세계
  기준: snapshot:A3
  상태: dirty

이 자리에서는 Artifact 변경을 확정할 수 없다.
먼저 `gil restore` 로 기준 세계를 복원한다.
현재 Step 과 Active Will 은 그대로 열린 채 남는다.
```

판정하지 못했으면 — **dirty라고 추측하지 않는다.**

```text
현재 세계
  기준: snapshot:A3
  상태: 확인하지 못했다

이유
  <구체적인 관측 실패와 그 오류가 주는 안전한 다음 행동>

현재 상태는 변경하지 않았다.
```

- 기준 Snapshot을 **새 규칙으로 계산하지 않는다.** dirty gate·Cycle Exit·`gil restore`가
  쓰는 그 하나의 read model을 그대로 지난다(Artifact Model §7.6·§8.1).
- 전체 manifest·파일 목록·내부 digest·객체 경로를 출력하지 않는다.
- **읽기 명령이다.** Snapshot·Report·Graph·Will·Journey·`state.yaml` 어느 것도 바꾸지 않고,
  관측 결과를 창고에 저장하지도 않는다.
- 밟을 수 없는 길을 안내하지 않는다(§6의 「Artifact를 바꿔 놓고 막혔을 때」).

### 4.5 상태에 민감한 `--help`

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

### Artifact를 바꿔 놓고 막혔을 때

Verify가 아닌 자리에서 Artifact를 바꾸면 그 자리는 닫히지 않는다(Artifact Model §6).
이때 안내는 **지금 여기서 밟을 수 있는 길**이어야 한다.

```text
거절: step:C1/S1 · question 에서는 Artifact 변경을 확정할 수 없다.

이유
  기준 세계 snapshot:A1 이후 프로젝트 파일이 바뀌었다.
    바뀜      work.txt

지금 해야 할 일
  `gil restore` 로 현재 변경을 되돌린 뒤 이 Step 을 닫는다.
  Artifact 를 변경해야 하는 작업은 Verify Step 에서 수행한다.

현재 Step 과 Active Will 은 그대로 열려 있다 — Node 도 Will 도 Journey 도 움직이지 않았다.
```

「Experiment Cycle로 가라」만 말하면 안 된다 — **Interview 안에서는 그 길이 없다.**
Verify가 없고, 이 Cycle을 닫는 것도 같은 gate에 막힌다. 먼저 되돌리는 길이 유일하게
지금 밟을 수 있는 수다.

`gil restore`의 규범 자체 — 무엇을 목표로 삼고 어떻게 원자적인지 — 는 여기 적지 않는다.
Artifact Model §8이 그 한 자리다.

### 경쟁 오류는 처방이 이미 손에 있는 receipt다

다른 GIL 명령이 프로젝트를 쥐고 있어 물러선 경우는 **가장 짧은 receipt**다. 무엇이
잘못된 것이 아니고, 에이전트가 고칠 것도 없다 — 같은 명령을 나중에 그대로 다시 실행하면
된다. 그러니 진단도 도움말 reference도 붙이지 않는다.

```text
다른 GIL 명령이 이 프로젝트를 사용하고 있다.

현재 상태를 읽거나 변경하지 않았다.
앞선 명령이 끝난 뒤 다시 시도한다.
```

「읽거나 변경하지 않았다」가 이 receipt의 핵심이다. 그것이 있어야 에이전트가 **되돌릴 것을
찾지 않고** 곧장 재시도한다.

잠금의 규범 자체 — 무엇을 잠그고 언제 잡고 왜 기다리지 않는지 — 는 여기 적지 않는다.
Artifact Model §10.6이 그 한 자리다.

---

## 7. 점진적 도움말

Topic 주소, 점진적 공개 단계, 저장·배포와 검증 규칙은 `GIL Manual Model v0.1`이 소유한다.
이 절은 Agent UX에서 도움말이 언제, 어느 정도 노출되는지만 정한다.

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

v0의 핵심 계약은 **필요한 개념만 요청해서 읽을 수 있다**는 점이다. 기본 Manual은 설치본과
함께 배포하며 자연어 검색과 외부 resource는 최소 Topic 조회가 검증된 뒤 판단한다.

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

## 11. 비개발자 설치와 Monitor 진입

GIL의 주 사용자는 package manager, terminal, port와 설정 파일을 모른다고 가정한다. 사용자는
Agent Host에서 Plugin을 설치하고 자연어로 Monitor를 요청한다.

Codex와 Claude Code에서 이 경험은 같은 이름과 같은 순서를 쓴다. 내부적으로 Codex manifest와
Claude Code manifest가 달라도 사용자는 둘 다 **GIL Plugin**으로 설치한다. 두 Plugin은 하나의
MCP server·Skill·Manual·Companion coordinator를 공유하며, 어느 Host에서도 MCPB·MCP namespace·
sidecar·bridge를 정상 사용법으로 가르치지 않는다.

tool namespace 는 **Host 내부 사실**이다. 두 Host 가 같은 prefix 를 준다고 전제하지 않으며,
실측한 Claude Code 의 자리는 `mcp__plugin_gil-companion-prototype_gil-companion__*` 로 설치
식별자를 품는다. 사용자에게 가는 문장에 prefix 를 적지 않고, 같음은 tool 의 이름·입력·출력·
거절·다음 행동에서 확인한다.

```text
Plugin 설치
→ Agent가 persistent Monitor surface를 확인
→ Host PiP가 실제로 지속되면 그 표면을 사용
→ 그렇지 않으면 Companion 없음·꺼짐·낡음·호환됨을 구분
→ 필요한 경우 설치 이유를 설명하고 사용자 승인을 받음
→ OS의 신뢰된 설치 표면
→ Agent가 설치 완료를 재감지
→ 원래 Monitor 열기 요청을 자동 재개
```

Agent는 사용자의 승인을 대신하지 않고 OS의 설치 보호를 우회하지 않는다. 대신 사용자가 download
folder, binary path, terminal command와 JSON 설정을 다루지 않게 한다. 설치 완료를 사용자가 다시
채팅으로 보고하게 하지 않는다.

Companion 설치가 거절되거나 실패해도 GIL의 text loop는 동작한다. 다만 inline 카드나 text만으로
인간용 Monitor 설치가 완료됐다고 말하지 않는다. 구체 계약은 `GIL Distribution Model v0.1`이
소유한다.

일반 Claude Desktop용 MCPB는 후속 배포 adapter다. Claude Code와 Codex의 일상 loop를 서로 다르게
만드는 이유로 쓰지 않으며, 필요해질 때도 같은 MCP와 Manual을 포장한다.

---

## 12. 아직 결정하지 않는 것

- 자연어 검색, embedding 또는 LLM 위키 색인
- 사용자·프로젝트별 Manual 확장과 override
- 명령 출력의 JSON 또는 다른 machine-readable renderer
- 출력별 구체적인 최대 token 수
- 현재 가능한 Node Kind가 여러 개일 때의 선택 UI
- 오류 code의 namespace와 안정성 정책
- GUI Monitor에서 domain-changing nudge를 승인받아 실행하는 방식

---

## 13. 핵심 문장

> **평상시에는 명령 출력이 다음 행동을 가르치고, 연속성이 끊겼을 때만 `gil context`가 작업을
> 복원한다.**

> **GIL의 내부 개념 수가 늘어나도 AI가 외워야 하는 공개 명령 수는 함께 늘어나지 않는다.**

> **비개발자에게 설치 명령을 가르치지 않는다. Agent가 상태를 감지하고 설치를 조율하며, 사용자와
> 운영체제는 신뢰 경계에서 승인한다.**
