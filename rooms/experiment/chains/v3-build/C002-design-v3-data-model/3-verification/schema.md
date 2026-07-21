# v3 스텝 트리 데이터 모델 — 스키마 명세 (C002 확정판)

부모: v3-build/C001 (스케치) → C002가 디스크 표현으로 확정.

## 1. STEP 노드

한 사이클은 스텝 노드들의 **트리**다. 각 노드:

| 필드 | 타입 | 규칙 |
|---|---|---|
| `id` | `s<N>` | 단조 증가(s1, s2, …). **순수 시간순(커밋순)**. 트리 위치를 담지 않는다. |
| `kind` | `define \| hypothesis \| verify \| analyze` | 문제정의* / 가설 / 검증 / 분석 |
| `parent` | `id \| null` | **논리적 부모**. 루트 define만 null. |
| `outcome` | `fail \| backtrack \| success \| null` | `kind=analyze`일 때만 non-null. |
| `backtrack` | `id \| null` | `outcome=backtrack`일 때만 non-null. 반드시 조상 중 `kind=define`. |
| `body` | 경로 | `steps/<id>.md` 노드 서술. |

**핵심 불변식** (v2 `parent`의 죄를 없애는 것):
- `id`는 시간순만 담는다. **트리 구조는 오직 `parent`/`backtrack` 포인터가 담는다.**
- v2는 `parent`에 시간순과 논리순을 겹쳐 백트래킹을 선형으로 뭉갰다. v3는 둘을 분리:
  시간순=`id`, 논리순=`parent`, 되돌아감=`backtrack`.

## 2. kind 상태기계

한 가지(branch) 안의 허용 전이:

```
define → hypothesis → verify → analyze → { fail | backtrack | success }
```

- `analyze.outcome = success` → **산 잎**. close 가능.
- `analyze.outcome = backtrack` → `backtrack`이 가리킨 define 밑에 **새 형제 가지**가
  자란다(다음 노드의 parent = 그 define, 또는 그 define에서 갈린 새 hypothesis).
- `analyze.outcome = fail` → backtrack의 특수형(목적지가 "가장 가까운 조상 define"으로
  자동 해소). 명시적 `backtrack` 없이 트리거만 기록하고 싶을 때. **C002 검증에선
  모든 되돌아감을 명시적 backtrack으로 적어 fail을 안 쓴다**(명시가 데이터로 더 낫다).

## 3. 디스크 표현

```
<chain>/<cycle-id>/
  cycle.yaml       # 사이클 메타 (닫힘 여부·verdict 등)
  steps.yaml       # 스텝 노드 리스트 = 트리의 단일 진실원 (인접 리스트)
  steps/<id>.md    # 노드별 본문
```

`steps.yaml` 형식 (stdlib로 파싱 가능한 최소 서브셋 — 노드당 한 블록):

```yaml
- id: s1
  kind: define
  parent: null
  outcome: null
  backtrack: null
  body: steps/s1.md
- id: s2
  kind: hypothesis
  parent: s1
  outcome: null
  backtrack: null
  body: steps/s2.md
```

디렉토리 **중첩 없음**: 백트래킹 형제 가지는 디렉토리 계층으로 못 담기므로(v2 고정
5-.md가 깨지는 지점) 평면 리스트 + 포인터로 트리를 담는다.

## 4. close 판정

`outcome=success`인 analyze 노드(산 잎)가 하나라도 있으면 close 가능. 죽은 잎
(`outcome=backtrack`)만 있으면 진행 중.
