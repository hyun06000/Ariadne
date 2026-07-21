# 2. 실험 설계

가설(1-hypothesis): C001의 스텝 노드 스키마를 **디스크 표현(`steps.yaml` + 노드별
본문 .md)**으로 구체화하면 실사례 C012→C013→C014를 (a) 왜곡 0 (b) 왕복 무손실
(c) 명령 파생 가능으로 담는다.

## 확정할 설계 (검증 대상)

### 스키마 (D1) — 스텝 노드

```
STEP =
  id:        문자열. 트리 지역 식별자. 발급 규칙은 아래 D3.
  kind:      enum { define, hypothesis, verify, analyze }
             (문제정의* / 가설 / 검증 / 분석)
  parent:    STEP.id | null. **논리적 부모** — 이 스텝이 자란 직전 스텝.
             루트(체인 목표 직속 첫 define)만 null.
  outcome:   enum { fail, backtrack, success } | null.
             kind=analyze인 노드에서만 non-null(분석이 분기를 결정하므로).
             그 외 kind는 항상 null.
  backtrack: STEP.id | null. outcome=backtrack일 때만 non-null이며, 반드시
             조상 중 kind=define인 노드를 가리킨다(되돌아갈 갈림길).
  body:      본문 .md 파일 경로(디렉토리 상대). 노드 서술.
```

C001의 5필드(id·kind·parent·outcome·backtrack)를 그대로 쓰되 **outcome을
analyze 전용으로 못박고**(C001에서 암묵적이던 것을 명시), body를 더한다.

### 디스크 표현 (D2)

사이클 디렉토리 안에:

```
<chain>/<cycle-id>/
  cycle.yaml          # 사이클 메타 (v2 유지, step 필드는 트리에선 "닫힘 여부"로 축소)
  steps.yaml          # 스텝 노드 리스트 (트리를 담는 단일 진실원)
  steps/
    <step-id>.md      # 노드별 본문
```

`steps.yaml` = 노드 리스트(순서 = 생성 순 = 커밋 순). 트리 구조는 각 노드의
`parent`/`backtrack` 포인터로 표현(인접 리스트). 디렉토리 중첩 아님 — 백트래킹
형제 가지가 디렉토리 계층으로는 안 담기기 때문(v2 5개 고정 .md가 깨지는 이유).

### id 발급 (D3, 최소)

`s<N>` 단조 증가(s1, s2, …). **트리 위치는 id가 아니라 parent 포인터가 담는다** —
이것이 v2 `parent`의 죄를 없애는 핵심: id는 순수 시간순(커밋순), 논리 구조는 포인터로
분리. 형제·백트래킹 순서 문제가 사라진다(id는 정렬만, 트리는 포인터가).

### kind 상태기계 (D4, 최소)

허용 전이(한 가지 안에서):
`define → hypothesis → verify → analyze → { fail | backtrack | success }`

- analyze.outcome=**fail** → 가장 가까운 조상 define으로 backtrack(=backtrack 노드가
  아니라, 다음에 나올 define의 parent 결정). *fail은 backtrack의 트리거, backtrack은
  그 실현.* 최소 설계에선 fail을 backtrack의 특수형으로 흡수 가능한지 검증에서 본다.
- analyze.outcome=**backtrack** → backtrack이 가리킨 define 밑에 **새 형제 가지**
  (새 define 또는 새 hypothesis)가 자란다.
- analyze.outcome=**success** → 산 잎. close 신호.

### close 판정 (D5, 최소)

산 잎(`outcome=success` analyze) 하나가 존재하면 사이클을 닫을 수 있다. 죽은 잎
(`outcome=backtrack`)만 있고 산 잎이 없으면 못 닫는다(진행 중).

## 절차

1. **스키마 명세 파일 작성**: `3-verification/schema.md`에 위 STEP·steps.yaml 형식을
   기계가독 예시와 함께 확정한다.
2. **실사례를 실제 steps.yaml로 씀**: C012→C013→C014를 손으로 하나의 스텝 트리로
   `3-verification/case-c012-c014/steps.yaml` + `steps/*.md`에 쓴다. 봉인된 5-report
   원문(loomlight/C012·C013·C014)을 근거로 왜곡 없이.
3. **재구성 스크립트 작성·실행**: `3-verification/roundtrip.py` — steps.yaml을 읽어
   트리를 메모리로 복원하고, (a) 트리 위상(parent/backtrack 엣지) 출력, (b) 다시
   steps.yaml로 재직렬화, (c) 원본과 정규화 비교(무손실 판정)한다. 순수 stdlib.
4. **명령 파생 확인**: 복원된 트리만으로 "다음 허용 행동(open/step/close)"이
   결정되는지 스크립트가 각 노드에서 계산해 출력(스키마 밖 관습 불필요 확인).

## 준비물

- Python 3 (stdlib만 — `pyyaml` 미사용, 단순 파서 자작 또는 최소 yaml 서브셋).
  환경 pyyaml 유무 불확실하므로 **의존 0**으로 간다.
- 봉인 원본: `rooms/experiment/chains/loomlight/C012·C013·C014/5-report.md`.
- 재현 산출물은 전부 `3-verification/` 아래.

## 측정 방법

- **M1 (왜곡 0, K1 대응)**: 실사례를 steps.yaml로 쓸 때 5필드+body로 담기지 않는
  정보가 0. 백트래킹(C013→뿌리→C014)이 `backtrack` 포인터로, 죽은 잎(C012·C013)이
  `outcome=backtrack`으로, 산 잎(C014)이 `outcome=success`로 보존. **기준: 3 요소
  모두 포인터/enum으로 담기면 PASS.**
- **M2 (왕복 무손실, K2 대응)**: roundtrip.py의 재직렬화 결과가 원본 steps.yaml과
  정규화 후 동일(노드 집합·엣지 집합 동형). **기준: diff 0이면 PASS.**
- **M3 (명령 파생, K3 대응)**: 복원된 트리의 각 노드에서 "다음 허용 kind/행동"이
  스키마만으로 유일하게 결정(analyze는 outcome에 따라 분기). **기준: 스키마 밖
  추가 관습 0으로 open/step/close가 파생되면 PASS.**

세 측정 중 하나라도 FAIL이면 해당 K가 발동, 가장 가까운 문제정의(D1 또는 D2)로
되돌아간다.

## 사용자 컨펌

- 생략 — 사유: 부모 C001의 5-report가 C002의 대상(데이터 모델 완전 설계)과 검증법
  (실사례를 실제 스키마 파일로 왕복)을 이미 명시했고, 상현님이 "이어서 해보자"로
  그 이월을 잇도록 위임했다. 설계는 그 이월을 구체 절차로 옮긴 것으로 새 분기점이
  아니다. 검증에서 갈래(예: fail을 backtrack에 흡수할지)가 실제로 나뉘면 그때 보고.

- [x] 컨펌 생략 (일자: 2026-07-21) — 부모 보고서 위임
