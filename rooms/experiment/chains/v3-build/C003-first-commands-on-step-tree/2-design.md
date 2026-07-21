# 2. 실험 설계

가설(1-hypothesis): C002의 `steps.yaml` 표현 위에서 open/step/close를 C002 상태기계를
전이 가드로 구현하면, 명령만으로 실사례 트리를 짓고 roundtrip.py를 통과한다.

## 확정할 설계 (검증 대상)

### 도구 — `gilv3` (v3 명령 프로토타입, 순수 stdlib)

C003의 산출물은 v3 명령의 **최소 실행 프로토타입** `gilv3.py`다. v2 gil.py를 안
건드린다(별개 도구 — v3는 처음부터 새로 짓는다, chain.md). 사이클 디렉토리 안
`steps.yaml`을 읽고 쓰는 것만 한다(깃 각인은 이번 범위 밖 — 데이터 조작이 먼저).

### 명령 표면

```
gilv3 open <dir> --title <문제>       # 빈 사이클 + 루트 define(s1) 생성
gilv3 step <dir> --kind <k> [--outcome <o>] [--to <define-id>]
                                       # 산 가지 끝에 다음 노드를 잇는다
gilv3 close <dir>                      # 산 잎 있으면 닫는다
gilv3 status <dir>                     # 현재 트리·커서·다음 허용 행동 출력
```

### 핵심 설계 결정 — 커서를 데이터에 저장하지 않는다 (K2 정면 대응)

C002 M3는 "트리만으로 다음 행동이 유일하게 파생된다"를 보였다. 그렇다면 `step`이
"어디에 이을지"도 **트리에서 계산**할 수 있어야 한다 — 커서 필드를 steps.yaml에 더하면
C002 불변식(트리는 포인터만)을 깨고 K2가 발동한다. 대신:

- **성장 팁(growing tip) = 트리에서 계산한다.** 팁 = "아직 닫히지 않은(analyze로 안
  끝난) 가장 최근 가지의 끝 노드". 규칙:
  - 마지막 노드가 analyze가 **아니면**(define/hypothesis/verify): 그 노드가 팁. 다음
    kind는 순환의 다음(define→hypothesis→verify→analyze).
  - 마지막 노드가 analyze(outcome=backtrack)면: **죽은 잎**. 다음 `step`은 `--to
    <define-id>`가 가리킨 조상 define 밑에 **새 형제 가지**(새 hypothesis)를 시작.
  - 마지막 노드가 analyze(outcome=success)면: **산 잎**. `step` 불가, `close`만.
- 이렇게 하면 커서는 순수 파생물이고 steps.yaml은 C002 스키마 그대로다.

### 전이 가드 (E5 = 명령이 스키마를 강제)

`step`은 계산된 팁의 kind에서 **허용된 다음 kind만** 받는다. 위반 시 거부(비-0 종료):
- define 다음은 hypothesis만. verify 없이 analyze 거부. 등.
- `--kind analyze`는 `--outcome {success|backtrack}` 필수. backtrack이면 `--to`(조상
  define) 필수.
- `close`는 산 잎(success analyze) 존재 시에만.

## 절차

1. **`gilv3.py` 구현** (3-verification/gilv3.py): 위 명령 표면 + 팁 계산 +
   전이 가드. steps.yaml 읽기/쓰기는 C002 roundtrip.py의 파서/덤퍼를 재사용(동일 형식
   보장). 순수 stdlib.
2. **실사례를 명령만으로 재현** (3-verification/rebuild-case.sh): 빈 디렉토리에서
   `gilv3 open` → 일련의 `gilv3 step`/`gilv3 close`로 C012→C013→C014 10노드 트리를
   **처음부터** 짓는다. 백트래킹(s4→s1, s7→s1) 포함.
3. **왕복 검증**: 명령이 지은 steps.yaml에 C002의 `roundtrip.py`를 그대로 돌려 M1·M2·M3
   PASS 확인 (C002 산출물을 검증기로 재사용 — 두 사이클의 계약 일치).
4. **위상 대조**: 명령이 지은 트리와 C002가 손으로 쓴 트리(case-c012-c014)를 정규화
   비교 — 노드 집합·엣지 집합 동형.
5. **전이 가드 테스트**: 불법 전이 3~4개(analyze 없이 close, define→verify 등)를
   시도해 전부 거부되는지 확인.

## 준비물

- Python 3 stdlib만 (의존 0, C002와 동일 환경).
- C002 산출물: `../C002-design-v3-data-model/3-verification/roundtrip.py`(검증기 재사용),
  `case-c012-c014/steps.yaml`(위상 대조 기준).
- 재현 산출물 전부 `3-verification/` 아래.

## 측정 방법

- **M1 (명령 재현, K1)**: `gilv3 open/step/close`만으로 실사례 10노드 트리를 짓고,
  결과 steps.yaml이 C002 roundtrip.py를 PASS(왜곡0·무손실·파생). **기준: PASS + C002
  손작성 트리와 위상 동형이면 PASS.**
- **M2 (커서 무저장, K2)**: 지어진 steps.yaml에 C002 스키마 밖 필드가 0(커서·순서
  메타 없음). 팁이 순수 계산. **기준: steps.yaml 필드 == C002 스키마이면 PASS.**
- **M3 (전이 강제, E5)**: 불법 전이 시도가 전부 비-0 종료로 거부. **기준: 시도한
  불법 전이 전부 거부되면 PASS.**

하나라도 FAIL이면 해당 K 발동, 가장 가까운 문제정의(E1/E2 또는 데이터 모델)로 되돌아감.

## 사용자 컨펌

- 생략 — 사유: 부모 C002가 명령 파생(M3)을 이미 실증했고, 상현님이 "v3 더 나가보자
  (명령 C003 병렬)"로 이 갈래를 위임했다. 커서 무저장이라는 핵심 결정은 C002 불변식의
  직접 귀결이라 새 분기점이 아니다. 만약 팁 계산이 실사례에서 애매해지면(예: 여러
  산 가지 동시 진행) 그때 갈래로 보고.

- [x] 컨펌 생략 (일자: 2026-07-21) — 부모 위임 + 병렬 갈래 승인
