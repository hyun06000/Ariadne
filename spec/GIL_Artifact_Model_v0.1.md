# GIL Artifact Model v0.1

## 1. 목적

Artifact는 AI와 인간의 작업으로 생성되거나 수정된 **실제 결과물**이다. 소스 코드, 데이터셋,
노트북, 문서, 이미지, 설정 파일이 모두 여기 속한다.

GIL은 Artifact를 파일 단위로 등록하거나 파일마다 복원 규칙을 두지 않는다. 작업 결과물 전체를
**하나의 tree snapshot**으로 다루며, 그 snapshot이 "그 Node의 세계가 무엇이었는가"를 재현한다.

이 문서는 **Artifact Timeline의 규범 단일 진실 공급원**이다. Artifact·Snapshot·`gil restore`에
관한 규범 문장은 여기에만 두고, 다른 명세는 이 문서를 참조한다.

```text
GIL Specification v0.1 §8·§16·§20·§21   개념과 위치만, 규칙은 여기 참조
GIL Cycle Model v0.1 §9                 Cycle-level revisit이 이 계약 위에 서는 방식
GIL Time Model v0.2 §8                  Artifact가 Lineage에 속한다는 시간 규칙
GIL Node Model v0.1 §10                 Node에 귀속되는 구조 필드
```

---

## 2. 두 시간선에서의 자리

`GIL Time Model v0.2` §17이 나눈 두 축에서 Artifact는 **World 쪽**이다.

```text
World Timeline      Cycle·Step Graph · Report · Artifact Snapshot
Journey Timeline    Existence State · Knowledge · Memory · Relations · Will
```

이 구분이 이 문서 전체의 뿌리다.

> **Artifact Snapshot은 World Timeline에 속한다. Journey Timeline은 Artifact 복원의 영향을
> 받지 않는다.**

과거 Snapshot을 현재 작업 폴더에 다시 투영하더라도 Journey revision, Done Will, Existence의
경험, 이미 기록된 Report와 Graph, 그리고 Snapshot 객체 자체는 삭제되거나 되감기지 않는다
(§9).

---

## 3. 관리 범위

`.gil`이 놓인 **프로젝트 루트 아래의 일반 파일**을 Artifact 관리 대상으로 삼는다.

v0에서 최소한 다음은 제외한다.

- `.gil/` 자체. GIL의 Graph·Report·Journey가 사는 내부 영역이며 Artifact tree에 포함되지
  않는다. Snapshot 복원은 `.gil` 안의 어떤 것도 삭제하거나 과거 사본으로 덮어쓸 수 없다.
- GIL이 관리할 수 없는 특수 파일(디바이스 노드, 소켓, FIFO 등).
- 구현상 반드시 제외해야 하는 내부 임시 파일.

### 사용자 정의 제외 규칙은 아직 없다

`.gilignore`의 공개 계약과 사용자 정의 제외 규칙은 **만들지 않는다.** 실제 dogfooding에서
필요성이 확인된 뒤 별도로 결정한다. 그때까지 GIL은 위 세 부류만 제외하며, 제외 목록을
사용자가 늘릴 수 있는 문법을 노출하지 않는다.

### 아직 결정하지 않은 것

다음은 임의로 확정하지 않는다. 구현 직전 또는 실사용에서 필요성이 드러난 뒤 정한다(§12).

- 심볼릭 링크의 취급(링크 자체를 저장하는가, 대상을 따라가는가, 거절하는가)
- 파일 실행 권한과 모드 비트의 보존 여부
- 대용량 파일의 상한과 초과 시의 동작
- 빈 디렉터리의 보존 여부

---

## 4. 최초 기준 세계

`gil start`는 GIL 저장소를 만들기 전의, 또는 `.gil/`을 제외한 동일한 관측 결과를 이용해
**현재 프로젝트 상태를 최초 불변 Artifact Snapshot으로 확정한다.**

이 최초 Snapshot은 빈 세계가 아니다. 사용자가 GIL을 시작한 시점의 **실제 프로젝트 상태**다.
이미 코드가 있는 저장소에서 GIL을 시작하면 그 코드가 기준 세계가 된다.

```text
gil start
→ 프로젝트 루트의 현재 상태를 관측 (`.gil/` 제외)
→ 최초 불변 Artifact Snapshot 확정
→ 최초 Existence X1 · 빈 Journey J0 · current_existence_ref
→ X1이 소유한 최초 Interview Cycle Open
→ 위 전부를 하나의 저장 트랜잭션으로 확정
```

`GIL Existence Model v0.1` §4가 정한 `gil start`의 한 save에 **최초 Artifact Snapshot의 확정과
그 참조 기록이 함께 들어간다.** Snapshot 없이 열린 Interview Cycle이나, Cycle 없이 확정된
Snapshot을 저장할 수 없다. 저장 경계의 자세한 규칙은 §10에 있다.

### 최초 Snapshot의 참조를 어디서 찾는가

이후의 변경 감지와 복원은 이 기준을 찾을 수 있어야 한다. 기존 명세가 이미 **Cycle Entry
snapshot**이라는 개념을 쓰고 있으므로(§7·`GIL Time Model v0.2` §8), 가장 작은 정합적 위치는
그것을 실재하는 구조 필드로 만드는 것이다.

```text
제안 — 확정이 아니다
  Cycle이 entry snapshot 참조를 구조 필드로 갖는다.
  뿌리 Cycle의 entry snapshot = 최초 기준 Snapshot
  자식 Cycle의 entry snapshot = 부모 Cycle의 Exit Snapshot
```

이 제안의 장점은 새 최상위 개념을 만들지 않는다는 것이다. `Cycle Entry snapshot`은 이미 여러
명세가 참조하는 값인데 저장되는 자리가 없었고, 이 제안은 그 빈자리를 채운다.

대안은 Project 뿌리에 `baseline_snapshot_ref`를 따로 두는 것이다. 그러면 뿌리 Cycle의 entry가
비어 있게 되어 계층마다 규칙이 갈린다.

**둘 중 무엇으로 할지는 구현 직전에 확정한다**(§12·§13). 이 문서는 "찾을 수 있어야 한다"만
규범으로 두고 저장 위치를 확정하지 않는다.

---

## 5. Snapshot 생성 권한

새 Artifact Snapshot은 **다음 두 시점에만** 생성된다.

```text
1. gil start의 최초 기준 세계 확정
2. 열린 Verify를 성공적으로 닫는 원자적 트랜잭션
```

Interview의 Question·Interpretation·Synthesis, Experiment의 Define·Hypothesis·Analysis,
두 Kind의 Outcome, 그리고 Cycle container close는 **새 Artifact Snapshot을 만들지 않는다.**

### "Verify를 성공적으로 닫는다"의 뜻

이것은 **Verify Report의 의미상 성공 판정을 뜻하지 않는다.** 필요한 Report가 유효하고, 저장
트랜잭션 전체가 성공하여 Verify Node가 정상적으로 닫힌다는 뜻이다.

> **Verify 자체에는 verdict가 없다.**

Verify는 관측하고 Analysis가 해석하며 Outcome이 판정한다(`GIL Specification v0.1` §11). 가설이
반증된 실험의 Artifact 상태도 그대로 Snapshot이 되며, 그 세계가 성공이었는지는 나중에 Outcome의
verdict가 말한다. Snapshot 생성과 verdict 판정은 서로 독립적이다.

---

## 6. 변경 허용 경계

> **Artifact를 바꿀 수 있는 유일한 Step 경계는 Verify다.**

Verify가 아닌 Action Step을 닫을 때 관리 대상 Artifact가 현재 기준 Snapshot과 다르면 **닫기를
거절한다.** 경고만 하고 닫거나, 자동으로 변경을 버리거나, 자동 복원과 Close를 한 동작으로 묶지
않는다. 자동 복원은 기록되지 않은 작업을 조용히 삭제하기 때문이다.

Cycle container close에서도 Artifact 변경이 발견되면 **닫기를 거절한다.** Cycle close는 Snapshot을
새로 만들지 않으므로(§5), 변경을 확정할 방법이 없는 채로 그릇을 닫게 되기 때문이다.

### 거절은 아무것도 남기지 않는다

거절된 Step과 그 Active Will은 **열린 상태로 유지되어야 한다.** 닫힘에 수반되는 다음 상태가
하나라도 부분적으로 저장되어서는 안 된다.

```text
Journey revision
Done Will
Node Report · journey_ref · Closed 상태
Cycle Report · Cycle의 journey_ref · Closed 상태
```

이는 `GIL Will Model v0.1` §7의 통합 Close 트랜잭션 원칙과 같은 규칙이며, Artifact 검사는 그
트랜잭션의 **가장 앞에 놓이는 관문**이다(§10).

### 사용자가 할 수 있는 것

거절된 자리에서 사용자는 둘 중 하나를 한다.

1. `gil restore`로 현재 확정 Snapshot을 다시 투영해 깨끗한 세계로 되돌린 뒤 다시 닫는다(§8).
2. 그 변경이 실제로 필요한 작업이었다면, 변경을 확정할 수 있는 Verify를 여는 경로로 돌아간다.

강제로 변경 상태를 채택하는 옵션은 두지 않는다.

---

## 7. Verify close와 Cycle Exit Snapshot

### Verify close

Verify close는 **하나의 원자적 동작**이다.

```text
1. Verify Report 검증
2. 현재 Artifact 상태 관측
3. 새 불변 Snapshot 확정
4. Verify Node에 snapshot_ref 기록
5. Active Will을 Done으로 이동
6. 새 Journey revision 생성
7. Verify Node 닫기
8. World Current Snapshot 갱신
```

이 중 **하나라도 실패하면 전체가 이전 상태로 남는다.** Will만 Done이 되거나, Snapshot을 가리키지
않는 Closed Verify가 생기거나, Report 없이 판이 오르는 중간 상태를 허용하지 않는다.

`snapshot_ref`는 Report의 일부가 아니라 **Verify Node의 구조 필드**다. 다른 Closed Step은 이
값을 복제하지 않고 §7의 유도 규칙으로 찾는다.

### 다른 Step의 Artifact Version은 유도한다

```text
Verify Step        구조 필드 snapshot_ref를 직접 갖는다
그 밖의 Closed Step Lineage에서 가장 가까운 선행 Verify의 snapshot
선행 Verify가 없으면 그 Cycle의 Entry Snapshot
```

같은 세계를 여러 Step이 가리킬 수 있다. 변경이 없었다는 뜻이며, 그것을 이름의 중복 저장으로
표현하지 않는다.

### World Current Snapshot

"현재 세계가 무엇인가"는 위 유도 규칙의 결과다. 즉 **현재 Step Lineage에서 가장 가까운 선행
Verify snapshot이고, 없으면 현재 Cycle의 Entry Snapshot이다.**

§7의 8번("World Current Snapshot 갱신")은 별도의 저장 값을 새로 쓴다는 뜻이 아니라, 새 Verify
snapshot이 확정되는 순간 이 유도값이 그것을 가리키게 된다는 뜻이다. 유도값과 저장값을 함께 두면
한쪽이 낡는다. **다만 성능이나 무결성 검사를 위해 이를 별도 필드로 캐시할지는 구현 직전에
정한다**(§12).

### Cycle Exit Snapshot

Cycle close는 새 Snapshot을 만들지 않는다.

> **닫히는 Cycle의 마지막 Outcome이 속한 구조적 lineage에서 가장 최근에 확정된 Verify
> Snapshot을 Cycle Exit Snapshot으로 기록한다.**

그 lineage에 Verify Snapshot이 하나도 없다면 그 Cycle의 **Entry Snapshot을 그대로 계승한다.**
Entry Snapshot은 부모 Cycle의 Exit Snapshot이고, 뿌리 Cycle이라면 최초 기준 Snapshot이다(§4).
따라서 Exit Snapshot은 어떤 경우에도 실재하는 Snapshot을 가리킨다.

Artifact를 바꾸지 않는 Interview Cycle은 이 규칙에 따라 **Artifact 관점에서 투명하다.**

```text
Interview Entry: A2
Interview Exit:  A2
```

### 무엇을 골라서는 안 되는가

- **버려진 가지의 Verify Snapshot을 고르지 않는다.** 되돌아감으로 버려진 형제 가지의 세계는
  이 Cycle이 도달한 세계가 아니다.
- **단순히 ID가 가장 큰 Snapshot을 고르지 않는다.** 이름의 크기는 순서의 근거가 아니다.

반드시 **닫히는 마지막 Outcome의 구조적 lineage**(`parent` 사슬)를 따른다. 이는 `basis_refs`와
`synthesis_ref`가 따르는 것과 같은 계보 규칙이다(`GIL Cycle Model v0.1` §16·§17).

---

## 8. `gil restore`

v0의 `gil restore`는 **현재 Cycle에서 이용 가능한 가장 최근의 확정 Snapshot**으로 관리 대상
Artifact를 복원한다. 그 대상은 §7의 World Current Snapshot과 같다.

용도는 하나다.

> **허용되지 않은 Artifact 변경 때문에 닫지 못하게 된 현재 Node를, 깨끗한 세계로 되돌린다.**

### 무엇을 바꾸지 않는가

`gil restore` 자체는 다음을 **변경하지 않는다.**

```text
Step / Cycle Graph
Report
Current Node
Active Will
Journey revision과 Done Will
Knowledge · Memory · Relation · Existence
```

즉 World의 Artifact만 복원한다. 열린 Node는 계속 열려 있고, 걸린 Will은 계속 걸려 있다. 사용자는
이후 다시 작업하거나 그 Node를 닫는다.

### 무엇을 보여 주는가

복원 전에 현재 변경을 자동으로 보존하거나 새 Snapshot으로 만들지 않는다. 대신 **덮어쓰게 될
변경이 있다는 사실과 복원 대상을 명확히 보여 준다.**

```text
덮어쓰게 될 변경   무엇이 바뀌었는지
복원 대상          어느 Snapshot의 세계로 돌아가는지
```

### 아직 결정하지 않은 것

`gil restore`의 **확인 절차와 비대화식 에이전트 사용법은 아직 정하지 않았다**(§12). 구현 편의를
위해 임의의 강제 옵션을 만들지 않는다.

### revisit과 다르다

`gil restore`는 현재 자리의 세계를 되돌리는 것이고, revisit은 과거 Closed ancestor를 골라 새
형제 가지를 여는 것이다. 둘을 한 명령으로 합치지 않는다.

---

## 9. 시간선 불변식

Artifact Snapshot은 World Timeline에 속한다. 과거 Snapshot을 복원하더라도 다음은 **삭제되거나
되감기지 않는다.**

```text
Journey revision
Done Will
Existence의 경험
이미 기록된 Report와 Graph
Snapshot 객체 자체
```

따라서 restore는 **기록 삭제가 아니라 과거 World 상태를 현재 작업 폴더에 다시 투영하는
동작**이다.

```text
Artifact:   과거의 상태
Report·Graph: 그대로
Journey:    계속 전진
Existence:  유지
```

> **과거 세계를 다시 선택해도, 그 세계를 다시 바라보는 나는 이미 달라져 있다.**

---

## 10. 저장과 원자성 경계

format 3은 World Graph와 Existence/Journey를 `.gil/state.yaml` 하나에 함께 눕히고, 임시 파일에
쓴 뒤 제자리로 옮겨 원자성을 얻는다(`GIL Existence Model v0.1` §4). Artifact Snapshot은 그
파일 안에 들어가지 않으므로 **경계가 둘이다.**

```text
① Snapshot 저장소   append-only · 내용을 담는다 · 지우지 않는다
② .gil/state.yaml   한 번의 교체로 논리 상태 전부를 확정한다
```

### 순서는 뒤집을 수 없다

```text
1. Artifact 관측과 Snapshot 확정          (① 에 쓴다)
2. 확정된 Snapshot의 실재 확인
3. Report · snapshot_ref · Will Done · Journey revision · Closed 를
   하나의 state 교체로 기록                (② 를 교체한다)
```

이 순서가 만드는 두 가지 비대칭이 이 설계의 핵심이다.

- **1·2가 끝나고 3 직전에 중단되면**, 아무도 가리키지 않는 Snapshot 하나가 남는다. 논리 상태는
  손상되지 않는다. 참조되지 않은 Snapshot은 잘못이 아니다.
- **반대는 허용하지 않는다.** state가 실재하지 않는 Snapshot을 가리키는 상태는 손상이다.
  복원 시 모든 `snapshot_ref`의 실재를 검사하고, 없으면 거절한다.

### Will/Existence 원자성과 충돌하지 않는다

`GIL Will Model v0.1` §7의 통합 Close 트랜잭션과 `GIL Existence Model v0.1` §4의 한 save 규칙은
**②의 규칙**이다. Artifact의 원자성은 **①에서 ②로 넘어가는 순서의 규칙**이다. 둘은 같은 자원을
다투지 않는다.

Verify close의 전체 순서는 다음과 같다.

```text
Artifact 검사·확정 (①)  →  state 교체 (②)
  ↑ 실패하면 여기서 멈추고 state는 한 글자도 바뀌지 않는다
```

Verify가 아닌 Close에서는 ①이 **검사만** 한다.

```text
Artifact 변경 여부 검사  →  변경이 있으면 거절, state 교체 없음
                          변경이 없으면 state 교체 (②)
```

`gil start`의 한 save도 같은 순서를 따른다. 최초 Snapshot을 ①에 확정한 뒤, 그 참조와 최초
Existence·Journey·Interview Cycle을 ②의 한 번의 교체로 함께 기록한다.

---

## 11. 방향 값의 세 상태

명세가 정의한 방향 값이라고 해서 지금 밟을 수 있는 것은 아니다. GIL은 다음 **세 상태를
구분해서 말한다.**

```text
1. 기록할 수 있고 실행할 수 있다
2. 유효하게 기록할 수 있지만 현재 버전에서는 실행할 수 없다
3. 아직 문법으로 제공되지 않는다
```

현재 상태는 다음과 같다.

| 값 | 계층 | 상태 |
|---|---|---|
| `close_cycle` | Step Outcome | 1 |
| `open_child` | Cycle Report | 1 |
| `revisit` | Step Outcome | 1 |
| `revisit` | Cycle Report | **2** |
| `close_chain` | Cycle Report | **3** |

Experiment Cycle의 failure Report에 적는 `revisit`은 **유효한 다음 방향으로 정상 기록된다.**
그러나 Artifact Snapshot 복원과 Cycle-level revisit이 완성되기 전에는 그 이동을 실행할 수 없다.

> **사용자와 에이전트에게 `revisit`이 잘못된 값이라고 말해서는 안 된다.**

방향은 정상적으로 기록되었고, **후속 전이가 아직 구현되지 않았다**고 설명한다. `GIL Agent UX
Model v0.1` §4.2의 허용값 설명이 이 구분을 그대로 전달한다.

Cycle-level `revisit`이 2번에서 1번으로 옮겨 가는 것은 M3의 Cycle Exit Snapshot이 확정된 뒤
M4가 하는 일이다.

---

## 12. 아직 결정하지 않은 것

- 관리 범위의 세부: 심볼릭 링크, 파일 권한과 모드, 대용량 파일 상한, 빈 디렉터리(§3)
- `.gilignore`의 공개 계약과 사용자 정의 제외 규칙(§3)
- 최초 기준 Snapshot 참조의 저장 위치 — Cycle entry 필드인가 Project 뿌리 필드인가(§4)
- World Current Snapshot을 유도값으로만 둘 것인가 캐시 필드를 둘 것인가(§7)
- 관측 결과가 기존 Snapshot과 **완전히 같을 때** 새 Snapshot 이름을 발급할 것인가 기존
  `SnapshotRef`를 재사용할 것인가(§13)
- `gil restore`의 확인 절차와 비대화식 에이전트 사용법(§8)
- Snapshot 객체의 내부 schema와 저장 엔진 — libgit2를 포함해 어떤 기법을 쓸지(§14)
- Artifact 변경 내역을 사용자에게 보여 주는 해상도와 형식

---

## 13. 같은 내용의 세계에 새 이름을 줄 것인가

이 질문은 두 기존 원칙이 만나는 자리라 임의로 정하지 않는다.

```text
내용 주소화       같은 내용은 같은 주소다
프로젝트 로컬 ID  `snapshot:A1` 은 순차 발급되며 재사용하지 않는다
                  (GIL Node Model v0.1 §2.1)
```

두 후보:

- **재사용** — 관측 결과가 기존 Snapshot과 같으면 그 `SnapshotRef`를 그대로 기록한다.
  `GIL Time Model v0.2` §8의 *"변경이 없으면 여러 Step이 같은 Version을 가리킬 수 있다"* 와
  자연스럽게 맞고, 이름의 변화가 곧 세계의 변화라는 읽기 쉬운 성질을 얻는다.
- **매번 새 이름** — Verify가 세계를 확정한 사건 자체를 이름으로 남긴다. 그러면 `A7`과 `A8`이
  같은 내용일 수 있고, "이 Verify가 세계를 바꿨는가"를 이름만으로 판정할 수 없게 된다.

**권고는 재사용이다.** 다만 확정하지 않는다 — 이 선택은 Snapshot 저장 엔진의 구조와 함께
결정되어야 하고, 그 엔진은 아직 고르지 않았다(§14).

이 문서의 규범 문장은 두 후보 어느 쪽에서도 성립하도록 적었다.

> **Verify close는 그 시점의 세계를 가리키는 확정 `SnapshotRef`를 Verify Node에 새긴다.**

---

## 14. 이번 범위에서 구현하지 않는 것

```text
Cycle-level revisit 실행            M4
성공한 Cycle들의 Artifact merge     M8
sibling Cycle merge                 M8
prune 또는 Snapshot 삭제            범위 밖
`.gilignore` 공개 계약              필요가 확인된 뒤
원격 저장·공유                      범위 밖
전체 Artifact history UI            M5 이후
구체 저장 엔진 선택과 공개 계약     후속 구현 단계
```

구현체가 내부적으로 어떤 저장 기법을 쓸지는 후속 구현 단계에서 결정한다. libgit2를 쓰더라도
그것은 구현 세부이며, **GIL의 공개 개념과 오류 메시지에서 Git 용어를 노출하지 않는다.**
staging, index, add, commit, branch, checkout은 사용자에게 보이는 GIL의 어휘가 아니다.

---

## 15. 검사 가능한 핵심 불변식

```text
artifact_scope_excludes_gil_dir
start_confirms_the_real_project_state_as_the_baseline
start_writes_baseline_and_first_cycle_in_one_transaction
snapshot_is_created_only_by_start_or_verify_close
verify_has_no_verdict
snapshot_creation_is_independent_of_verdict
non_verify_close_is_refused_when_artifacts_changed
cycle_close_is_refused_when_artifacts_changed
cycle_close_creates_no_snapshot
refused_close_leaves_the_step_and_the_will_open
refused_close_writes_no_partial_state
verify_close_is_all_or_nothing
snapshot_ref_is_a_structural_field_not_a_report_field
other_steps_derive_their_snapshot_from_lineage
cycle_exit_snapshot_follows_the_last_outcome_lineage
cycle_exit_snapshot_inherits_entry_when_no_verify_ran
abandoned_branch_snapshots_are_never_inherited
largest_snapshot_id_is_never_the_selection_rule
every_snapshot_ref_exists_at_restore_time
unreferenced_snapshots_are_not_corruption
restore_changes_only_artifacts
restore_does_not_rewind_journey_or_graph
restore_shows_what_it_will_overwrite
recorded_direction_is_not_called_invalid_when_unimplemented
no_git_vocabulary_in_the_public_surface
```

---

## 16. 핵심 문장

> **Artifact는 "그 Node의 세계가 무엇이었는가"를 재현한다.**

> **세계를 바꿀 수 있는 자리는 Verify 하나뿐이고, 세계를 확정하는 시점도 그때 하나뿐이다.**

> **restore는 기록을 지우는 것이 아니라 과거의 세계를 지금 폴더에 다시 투영하는 것이다.**

> **기록할 수 있다는 것과 지금 실행할 수 있다는 것은 다르다. GIL은 그 둘을 구분해서 말한다.**
