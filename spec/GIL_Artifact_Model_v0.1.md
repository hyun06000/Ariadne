# GIL Artifact Model v0.1

## 1. 목적

Artifact는 AI와 인간의 작업으로 생성되거나 수정된 **실제 결과물**이다. 소스 코드, 노트북,
문서, 이미지, 설정 파일, 그리고 프로젝트 폴더 안에 놓인 데이터 파일이 모두 여기 속한다.

실험을 위해 외부에서 반입해 추적하는 **Managed Dataset은 Artifact가 아니다**(§14).

GIL은 Artifact를 파일 단위로 등록하거나 파일마다 복원 규칙을 두지 않는다. 작업 결과물 전체를
**하나의 tree snapshot**으로 다루며, 그 snapshot이 "그 Node의 세계가 무엇이었는가"를 재현한다.

이 문서는 **Artifact Timeline의 규범 단일 진실 공급원**이다. Artifact·Snapshot·`gil restore`에
관한 규범 문장은 여기에만 두고, 다른 명세는 이 문서를 참조한다.

```text
GIL Specification v0.1 §8·§16·§20·§21   개념과 위치만, 규칙은 여기 참조
GIL Cycle Model v0.1 §9                 Cycle-level revisit이 이 계약 위에 서는 방식
GIL Time Model v0.2 §8                  Artifact가 Lineage에 속한다는 시간 규칙
GIL Node Model v0.1 §2.1·§10            공개 참조 문법과 Node에 귀속되는 구조 필드
GIL Storage Model v0.1                  format 4·객체 저장소·잠금의 물리 저장 계약
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

## 3. 무엇이 하나의 Artifact 세계인가

`.gil`이 놓인 **프로젝트 루트 아래의 일반 파일**이 Artifact 관리 대상이다.

### 3.1 일반 파일의 정체성

v0의 일반 파일 Artifact 정체성은 **두 값의 조합**으로 결정한다.

```text
① 정규화된 프로젝트 상대 경로
② 파일의 실제 바이트
```

따라서 다음은 모두 **다른 Artifact 세계**를 만든다.

- 파일 내용 변경
- 일반 파일 생성
- 일반 파일 삭제
- 파일 이름 변경
- 파일 위치 변경

이름이나 위치 변경은 **기존 경로의 삭제와 새 경로의 생성으로 관측한다.** GIL은 rename을
별도 사건으로 추적하지 않는다.

다음은 Artifact 정체성에 **포함하지 않는다.**

```text
수정 시각 (mtime)
생성 시각
소유자
파일 권한과 mode bit
```

같은 바이트를 담은 파일은 언제 쓰였든, 누구 것이든, 권한이 무엇이든 **같은 세계의 같은
파일**이다.

### 3.2 바이트로 비교한다

> **줄바꿈이나 텍스트 인코딩을 GIL이 임의로 변환하지 않는다.**

파일은 텍스트 의미가 아니라 **실제 바이트**로 비교한다. `CRLF`와 `LF`는 다른 바이트이므로
다른 세계다. UTF-8과 UTF-16은 다른 바이트이므로 다른 세계다. BOM의 유무도 마찬가지다.

GIL은 파일 내용을 정규화하지 않는다 — 「정규화」는 §3.3의 **경로**에만 쓰는 말이다.

### 3.3 경로 정규화

Artifact manifest의 **공개 경로 계약**은 다음과 같다.

```text
프로젝트 루트 기준 상대 경로
디렉터리 구분자는 /
UTF-8로 표현 가능한 경로만
```

- 절대경로를 허용하지 않는다.
- `.`·`..` 경로 구성 요소를 허용하지 않는다.
- **구성 요소에 `\` 를 담은 이름을 허용하지 않는다.** `/` 가 유일한 canonical 구분자이므로,
  실제 파일 이름에 `\` 가 들어 있으면 v0 Artifact 경로로 **표현되지 않는다.** 이것은 Windows
  경로를 `\` 로 저장한다는 뜻이 아니다 — 모든 플랫폼의 공개 표현은 `/` 하나다.
- **대소문자를 임의로 변환하지 않는다.**
- **Unicode NFC/NFD 등 정규화를 임의로 적용하지 않는다.**
- 파일 시스템에서 관측한 대소문자와 Unicode 표기를 **그대로 보존한다.**

이 계약으로 표현할 수 없는 경로가 하나라도 있으면 **조용히 제외하지 않고 Artifact 관측
전체를 거절한다.** 조용한 제외는 그 파일이 세계에 없다는 거짓말이 된다.

**같은 규칙이 두 방향에 쓰인다** — 파일 시스템에서 관측한 이름과 사람이 적어 준 canonical
글자가 같은 검사를 지난다. 그래서 관측이 만든 경로는 언제나 같은 parser 로 다시 읽힌다.

#### 프로젝트의 절대 위치는 세계의 일부가 아니다

프로젝트가 디스크 어디에 있는지는 manifest에 들어가지 않는다.

> **프로젝트 폴더를 옮겨도 상대 경로와 내용이 같다면 같은 Artifact 세계다.**

#### 정렬

manifest 항목은 **정규화된 경로의 UTF-8 바이트를 부호 없는 값으로 보는 오름차순**으로
정렬한다. 이 하나가 canonical 순서이며, **플랫폼 locale·collation에 의존하지 않는다.**
같은 세계는 어느 기계에서 관측해도 같은 순서의 manifest가 된다.

### 3.4 관리 대상 종류

v0의 Artifact manifest는 **일반 파일만 기록한다.**

| 종류 | 취급 |
|---|---|
| 일반 파일 | **관리한다** |
| 일반 디렉터리 | 탐색에만 쓴다 |
| 빈 디렉터리 | Artifact 세계에 **포함하지 않는다** |
| **프로젝트 루트 바로 아래의 `.gil/`** | 현재 프로젝트의 내부 저장소 — 제외 |
| **그보다 깊은 곳의 `.gil/` 디렉터리** | 중첩 GIL 경계 — **전체 관측 거절** |
| 심볼릭 링크 | 존재하면 **전체 관측 거절** |
| socket · FIFO · device file 등 특수 항목 | 존재하면 **전체 관측 거절** |

> **심볼릭 링크와 특수 항목은 따라가지도, 저장하지도, 조용히 제외하지도 않는다.**

거절은 프로젝트 관리 범위 안에서 **하나라도 발견되면** 발생한다. 그때 GIL은 해당 항목이나
다른 프로젝트 파일을 **변경하지 않으며 논리 상태도 확정하지 않는다.**

빈 디렉터리만 만들거나 지우는 것은 **dirty가 아니다.** `gil restore`는 일반 파일을 놓는 데
필요한 부모 디렉터리만 만든다(§8).

#### 프로젝트 루트의 `.gil/` 하나만 제외한다

> **프로젝트 루트의 `.gil/` 하나는 현재 프로젝트의 내부 저장소이므로 Artifact 관측에서
> 제외한다. 관리 범위의 다른 깊이에서 `.gil` 디렉터리를 발견하면 중첩된 GIL 경계로 간주하고
> 전체 관측을 거절한다. v0은 중첩 GIL 프로젝트를 지원하지 않는다.**

```text
project/
  .gil/             현재 프로젝트 내부 저장소 → 제외
  src/main.rs       관리
  sub/
    .gil/           중첩 GIL 경계 → 전체 관측 거절
    lib.rs
```

거절은 **디렉터리 항목의 이름과 위치만으로** 즉시 일어난다. 중첩 `.gil` 의 내부를 먼저 읽거나
분류하지 않는다.

루트 `.gil/` 안은 GIL의 Graph·Report·Journey가 사는 내부 영역이다. Snapshot 복원은 그 안의
어떤 것도 삭제하거나 과거 사본으로 덮어쓸 수 없다.

#### 왜 조용히 제외하지도, 관리하지도 않는가

**모든 중첩 `.gil` 을 조용히 제외하면** — 바깥 restore가 안쪽 프로젝트의 작업 파일은 과거로
복원하면서 안쪽 `.gil` 의 World Graph·Journey·Snapshot은 현재에 남긴다. 그러면 **안쪽 GIL의
기록과 실제 Artifact 세계가 어긋난다.** 게다가 임의의 중첩 `.gil` 이 바깥 Snapshot에서 조용히
사라지는 **숨은 제외 영역**이 된다 — §3.6이 금지한 사용자 정의 ignore가 이름만 바꿔 생기는
셈이다.

**중첩 `.gil` 을 일반 Artifact로 추적하면** — 바깥 restore가 안쪽에 저장된 Journey revision ·
Done Will · Existence · Report · Graph · Snapshot metadata를 과거로 되돌린다. 이는 **World
restore가 Journey Timeline을 되돌리지 않는다**는 §9의 불변식을 정면으로 위반한다.

둘 다 안 되므로 **거절한다.** 정의되지 않은 경계 위에서 세계를 확정하지 않는다.

#### 이 규칙은 디렉터리에 관한 것이다

`.gil` 이라는 이름의 **일반 파일은 중첩 GIL 저장소가 아니다.** 일반 파일 규칙을 그대로 따라
manifest에 들어간다. `.gil` 이라는 이름의 심볼릭 링크는 심볼릭 링크 규칙으로 거절한다.

#### v0이 지원하지 않는 것

중첩 GIL 프로젝트는 v0의 지원 범위가 아니다. 다음은 전부 **후속 별도 모델**이다(§14).

```text
nested project 또는 subproject reference
안쪽 프로젝트 전체를 하나의 외부 경계로 취급
바깥 Graph가 안쪽의 특정 SnapshotRef를 참조
바깥 restore가 안쪽 Journey와 내부 저장소를 변경하지 않는 규칙
중첩 프로젝트 이동·삭제·복원 계약
```

### 3.5 대용량 파일

v0은 일반 파일에 **공개적인 크기 상한을 두지 않는다.**

- 대용량 파일도 다른 일반 파일과 **같은 Artifact**로 취급한다.
- 파일 전체를 한꺼번에 메모리에 적재하지 않는다.
- 일정 크기의 조각으로 **스트리밍하여** 관측·내용 주소 계산·저장한다.
- 읽기 실패·저장 공간 부족·내부 저장 실패 시 **전체 트랜잭션을 거절한다.**
- 논리 상태를 **부분적으로 확정하지 않는다.**

도중에 만들어진 미참조 내부 내용 객체는 남을 수 있다. 어떤 `SnapshotRef`도 그것을 가리키지
않는다면 **논리 World 상태의 일부가 아니며 손상이 아니다**(§10).

### 3.6 사용자 정의 제외 규칙은 아직 없다

`.gilignore`의 공개 계약과 사용자 정의 제외 규칙은 **만들지 않는다.** 실제 dogfooding에서
필요성이 확인된 뒤 별도로 결정한다. 그때까지 제외되는 것은 **프로젝트 루트의 `.gil/` 하나
뿐**이고, 제외 목록을 사용자가 늘릴 수 있는 문법을 노출하지 않는다. 더 깊은 곳의 `.gil` 은
제외 대상이 아니라 **거절 사유**다(§3.4) — 숨은 ignore 영역을 만들지 않기 위해서다.

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

### 4.1 최초 Snapshot의 참조는 뿌리 Cycle의 entry가 갖는다

**확정된 결정이다.** `Project` 뿌리에 별도의 `baseline_snapshot_ref`를 **중복 저장하지
않는다.** 최초 Snapshot은 Snapshot 저장소에 존재하고, **뿌리 Cycle의
`entry_snapshot_ref`가 그것을 가리킨다.**

```text
뿌리 Cycle
  entry_snapshot_ref: gil start가 확정한 최초 SnapshotRef
```

이유는 계층마다 규칙이 갈리지 않게 하려는 것이다. 뿌리에 별도 필드를 두면 뿌리 Cycle의
entry만 비어 있게 되고, 그것을 읽는 모든 자리가 "지금 뿌리인가?"를 되묻게 된다. 모든 Cycle이
같은 자리에 같은 종류의 값을 지니면 그 물음이 사라진다(§7.1).

---

## 5. Snapshot 확정 권한

Artifact 세계를 **새로 확정할 권한**은 다음 두 시점에만 있다.

```text
1. gil start의 최초 기준 세계 확정
2. 열린 Verify를 성공적으로 닫는 원자적 트랜잭션
```

Interview의 Question·Interpretation·Synthesis, Experiment의 Define·Hypothesis·Analysis,
두 Kind의 Outcome, 그리고 Cycle container close는 **Artifact 세계를 확정하지 않는다.**

### 권한이 있다고 반드시 새 객체가 나는 것은 아니다

확정 권한과 새 `SnapshotRef` 발급은 같은 말이 아니다.

```text
관측한 세계가 이미 있는 Snapshot과 같다   → 기존 SnapshotRef를 다시 가리킨다
관측한 세계가 처음 보는 것이다             → 새 SnapshotRef를 발급한다
```

「다시 가리킨다」는 **ID 재사용이 아니다.** 그 구분은 §13에 있다.

`SnapshotRef`는 **사건의 이름이 아니라 하나의 불변 Artifact 세계의 정체성**이기 때문이다
(§13). 아무것도 바꾸지 않은 Verify를 닫으면 새 이름이 나지 않고, 그 Verify가 기존 세계를
가리킨다.

`gil start`에서는 아직 Snapshot 저장소가 없으므로 관측한 최초 기준 세계에 **언제나 새
`SnapshotRef`를 발급한다.**

### "Verify를 성공적으로 닫는다"의 뜻

이것은 **Verify Report의 의미상 성공 판정을 뜻하지 않는다.** 필요한 Report가 유효하고, 저장
트랜잭션 전체가 성공하여 Verify Node가 정상적으로 닫힌다는 뜻이다.

> **Verify 자체에는 verdict가 없다.**

Verify는 관측하고 Analysis가 해석하며 Outcome이 판정한다(`GIL Specification v0.1` §11). 가설이
반증된 실험의 Artifact 상태도 그대로 Snapshot이 되며, 그 세계가 성공이었는지는 나중에 Outcome의
verdict가 말한다. 세계의 확정과 verdict 판정은 서로 독립적이다.

---

## 6. 변경 허용 경계

> **Artifact를 바꿀 수 있는 유일한 Step 경계는 Verify다.**

### 무엇을 "다르다"고 하는가

변경 판정은 **manifest 비교**다. 현재 관리 범위(§3)와 정규화 규칙으로 만든 Artifact
manifest를 기준 Snapshot의 manifest와 비교한다.

```text
manifest가 같다   → clean · 기준 SnapshotRef를 그대로 유지한다
manifest가 다르다 → dirty
```

여기서 **동일한 Artifact 세계**란 §3의 관리 범위와 정규화 규칙에 따라 만든 manifest가 같은
상태를 뜻한다. manifest는 정규화된 상대 경로와 파일 바이트만 담으므로(§3.1), mtime·소유자·
권한이 바뀌어도 dirty가 아니고, 빈 디렉터리를 만들거나 지워도 dirty가 아니다.

dirty인 세계를 실제로 확정할 수 있는 자리는 Verify close 하나뿐이다(§5·§7).

### 안정된 관측

Artifact를 읽는 동안 프로젝트가 변하여 **서로 다른 순간의 파일이 하나의 세계로 조용히
섞여서는 안 된다.** v0 관측 절차의 규범은 다음과 같다.

```text
1. 관리 대상 파일을 canonical 순서로 읽어
   후보 manifest와 내부 내용 객체를 준비한다.
2. 논리 상태를 확정하기 직전에 프로젝트를 다시 관측한다.
3. 재관측 결과가 후보 manifest와 같을 때만
   Snapshot 또는 clean 상태를 확정한다.
4. 다르면 「관측 중 Artifact 세계가 변경되었다」고 거절한다.
5. 읽는 동안 파일이 사라지거나 생기거나 읽기 오류가 나도 전체 관측을 거절한다.
```

거절할 때 **Step·Active Will·Journey revision·Done Will·Report·Graph·World Current 중 어떤
것도 부분적으로 바꾸지 않는다.**

#### GIL이 보장하지 않는 것

GIL은 외부 프로세스의 파일 쓰기를 **운영체제 수준에서 물리적으로 차단한다고 주장하지
않는다.** v0의 보장은 정확히 다음까지다.

> **Snapshot은 GIL이 관측하여 저장한 정확한 파일 경로와 바이트의 집합이다. GIL은 확정 직전
> 재관측으로 동시 변경을 검사하지만, 외부 프로세스의 쓰기를 물리적으로 금지하지 않는다.**

### Verify가 아닌 자리

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

## 7. Cycle의 Snapshot과 Verify close

### 7.1 모든 Cycle은 실재하는 Entry Snapshot을 지닌다

> **모든 Cycle은 생성과 동시에 반드시 실재하는 `entry_snapshot_ref`를 갖는다.
> `entry_snapshot_ref`는 그 Cycle을 연 전이가 출발한 Artifact 세계의 Snapshot을 가리킨다.**

Cycle을 여는 전이마다 그 값이 어디서 오는지가 다르다.

| Cycle을 연 전이 | `entry_snapshot_ref` |
|---|---|
| **뿌리** (`gil start`) | `gil start`가 확정한 최초 SnapshotRef |
| **`open_child`** | 부모 Cycle의 `exit_snapshot_ref` |
| **`revisit`** | **revisit 대상 Cycle의 `exit_snapshot_ref`** |
| **merge** (미래) | merge 규칙이 확정한 Snapshot — 아직 만들지 않았다 |

`open_child`는 부모 Cycle이 **닫혀 있고 실재하는 Exit Snapshot을 가질 때만** 열 수 있다.

#### Revisit 대상과 갈래의 출처는 같지 않다

```text
Cycle Graph의 구조적 parent       누구의 사고와 세계를 이어받았는가
revisit_from                     어느 실패가 이 새 갈래를 낳았는가
```

**이 둘을 같은 것으로 가정하지 않는다.** `revisit`으로 열린 Cycle의 구조적 parent는 revisit
대상 Cycle이고, Entry는 바로 그 대상 Cycle의 Exit Snapshot이다. `revisit_from`만 방금 버린
실패 Cycle을 가리키며 Lineage가 따라가는 parent edge가 아니다. Cycle-level revisit을 구현할
때 이 구조적 관계와 provenance가 함께 정확한 출발 세계와 갈래의 원인을 설명해야 한다.

이번 M3에서 Cycle-level revisit **실행**은 짓지 않는다. 다만 위 규칙이 그것을 막지 않는다 —
Entry는 「연 전이가 출발한 세계」로 정의되어 있으므로, M4는 표에 한 줄을 채우는 것이 아니라
**이미 있는 줄을 밟기만** 하면 된다. v0의 `open_child`와 `revisit`에서는 그 세계가 구조적
parent의 Exit과 일치하며, 미래 merge의 Entry는 별도 규칙이 정한다.

미래의 merge로 열린 Cycle의 Entry는 **별도의 merge 규칙이 확정한 Snapshot**을 쓴다. merge
규칙과 Artifact merge는 아직 만들지 않았고, **부모 Exit을 무조건 쓴다고 미리 고정하지
않는다**(§14).

### 7.2 Cycle의 Snapshot 필드

```text
열려 있는 동안
  entry_snapshot_ref: snapshot:A1
  exit_snapshot_ref:  null

닫힌 뒤
  entry_snapshot_ref: snapshot:A1
  exit_snapshot_ref:  snapshot:A2
```

불변식:

- 열린 Cycle과 닫힌 Cycle **모두** `entry_snapshot_ref`가 필수다.
- Cycle 생성 시 `entry_snapshot_ref`가 가리키는 Snapshot의 **실재를 검사한다.**
- 열린 Cycle의 `exit_snapshot_ref`는 `null`이다.
- 닫힌 Cycle의 `exit_snapshot_ref`는 필수다.
- 닫힌 Cycle을 복원할 때 Exit Snapshot의 **실재를 검사한다.**
- **Entry와 Exit이 같은 `SnapshotRef`를 가리킬 수 있다** — 그 Cycle이 세계를 바꾸지 않았다는
  뜻이며 정상이다(§13).
- Cycle close는 **새 Snapshot을 확정하지 않는다**(§5).
- Exit은 마지막 Outcome의 **구조적 lineage**에서 가장 가까운 Verify Snapshot을 쓴다(§7.5).
- 그 lineage에 Verify Snapshot이 없으면 **그 Cycle의 Entry Snapshot을 Exit으로 계승한다.**
- 버려진 가지나 이름이 가장 큰 Snapshot을 Exit으로 쓰지 않는다.

**`Project`에는 최초 기준 Snapshot을 위한 중복 필드를 두지 않는다**(§4).

### 7.3 Verify close

Verify close는 **하나의 원자적 동작**이다.

```text
1. Verify Report 검증
2. 현재 Artifact 상태 관측 — manifest 생성
3. 세계를 확정한다
     dirty  → 새 불변 Snapshot 객체와 새 SnapshotRef 발급
     clean  → 새 객체도 새 ID도 만들지 않고 기존 SnapshotRef를 쓴다
4. Verify Node에 snapshot_ref 기록
5. Active Will을 Done으로 이동
6. 새 Journey revision 생성
7. Verify Node 닫기
8. World Current Snapshot 갱신
```

이 중 **하나라도 실패하면 전체가 이전 상태로 남는다.** Will만 Done이 되거나, Snapshot을 가리키지
않는 Closed Verify가 생기거나, Report 없이 판이 오르는 중간 상태를 허용하지 않는다.

3번의 두 갈래가 §13의 결정이다. **아무것도 바꾸지 않은 Verify도 정상적으로 닫히며**, 그때
`snapshot_ref`는 기존 세계를 가리킨다 — Verify를 열었다는 사실만으로 새 세계가 나지 않는다.

`snapshot_ref`는 Report의 일부가 아니라 **Verify Node의 구조 필드**다. 다른 Closed Step은 이
값을 복제하지 않고 §7의 유도 규칙으로 찾는다.

### 7.4 다른 Step의 Artifact Version은 유도한다

```text
Verify Step        구조 필드 snapshot_ref를 직접 갖는다
그 밖의 Closed Step Lineage에서 가장 가까운 선행 Verify의 snapshot
선행 Verify가 없으면 그 Cycle의 Entry Snapshot
```

같은 세계를 여러 Step이 가리킬 수 있다. 변경이 없었다는 뜻이며, 그것을 이름의 중복 저장으로
표현하지 않는다.

### 7.5 Cycle Exit Snapshot

Cycle close는 새 Snapshot을 만들지 않는다.

> **닫히는 Cycle의 마지막 Outcome이 속한 구조적 lineage에서 가장 최근에 확정된 Verify
> Snapshot을 Cycle Exit Snapshot으로 기록한다.**

그 lineage에 Verify Snapshot이 하나도 없다면 그 Cycle의 **Entry Snapshot을 그대로 계승한다.**
Entry는 그 Cycle을 연 전이가 정한 값이며 생성 시점에 이미 실재가 검사됐다(§7.1). 따라서 Exit
Snapshot은 **어떤 경우에도 실재하는 Snapshot을 가리킨다** — Exit이 어디서 오는지 묻기 위해
부모나 뿌리를 다시 순회할 필요가 없다.

Artifact를 바꾸지 않는 Interview Cycle은 이 규칙에 따라 **Artifact 관점에서 투명하다.**

```text
Interview Entry: A2
Interview Exit:  A2
```

#### 무엇을 골라서는 안 되는가

- **버려진 가지의 Verify Snapshot을 고르지 않는다.** 되돌아감으로 버려진 형제 가지의 세계는
  이 Cycle이 도달한 세계가 아니다.
- **단순히 ID가 가장 큰 Snapshot을 고르지 않는다.** 이름의 크기는 순서의 근거가 아니다.

반드시 **닫히는 마지막 Outcome의 구조적 lineage**(`parent` 사슬)를 따른다. 이는 `basis_refs`와
`synthesis_ref`가 따르는 것과 같은 계보 규칙이다(`GIL Cycle Model v0.1` §16·§17).

---

### 7.6 World Current Snapshot — 유도값이다

**v0에서는 별도의 `world_current_snapshot_ref` 캐시 필드를 두지 않는다.** 확정된 결정이다.

World의 마지막 확정 Snapshot은 **현재 구조에서 유도한다.**

```text
현재 Step lineage에 닫힌 Verify Snapshot이 있다  → 가장 가까운 것
없다                                             → 현재 Cycle의 Entry Snapshot
닫힌 Cycle의 경계에 서 있다                      → 그 Cycle의 Exit Snapshot
```

§7.3의 8번("World Current Snapshot 갱신")은 별도의 저장 값을 새로 쓴다는 뜻이 아니라, 새
Verify snapshot이 확정되는 순간 **이 유도값이 그것을 가리키게 된다**는 뜻이다.

> **유도값을 별도 필드로 중복 저장하지 않는다.**

두 자리에 적으면 한쪽이 낡는다. 실제 dogfooding에서 **조회 비용이 문제가 될 때** 캐시를
검토한다 — 지금은 문제가 있다는 증거가 없다.

## 8. `gil restore`

용도는 하나다.

> **허용되지 않은 Artifact 변경 때문에 닫지 못하게 된 현재 Node를, 깨끗한 세계로 되돌린다.**

### 8.1 복원 목표는 유도한다 — 고르지 않는다

**v0의 `gil restore`에는 Snapshot 대상 인수를 두지 않는다.** 목표는 현재 위치의 구조적
lineage에서 **하나로 유도된다.**

```text
1. 현재 위치의 구조적 Step lineage에서 가장 가까운 닫힌 Verify의 snapshot_ref
2. 없으면 현재 Cycle의 entry_snapshot_ref
```

**두 줄이 전부다.** restore는 **부모 Cycle이나 `Project` 뿌리를 다시 순회해 최초 Snapshot을
찾지 않는다** — 현재 Cycle의 `entry_snapshot_ref`가 이미 완전한 출발 세계를 갖기 때문이다
(§7.1). 그것이 어느 전이에서 왔는지(뿌리·`open_child`·`revisit`)는 restore가 알 필요가 없다.

Cycle close 경계에서는 **마지막 Outcome의 구조적 lineage**를 현재 lineage로 쓴다.

이것은 §7.6의 World Current Snapshot과 같은 값이다. 유도 규칙이 하나이므로 두 자리가 갈리지
않는다.

다음은 복원 목표 선택에 **쓰지 않는다.**

- 버려진 가지
- 단순히 ID가 가장 큰 Snapshot
- 시간상 가장 최근에 생성된 Snapshot
- **사용자가 임의로 지정한 Snapshot**

열린 Verify가 아직 세계를 확정하지 않았다면, **그 Verify에서 생긴 변경도 직전 lineage 기준
Snapshot으로 되돌린다.** 아직 확정되지 않은 것은 돌아갈 자리가 아니기 때문이다.

### 8.2 무엇을 하는가

restore는 프로젝트의 관리 대상 Artifact 세계 **전체**를 목표 manifest와 정확히 같게 만든다.

| 상황 | 동작 |
|---|---|
| 대상과 현재에 모두 있고 내용이 다른 파일 | 대상 내용으로 **교체** |
| 대상에 있고 현재에 없는 파일 | **생성** |
| 현재에 있고 대상에 없는 일반 파일 | **삭제** |
| 내용이 같은 파일 | **변경하지 않는다** |
| 복원 결과 비게 된 디렉터리 | 제거할 수 있다 |
| `.gil/` | **절대 변경하지 않는다** |

### 8.3 무엇을 바꾸지 않는가

`gil restore` 자체는 다음을 **변경하지 않는다.**

```text
현재 Step
Active Will
Journey revision
Done Will
Existence
Knowledge · Memory · Relation
Step / Cycle Graph
이미 기록된 Report
기존 Snapshot 객체
```

> **restore는 행동 취소가 아니다.**

현재 Action Node와 Active Will은 **그대로 열린 상태로 남는다.** 사용자는 같은 행동을 다시
수행하거나 다른 접근을 거쳐 **정상적인 Report로 닫는다.** World의 Artifact만 과거 기준
상태로 다시 투영할 뿐, Journey Timeline은 되돌리지 않는다(§9).

### 8.4 원자성과 중단 복구

restore는 **원자적이어야 한다.**

#### 실행 전

```text
1. 현재 프로젝트를 완전히 관측한다.
2. 심볼릭 링크·특수 항목·표현할 수 없는 경로가 있으면
   아무것도 변경하지 않고 거절한다.
3. 목표 Snapshot의 manifest와 모든 내부 내용 객체가
   존재하고 읽을 수 있는지 확인한다.
4. 필요한 복원 내용과 rollback 자료를 .gil 내부 임시 영역에 준비한다.
5. 그 뒤에만 파일 교체·생성·삭제를 시작한다.
```

내부 구현은 다음 논리 단계를 따른다.

```text
preflight → prepare → apply → verify → commit → cleanup
                         │       │
                         └───────┴──→ 실패하면 rollback
```

- **복원 도중 오류가 나면 실행 전 Artifact 세계로 되돌린다.**
- **프로세스가 중단되면**, 다음 GIL 명령이 미완료 restore transaction을 감지하고 **실행 전
  상태로 복구한 뒤에만** 다른 동작을 허용한다.

#### transaction이 사는 자리

```text
.gil/restore/
  preparing-<pid>-<표>/   아직 rollback이 걸리지 않은 준비 중 자료
  active/                 rollback이 걸린 transaction
    PLAN                  무엇을 바꾸는가 (내부 이진 형식)
    backup/<서수>         되돌릴 원본들 — 이름이 불투명하다
    COMMITTED             forward가 성공으로 확정됐다는 표식
  cleanup-<pid>-<표>/     논리 결정이 끝나 지우기만 남은 잔해
```

프로젝트 잠금 덕분에 한 프로젝트에 `active`는 **최대 하나**다(§10.6). 이름과 배치를 아는
자리는 코드 한 곳이고, **사용자 입력을 내부 경로에 이어 붙이지 않는다.**

이 구조는 루트 `.gil/` 안이라 Artifact 관측에서 통째로 제외된다(§3.4).

#### 계획은 사람이 고칠 형식이 아니다

`PLAN`은 magic·version·big-endian 고정 폭의 **엄격한 내부 이진 형식**이다. manifest codec과
같은 규율을 쓴다(§10.5).

```text
Replace  경로 · 실행 전 내용 · 보관 서수 · 실행 전 권한 · 목표 내용
Delete   경로 · 실행 전 내용 · 보관 서수 · 실행 전 권한
Create   경로 · 목표 내용
```

- 경로는 검증된 정규화 경로다. `..`·절대경로는 **디코더가 거절한다** — 손상된 계획 파일
  하나가 프로젝트 밖을 지우지 못하게.
- 엄격한 오름차순, 중복 없음. **정렬해서 받아들이지 않는다.**
- 모르는 version·동작, 잘린 계획, 뒤에 남은 바이트는 전부 거절한다.
- 보관 이름은 **불투명한 서수**다. 사용자 경로를 내부 파일 이름으로 쓰지 않는다.

YAML로 적지 않은 까닭은 하나다: 이것은 **죽은 프로세스가 남긴 자료**이고, 반쯤 쓰인 것을
반쯤 읽으면 안 된다. 들여쓰기 하나가 다른 계획이 되면 그 계획이 남의 파일을 지운다.

#### 되돌릴 자료는 역사가 아니다

세계 전체를 복제하지 않는다. **실제로 덮어쓰거나 지울 현재 파일만** 보관한다.

```text
새 SnapshotRef 발급 없음
registry 추가 없음
지금의 dirty 세계를 자동 보존한 역사로 만들지 않음
```

확정되지 않은 세계에 이름을 주면, 사람이 확정한 적 없는 것이 시간선에 남는다.

#### 순서가 전부다

```text
preparing 만들기 → 원본 보관 → PLAN 쓰기 → 각각 fsync → 디렉터리 fsync
→ preparing을 active로 원자적 rename       ← 여기서부터 rollback이 걸린다
→ restore 폴더 fsync
```

`active`가 생기기 전에 중단되면 남는 것은 `preparing-*`뿐이고, 다음 명령이 그냥 치운다.
생긴 뒤에 중단되면 **반드시 rollback하거나 commit 상태를 처리한다.**

commit도 같다.

```text
COMMITTED 쓰기 → fsync → active fsync   ← 여기가 지나면 되돌리지 않는다
→ active를 cleanup-*로 rename → restore 폴더 fsync → 잔해 제거
```

**보관한 원본을 먼저 지우고 표식을 나중에 쓰지 않는다.** 그 사이에 죽으면 다음 명령이
「rollback해야 한다」고 판단하고도 되돌릴 자료가 없다.

성공한 restore 뒤에도 **`state.yaml`은 저장하지 않는다.**

#### 다음 명령의 복구

모든 프로젝트 상태 접근 명령은 다음 순서를 지킨다.

```text
잠금 → restore 복구 → artifact tmp 회수 → state load → 명령
```

| 남아 있는 것 | 무엇을 하는가 |
|---|---|
| `preparing-*` | 그냥 치운다 — rollback이 걸리기 전이다 |
| `active/`, `COMMITTED` 없음 | 계획과 보관 자료를 검증하고 **되돌린 뒤** 치운다 |
| `active/COMMITTED` | **되돌리지 않는다.** 잔해만 치운다 |
| `cleanup-*` | 이미 결정이 끝났다 — 치운다 |
| 그 밖의 이름·링크·특수 항목 | 조용히 지우지 않고 **거절한다** |

복구가 실패하면 **원래 명령을 실행하지 않는다.** 손상된 상태를 정상이라고 선언하지 않는다.

#### 파일을 놓는 방식

```text
목표 내용을 대상과 같은 폴더의 옆자리에 흘려 복사 — 복사하며 지문 재검증
→ flush + fsync → 필요한 권한 적용 → rename으로 교체 → 부모 디렉터리 fsync
```

**목표 blob과 hard link하지 않는다.** 작업 파일은 사람이 곧 고칠 파일이고, 그것이 immutable
blob과 inode를 나눠 쓰면 다음 편집이 **창고 안의 객체를 함께 고친다.** 그 순간 그 주소의
내용이 주소와 달라지고, 그 세계를 가리키는 모든 Snapshot이 거짓이 된다.

복원 결과 비게 된 폴더는 치운다. rollback은 **이번 적용이 실제로 만든 폴더만** 비었을 때
거둔다 — 원래 있던 빈 폴더까지 지우면 되돌린 것이 아니라 더 깎아 낸 것이다.

#### 외부 writer

프로젝트 잠금은 GIL 명령끼리의 협력적 잠금이라(§10.6) **편집기의 쓰기를 막지 않는다.**

- 파일을 건드리기 **직전에** 그 자리가 계획이 본 그대로인지 다시 묻는다.
- 다르면 앞으로 가지 않고 **실행 전 세계로 되돌린다.** 그 사이에 끼어든 편집도 함께
  사라진다 — 그것이 「실행 전 세계로 되돌린다」의 뜻이다.
- 적용을 마친 뒤에도 **결과를 다시 관측해** 목표와 견준다. 다르면 되돌린다.
- 외부 쓰기를 완전히 방지한다고 **주장하지 않는다.**

rollback 자체와 외부 writer가 계속 경쟁하면 안전한 완료를 보장할 수 없다. 그때는 다른 GIL
명령을 진행하지 않고 **recovery-required 오류를 유지한다.**

#### blob 전수 검증은 여기서 한다

`load`는 manifest까지만 본다(§10.9). 그 바이트를 실제로 쓰는 자리가 restore이므로, **파일을
하나도 건드리기 전에** 목표 manifest가 가리키는 모든 blob을 흘려 읽어 지문을 다시 잰다.
하나라도 없거나 손상됐으면 작업 폴더를 손대지 않고 멈춘다.

#### 내부 준비 영역은 staging이 아니다

이 준비 영역은 **공개 사용자 상태가 아니다.**

- 사용자가 포함할 파일을 고르지 않는다.
- 성공하면 사라진다.
- 실패·중단 시 rollback에만 쓴다.
- Report나 Graph가 참조하지 않는다.
- 공개 CLI에서 **staging·index·add·commit이라는 용어를 쓰지 않는다**(§14).

### 8.5 권한 처리

파일 권한은 Artifact 정체성에 포함하지 않는다(§3.1). 따라서 restore도 권한을 세계의 일부로
다루지 않는다.

- 기존 파일을 **내용만 교체**할 때 **기존 권한을 보존한다.**
- 대상에만 있어 새로 만드는 파일은 **안전한 시스템 기본 권한**을 적용한다.
- restore가 기존 권한을 Snapshot 값으로 바꾸지 않는다 — Snapshot에 그 값이 없다.
- 권한 때문에 읽기·교체·생성·삭제가 불가능하면 **전체 restore를 거절하고 rollback한다.**

플랫폼별 기본 권한의 구체 값은 **공개 Artifact 정체성의 일부가 아니다.**

### 8.6 멱등성과 receipt

> **`gil restore`는 멱등적이다.**

현재 Artifact 세계가 목표 Snapshot과 이미 같다면 **오류가 아니라 성공적인 no-op**이다.
사용자가 먼저 별도 상태 확인 명령을 실행할 필요가 없다.

clean 상태의 기본 receipt는 다음 의미를 전달한다.

```text
복원할 변경이 없다.
현재 Artifact 세계는 기준 Snapshot snapshot:A2 와 같다.
현재 Step과 Active Will은 그대로 유지된다.
```

실제로 복원했을 때 기본 receipt는 다음만 간결하게 보여 준다.

```text
목표 SnapshotRef
교체한 일반 파일 수
생성한 일반 파일 수
삭제한 일반 파일 수
유지된 현재 Cycle · Step · Active Will
```

**개별 파일 목록 전체는 기본 출력에 늘어놓지 않는다.** 상세 조회 기능은 실제 필요성이
확인된 뒤 별도로 결정한다(§12).

**raw manifest·blob 주소도 내보이지 않는다.** 공개 표면은 `snapshot:A*` 하나다(§13).

no-op은 아무것도 만들지 않는다 — transaction도, Artifact 객체도, `state.yaml` 저장도.
필요한 현재 항목이 없는 합법적 경계(열린 Step이 없는 Cycle 경계 등)라면 **없는 값을 지어내지
않고** 현재 Cycle만 표시한다.

복원 전에 현재 변경을 자동으로 보존하거나 새 Snapshot으로 만들지 않는다. 복원 receipt에서
**바뀐 항목 수와 복원 대상**을 명확히 보여 준다.

### 8.7 revisit과 다르다

`gil restore`는 **현재 자리의 세계**를 되돌리는 것이고, revisit은 **과거 Closed ancestor를
골라** 그 아래에서 새 가지를 열 준비를 하는 것이다. 대상이 실패 Cycle의 직접 부모일 때 그
새 가지가 형제가 된다. 둘을 한 명령으로 합치지 않는다.

restore가 목표를 인자로 받지 않는 것도 같은 이유다 — 과거의 다른 세계를 고르는 일은
revisit의 몫이며, 그것은 M4가 짓는다(§11).

### 8.8 실행 확인 — 명령 자체가 의사 표시다

**확정된 결정이다.** `gil restore`의 확인 절차는 더 이상 미결이 아니다.

> **`gil restore`는 명시적인 파괴적 명령이며, 그 명령을 실행하는 것 자체가 사용자 또는 실행
> 에이전트의 복원 의사다. v0에서는 추가 대화형 확인을 요구하지 않는다.**

따라서 v0에서는 다음을 **만들지 않는다.**

```text
대화형 yes/no 확인
--force
--yes
별도의 confirm 명령
restore 전에 반드시 실행해야 하는 status/check 명령
대상 Snapshot 인수
```

`--force`가 없는 것은 제약이 아니라 **필요가 없기 때문이다.** 강제할 대상이 없다 — 목표는
고를 수 없고(§8.1), 확인 관문도 없다.

#### 안전성은 어디서 오는가

추가 확인 문법이 아니라 **다음에서 온다.**

```text
목표 Snapshot의 구조적 유도            사용자가 엉뚱한 세계를 고를 수 없다   §8.1
실행 전 전체 검증                      되돌릴 수 없는 상태로 들어가지 않는다 §8.4
링크·특수 항목·읽기 실패 시 무변경 거절 반쯤 복원된 세계가 없다              §3.4
prepare → apply → finalize             중간 상태가 논리 상태가 아니다        §8.4
실패 시 rollback                       실행 전 세계로 돌아간다               §8.4
중단 시 다음 GIL 명령에서 복구         다음 명령이 먼저 치운다               §8.4
Journey · Graph · Will 불변            사고의 기록은 무엇을 해도 안 지워진다 §8.3
```

clean 상태에서는 **성공적인 no-op으로 끝난다**(§8.6). 그러므로 "혹시 몰라 먼저 확인"할 이유가
없고, 그 확인 명령을 강제하지도 않는다.

비대화식 에이전트는 `gil restore`를 **그냥 부른다.** 물어볼 것이 없으므로 답할 것도 없다.

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
  손상되지 않는다. 참조되지 않은 Snapshot은 잘못이 아니다. 대용량 파일을 스트리밍하다 만든
  미참조 내용 객체도 마찬가지다(§3.5).
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

### `gil restore`는 ②를 열지 않는다

restore는 논리 상태를 바꾸지 않으므로(§8.3) `state.yaml`을 교체하지 않는다. 대신 **작업
폴더 자체를 원자적으로 바꾸는 세 번째 경계**를 쓴다.

```text
③ 작업 폴더   prepare → apply → finalize (§8.4)
              중단되면 다음 명령이 실행 전 상태로 복구한 뒤에만 진행한다
```

미완료 restore transaction의 흔적은 `.gil` 내부 임시 영역에 남으며, 그것을 감지하고 되돌리는
것이 다음 명령의 첫 일이다. **①·②·③은 서로 다른 자원을 다루므로 충돌하지 않는다.**

### Cycle-level revisit은 ②를 먼저 확정하고 ③을 수렴시킨다

Cycle-level revisit은 논리 상태와 작업 폴더를 함께 옮기는 첫 동작이다. 이때도 Snapshot
저장소에는 쓰지 않는다. revisit은 세계를 새로 확정하지 않고 이미 실재하는 대상 Cycle의 Exit
Snapshot을 선택하기 때문이다.

```text
1. 현재 세계가 clean인지 검사한다.
2. 대상이 실재하는 Closed ancestor이며 새 자식을 가질 수 있는지 검사한다.
3. current = 대상 ancestor와 pending_cycle_revisit = 실패 Cycle을
   한 번의 state 교체로 확정한다.                                      (②)
4. 기존 restore transaction으로 작업 폴더를 대상 ancestor의 Exit에 수렴시킨다. (③)
```

**②가 ③보다 먼저다.** 작업 폴더는 논리 상태에서 유도되는 투영이기 때문이다.

- ② 이전에 실패하면 아무 변화도 남지 않는다.
- ② 뒤 ③ 이전에 중단되면 논리 상태는 이미 대상 ancestor를 가리키고 작업 폴더만 dirty다.
- 다음 `gil restore`는 그 논리 상태에서 같은 대상 Exit을 유도하여 작업 폴더를 수렴시킨다.
- ③ 도중 중단되면 §8.4의 기존 restore rollback과 recovery 계약을 그대로 따른다.

이 계약은 ②와 ③이 한 번에 커밋된다고 과장하지 않는다. 보장하는 것은 어느 중단점에서도
논리적으로 정해진 세계가 하나이며, 기존의 멱등 명령으로 그 세계에 수렴한다는 것이다. 별도의
Snapshot, restore plan 형식, Journey rollback을 만들지 않는다.

---

## 10.5 내부 객체 저장소

> **이 절은 구현이 어떻게 담는가를 말한다. 공개 계약은 여전히 `snapshot:A1` 하나다.**

### 세 층

```text
SnapshotRef  →  manifest      snapshot:A1 이 한 세계를 가리킨다   (Snapshot registry)
manifest     →  blob 목록     그 세계의 경로와 내용 목록
blob         →  바이트        일반 파일의 실제 바이트 그대로
```

위 두 층은 **`state.yaml` 의 논리 상태**에 속하고, 아래 두 층은 `.gil/` 안의
**content-addressed 창고**에 산다. 창고의 주소는 내용에서 나오므로 이름을 발급하지 않는다.

### canonical manifest

manifest 는 사람이 손으로 고치는 문서가 아니라 **내용이 주소를 정하는 내부 객체**다. YAML·
JSON 으로 적으면 공백·따옴표·key 순서가 주소를 바꾸고, 그러면 같은 세계에 두 주소가 생겨
§13의 「이름이 같으면 세계가 같다」가 무너진다. 그래서 엄격한 이진 형식을 쓴다.

```text
── 머리 (21 바이트) ────────────────────────────────
magic             8 bytes   "GILMANIF" (ASCII)
format_version    4 bytes   big-endian u32 = 1
digest_algorithm  1 byte    1 = SHA-256
entry_count       8 bytes   big-endian u64

── 항목 (entry_count 번) ───────────────────────────
path_length       4 bytes   big-endian u32 (1..=4096)
path              path_length bytes  canonical UTF-8
content_digest    32 bytes  SHA-256 raw
```

- 정수는 전부 **big-endian 고정 폭**이다. 플랫폼의 native endian 이나 `usize` 폭에 기대지
  않는다 — 같은 세계는 어느 기계에서 적어도 같은 바이트가 되어야 한다.
- 항목은 §3.3의 canonical 경로 바이트 순서로 **엄격히 오름차순**이다. 중복 경로는 없다.
- **알고리즘은 머리에 한 번만 적는다.** 한 manifest 안의 모든 항목이 그 하나를 따르고,
  항목마다 태그를 되풀이하지 않는다.
- 비canonical 입력은 **정렬해서 받아들이지 않고 거절한다.**

### 내부 주소와 공개 참조는 다르다

```text
blob 주소       SHA-256(원본 파일 바이트)
manifest 주소   SHA-256(canonical manifest 바이트)
공개 참조       snapshot:A1     ← 사람과 Report 가 보는 유일한 이름
```

내부 주소는 §13이 말한 그대로 **공개 `SnapshotRef` 가 아니다.** 저장 엔진을 바꿔도 공개
참조는 바뀌지 않는다.

### append-only 와 손상 검증

객체를 확정하는 길은 **하나**다. blob 이든 manifest 든 같은 절차를 지난다.

```text
1. tmp/ 에 전체를 흘려 쓴다          아직 주소가 없다
2. flush + fsync                     내용을 파일 시스템에 밀어 넣는다
3. 지문으로 최종 주소를 정한다
4. 그 자리의 부모 디렉터리를 만든다
5. tmp → 최종 주소로 **hard link**    이미 있으면 실패한다
6. 임시 이름을 걷고 부모를 fsync      이름이 디스크에 새겨진다
7. 최종 객체를 **다시 열어** 지문을 잰다
```

- **덮어쓸 수 있는 방식으로 확정하지 않는다.** `rename` 은 최종 경로가 이미 있으면 말없이
  갈아 끼운다. 두 프로세스가 같은 주소를 동시에 확정하면 먼저 놓인 append-only 객체가
  사라진다. 내용이 같을 것으로 기대되더라도 **덮어쓰는 동작 자체**가 append-only 를 어긴다.
  `hard_link` 는 최종 경로가 이미 있으면 실패하므로, 기존 객체를 건드릴 길이 원천적으로 없다.
- **이미 있으면 그것을 확인만 한다.** 내용이 주소와 같으면 그 객체를 공유하고, 다르면 손상으로
  거절한다 — 어느 쪽이든 기존 파일을 건드리지 않는다.
- **fallback 을 두지 않는다.** hard link 를 걸 수 없는 파일 시스템에서는 보장을 약화하며
  이어가지 않고 거절한다. `.gil` 을 그런 자리에 두었다는 사실 자체를 사람에게 말한다.
- **「썼으니 있다」를 믿지 않는다.** 흘려 쓰며 잰 지문은 *읽어들인* 바이트의 것이지 디스크에
  실제로 앉은 바이트의 것이 아니다. 확정 직후 최종 객체를 다시 열어 지문을 재고, 갈리면
  손상으로 거절한다.
- 읽을 때도 **저장 경로만 믿지 않는다.** 바이트를 흘리며 지문을 다시 재고 주소와 다르면
  손상으로 거절한다.
- **어떤 손상도 조용히 넘기거나 새 객체로 덮어써 고치지 않는다.** 고쳐진 창고는 무엇이
  진짜였는지 더는 말하지 못한다.
- 실패한 확정은 **제가 만든 임시 이름을 제 손으로 걷는다.** 남기면 다음 사람이 그것을 미완의
  객체로 오해한다. 다만 **프로세스가 죽어 남은 임시 파일을 거두는 일**은 아직 정하지 않았다(§12).

### 객체 내구성이 상태 내구성보다 먼저다

`state.yaml`이 객체를 가리키기 **전에** 다음이 전부 끝나 있어야 한다.

```text
필요한 blob 전부 publish + 재검증
→ manifest publish + 재검증
→ 객체 부모 디렉터리 동기화(지원 플랫폼)
→ state temp 작성 → flush → sync_all
→ state.yaml 로 원자적 교체
→ .gil 디렉터리 동기화(지원 플랫폼)
```

전 구간 동안 프로젝트 잠금을 쥔다(§10.6). 순서가 뒤집히면 `state.yaml`이 **아직 없는
객체**를 가리키는 순간이 생기고, 그때 전원이 끊기면 되살릴 수 없는 상태가 남는다.

거꾸로는 괜찮다. 객체를 눕힌 뒤 도메인이나 저장이 실패하면 그 객체는 **미참조로 남을 수
있지만**, 논리 상태의 부분 변경은 남지 않는다(§3.5).

### 이 내구성 보장의 실제 범위

여기서 주장하는 것은 **파일 시스템 계층까지의 내구성**이며, 전원 차단 복구가 완전하다는
주장이 아니다.

- 부모 디렉터리 `fsync` 는 Unix 에서만 한다. 그 밖의 플랫폼에서는 표준 라이브러리로 안전하게
  할 방법이 없어 하지 않는다.
- macOS 의 `fsync` 는 드라이브의 쓰기 캐시까지 비우지 않는다(`F_FULLFSYNC` 가 그 일을 한다).
- **동시 쓰기 잠금은 여기에 없다.** hard link 가 지키는 것은 「객체를 덮어쓰지 않는다」 하나다.
  `state.yaml` 의 논리 상태를 두 프로세스가 동시에 바꾸는 문제는 별개이며, **프로젝트 단위
  트랜잭션 잠금**이 진다(§10.6).

### 같은 내용은 한 blob 을 나눠 쓴다

파일 단위 content addressing 이므로, 경로가 다르고 Cycle 이 달라도 **바이트가 같으면 blob 은
하나**다. 세계가 늘어도 바뀌지 않은 파일은 다시 담기지 않는다.

**부분적으로만 비슷한 큰 파일**은 아직 통째로 다시 담긴다. delta·chunk 단위 중복 제거는
**후속 최적화**이며 필요성이 확인된 뒤에 한다(§14).

### 미참조 객체는 손상이 아니다

두 번째 관측이 달라 세계가 확정되지 않으면, 첫 관측이 담은 blob 들은 아무 `SnapshotRef` 도
가리키지 않는 채 남는다. **그것은 논리 손상이 아니다** — 논리 World 상태는 `state.yaml` 이
지고, 창고는 그것이 가리킬 때만 뜻을 갖는다(§3.5·§10).

거꾸로는 허용하지 않는다. `state.yaml` 이 실재하지 않는 객체를 가리키는 상태는 손상이다.

## 10.6 프로젝트 트랜잭션 잠금

> **한 GIL 프로젝트에서는 한 번에 하나의 GIL 명령만 프로젝트 상태를 읽거나 바꾼다.**

### 왜 필요한가

`state.yaml`은 논리 상태 전부를 한 파일에 담고 통째로 쓴다(§10). 두 명령이 겹치면 나중에
쓴 쪽이 앞선 쪽의 변경을 조용히 덮는다.

```text
A: state 읽기 ─── Graph 변경 ──── state 쓰기
B:      state 읽기 ─── Journey 변경 ──── state 쓰기   ← A 의 변경이 사라진다
```

- 두 writer의 lost update
- 같은 `next_snapshot_id`를 읽어 **같은 이름을 서로 다른 세계에 발급**(§13이 무너진다)
- Graph·Journey·Will 중 한쪽 변경만 남는 상태
- 아직 끝나지 않은 restore recovery의 중간 상태를 읽기 명령이 관측하는 것

### v0의 규칙

- 프로젝트 상태에 접근하는 **모든** 명령이 **같은 exclusive lock**을 짧게 쓴다.
- shared read lock을 두지 않는다. `status`·`story`·`context`도 같은 잠금을 쓴다 —
  두 문법과 플랫폼 차이를 피하고, 향후 restore recovery가 먼저 실행될 자리를 확보한다.
- 읽기 명령은 잠금을 쥐었다는 이유로 어떤 상태도 저장하지 않는다.

### 잠금의 자리와 방식

```text
.gil/project.lock       현재 프로젝트 루트의 내부 저장소 안
```

**파일의 존재는 잠금 상태가 아니다.** 파일은 계속 남아 있고, 남아 있다는 사실은 아무것도
뜻하지 않는다. 실제 잠금은 그 파일에 건 **운영체제의 advisory file lock**이 진다.

```text
파일이 있다      지난 명령이 남긴 자리일 뿐이다
lock 이 걸렸다   지금 다른 GIL 명령이 이 프로젝트 안에 있다
```

그래서:

- 프로세스가 비정상 종료해도 **운영체제가 푼다**. 사람이 stale lock을 지울 일이 없다.
- PID 파일의 존재로 살아 있는지 추측하지 않는다.
- `create_new` sentinel도, lock 디렉터리 polling도 쓰지 않는다 — 둘 다 그 추측을 되살린다.
- 정상 코드가 잠금 파일을 매번 만들고 지우며 경쟁하지 않는다.

### 획득은 상태를 읽기보다 먼저다

```text
프로젝트 루트와 루트 .gil 위치 결정
→ 잠금 획득                       ← 여기서 실패하면 아무것도 읽지 않았다
→ state.yaml 읽기 · 복원 · 검증
→ 명령 수행
→ 필요한 객체 저장
→ state.yaml 저장
→ guard 해제
```

읽고 나서 잠그면 그 사이에 다른 명령이 끝나 버려 **이미 낡은 상태를 쥔 채** 잠금을 얻는다.
그것은 잠그지 않은 것과 같다.

guard는 RAII다. 정상 반환·오류 반환·panic unwind 어느 길로 나가든 풀리고, 프로세스가
죽으면 운영체제가 푼다. 잠금이 걸린 **열린 파일 handle의 수명과 guard의 수명이 같다.**

**같은 프로세스가 잠금을 두 번 잡지 않는다.** 명령 경계에서 한 번 잡고 안쪽 작업에는 잡은
것을 넘긴다. 두 번 잡으면 제 발에 걸려 스스로를 「다른 명령이 쓰고 있다」로 거절한다.

### 경쟁하면 기다리지 않는다

non-blocking으로 시도하고, 이미 다른 GIL 명령이 쥐고 있으면 **즉시** 거절한다.

```text
다른 GIL 명령이 이 프로젝트를 사용하고 있다.

현재 상태를 읽거나 변경하지 않았다.
앞선 명령이 끝난 뒤 다시 시도한다.
```

- 상태를 읽기 **전에**, Artifact 객체를 만들기 **전에** 실패한다.
- `state.yaml`도 프로젝트 파일도 바뀌지 않는다.
- 무기한 sleep도 busy polling도 없다. 자동으로 잠금을 빼앗거나 상대를 종료하지 않는다.
- 진짜 경쟁과 「이 자리에서는 잠글 수 없다」를 **구분해** 말한다 — 사람이 할 일이 다르다.

timeout·retry 횟수·wait 옵션은 v0에 없다.

### `gil start` bootstrap

`.gil/`이 아직 없을 수 있다. 그래서 **만들고 잠근 다음에** 무엇이 있는지 본다.

```text
프로젝트 루트 결정
→ 루트 .gil 디렉터리 준비
→ .gil/project.lock 열고 잠금 획득
→ 잠금 안에서 기존 state/legacy/미지 파일 재검사
→ 최초 초기화
```

잠그기 전에 보면 두 `gil start`가 나란히 「비어 있다」를 읽고 각자 다른 최초 상태를 세운다.

이 때문에 **`.gil/`은 있는데 `state.yaml`은 없는 상태**가 생긴다. 그것을 둘로 가른다.

| `.gil/` 안에 있는 것 | `gil start` |
|---|---|
| `project.lock` | 다시 시도할 수 있다 |
| 아직 아무 논리 상태도 참조하지 않는 `artifacts/`(`tmp`·미참조 blob·manifest 포함) | 다시 시도할 수 있다 |
| 유효한 `state.yaml` | 거절 — 이미 걷고 있다 |
| legacy `walk.yaml` | 거절 — 앞 형식이다 |
| 그 밖의 아무 파일·디렉터리 | 거절 — GIL이 모르는 것을 덮어쓰지 않는다 |

초기화에 실패해 `.gil/project.lock` 하나가 남는 것은 **손상이 아니다.** 파일의 존재는
초기화 완료도 잠금 보유도 뜻하지 않는다.

Artifact 관측기는 루트 `.gil/`을 통째로 제외하므로(§3.4) bootstrap 잠금 파일은 최초
Snapshot에 들어가지 않는다. 잠금 파일의 OS metadata 변화도 마찬가지로 세계 밖이다.

두 프로세스가 동시에 `gil start`하면 하나만 잠금을 얻어 초기화하고, 다른 하나는 경쟁
오류를 받는다. **둘이 각각 다른 최초 상태를 저장하는 일은 없다.**

### 이 잠금이 막지 못하는 것

**GIL 명령끼리의 협력적 잠금이다.** 다음은 막지 않으며, 막는다고 주장하지 않는다.

- 편집기·`rm`·다른 프로그램이 `.gil`을 직접 고치는 것
- 라이브러리의 저층 `load`/`save`를 잠금 없이 직접 부르는 외부 코드
- advisory lock을 제대로 구현하지 않는 네트워크 파일 시스템(NFS·SMB 등)

CLI의 모든 상태 접근 경로는 이 잠금을 지나므로 **GIL 명령끼리는** 직렬화된다. 그 밖의
사용까지 안전하다고 말하지 않는다.

### format 4의 전제

Snapshot registry를 `state.yaml`에 결합하려면(M3-B2b) `next_snapshot_id` 발급이 직렬화되어
있어야 한다. 두 명령이 같은 `next_id`를 읽으면 같은 이름을 서로 다른 세계에 주고, 그러면
§13의 「이름이 같으면 세계가 같다」가 무너진다. **그래서 잠금이 format 4보다 먼저다.**

## 10.7 format 4의 저장 구조

> **format 4의 유효 상태는 처음부터 완전하다.** 「나중에 채울 null」을 두지 않는다.

### `state.yaml`이 담는 것

```yaml
format: 4
next_will_id: 1
current_existence_ref: existence:X1
existences: { … }
existence_states: { … }
artifacts:
  next_snapshot_id: 3
  snapshots:
    - id: A1                    # 제 이름은 bare
      manifest:
        algorithm: sha256
        digest: ad8c0134…       # 소문자 canonical hex, 64자
    - id: A2
      manifest:
        algorithm: sha256
        digest: 5891b5b5…
cycles:
  nodes:
    - id: 1
      entry_snapshot_ref: snapshot:A1     # 가리키는 자리는 typed
      exit_snapshot_ref: snapshot:A2      # 열려 있으면 null
      steps:
        nodes:
          - id: 3
            kind: verify
            snapshot_ref: snapshot:A2     # 닫힌 Verify에만 있다
```

- **실제 파일 목록도 blob도 `state.yaml`에 없다.** 여기 눕는 것은 이름과 manifest 주소뿐이고,
  그 아래 두 층은 `.gil/artifacts/`의 content-addressed 창고가 진다(§10.5).
- `next_snapshot_id`는 `next_will_id`와 같은 관례 — 마지막으로 발급한 것 다음이다.
- `snapshot_ref`는 값이 없으면 **키 자체를 적지 않는다.** Verify가 아닌 Step에 `null`을
  적어 두지 않는다는 뜻이다.

### 유효한 format 4가 언제나 만족하는 것

| | |
|---|---|
| registry | 존재한다 · 모든 ID가 유일 · `A0` 없음 · 오름차순 · 빈틈 없음 · `next_id` = 마지막+1 |
| manifest | 모든 record가 실재하고 검증되는 manifest를 가리킨다 |
| 한 세계 한 이름 | 서로 다른 ID가 같은 manifest를 가리키지 않는다 |
| Cycle Entry | 모든 Cycle에 있다 |
| Cycle Exit | 열린 Cycle에 없다 · 닫힌 Cycle에 있다 |
| Verify | 닫힌 Verify에 있다 · 열린 Verify에 없다 |
| 그 밖의 Step | 없다 |
| 구조적 참조 | 전부 registry에 있다 |
| 뿌리 | Entry = `gil start`의 최초 Snapshot |
| 자식 | Entry = 부모의 Exit |

Snapshot record는 **삭제·수정·재할당하지 않는다.**

### format 3은 변환하지 않는다

기존 format 3 파일은 **그대로 보존하고 읽지 않는다.** 앞 형식임을 말하고 거절할 뿐,
수정하지도 삭제하지도 않는다. 자동 migration은 만들지 않았다 — format 3에는 관측된 세계가
없어서 `entry_snapshot_ref`를 채울 근거가 없고, 지어내면 그것은 **일어나지 않은 관측**이다.

새 format 4로 시작하려면 새 프로젝트에서 `gil start`한다.

## 10.8 `tmp/` 회수

프로젝트 잠금을 잡은 **직후, 상태를 읽기 전에** `.gil/artifacts/tmp/`를 본다.

```text
<pid>-<표> 인 일반 파일   지운다
그 밖의 이름              거절한다 — 명령이 진행되지 않는다
디렉터리·심볼릭 링크      거절한다
tmp 가 없다               정상이다
```

- **모르는 것을 지우지 않는다.** 이름 규칙은 임시 파일을 만드는 자리와 거두는 자리가
  **같은 함수 하나**를 쓴다 — 각자 적으면 언젠가 갈리고, 그러면 남의 파일을 지운다.
- 심볼릭 링크는 따라가지 않고(`symlink_metadata`) 거절한다. 따라가면 링크가 가리키는 것을
  보고 「일반 파일」이라 답하고, 링크를 지우며 남의 파일을 지웠다고 믿게 된다.
- 삭제에 실패하면 상태를 읽지 않고 멈춘다.
- **잠금 안에서만 한다.** 잠금을 쥔 명령은 한 번에 하나이므로(§10.6), 살아 있는 다른 GIL
  프로세스의 임시 파일을 지울 수 없다.

읽기 명령도 잠금을 잡은 뒤 이 회수를 수행한다. 미참조 내부 transaction 잔해를 거두는 것은
World·Journey·Graph의 변경이 아니다.

### 창고 최상위 구조

`gil start`를 다시 시도할 때 `.gil/artifacts/` 최상위에 있어도 되는 이름은 셋뿐이다.

```text
blobs · manifests · tmp
```

그 밖의 이름은 **조용히 무시하지도, 삭제하지도 않고 거절한다.** 유효한 미참조 blob·manifest는
허용한다 — 중단된 확정의 흔적이지 손상이 아니다(§3.5).

정상 명령마다 창고 전체를 순회하지 않는다. 참조된 객체만 필요한 시점에 검증한다.

## 10.9 load 검증의 해상도

```text
① registry 구조     A0 · 중복 ID · 한 세계 두 이름 · 순서 · 빈틈 · next_id · 알고리즘 · hex
② manifest 객체     실재 · 주소와 bytes 일치 · canonical decoder 통과
③ Graph 참조        Entry/Exit/Verify 의 유무와 registry 등재 · 자식 Entry = 부모 Exit
```

순서가 ①②③이다. 구조가 깨진 registry를 들고 디스크를 뒤지는 것은 잘못된 자리를 열어 보는
일이다.

**매 load마다 blob을 전수 해시하지 않는다.** manifest 하나를 읽는 비용은 세계의 크기에
비례하지만, blob 전수 해시는 프로젝트 전체를 다시 읽는 일이다. `gil status` 한 번이 그것을
하면 도구를 못 쓴다.

그래서 format 4 load가 보장하는 것은 **「세계의 목록이 온전하다」까지**다. blob 하나가 밖에서
손상된 것을 `status`가 반드시 발견한다고 **주장하지 않는다**(§14). 그것은 실제로 그 바이트를
쓰는 자리에서 걸린다 — capture가 기존 blob을 공유할 때, 그리고 훗날 restore 직전에.
`gil fsck`는 아직 없다.

손상된 참조를 **이름 순서나 지금 위치로 추측해 복구하지 않는다.**

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
| `revisit` | Cycle Report | **1** |
| `close_chain` | Cycle Report | **3** |

Experiment Cycle의 failure Report에 적는 `revisit`은 **유효한 다음 방향으로 정상 기록되고
실행할 수 있다.** `gil revisit`이 Report의 target을 읽어 논리 상태를 먼저 옮기고, 기존 restore
transaction으로 대상 Cycle의 Exit 세계를 복원한다. 다음 `gil open <kind>`가 새 Cycle을 연다.

> **사용자와 에이전트에게 `revisit`이 잘못된 값이라고 말해서는 안 된다.**

`GIL Agent UX Model v0.1` §4.2의 허용값 설명도 이 실행 가능성을 그대로 전달한다.

---

## 12. 아직 결정하지 않은 것

- `.gilignore`의 공개 계약과 사용자 정의 제외 규칙(§3.6)
- **merge로 열린 Cycle의 Entry Snapshot 규칙**(§7.1) — merge 자체가 M8이다
- 복원한 개별 파일 목록을 보여 주는 상세 조회 기능(§8.6)
- rollback과 외부 writer가 계속 경쟁할 때의 종결 전략 — 지금은 recovery-required를 유지한다(§8.4)
- 대용량 파일을 읽는 조각 크기 — 공개 계약이 아니라 구현 선택(§3.5)
- 미참조 내부 객체를 언제 어떻게 거둘 것인가 (prune은 v0 범위 밖 §14)

### 해결된 것

- **Snapshot 객체의 내부 schema와 저장 엔진** — format 4의 `SnapshotRegistry`, canonical
  binary manifest와 SHA-256 내용 주소 객체 저장소를 쓴다(§10.5·§10.7). 공개
  `SnapshotRef`와 내부 주소는 분리한다.

- **프로세스가 죽어 `tmp/`에 남은 임시 파일을 언제 거둘 것인가** — 프로젝트 잠금을 잡은
  직후, 상태를 읽기 전에 거둔다. GIL이 만든 이름의 일반 파일만 지우고, 모르는 것은
  거절한다(§10.8).
- **두 프로세스가 같은 프로젝트의 논리 상태를 동시에 바꿀 때** — 프로젝트 단위 exclusive
  advisory lock으로 직렬화한다. 상태를 읽기 전에 잡고, 경쟁하면 기다리지 않고 즉시
  거절한다(§10.6).
- **객체를 어떻게 확정하는가** — 임시 자리에 흘려 쓴 뒤 **hard link** 로 건다. `rename` 으로
  물러서는 fallback을 두지 않는다. 확정 직후 다시 열어 지문을 재검증한다(§10.5).
- **동일 내용일 때 이름을 재사용할 것인가** — 재사용한다. `SnapshotRef`는 사건의 이름이
  아니라 세계의 정체성이다(§13).
- **심볼릭 링크** — 따라가지도 저장하지도 않고, 있으면 전체 관측을 거절한다(§3.4).
- **파일 권한과 mode bit** — Artifact 정체성에 넣지 않는다. 교체 시 기존 권한을 보존하고,
  새로 만드는 파일은 시스템 기본 권한을 쓴다(§3.1·§8.5).
- **대용량 파일 상한** — 두지 않는다. 스트리밍으로 관측하고 실패하면 전체를 거절한다(§3.5).
- **빈 디렉터리** — 세계에 포함하지 않는다. 만들거나 지워도 dirty가 아니다(§3.4).
- **manifest의 정규화 규칙** — 경로만 정규화하고 내용은 바이트 그대로. 정렬은 경로의 UTF-8
  바이트 오름차순 하나뿐이다(§3.2·§3.3).
- **restore 목표를 사용자가 고르는가** — 고르지 않는다. lineage에서 유도한다(§8.1).
- **최초 기준 Snapshot 참조의 저장 위치** — 뿌리 Cycle의 `entry_snapshot_ref`가 갖는다.
  `Project` 뿌리에 중복 필드를 두지 않는다(§4·§7.1).
- **World Current Snapshot을 캐시할 것인가** — v0은 **유도**한다. 캐시 필드를 두지 않고,
  조회 비용이 실제 문제가 될 때 검토한다(§7.6).
- **`gil restore`의 확인 절차와 비대화식 사용법** — 명령 실행 자체가 의사 표시다. 대화형
  확인도 `--force`도 만들지 않는다(§8.8).

---

## 13. `SnapshotRef`는 세계의 정체성이다

> **`SnapshotRef`는 사건의 이름이 아니라, 프로젝트 안에서 하나의 불변 Artifact 세계를
> 가리키는 정체성이다.**

이 절은 **확정된 결정**이다.

### 공개 참조

```text
snapshot:A1     공개 참조. 기존 typed reference 문법 그대로다.
A*              프로젝트 로컬 순차 ID.
```

- **같은 Artifact 세계에는 기존 `SnapshotRef`를 재사용한다.**
- **새로운 세계가 처음 관측될 때만** 새 `SnapshotRef`를 발급한다.
- 여기서 "같은 세계"는 §6이 정의한 **manifest가 같은 상태**다.

### 순차 ID 재사용 금지 규칙과 충돌하지 않는다

`GIL Node Model v0.1` §2.1은 *"모든 영구 ID는 같은 종류 안에서 유일하고 재사용하지 않는다"*
고 정한다. 이 결정은 그 규칙을 **어기지 않는다.**

```text
금지되는 것   A1 이 가리키던 객체가 사라지고, 다른 객체가 다시 A1 을 받는 것
              → ID 재발급 · 다른 객체에 대한 ID 재사용
이 결정       A1 이 가리키는 불변 객체는 하나뿐이고 영원히 그것이다.
              여러 Node가 그 하나를 함께 가리킨다
              → 객체 공유이지 ID 재사용이 아니다
```

`A1`은 언제나 정확히 하나의 세계를 뜻한다. 그 뜻이 옮겨 간 적이 없으므로 §2.1의
「유일하고 재사용하지 않는다」는 그대로 성립한다.

같은 원리가 다른 종류에도 이미 있다. `existence:X1`은 수많은 Node가 함께 가리키지만 X1이
둘이 되지는 않는다. Snapshot도 같다 — **참조가 여럿인 것과 ID가 재사용되는 것은 다르다.**

### 여러 Step이 같은 Version을 가리킨다

`GIL Time Model v0.2` §8의 다음 문장이 이 결정의 다른 쪽 면이다.

> *"변경이 없으면 여러 Step이 같은 Version을 가리킬 수 있다."*

```text
#1 artifact = A0
#2 artifact = A0
#3 artifact = A1
#4 artifact = A1
```

Time Model은 이것을 **유도의 결과**로 말했다(비-Verify Step은 선행 Verify의 snapshot을
가리킨다). 이 결정은 거기에 하나를 더한다 — **Verify끼리도** 세계가 같으면 같은 이름을
가리킨다. 두 규칙이 만나면 다음 성질이 나온다.

> **이름이 바뀌었다는 것은 세계가 바뀌었다는 뜻이다.**

`snapshot_ref`만 비교해도 "이 Verify가 세계를 바꿨는가"에 답할 수 있다. 내용을 다시 열어
보지 않아도 된다.

### 공개 참조와 내부 내용 주소는 다르다

내부 Snapshot 저장소는 manifest hash·content hash 같은 **내용 기반 주소와 중복 제거**를
사용할 수 있다. 그것이 같은 세계를 알아보는 자연스러운 방법이다.

```text
공개 SnapshotRef    snapshot:A1        명세가 정한 문자열. Report·구조 필드·오류 메시지.
내부 주소           (구현이 정한다)     저장소가 객체를 찾는 방법. 공개 계약이 아니다.
```

- **내부 해시와 저장 경로는 공개 `SnapshotRef`가 아니다.** 공개 명세에 노출하지 않는다.
- `snapshot:A1`의 `A1`은 hash가 아니라 **프로젝트 로컬 순차 ID**다. 「내용 주소화」가 공개
  참조의 문자열 형식이 된다는 뜻이 아니다.
- 사용자와 에이전트가 보는 것, Report에 적히는 것, 오류가 말하는 것은 언제나 `snapshot:A1`
  꼴이다.
- 따라서 저장 엔진을 바꿔도 공개 참조는 바뀌지 않는다.

v0 저장 엔진은 canonical manifest와 SHA-256 내용 주소 객체 저장소, format 4의
`SnapshotRegistry`로 구현됐다. 이것은 내부 계약이며 공개 참조와 분리된다. 장차 엔진을
교체하더라도 같은 `snapshot:A*`가 다른 세계를 가리키게 해서는 안 된다.

---

## 14. 이번 범위에서 구현하지 않는 것

```text
Cycle-level revisit 실행            M4
성공한 Cycle들의 Artifact merge     M8
sibling Cycle merge                 M8
prune 또는 Snapshot 삭제            범위 밖
delta·chunk 단위 중복 제거          후속 내부 최적화
객체 pack 과 미참조 객체 회수        후속 내부 최적화
`.gilignore` 공개 계약              필요가 확인된 뒤
원격 저장·공유                      범위 밖
전체 Artifact history UI            M5 이후
저장 엔진 교체와 migration           필요성이 확인된 뒤의 내부 작업
Managed Dataset                     M3 이후 별도 명세
중첩 GIL 프로젝트 지원              M3 이후 별도 미결 기능
```

**Dataset은 Artifact가 아니다.** Artifact Snapshot이 Dataset을 소유하거나 그 실제 바이트를
반복 저장하지 않으며, World restore와 Cycle revisit은 Dataset 객체와 그 Journey 기록을
지우거나 되돌리지 않는다. Dataset schema·`DatasetRef`·CLI·저장소는 이번 범위에서 만들지
않는다 — 확정된 방향은 `GIL Roadmap` §「M3 이후 — Managed Dataset」에 결정 로그로 남겼다.

구현체가 내부적으로 어떤 저장 기법을 쓸지는 후속 구현 단계에서 결정한다. libgit2를 쓰더라도
그것은 구현 세부이며, **GIL의 공개 개념과 오류 메시지에서 Git 용어를 노출하지 않는다.**
staging, index, add, commit, branch, checkout은 사용자에게 보이는 GIL의 어휘가 아니다.

---

## 15. 검사 가능한 핵심 불변식

```text
a_backslash_component_is_never_an_artifact_path
an_observed_path_round_trips_through_the_parser
the_project_root_is_never_an_entry_path
artifact_scope_excludes_only_the_root_gil_dir
a_nested_gil_directory_refuses_the_whole_observation
a_nested_gil_directory_is_never_descended_into
a_regular_file_named_gil_is_an_ordinary_artifact
artifact_identity_is_path_plus_bytes
mtime_owner_and_permissions_are_not_part_of_the_world
empty_directories_are_not_part_of_the_world
content_is_never_normalized_only_paths_are
rename_is_observed_as_delete_plus_create
project_absolute_location_is_not_in_the_manifest
manifest_order_is_utf8_path_bytes_ascending
a_symlink_or_special_entry_refuses_the_whole_observation
an_unrepresentable_path_refuses_the_whole_observation
nothing_is_silently_excluded
no_public_file_size_limit
observation_is_rechecked_before_confirming
concurrent_change_during_observation_is_refused
start_confirms_the_real_project_state_as_the_baseline
start_writes_baseline_and_first_cycle_in_one_transaction
world_is_confirmed_only_by_start_or_verify_close
the_same_world_reuses_its_snapshot_ref
a_new_snapshot_ref_means_a_new_world
snapshot_ref_is_a_sequential_project_local_id_not_a_hash
internal_content_addresses_are_never_public
a_verify_that_changed_nothing_still_closes
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
every_cycle_has_an_existing_entry_snapshot
entry_snapshot_comes_from_the_transition_that_opened_the_cycle
structural_parent_is_not_always_the_world_origin
an_open_cycle_has_no_exit_snapshot
a_closed_cycle_must_have_an_exit_snapshot
entry_and_exit_may_be_the_same_ref
the_project_root_stores_no_baseline_snapshot_ref
world_current_snapshot_is_derived_never_cached
restore_target_is_derived_never_chosen
restore_takes_no_snapshot_argument
restore_never_walks_outside_the_current_cycle
restore_asks_no_confirmation_and_has_no_force_flag
restore_changes_only_artifacts
restore_does_not_rewind_journey_or_graph
restore_reports_its_target_and_change_counts
restore_is_idempotent_and_a_clean_world_is_a_no_op
restore_is_atomic_and_rolls_back_on_failure
an_interrupted_restore_is_undone_before_anything_else_runs
restore_preserves_existing_permissions
the_restore_staging_area_is_not_user_state
recorded_direction_is_not_called_invalid_when_unimplemented
no_git_vocabulary_in_the_public_surface
```

---

## 16. 핵심 문장

> **Artifact는 "그 Node의 세계가 무엇이었는가"를 재현한다.**

> **세계를 바꿀 수 있는 자리는 Verify 하나뿐이고, 세계를 확정하는 시점도 그때 하나뿐이다.**

> **restore는 기록을 지우는 것이 아니라 과거의 세계를 지금 폴더에 다시 투영하는 것이다.**

> **기록할 수 있다는 것과 지금 실행할 수 있다는 것은 다르다. GIL은 그 둘을 구분해서 말한다.**

> **`SnapshotRef`는 무슨 일이 있었는지의 이름이 아니라, 어떤 세계였는지의 이름이다.
> 이름이 같으면 세계가 같고, 이름이 바뀌었으면 세계가 바뀐 것이다.**
