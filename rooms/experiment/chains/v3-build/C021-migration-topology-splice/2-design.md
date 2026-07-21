# 2. 설계 — 사이클 간 엣지 접합기 + 사이클 DAG 재구성

## 설계 원칙

- **격리 복제본(C020 계승).** 우리 원장 안 건드림.
- **notes 소급(C018 계승).** cycle.yaml 안 바꾸고 루트 지문 notes에 Cycle-Parent 첨부. 커밋 불변.
- **lineage=머지 재사용(C015).** 머지 parent(리스트)는 C015가 도구화한 다중부모 계보와 동형 — 개념 재구현 0.
- **사이클이 단위.** Cycle-Parent는 사이클 루트(s1)에만 — 사이클을 대표. 스텝별 반복 불필요.

## 무엇을 만드나 — 두 조각

### 조각 1 — 접합기 `splice_topology.py`
각 사이클의 루트 커밋(open 또는 s1 step)에 Cycle-Parent를 notes로 소급.

```python
def parse_parent(cycle_yaml_parent):
    """cycle.yaml parent 값 → 부모 사이클 id 리스트.
    'C014' → ['C014']  ·  '[C020, C016]' → ['C020','C016']  ·  'null' → []."""

def splice_cycle(repo, cycle_meta):
    """사이클 루트 지문에 Cycle-Parent 엣지를 notes로 추가.
    루트 = 그 사이클 s1 커밋(C020 도출이 이미 s1 지정). 기존 notes(Step-Id 등)에
    Cycle-Parent 라인을 덧붙임(notes append, 커밋 불변).
    parents: 단일→'C014' · 머지→'C020, C016' · 루트→'null'."""
```

- **루트 커밋 찾기**: C020이 각 사이클 step 커밋에 s1~s5 지문을 박았다. s1 커밋(사이클 루트)에 Cycle-Parent 추가.
- **notes append**: 기존 s1 notes(Step-Id: s1, Kind: define, Parent: null)에 `Cycle-Parent: <부모들>` 한 줄 덧붙임. `git notes append`(커밋 불변 유지).

### 조각 2 — 사이클 DAG 재구성 `rebuild_cycle_dag.py`
접합된 notes에서 사이클 간 DAG 복원.

```python
def rebuild_cycle_dag(repo):
    """각 사이클 루트 notes의 Cycle-Parent를 읽어 사이클 DAG 복원.
    반환: {cycle_id: [parent_ids]} — 150 섬이 이어진 그래프.
    루트(Cycle-Parent=null)·선형(1부모)·머지(≥2부모) 구분."""
```

## 접합 = C015 lineage의 마이그레이션 판

C015가 "lineage=머지=다중부모"를 도구 명령으로 만들었다. 여기선 그 **개념을 소급 데이터에 적용**한다: cycle.yaml `parent: [A,B]`가 곧 다중부모 계보이고, notes Cycle-Parent가 그것을 v3 지문으로 담는다. 살아있는 v3 사이클은 close --lineage로 머지 커밋을 만들지만(C015), 죽은 v2 사이클은 notes Cycle-Parent로 계보를 담는다 — **같은 lineage 개념, 다른 각인 수단**(살아있음=머지 커밋, 죽음=notes 소급).

## 측정 설계 (build_case + measure)

C020 격리 복제본 재사용. 세 형태를 담는 대표 사이클 부분집합:
- 단일: v3-build/C015 (parent: C014)
- 머지: loom/C036 (parent: [C020, C016]) · v3-build/C005 (parent: [C003, C004])
- 루트: 각 체인 첫 사이클 (parent: null)

측정:
- **M1 엣지 접합(H1a):** 사이클 루트 notes에 Cycle-Parent, rebuild_cycle_dag가 엣지 복원.
- **M2 세 형태(H1b):** 단일 1부모·머지 ≥2부모·루트 0부모 각각 정확.
- **M3 커밋 불변(H1c):** 접합 전후 커밋 SHA·cycle.yaml 파일 불변.
- **M4 DAG 정합(H1d):** 접합 DAG의 루트 수·머지 노드 수·총 엣지 수 == cycle.yaml 집계(전량 대조).

## 정직한 경계
- 사이클 간 엣지만(노드 위상은 C020).
- 격리 복제본(드라이런).
- Cycle-Parent는 루트에만.
- 전량 집계 대조 + 대표 세 형태 실증. 전량 그래프 렌더는 뷰어 축(Sheen).
- 접합은 C020이 도출 성공한 사이클(150개)에 한함 — 미발견 20·도출실패는 여전히 섬(정직).
