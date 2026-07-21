# 3. 검증 — 사이클 간 엣지 접합 (마이그레이션 위상 복원)

C020이 532 스텝을 각 사이클 안에서 편입했으나 150개 분리된 섬이었다. 이 카브는 cycle.yaml parent를 각 사이클 루트 지문에 `Cycle-Parent` notes로 소급해 섬들을 한 v3 체인 DAG로 잇는다. **격리 복제본(우리 원장 안 건드림).**

## 재현

```bash
bash build_case.sh <scratch>     # clone → 노드소급(C020) → 엣지접합(C021) → DAG재구성
python3 measure.py <scratch>     # 4측정 감사
```

## 산출물

- `splice_topology.py` — cycle.yaml parent를 사이클 루트 notes에 Cycle-Parent로 append(커밋 불변).
- `rebuild_cycle_dag.py` — 접합된 notes에서 사이클 간 DAG 복원.
- `full_ledger_migrate.py` 등 — C020판 재사용(노드 소급).
- `build_case.sh`·`measure.py`·`*-out.txt` — 격리 접합 + 4측정(ALL PASS).

## ⭐ 접합 = C015 lineage=머지의 마이그레이션 판

C015가 "lineage=머지=다중부모"를 도구 명령으로 만들었다. 여기선 그 **개념을 소급 데이터에 적용**한다: cycle.yaml `parent: [A,B]`가 다중부모 계보(C012)이고, notes Cycle-Parent가 그것을 v3 지문으로 담는다. **살아있는 v3 사이클은 close --lineage로 머지 커밋(C015), 죽은 v2 사이클은 notes Cycle-Parent로 계보를 담는다 — 같은 lineage 개념, 다른 각인 수단**(살아있음=머지 커밋, 죽음=notes 소급).

## ⭐ 측정 중 함정 — short_id 체인 간 충돌

첫 재구성이 131 접합인데 DAG 104만 복원. 원인: DAG 키를 `short_id`(C001)로만 하니 **체인 간 충돌**(loom/C001·v3-build/C001·genesis/C001 모두 `C001`) — dict에서 덮였다. cycle id는 체인 안에서만 유일하므로 키를 `chain/short_id`로 전역 유일화 → 131 복원. 계측기 결함(가설 반증 아님).

## 접합 결과 (실측)

- **131 사이클 접합**(루트 5·선형 122·머지 4), 20 도출실패는 접합 밖(여전히 섬, 정직).
- **DAG 재구성 131 노드·130 엣지** — notes만으로 사이클 간 계보 복원.

## 4측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 엣지 접합** | DAG 131 노드·130 엣지 — 섬들이 Cycle-Parent notes로 이어짐 | PASS |
| **M2 세 형태** | 단일(C015→C014)·머지(C036→[C020,C016], C015 lineage 동형)·루트(5개) 각각 정확 | PASS |
| **M3 커밋 불변** | 복제본 SHA==우리 원장 SHA, cycle.yaml 파일 불변 — Cycle-Parent가 notes append(C018 계약) | PASS |
| **M4 DAG 정합** | 머지 4==cycle.yaml 4 완전 일치, 총계 gap 20==도출실패 20(정직히 설명) | PASS |

## DAG 정합의 정직한 회계

| | 접합 DAG | cycle.yaml | 차이 |
|---|---|---|---|
| 루트 | 5 | 8 | 3 (도출실패 루트) |
| 선형 | 122 | 139 | 17 (도출실패 선형) |
| 머지 | 4 | 4 | **0 (완전 일치)** |
| 총 | 131 | 151 | 20 = C020 도출실패 |

머지가 완전 일치하는 건 머지 사이클이 전부 최신 형식(도출 성공)이기 때문. 차이 20은 전부 C020이 커밋 못 찾은 도출실패 사이클 — 새 손실이 아니라 C020에서 이미 알던 잔여.

## 결론

**ALL PASS → supported.** cycle.yaml parent가 사이클 간 v3 엣지로 접합돼 C020의 150 섬이 한 체인 DAG(131 노드·130 엣지)로 이어졌다. 단일·머지·루트 세 형태 정확(머지는 C015 lineage와 동형), 커밋·cycle.yaml 불변(notes append), DAG가 실제 계보와 정합(머지 완전 일치, 잔여는 C020 도출실패로 정직히 설명). **마이그레이션 4단계 중 ④ 백트래킹 복원(위상)이 섰다** — 사이클 내부(C020)와 사이클 간(C021)이 모두 v3의 눈에 복원됐다. 남은 건 도출실패 157/20 정밀화와 실제 원장 적용 결정.

## 정직한 경계

- **사이클 간 엣지만**(노드 위상은 C020).
- **격리 복제본(드라이런).** 실제 적용은 별도 결정.
- **20 도출실패는 여전히 섬**(C020 이월) — 접합 대상 밖, 정직.
- Cycle-Parent는 루트에만(사이클이 단위).
- 전량 그래프 렌더는 뷰어 축(Sheen).
- 계측기 결함 1건(short_id 충돌) 수리 — 반증 아님.
