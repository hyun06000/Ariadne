# GIL Manual Model v0.1

> AI가 GIL 전체 명세를 매번 읽지 않고도, 현재 상태에서 필요한 규칙 하나를 발견하고 적용하는
> 지식 전달 계약

---

## 1. 목적

GIL은 작은 공개 명령 표면을 유지하지만 내부 개념은 Step, Cycle, Artifact, Journey와
Existence로 확장된다. 모든 개념과 예제를 매 세션의 few-shot에 넣으면 같은 내용이 반복되고,
프로젝트가 길어질수록 실제 작업을 위한 context가 줄어든다.

반대로 짧은 명령 이름만 주면 새 Agent는 왜 명령이 거절됐는지, 어떤 Report를 써야 하는지,
현재 행동이 세계와 Journey 중 무엇을 바꾸는지 알 수 없다.

GIL Manual은 이 사이를 잇는다.

> **평상시에는 현재 명령의 nudge만 따른다. 모르는 규칙이 생긴 순간에만 주소가 지정된 작은
> 주제 하나를 읽는다.**

이는 모델을 사전 학습시키는 체계가 아니다. 모델과 세션이 달라져도 같은 규칙을 필요할 때
context에 올리는 **점진적 onboarding** 체계다.

---

## 2. 다른 읽기 모델과의 경계

```text
gil status   지금 위치와 세계의 짧은 상태
gil story    인간이 현재 여정을 이해하는 설명
gil context  새 Agent 세션이 작업을 이어받는 onboarding
gil help     Agent가 필요한 규칙 하나를 배우는 Manual
gil history  전체 실행 경로의 감사
```

Manual은 프로젝트의 현재 기록을 소유하지 않는다. Topic 본문은 GIL 사용법이고, Graph와
Report는 실제 프로젝트에서 일어난 일이다.

- Context를 복제하지 않는다.
- History를 요약하지 않는다.
- 현재 Will을 새로 만들지 않는다.
- 명세에 없는 전이와 필드를 발명하지 않는다.
- 코어가 거절해야 할 행동을 설명만으로 막으려 하지 않는다.

Manual은 통과하는 길을 가르치고, 코어는 잘못된 길을 계속 막는다.

---

## 3. 네 단계의 점진적 공개

### 3.1 Bootstrap Capsule

새 Agent에게 항상 주는 내용은 다음으로 제한한다.

```text
GIL은 한 번에 하나의 행동만 수행한다.
새 세션에서는 먼저 gil context를 읽는다.
그 뒤에는 gil open·gil close와 각 명령의 다음 nudge를 따른다.
거절되면 오류가 제시한 다음 행동을 따른다.
그 규칙이 낯설면 오류가 가리킨 help topic을 읽는다.
같은 세션에서 이미 이해한 topic은 불확실할 때만 다시 읽는다.
전체 규칙이 필요하다고 추측해 모두 읽지 않는다.
.gil 내부 파일은 직접 읽거나 수정하지 않는다.
```

Bootstrap Capsule은 GIL의 철학, 모든 Node Kind, 전체 전이표와 예제 모음을 포함하지 않는다.
설치본과 Agent adapter가 같은 문구를 제공할 수 있지만 Project state에 반복 저장하지 않는다.

#### 거절과 조회는 다른 단계다

넷째와 다섯째 줄이 나뉘어 있는 것은 의도다. **거절은 대개 그 자체로 다음 행동을 말한다.**
Topic은 그 행동이 왜 그런지가 낯설 때만 읽는다.

```text
거절  → 다음 행동          대부분 여기서 끝난다
      → 낯설면 Topic 하나  그 규칙을 처음 만났을 때만
```

#### 읽은 Topic은 프로젝트의 사실이 아니다

여섯째 줄은 **세션 안의 작업 기억**을 말한다. 어떤 Topic을 읽었는지는 Graph·Journey·
Memory·Will 어디에도 저장하지 않는다. 그것은 그 세션이 무엇을 이미 이해했는가일 뿐,
프로젝트에서 일어난 일이 아니다.

따라서 재조회를 **금지하지도, 별도 상태로 추적하지도 않는다.** 에이전트가 불확실하면
다시 읽는 것이 맞다. 실제 dogfood에서 한 세션이 같은 Topic을 두 번 읽었고(§16), 그것은
결함이 아니라 Bootstrap 문구 한 줄로 다룰 일이었다.

### 3.2 Discovery Index

Agent가 모든 Topic 본문을 읽지 않고도 필요한 것을 고를 수 있도록 다음 metadata만 노출한다.

```text
id
한 줄 summary
적용되는 상태의 짧은 표지
```

Discovery에서 예제와 상세 설명을 펼치지 않는다.

### 3.3 Topic

현재 상태나 오류가 가리킨 Topic 하나를 완전히 읽는다. Topic은 개념 장 전체가 아니라 한
행동 또는 한 실패 지점을 해결하는 원자 단위다.

**Topic은 few-shot prompt를 대신하는 정적 교재가 아니다.** 미리 읽어 두는 것이 아니라,
지금 걸린 마찰에서 필요한 개념 하나를 그 주소로 가져오는 **주소 가능한 안내서**다.

```text
정적 교재     시작할 때 전부 준다 · 대부분 이번 작업과 무관하다
Topic         막힌 순간에 하나를 준다 · 그것이 지금 밟을 수를 말한다
```

그래서 Topic이 늘어나는 것과 Agent가 읽는 양이 늘어나는 것은 **같은 일이 아니다.**
백 개가 실려 있어도 한 번의 마찰에서 읽히는 것은 하나다.

### 3.4 Reference와 Example

Topic이 직접 요구할 때만 관련 규범 설명이나 예제 하나를 추가로 읽는다. reference가 다른
reference를 자동으로 재귀 확장하지 않는다.

---

## 4. Topic 주소

Topic ID는 사람이 읽을 수 있고 기계가 안정적으로 비교할 수 있는 `/` 구분 주소다.

```text
current
interview/approval
step/verify/close
cycle/experiment/close
artifact/restore
artifact/dirty/non-verify
report/observation-vs-interpretation
error/parent-not-closed
```

주소는 다음 원칙을 따른다.

- ASCII 소문자와 숫자, `-`, `/`만 쓴다.
- 빈 segment, 선행·후행 `/`, `//`, `.`과 `..`를 거절한다.
- 파일 경로와 내부 enum 이름이 아니라 **공개 의미**를 나타낸다.
- Node Kind만으로 끝내지 않고 필요한 경우 `open`, `close`, `restore` 같은 행동을 포함한다.
- 오류 Topic은 사용자가 복구할 수 있는 실패 종류를 가리킨다.
- 이미 배포된 ID를 다른 뜻으로 재사용하지 않는다.
- 이름을 바꿔야 하면 옛 ID는 새 ID를 가리키는 명시적 alias로 남긴다.
- alias는 순환할 수 없고 최종 canonical Topic 하나로 끝나야 한다.

주소의 계층은 자동 상속을 뜻하지 않는다. `artifact/restore`를 읽었다고 모든 `artifact/*`를
함께 읽지 않는다.

---

## 5. Topic의 계약

각 Topic은 다음 metadata와 본문을 가진다.

```yaml
id: artifact/dirty/non-verify
title: Verify가 아닌 자리에서 Artifact가 바뀐 경우
summary: 현재 변경을 확정할 수 없으므로 기준 세계를 복원한 뒤 같은 행동을 이어 간다.
applies_when:
  world_state: dirty
  open_step: not_verify
related:
  - artifact/restore
examples:
  - artifact/dirty/non-verify/basic
```

본문의 고정 구조:

```text
[언제 읽는가]
  이 Topic이 적용되는 관측 가능한 조건

[지금 할 일]
  현재 상태에서 실제로 밟을 수 있는 한 가지 행동

[불변식]
  그 행동이 지켜야 하는 규칙

[올바른 예]
  최소 입력과 중요한 결과

[흔한 실패]
  가장 혼동하기 쉬운 잘못된 행동 하나와 거절 이유

[관련 주제]
  필요할 때만 따라갈 주소
```

모든 절을 억지로 길게 채우지 않는다. 그러나 Topic을 독립적으로 읽었을 때 대상, 적용 조건,
행동과 완료 조건을 다른 문서 없이 식별할 수 있어야 한다.

---

## 6. 진실 원천과 중복 금지

Manual은 기존 규범의 새로운 복사본이 아니다.

```text
Domain Specification   개념과 불변식
gil-spec.yaml          현재 Grammar·필드·허용값
Read Model             현재 상태와 가능한 행동
Manual Topic           위 원본을 Agent가 적용할 수 있게 설명하는 투영
```

- 필수 Report 필드와 enum 허용값은 Grammar에서 읽는다.
- 현재 가능한 행동과 world state는 기존 read model에서 읽는다.
- Artifact, Will과 Cycle의 의미는 각 Domain Model을 참조한다.
- Topic은 원본 전체를 복제하지 않고 지금 필요한 부분만 투영한다.
- Manual 본문과 machine-readable 원본이 갈리면 조용히 한쪽을 택하지 않고 검증 실패로 다룬다.

Topic 본문은 Grammar를 **투영**한다. 투영은 셋뿐이고, 셋 다 이미 있는 읽는 자리에 물어본다.

```text
{{open_requires}}                 실행형 자리를 여는 행동 계약의 칸들
{{close_requires:<cycle>/<kind>}} 그 Step을 닫는 데 필요한 칸들
{{close_contract:<cycle>}}        그 Cycle을 닫는 계약 — 칸·허용값·값의 뜻·좁혀진 갈래
```

마지막 것은 `gil close --help`와 **같은 renderer**를 쓴다. 그래서 허용값, verdict가 좁힌
갈래, 그리고 「아직 없음」으로 표시되는 미구현 전이가 화면과 Topic에서 갈릴 수 없다.

Topic마다 Grammar parser를 새로 만들지 않고, renderer에 필드 목록을 복제하지 않는다.
**모르는 투영은 빈 문자열로 지우지 않는다** — 지우면 그 자리에 있어야 할 것이 없다는 사실이
사라진다. 못 채웠다는 사실을 그 줄에 남긴다.

Topic metadata의 `applies_when`은 새로운 전이 엔진이 아니다. 코어가 이미 판정한 상태를 Topic
선택에 쓰는 표지일 뿐이다.

---

## 7. Topic 선택

v0은 embedding, LLM reranking과 자연어 추측보다 결정적 선택을 우선한다.

우선순위:

```text
1. 오류가 정확한 help_ref를 제공
2. status·open·close receipt가 현재 상태의 help_ref를 제공
3. gil help <topic>으로 canonical 주소를 직접 조회
4. gil help가 현재 상태에서 관련 Topic 3~5개만 제시
```

`gil help`는 전체 목차를 기본 출력하지 않는다. 현재 상태를 읽을 수 있으면 관련 Topic만
보이고, 프로젝트 밖이나 상태가 없으면 Bootstrap과 핵심 시작 Topic만 보여 준다.

### 선택과 정렬 (v0 확정)

`applies_when`에 적힌 조건을 **모두(AND)** 만족하는 canonical Topic만 고른다. 조건이 없는
Topic은 모든 상태에 맞는다.

```text
① 조건이 많은 것 — 더 구체적인 Topic이 먼저다
② 같으면 canonical Topic ID 오름차순
```

조건이 없는 Topic은 ①에 의해 자연히 맨 뒤로 간다. **「현재 행동과 직접 연결」을 재는 별도
metadata는 두지 않았다** — 실제 Topic들의 기대 차례가 이 두 열쇠로 전부 맞고, 맞는 규칙
가운데 가장 단순한 것을 고른다. 동점이 실행마다 달라지는 hash 순서에 기대지 않는다.

`world_state == unknown`은 dirty가 아니다. dirty 전용 Topic을 고르지 않고, 세계를 확인하지
못해 일부를 고르지 못했다는 사실만 짧게 말한다. 까닭 전체는 `gil status`가 이미 말하므로
여기서 되풀이하지 않는다.

### 상태 표지는 검색식이 아니다

`applies_when`의 key와 값은 **유한하다.** 임의 query, 정규식, 표현식 언어와 LLM 판정을
만들지 않는다.

```text
project                present · absent
cycle_kind             interview · experiment
cycle_status           open · closed
step_kind              question · interpretation · synthesis · outcome
                       define · hypothesis · verify · analysis · none
step_status            open · closed · none
world_state            clean · dirty · unknown
artifact_confirmation  verify · unavailable
```

- `step_kind: none`과 `step_status: none`은 **Cycle 경계**를 뜻한다. 「비-Verify」를
  `step_kind != verify` 같은 부정 검색식으로 쓰지 않는다.
- `artifact_confirmation`은 별도 권한 규칙이 아니라 **코어의 Verify 판정 하나를 그대로**
  옮긴 표지다.
- 모르는 key, 모르는 값, 글자가 아닌 값은 Manual index를 세울 때 거절한다. 무시하거나
  truthiness로 다루지 않는다.
- **필드가 없는 것과 `applies_when: {}`은 다르다.** 앞은 모든 상태, 뒤는 실수로 보고
  거절한다.
- 프로젝트 밖에서는 `project` 말고 어떤 표지도 맞지 않는다 — 「없다」가 아니라
  **「알 수 없다」**이기 때문이다.

여러 Topic이 적용돼도 다음 행동을 직접 결정하는 Topic을 먼저 둔다. 철학적 배경이나 먼 미래
기능은 뒤에 둔다.

자연어 검색은 v0의 전제가 아니다. 나중에 추가하더라도 검색 결과는 canonical Topic ID를
돌려주고, 검색이 규칙 본문을 새로 생성하지 않게 한다.

---

## 8. 공개 명령

새 명령군을 늘리지 않고 기존 `gil help` 하나를 쓴다.

```text
gil help
  현재 상태와 직접 관련된 Topic만 보여 준다.

gil help <topic>
  canonical Topic 하나를 완전히 보여 준다.
```

정적 `gil --help`는 명령 목록을 보여 주고, 상태에 민감한 `gil open --help`와
`gil close --help`는 현재 입력 계약을 보여 준다. `gil help`는 그보다 깊은 의미와 복구법을
설명한다. 셋을 한 출력으로 합치지 않는다.

도움말 조회는 읽기 전용이다.

- `state.yaml`, Graph, Report, Will과 Journey를 바꾸지 않는다.
- Artifact 객체와 Snapshot을 만들지 않는다.
- Topic을 읽었다는 사실을 프로젝트 역사에 기록하지 않는다.

---

## 9. 오류가 Manual의 Router다

오류는 가능하면 다음을 함께 준다.

```text
무엇이 거절됐는가
왜 거절됐는가
지금 밟을 수 있는 다음 행동
help: <canonical topic id>
```

예:

```text
이 자리에서는 Artifact 변경을 확정할 수 없다.

지금 해야 할 일
  gil restore

더 알아보기
  gil help artifact/dirty/non-verify
```

오류 문구가 바뀌어도 `help_ref`의 뜻은 안정적이어야 한다. 내부 오류 enum과 공개 Topic ID를
같은 문자열로 강제하지 않는다.

오류가 이미 충분히 자명하고 같은 명령을 재시도하는 것만이 답이라면 Topic을 붙이지 않을 수
있다. 프로젝트 잠금 경쟁이 그 예다. 링크를 늘리는 것이 목적이 아니다.

### 소유권 — 오류가 Manual을 소유하지 않는다

```text
Domain 오류        사실과 까닭만 지닌다
    ↓
Help Router        공개 거절을 복구 Topic으로 대응한다
    ↓
Option<TopicId>
    ↓
Renderer           대응이 있을 때만 짧은 한 줄을 더한다
```

- `SessionError::Dirty { help_topic }` 같은 꼴을 만들지 않는다. 도메인이 문서를 알게 되면
  Topic 주소를 바꾸는 일이 도메인 타입을 고치는 일이 된다.
- 대응표는 **한 자리**에 있다. 여러 파일로 흩어지면 어느 오류가 어디를 가리키는지 아무도
  한눈에 못 본다.
- Router는 **순수하다.** 파일을 읽지 않고, Project·Session·Graph를 다시 읽지 않고, 잠금을
  잡지 않고, Topic 본문을 펴지 않는다. dirty 거절에서 Topic을 고르려고 `world_state()`를
  다시 부르지 않는다 — 그 정보는 오류의 gate에 이미 실려 있다.
- **문자열을 뒤져 고르지 않는다.** typed 구조만 본다. 메시지 한 글자를 다듬는 일이 링크를
  끊는 일이 되면 아무도 메시지를 못 고친다.
- 오류 하나에 Topic은 **최대 하나**다.
- Router가 돌려줄 수 있는 모든 주소는 bundled index에 실재해야 하며, 그것을 **배포 전
  테스트가** 확인한다. 런타임에 조용히 링크를 빼는 것으로 끝내지 않는다.

### 최초 대응표

| 거절 | Topic |
|---|---|
| Verify가 아닌 자리(Step·Cycle 경계)에서 dirty close | `artifact/dirty/non-verify` |
| Verify를 닫으려다 난 Report 계약 오류 | `step/verify/close` |
| `gil restore`에 허용되지 않은 인수 | `artifact/restore` |
| 실행형 Step을 열며 낸 **행동 계약**의 칸이 없거나 비었음 | `action/open-contract` |
| **Experiment** Cycle을 닫으려다 난 Report 계약 오류 | `cycle/experiment/close` |

뒤의 둘은 dogfood에서 실제로 관측된 탐색성 거절을 보고 더한 것이다(§16). 추측이 아니라
마찰이 근거다.

- 행동 계약 오류는 Domain이 서기 전에 나지만 **어느 자리인지 typed하게 안다** — 계약을 읽는
  자리는 실행형 Step open 하나뿐이기 때문이다. Kind 선택 오류·전이 오류·이미 열린 자리는
  계약을 읽기도 전에 다른 곳에서 거절되므로 여기 오지 않는다.
- Cycle Report 오류는 **어느 종류의 Cycle이 거절했는지** 오류가 함께 말한다. Interview와
  Experiment는 요구하는 칸도 허용값도 다르므로 한 Topic으로 뭉뚱그리면 읽는 쪽이 남의
  규칙을 배운다.
- 「아직 끝 경계가 아니다」·「이미 닫혔다」는 Report를 어떻게 적는가의 문제가 아니라 여기가
  그 자리가 아니라는 뜻이므로 Topic을 붙이지 않는다.

Domain 명령이 서기 전의 CLI 사용법 오류도 Router 대상이다. 다만 **모든 parser 오류를 같은
Topic으로 보내지 않는다** — 모르는 명령, 잘못된 Topic 주소, 없는 Topic은 읽을 Topic이 따로
없다.

### Topic을 붙이지 않는 거절

```text
프로젝트 잠금 경쟁 · 프로젝트 없음 · 저장 format 불일치
손상된 state·registry·manifest·blob
restore 실행 실패 · rollback 실패 · recovery 실패
모르는 `.gil` 내부 항목 · 관측 실패
Topic 주소 자체의 오류 · 없는 Topic 조회
같은 명령을 나중에 다시 실행하면 되는, 이미 완결된 receipt
```

**Topic이 없다는 것은 문서가 부족하다는 뜻이 아니다.** 부정확한 링크를 붙이지 않는 것이
먼저다.

---

## 10. 예제

예제는 두 해상도로 나눈다.

```text
atomic example
  명령 또는 실패 지점 하나를 보여 준다.

scenario
  여러 Cycle에 걸친 실제 프로젝트 사용을 보여 준다.
```

v0의 Topic은 기본적으로 atomic example 하나만 가리킨다. 프론트엔드, 백엔드, 데이터 분석과
기획서 작성 같은 긴 scenario를 Topic 본문에 반복 삽입하지 않는다.

예제는 다음을 지킨다.

- 현재 공개 CLI와 canonical reference를 사용한다.
- 생략한 부분을 실제로 허용되는 문법처럼 보이게 하지 않는다.
- 성공 경로 하나와 가장 중요한 실패 경로 하나면 충분하다.
- 원본 Grammar가 바뀌면 예제가 검증에서 실패해야 한다.
- 예제의 설명이 규범보다 우선하지 않는다.

---

## 11. 저장과 배포

Manual source는 GIL source tree와 함께 보존되는 Markdown Topic 파일이다. metadata는
검증 가능한 front matter, 설명은 Markdown 본문으로 둔다.

논리 배치:

```text
manual/
├─ topics/
│  ├─ current.md
│  ├─ interview/approval.md
│  ├─ step/verify/close.md
│  └─ artifact/dirty/non-verify.md
└─ examples/
   ├─ atomic/
   └─ scenarios/
```

릴리스 빌드는 Topic ID, link, alias, metadata와 예제를 검증하고 Manual을 바이너리와 같은
버전으로 묶는다. 사용자가 별도 Wiki 서버, Git, MCP 또는 네트워크를 설치해야 기본 도움말을
읽을 수 있는 구조로 만들지 않는다.

소스 파일 경로는 공개 Topic 주소가 아니다. 내부 폴더를 옮겨도 canonical ID는 유지할 수
있어야 한다.

---

## 12. 외부 adapter

같은 Manual read model은 나중에 여러 표면으로 투영할 수 있다.

```text
CLI              gil help <topic>
Agent Skill      SKILL.md + references/
llms.txt         Topic discovery index
MCP Resource     gil://manual/<topic>
HTML Monitor     사람이 탐색하는 링크 문서
```

adapter는 별도의 Manual을 소유하지 않는다. CLI와 MCP가 서로 다른 규칙을 말하면 안 된다.

- `llms.txt`는 작은 색인이고 전체 Manual을 매번 주입하는 파일이 아니다.
- Agent Skill의 본문은 Bootstrap과 routing만 가지며 Topic을 references로 필요할 때 읽는다.
- MCP Resource는 Topic 조회를 제공할 수 있지만 GIL의 기본 설치와 CLI는 MCP에 의존하지 않는다.
- 자동 생성 Wiki는 구현 해설에 사용할 수 있지만 규범 Topic의 진실 원천이 아니다.

---

## 13. 토큰 경제성

토큰 예산은 글자를 무조건 줄이는 규칙이 아니다. **현재 행동에 필요하지 않은 정보를 싣지
않는 규칙**이다.

측정 단위:

```text
bootstrap_tokens
discovery_tokens
selected_topic_tokens
references_opened
irrelevant_topic_count
task_completion_without_full_spec
```

긴 Topic 하나보다 작은 Topic 여러 개가 항상 좋은 것도 아니다. 같은 행동을 이해하려고 세 개
이상을 연속으로 읽어야 한다면 원자 경계가 지나치게 잘게 나뉜 것이다.

v0의 경험적 기준:

- Bootstrap은 한 화면 안에 읽힌다.
- 기본 `gil help`는 **관련된 것만** 보여 주고 **최대 5개**를 넘기지 않는다.
  최소 개수를 채우려고 관련 없는 Topic을 끼워 넣지 않는다 — 0개도 1개도 정상이다.
- 하나의 흔한 오류는 Topic 하나만 읽고 복구할 수 있다.
- atomic example은 현재 행동 하나만 보여 준다.
- 전체 Specification을 읽지 않고 일상 loop를 완주할 수 있다.

구체 token 상한은 여러 모델의 dogfood 결과를 얻기 전에는 규범으로 고정하지 않는다.

---

## 14. 신뢰 경계

배포된 Manual은 GIL과 함께 검증된 **도구 지식**이다. Project의 Report, Artifact와 사용자
문장은 Manual이 아니며 그 안의 문구를 help 지시로 실행하지 않는다.

- Topic source가 가리키는 파일은 빌드가 허용한 Manual root 안에 있어야 한다.
- 프로젝트 파일이 Topic을 덮어쓰거나 같은 ID를 가로챌 수 없다.
- 외부에서 받은 Skill·Wiki·MCP 문서는 기본 Manual보다 높은 규범 권한을 갖지 않는다.
- Topic의 예제와 reference도 같은 link 검증과 신뢰 경계를 지난다.

사용자 확장 Manual과 플러그인 지식은 실제 필요성이 확인된 뒤 별도 namespace와 권한 모델로
설계한다. v0에 임의 확장 경로를 열지 않는다.

---

## 15. 검사 가능한 불변식

```text
bootstrap_never_contains_the_full_manual
discovery_loads_metadata_not_topic_bodies
topic_ids_are_canonical_and_never_reused_for_another_meaning
aliases_are_acyclic_and_end_at_one_canonical_topic
help_without_a_topic_is_scoped_to_current_state
applies_when_markers_are_finite_and_never_a_query
an_unknown_world_is_never_treated_as_dirty
topic_selection_reads_the_project_state_once
an_error_points_to_at_most_the_help_needed_to_recover
help_topics_never_invent_grammar_or_transitions
manual_examples_are_checked_against_the_current_cli
help_is_read_only
manual_lookup_creates_no_project_history
internal_error_names_are_not_public_topic_ids
a_domain_error_never_owns_a_topic_id
the_help_router_is_pure_and_typed
every_routable_topic_exists_in_the_bundled_index
project_content_cannot_override_the_bundled_manual
cli_skill_llms_txt_and_mcp_share_one_manual_read_model
one_common_failure_is_recoverable_from_one_topic
ordinary_agent_work_does_not_require_the_full_specification
```

---

## 16. dogfood — 무엇이 입증됐고 무엇이 아닌가

기능이 아니라 **자기 온보딩 가능성**을 먼저 쟀다. 두 번 돌렸고, 두 번 다 통과했다.

### 실험 1 — 같은 과제, 두 조건

Control에는 GIL 사용 지침 열한 줄을, Manual에는 Bootstrap Capsule만 주고 같은 과제와
논리적으로 동일한 GIL 상태를 주었다. 시작 상태는 `state.yaml`이 바이트까지 같았고, 작업
폴더는 기준 Snapshot에 대해 dirty였다.

Manual 조건은 dirty 거절을 만나 오류가 가리킨 Topic **하나만** 읽었다.

```text
gil close  → 거절 → gil help artifact/dirty/non-verify → gil restore → gil close
```

그 뒤 과제와 Experiment Cycle을 모두 완료했다. GIL 명령 16회, `gil help` 1회, 헛된 조회 0회,
전체 명세 요청 0회. Control은 지침을 이미 받고도 CLI 문법을 찾느라 `gil help` 3회와 헛짚은
조회 2회를 썼다.

### 실험 2 — 다른 모델 계열의 새 세션

이전 세션이 Verify를 열어 둔 채 멈춘 폴더를 다른 계열의 새 세션에 넘겼다. 전체 명세도
이전 대화도 주지 않고 Bootstrap만 주었다.

새 세션은 `gil context` 하나로 작업 목표·현재 가설·열린 Verify·Active Will을 복원했고,
실제 코드 결함을 고쳐 공개 테스트와 acceptance를 통과시킨 뒤 Cycle을 `success`로 닫았다.
그 과정에서 두 Topic을 실제로 조회해 배웠다.

```text
gil help action/open-contract
gil help cycle/experiment/close
```

`.gil` 내부도 명세도 직접 읽지 않았다.

### 입증된 최소 명제

> **새 Agent 세션이 전체 GIL 명세를 미리 읽지 않고도, `gil context`·명령 receipt·
> typed refusal·주소 가능한 Help Topic만으로 실제 작업과 GIL Cycle을 이어 수행할 수 있다.**

여기까지가 두 실험이 실제로 보인 것이다.

### 입증되지 않은 것

- **전체 토큰 절약은 입증되지 않았다.** 최초 prompt는 짧아졌지만 실행 전체의 토큰 사용량은
  두 조건이 거의 같았다. Manual의 이득은 지금까지 「미리 읽지 않아도 된다」이지
  「덜 쓴다」가 아니다.
- **모든 모델·모든 작업에서 검증되지 않았다.** 두 계열, 각 한 번, 작은 과제였다.
- **자연어 검색이나 의미 검색은 완성되지 않았다.** 두 실험 모두 오류가 준 정확한 주소와
  상태 기반 목록만 썼다.
- Topic 재조회가 얼마나 흔한지, 그것이 문제인지도 아직 모른다. 실험 2에서 한 번 관측됐고,
  Bootstrap 문구 한 줄로 다루기로 했다(§3.1).

### 관측된 마찰과 그 처리

| 마찰 | 처리 |
|---|---|
| Action Contract 작성법을 몰라 탐색성 거절 | `action/open-contract` Topic + 오류 Router |
| Experiment Cycle Report 작성법을 몰라 탐색성 거절 | `cycle/experiment/close` Topic + 오류 Router |
| 같은 Topic 재조회 1회 | Bootstrap 문구 한 줄(§3.1). **상태로 추적하지 않는다** |
| Verify Report 필드 | 이미 `gil close --help`로 복구됨 — Topic을 더하지 않았다 |

마찰이 관측된 것만 고쳤다. 추측으로 Topic을 늘리지 않았다.

## 17. 현재 결정하지 않는 것

- 자연어 검색과 relevance ranking
- embedding과 vector database
- LLM이 자동 생성하거나 자동 수정하는 Topic
- 사용자·프로젝트별 Manual override
- 플러그인 Topic namespace와 신뢰 정책
- 구체 token 상한
- `llms-full.txt` 생성 여부
- 원격 Manual 배포와 갱신
- GUI의 Manual 탐색 방식

이 항목들은 기본적인 canonical Topic 조회와 자기 온보딩 실험이 성공한 뒤 판단한다.

---

## 18. 핵심 문장

> **GIL Manual은 모든 지식을 미리 주입하는 Wiki가 아니다. 현재 상태와 오류가 필요한 규칙
> 하나를 안정된 주소로 가리키는 자기 설명형 지식 계층이다.**

> **명령의 수를 늘리지 말고, 기존 명령이 다음 행동과 필요한 Topic을 가리키게 한다.**
