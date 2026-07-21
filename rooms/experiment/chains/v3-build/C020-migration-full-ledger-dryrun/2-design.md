# 2. 설계 — 전량 순회 소급 (격리 복제본, 견고화 + 정직한 잔여)

## ⭐ 설계 착수 중 발견 — 실제 원장은 관습이 진화했다

subject 전수 조사가 C019 가정을 깨뜨렸다:
- **step N/5의 N이 대부분 2~5** — 최신 형식은 open이 "1/5 가설"을 겸하고 step은 2/5부터. 사이클당 step 커밋 = **4개**(2·3·4·5)가 표준(C019의 "5개" 틀림).
- **초기 사이클은 완전히 다른 형식** — `gil: C057 가설 작성`, `gil: C058 구현+검증+분석+보고`(여러 스텝 한 커밋) 등. `gil: step` prefix조차 없다.
- **원장 관리 커밋 다수** — release 77·land 15·reserve 9·renumber·withdraw… (스텝 아님).

**결론: subject만으로 전량 도출은 불가능하다 — 관습이 진화했기 때문.** 그러나 이것은 실패가 아니라 **C017 가시성 원리의 대규모 적용 지점**이다: 도출 가능한 것은 도출하고, 못 하는 것은 정직히 유령으로 남겨 정체를 보고한다.

## 진실원 재선택 — subject 대신 cycle.yaml

subject는 관습이 진화해 불안정하다. 그러나 **cycle.yaml은 스키마가 안정적**이다(id·chain·parent·step·verdict). 전량 소급의 견고한 진실원은 subject 파싱이 아니라:

1. **사이클 발견**: `find rooms/experiment/chains -name cycle.yaml` → 196 사이클, 각 id·parent·step·verdict.
2. **사이클→커밋 매핑**: 각 사이클의 open/step 커밋을 subject로 찾음(cycle id는 subject에 안정적으로 들어감 — `open <chain>/<id>`·`step <chain>/<id>`).
3. **도출**: cycle.yaml의 step 수만큼 스텝 노드, verdict로 마지막 outcome. C019 규칙을 cycle.yaml 기반으로.

**subject는 커밋을 찾는 열쇠로만 쓰고, 구조(스텝 수·parent·verdict)는 cycle.yaml에서.** 관습 진화에 견고.

## 무엇을 만드나 — `full_ledger_migrate.py`

```python
def discover_cycles(repo):
    """cycle.yaml 전량 발견 → [{id, chain, parent, step, verdict, dir}, ...]."""

def cycle_commits(repo, chain, cid):
    """한 사이클의 open/step 커밋 해시를 subject로 찾음 (시간순).
    subject의 <chain>/<id> 매칭 — cycle id는 관습 진화에도 안정적."""

def migrate_all(repo, apply=False):
    """전량 순회: 각 사이클의 커밋에 derive→retro_imprint(notes).
    apply=False면 도출만(드라이런 카운트), True면 실제 notes 각인.
    반환: {소급된 커밋 수, 도출 실패 사이클, 잔여 유령 분류}."""
```

- **견고 파서**: `→`·`—` 둘 다, `gil: step <chain>/<id>` prefix. 매칭 안 되면 그 커밋은 도출 대상 밖(유령 유지).
- **정직한 잔여 분류**(H1d): 소급 후 유령을 3종으로 — ①비-원장(memory·부트스트랩) ②원장 관리(release·land…) ③도출 실패(관습 이질 사이클). 각 수 보고.

## 격리 (H1a·M5 — 우리 원장 무손상)

**우리 저장소를 복제본으로 뜬다**: `git clone <우리레포> <복제본>` 또는 `cp -r`. 모든 각인은 복제본에서만. 측정이 우리 실제 원장 SHA·notes를 안 건드림을 확인(M5).

## 측정 설계 (build_case + measure)

복제본에서 전량 드라이런 + 통합 실측.
- **M1 전량 순회 무사고(H1a):** 복제본에서 원장 커밋 소급 완주, 원장 커밋 SHA 불변.
- **M2 유령 감소(H1b):** 소급 전후 재구성기 유령 수 대조(대폭 감소). 단, 재구성기는 사이클 단위라 전체 원장 rebuild가 아니라 대표 사이클들로.
- **M3 도출 견고성(H1c):** `→`·`—` 둘 다 파싱, release/land/비-원장 스킵 정확(오각인 0).
- **M4 잔여 투명성(H1d):** 소급 후 유령 3종 분류 보고, 합이 전체 유령과 일치.
- **M5 원장 불변(격리):** 우리 실제 저장소 HEAD·notes가 측정 전후 동일.

## 정직한 경계
- **드라이런(복제본)만.** 실제 적용은 검증 뒤 별도 결정.
- **cycle.yaml 진실원** — subject는 커밋 찾기 열쇠. 관습 진화 대응.
- **도출 실패는 정직히 유령 유지** — 전량 도출 억지 안 함(C017 가시성). 초기 이질 사이클은 잔여로 남고 보고됨.
- 위상 접합(④ 복원) 안 함 — 사이클 내 노드 편입만.
- verdict 근사(C019) 유지.
