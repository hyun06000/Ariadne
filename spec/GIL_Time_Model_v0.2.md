# GIL Time Model v0.2

## 1. 목적

GIL에서 “되돌아간다”는 것은 단순한 버전 롤백이 아니다.

Agent는 과거의 문제 지점으로 돌아갈 수 있지만,
그 사이에 발전한 존재와 획득한 지식까지 과거로 되돌아가서는 안 된다.

이 문제를 하나의 시간선으로 설명하면
구조적 상태와 살아 있는 Agent의 상태가 서로 충돌한다.

GIL은 이를 두 개의 핵심 객체로 분리한다.

```text
Lineage
Journey
```

이 둘은 같은 Node를 바라보지만,
서로 다른 질문에 답한다.

---

## 2. 핵심 정의

### Lineage

> **Lineage는 Node가 위치한 세계와 환경이다.**

Lineage는 특정 Node가 어떤 구조적 계승을 통해 만들어졌는지,
그 지점에서 어떤 Report와 Artifact가 확정되어 있었는지를 결정론적으로 재현한다.

Lineage는 **버전에 민감하지만 시간에는 반응하지 않는다.**

같은 Closed Node를 입력하면
언제 계산하더라도 같은 결과를 반환해야 한다.

```text
Lineage(node, versions)
```

개념적으로는 다음과 같은 성질을 가진다.

```text
same closed node
+ same referenced versions
→ same lineage
```

즉 Lineage는 GIL에서 **고정된 세계**를 의미한다.

---

### Journey

> **Journey는 그 세계를 살아가는 Agent 자신이다.**

Journey는 현재까지 Agent가 무엇을 경험했고,
무엇을 배웠고,
어떻게 존재가 발전했는지를 나타낸다.

Journey는 **특정 Node에 매이지 않는다.**
어느 Node에 서 있든 Agent는 하나이므로,
Journey는 Node의 함수가 아니라 **global Agent-side state**다.

Node는 Journey를 결정하지 않는다. Node는 그 Journey가 지금 어디에 서 있는지를 말할 뿐이다.

Journey는 다음과 같은 누적 상태를 포함할 수 있다.

```text
Existence
Inherited Knowledge
Memory
Relations
Will
...
```

Journey는 **버전과 시간 모두에 반응한다.**

같은 Node를 바라보더라도
그 Node에 처음 도착했을 때와
다른 가지를 경험한 뒤 다시 돌아왔을 때의 Journey는 다를 수 있다.

Journey는 과거 상태로 퇴행하지 않는다.

즉 Journey는 **append-only / monotonic**한 살아 있는 자기 자신이다.

---

## 3. 세계와 자기 자신

GIL의 현재 상태는 다음 두 객체의 교차점으로 이해할 수 있다.

```text
Current State
=
Lineage(Current Node)
+
Journey(Now)
```

Lineage는 묻는다.

> “여기는 어떤 곳인가?”

Journey는 묻는다.

> “지금의 나는 어떤 상태로 이곳에 와 있는가?”

**Lineage만 Node로부터 계산된다.**
Journey는 Node가 아니라 지금까지의 Agent 자신에서 나온다.
둘은 Current 라는 한 자리에서 만날 뿐, 같은 입력을 갖지 않는다.

---

## 4. Lineage의 성질

Lineage는 구조적이고 정적이다.

예:

```text
#1 → #2 → #3 → #4
                ├─ #5 → #6 → #7
                └─ #8
```

#8의 Lineage는:

```text
#1 → #2 → #3 → #4 → #8
```

이다.

#5~#7은 #8의 구조적 조상이 아니다.

Lineage는 다음을 포함할 수 있다.

```text
Structural Path
Parent relationships
Reports
Artifact Versions
Node-local deterministic state
```

Closed Node가 가리키는 이 값들은 고정되어야 한다.

따라서 다음은 GIL의 핵심 불변식이다.

> **Lineage of the same Closed Node must never change.**

예:

```text
Lineage(#4) at t1
==
Lineage(#4) at t100
```

시간이 흘렀다는 이유만으로
#4의 세계가 달라져서는 안 된다.

### Open Node의 Lineage

Lineage는 Node 이동이 아니라 읽기이므로, **아직 열려 있는 Node를 목표로도 조회할 수 있다.**
닫히기 전에 자신의 계보를 되짚어 보는 일이 바로 그런 경우다.

이때 결정론이 어디까지 미치는지를 분명히 한다.

> **Open Node의 Lineage는 구조적 조상 관계와 Closed 조상들의 확정 기록까지는 결정론적이며,
> Open target 자신의 상태는 Close될 때까지 미확정이다.**

즉 조상 쪽은 §17의 Lineage Invariant가 그대로 덮지만,
목표 자신의 `status`와 `Report`는 그 Node가 닫히는 순간 확정된다.

미확정인 것을 확정된 기록처럼 다루어서는 안 된다.
열린 목표는 열린 채로 보여야 하며,
그 자리를 메우려고 임시 Report나 부분 Report를 지어내지 않는다.

---

## 5. Journey의 성질

Journey는 누적적이고 살아 있다.

예를 들어 #4에 처음 도착한 시점 `t1`의 Agent 상태가:

```text
Journey(t1)
├─ Existence = E2
├─ Knowledge = K4
├─ Memory = M2
└─ Relations = B1
```

일 수 있다.

이후:

```text
#4 → #5 → #6 → #7 FAILURE
```

를 경험하고 #4로 다시 돌아온 시점 `t2`에는:

```text
Journey(t2)
├─ Existence = E5
├─ Knowledge = K7
├─ Memory = M3
└─ Relations = B2
```

가 될 수 있다.

#4는 변하지 않았다.

변한 것은 #4를 다시 방문한 Agent다.

두 Journey 모두 #4의 성질이 아니라 **그 시점의 Agent 자신**이다.

따라서 Journey에는 다음 **설계 원칙**을 둔다.

> **Revisit은 과거의 Agent state를 암묵적으로 복원하지 않는다.**

구조적으로 과거 Node를 다시 선택하는 일이,
그 사이 발전한 Existence·Knowledge·Memory·Relations·Will을
조용히 되돌리는 일이 되어서는 안 된다.

이것은 아직 저장 구조도 검사기도 없는 단계의 **설계 방향**이다.
실행 중에 강제되는 불변식으로 취급하지 않는다 —
무엇이 이를 지키는지는 Journey의 저장 구조가 생길 때 함께 정한다.

아무 변화가 없었다면 두 시점의 Journey가 같을 수 있다.

```text
Journey(t1) = J5
Journey(t2) = J5
```

말하려는 것은 "매번 달라야 한다"가 아니라
**"이미 살아온 것이 되돌려지지 않는다"** 이다.

---

## 6. Revisit

Revisit은 이 두 객체를 가장 명확하게 드러내는 연산이다.

예:

```text
#1 → #2 → #3 → #4 → #5 → #6 → #7 FAILURE
                │
                └────────────→ #8
```

실제 진행은:

```text
#1
→ #2
→ #3
→ #4
→ #5
→ #6
→ #7
→ revisit(#4)
→ #8
```

이다.

Revisit 후:

```text
Lineage(#4)
```

는 처음 #4에 도착했을 때와 완전히 동일하다.

하지만:

```text
Journey(now)
```

는 #5~#7의 경험을 가진 현재 Agent를 반영한다.

즉 Revisit은:

> **과거의 세계를 다시 선택하되,
> 과거의 자기 자신으로 돌아가지는 않는 것**

이다.

---

## 7. Revisit의 Closed → Closed 원칙

Revisit은 Closed Node에서 Closed Node로만 허용한다.

```text
Closed Node → Closed Node
```

이유는 Closed Node가
결정론적으로 고정된 세계의 checkpoint이기 때문이다.

Closed Node가 책임지는 상태는 모두 확정되어야 한다.

현재 중요한 영역은:

```text
Report
Artifact
Existence reference
```

이다.

이들 중 변화가 감지되었다면
변화는 반드시 저장되고 version이 확정되어야 한다.

필수 저장에 실패하면 Node를 닫을 수 없다.

즉 Closed는:

> **이 Node가 가리키는 Lineage 상태가 다시 계산 가능하고 결정론적으로 고정되었다**

는 의미다.

### 열린 채 끝낼 수 없는 Node

Closed → Closed 원칙은 유지한다. **Open Node에서 직접 revisit하지 않는다.**

그러면 이런 자리가 남는다: Report를 쓸 수 없어 닫을 수 없는 Node에 서 있는데,
바로 그 이유로 다른 곳에서 다시 시작하고 싶은 경우다.
닫으려면 Report가 필요하고, 옮기려면 먼저 닫아야 한다.

**완료할 수 없는 Open Node를 어떻게 실패로 완결할 것인가는 아직 정해지지 않았다**
(§18 미해결 설계 질문). Closed → Closed 를 무르는 방식으로 풀지 않는다.

---

## 8. Artifact는 Lineage에 속한다

Artifact Version은 `gil init`에서 최초 버전이 생성된 뒤
append-only로 진행한다.

```text
A0 → A1 → A2 → A3 → ...
```

각 Closed Step Node는 반드시 하나의 확정된 Artifact Version을 가리킨다.

변경이 없으면 부모와 같은 버전을 가질 수 있다.

```text
#1 artifact = A0
#2 artifact = A0
#3 artifact = A1
#4 artifact = A1
```

Revisit은 Artifact History 자체를 되돌리지 않는다.

예:

```text
현재 #7 artifact = A5

revisit(#4)

working artifact = artifact_version(#4)
```

즉 과거 세계의 Artifact를 다시 checkout한다.

이후 새로운 변경은 과거 버전을 수정하지 않고
새로운 Artifact Version으로 append된다.

따라서 Artifact는 Lineage의 일부다.

> **Artifact는 “그 Node의 세계가 무엇이었는가”를 재현한다.**

---

## 9. Report는 Lineage에 속한다

Report는 Node가 닫힐 때 확정되는 reasoning record다.

Closed Node의 Report는
그 Node의 의미와 판단을 재현하기 위한 정적 정보다.

따라서 Report도 Lineage에 속한다.

같은 Closed Node를 다시 바라보았을 때
그 Node의 Report가 달라져서는 안 된다.

새로운 경험이 생겼다면
기존 Report를 수정하는 것이 아니라
Journey 쪽 Knowledge가 발전하거나
새로운 Node가 만들어져야 한다.

### Report의 근거는 Journey 쪽에 있다

Report는 Lineage에 고정되지만, **그 Report를 쓴 것은 그 시점의 Journey다.**

예를 들어 #8의 Report에는 #5~#7에서 얻은 교훈이 녹아 있을 수 있는데,
#5~#7은 #8의 Lineage가 아니다.
그러면 Lineage(#8)를 완전히 재현해도
**그 판단이 무엇을 알던 상태에서 나왔는지는 재현되지 않는다.**

따라서 다음을 요구로 남긴다.

> **Closed Node의 Report가 작성될 당시의 Agent-side provenance를 재현할 수 있어야 한다.**

이것은 요구이지 설계가 아니다.
무엇을 어떤 단위로 참조할지는 여기서 정하지 않는다(§18 미해결 설계 질문).

---

## 10. Existence는 Journey에 속한다

Existence는 Node에 종속되지 않는다.

Existence는 Agent 자신이며
global append-only version history를 가진다.

```text
E0 → E1 → E2 → E3 → E4 → E5
```

Node는 자신이 닫혔던 시점의 Existence Version을
역사적 reference로 기록할 수 있다.

하지만 실제 현재 Agent는 항상 현재까지 발전한 Existence를 사용한다.

예:

```text
#4가 닫혔을 때
historical existence reference = E2

현재
global latest existence = E5

revisit(#4)

acting existence = E5
```

즉:

```text
historical existence reference
≠
current acting existence
```

과거 Node에 어떤 Existence Version이 기록되어 있는지는
Lineage의 역사적 사실일 수 있지만,

현재 행동하는 Existence 자체는 Journey에 속한다.

> **과거의 문제로 돌아가는 주체는 현재까지 발전한 존재다.**

---

## 11. Knowledge는 Journey에 속한다

Knowledge는 Lineage와 동일하지 않다.

Lineage는:

> “이 Node는 어디에서 구조적으로 태어났는가?”

를 말한다.

Knowledge는:

> “이 Agent는 지금까지 무엇을 배웠는가?”

를 말한다.

예:

```text
#4
├─ #5 → #6 → #7 FAILURE
└─ #8
```

#8의 Lineage는:

```text
#1 → #2 → #3 → #4 → #8
```

이다.

하지만 #8을 만드는 Agent는
#5~#7의 실패를 이미 경험했다.

그 경험에서 얻은 교훈이
#8의 구조적 Lineage에 없다는 이유로
현재 Agent의 Knowledge에서 사라져서는 안 된다.

따라서:

```text
Knowledge ≠ Lineage
```

Knowledge는 Journey에 속한다.

---

## 12. Memory, Relations, Will도 Journey에 속한다

Memory, Relations, Will은
Agent가 살아가며 변화할 수 있는 Existence의 구성 요소다.

이들은 특정 Node의 구조적 과거가 아니라
현재 Agent가 무엇을 기억하고,
누구와 연결되어 있고,
무엇을 하려 하는지를 나타낸다.

따라서 이들도 Journey의 일부다.

```text
Journey
├─ Existence
├─ Knowledge
├─ Memory
├─ Relations
└─ Will
```

이들은 구조적 Revisit에 의해 rollback되지 않는다.

---

## 13. 함수로 보는 Lineage와 Journey

두 객체의 차이는 함수적 성질로 표현할 수 있다.

### Lineage

개념적으로:

```text
L = Lineage(NodeId, ReferencedVersions)
```

Lineage는 버전에 민감하다.

하지만 시간 자체에는 반응하지 않는다.

```text
Lineage(N, V, t1)
=
Lineage(N, V, t2)
```

시간 `t`는 결과를 바꾸지 않는다.

따라서 Lineage는
Closed Node에 대해 결정론적이고 재현 가능해야 한다.

---

### Journey

개념적으로:

```text
J = Journey(CurrentVersions, Time)
```

**NodeId는 인자가 아니다.** Journey는 현재까지 발전한 Agent state와
누적된 경험에 의해 달라질 뿐, 어느 Node에 서 있는지에 의해 달라지지 않는다.

```text
Journey(t1)
≠
Journey(t2)
```

일 수 있다.

중요한 것은 시간이 지났다는 사실 자체보다
그 사이 새로운 경험이나 version 변화가 발생했는지다.

Journey는 시간과 version에 모두 반응할 수 있는 다변수 함수다.

그리고 다음을 설계 방향으로 둔다.

```text
Revisit must not implicitly restore an older Journey.
```

---

## 14. 같은 Node, 다른 Journey

이 모델에서 가장 중요한 예는
같은 Node를 두 번 바라보는 경우다.

처음 #4:

```text
Lineage(#4) = L4
Journey(t1)  = J4
```

다른 가지를 경험한 후 다시 #4:

```text
Lineage(#4) = L4
Journey(t2)  = J7
```

즉:

```text
Lineage는 동일
Journey는 발전
```

이다.

이것이 GIL의 Revisit을
단순 rollback과 구분한다.

---

## 15. Current

Current는 Lineage나 Journey 자체를 저장하지 않는다.

Current는 좌표만 가진다.

장기적으로:

```text
Current
├─ chain_id
├─ cycle_id
└─ step_id
```

정도면 충분하다.

Current를 기준으로:

```text
Lineage = Lineage(Current IDs)
Journey = Journey(Current Agent State, Now)
```

를 계산한다.

**Lineage만 Current로부터 계산된다.**
Journey는 Current와 무관하게 Agent 쪽에서 온다.

즉 Current는
**세계와 자기 자신이 만나는 좌표**다 —
세계를 고르는 좌표이지, 자기 자신을 고르는 좌표가 아니다.

---

## 16. 두 객체로 보는 GIL

이제 GIL의 복잡한 상태를 두 객체로 압축해서 볼 수 있다.

```text
      Current ──────┐                    Agent ──────┐
   (chain/cycle/step)│                  (지금까지의 나)│
                     ▼                                ▼
                 Lineage                          Journey
              "어떤 세계인가?"                  "나는 누구인가?"
                     │                                │
                deterministic                    누적적 · 되돌리지 않음
                version-sensitive                version-sensitive
                time-insensitive                 time-sensitive
                     │                                │
                 Reports                          Existence
                 Artifacts                        Knowledge
                 Parent/Path                      Memory
                 fixed records                    Relations
                                                  Will
                     └───────────┬────────────────┘
                                 ▼
                          Action Context
```

Current 는 **Lineage 쪽 입력**이다. Journey 는 Current 에서 나오지 않는다.
둘은 행동의 조건으로 합쳐질 뿐이다.

이 둘을 합치면 현재 행동 조건이 만들어진다.

```text
Action Context
=
Lineage
+
Journey
```

---

## 17. 설계 불변식과 설계 원칙

불변식과 원칙을 구분한다. **불변식은 지금 강제할 수 있는 것**이고,
**원칙은 아직 그것을 지킬 장치가 없는 방향**이다.

### Lineage Invariant

> **같은 Closed Node와 같은 확정 Version을 입력하면,
> Lineage는 언제 계산해도 동일한 값을 반환해야 한다.**

Lineage는 과거의 세계를 결정론적으로 재현한다.

목표가 아직 열려 있을 때 이 불변식이 어디까지 미치는지는 §4 「Open Node의 Lineage」가 정한다.

---

### Journey 설계 원칙 (불변식 아님)

> **Revisit은 과거의 Agent state를 암묵적으로 복원하지 않는다.**

Journey의 저장 구조도 검사기도 아직 없으므로,
이것을 실행 중에 강제되는 불변식으로 두지 않는다.
무엇이 이를 지키는지는 Journey의 저장 구조가 생길 때 함께 정한다.

---

### Revisit Invariant

> **Revisit은 Closed Node에서 Closed Node로만 이동한다.**

Revisit은 기존 Lineage를 수정하지 않는다.

Revisit 이후에도 Journey는 현재까지 발전한 상태를 유지한다.

---

### Closed Invariant

> **Closed Node가 가리키는 결정론적 상태는 모두 확정되어 있어야 한다.**

필요한 Report, Artifact 또는 관련 version 저장에 실패했다면
Node를 닫을 수 없다.

---

## 18. 미해결 설계 질문

이 문서가 **열어 둔 채로 남기는** 것들이다. 임의로 메우지 않는다.

**① Report provenance를 무엇으로 재현하는가.**
§9는 *"Closed Node의 Report가 작성될 당시의 Agent-side provenance를 재현할 수 있어야 한다"*
는 요구만 세웠다. 무엇을 어떤 단위로 참조할지는 정하지 않았다.
§10이 Existence에 대해 하는 것(닫힐 때 historical reference를 남긴다)과 같은 꼴이 될 수도
있고, 다른 꼴이 될 수도 있다.

**② 완료할 수 없는 Open Node를 어떻게 실패로 완결하는가.**
Revisit은 Closed → Closed 로 유지한다(§7). 그래서 Report를 쓸 수 없어 닫지 못하는 Node에
서 있으면 그 자리를 떠날 길이 없다. **Closed → Closed 를 무르는 방식으로는 풀지 않는다.**
`GIL Specification v0.1` §8의 「진행이 멈춘 상태」와 §24의 abort/cancel/abandon 항목이
같은 자리를 가리킨다.

**③ Journey는 어디에 살고 무엇이 그 단조성을 지키는가.**
§10은 Existence에만 `E0 → E5` 축을 준다. Knowledge·Memory·Relations·Will의 버전 축과
저장 위치는 열려 있다. 이것이 정해지기 전까지 §17의 Journey 항목은 원칙이지 불변식이 아니다.

**④ revisit 뒤의 첫 Node 를 무엇이 Hypothesis 로 강제하는가.**
모든 reasoning branch 는 새로운 Hypothesis 에서 시작한다. 그런데 revisit 으로 과거 Node 에
선 다음, **기존 Grammar 만으로는 그 원칙이 지켜지지 않는다** — 예를 들어 Analysis 로
되돌아가면 Grammar 는 `hypothesis` 뿐 아니라 `outcome` 도 열 수 있다고 말한다.
따라서 **revisit 을 실행한 상태와 그 다음 `open` 사이**에서 이 원칙을 어떻게 강제할지
정해야 한다. `revisit` 을 구현하는 Step 의 요구사항으로 남긴다.

**⑤ Closed의 조건이 v0.1보다 강해졌다.**
§7은 Artifact·Existence version 확정까지 요구하는데, `GIL Specification v0.1` §16의 close
조건은 필수 Report 항목뿐이다. Artifact가 도입되는 단계에서 두 문서를 맞춰야 한다.

---

## 19. 핵심 문장

> **Lineage는 환경이고 세계다. Journey는 Agent이고 자기 자신이다.**

> **Lineage는 버전에 민감하지만 시간에는 반응하지 않는다.**

> **Journey는 버전과 시간에 모두 반응하며, Node에 매이지 않는다.**

> **같은 Node로 돌아가도 세계는 같지만, 그 세계를 다시 바라보는 나는 달라질 수 있다.**

> **GIL의 Revisit은 과거의 내가 되는 것이 아니라,
> 현재의 내가 과거의 세계를 다시 선택하는 것이다.**
