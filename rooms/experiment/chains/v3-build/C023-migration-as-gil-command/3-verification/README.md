# 3. 검증 — 마이그레이션의 gil 명령화 (도구 강제로 승격)

C022가 실증한 마이그레이션 절차(동결백업 + 노드 소급 + 위상 접합 + 되돌림)를 흩어진 사이클 스크립트에서 **gilv3의 `migrate` 서브명령군으로 승격**한다. C014~C016이 쓰기 축을 도구 강제한 것처럼, 마이그레이션을 도구 강제해 다른 사용자·다른 원장의 v2→v3 이주에 재사용 가능하게 한다.

## ⭐ 재사용이 핵심 — 새 로직 없음

`cmd_migrate`는 C020(`full_ledger_migrate.migrate_all`)·C021(`splice_topology.splice_all`)·C022(백업/되돌림·snapshot 불변 게이트) 검증 함수를 **import해서 호출**한다. 명령화는 알고리즘 재설계가 아니라 **흩어진 검증 스크립트를 한 도구 표면으로 통합**하는 것. 오라클 대조(M1·M2)가 이 보존을 집행한다.

## 세 서브명령 표면

- `gilv3 migrate <repo> --dry` — 도출·접합 수 보고, 각인 0(notes 안 생김).
- `gilv3 migrate <repo>` — 동결백업 + 노드 소급 + 위상 접합 + 불변 게이트.
- `gilv3 migrate <repo> --rollback` — 백업 ref로 리셋 / notes 삭제(잔재 0).

## 재현

```bash
bash build_case.sh <scratch>     # clone-A(오라클)·clone-B(명령) 대조 시연
python3 measure.py <repo> <scratch>   # 5측정(신선 복제본마다 명령 vs 오라클)
```

## 산출물

- `gilv3.py`(C023판) — C019판 + `cmd_migrate` + migrate 서브파서. 마이그레이션 헬퍼 import.
- `full_ledger_migrate.py`·`splice_topology.py`·`snapshot.py` 등 — C022판 재사용(오라클 겸 명령 백엔드).
- `build_case.sh` — 명령 3서브모드 시연(적용·드라이런·되돌림).
- `measure.py`·`measure-out.txt` — 5측정(오라클 대조 + 안전·되돌림·드라이런 계약).

## 5측정

| 측정 | 확인 | 통과 기준 |
|---|---|---|
| **M1 오라클 대조 (적용)** | `gil migrate` DAG == C022 스크립트 DAG (노드·엣지·머지) | 구조 동일 |
| **M2 notes 내용 동일** | 두 클론의 notes 본문(지문·Cycle-Parent) 대조 | 동일 |
| **M3 안전 계약** | 명령 적용 후 커밋 SHA·cycle.yaml 불변 | 바이트 동일 |
| **M4 되돌림 명령** | `migrate --rollback` 후 notes 잔재 0 | 잔재 0 |
| **M5 드라이런 계약** | `migrate --dry`가 각인 안 함, 수 보고만 | notes 안 생김 |

## 명령 시연 (build_case.sh 실측)

```
gilv3 migrate B          → 노드 소급 153사이클·546각인, 위상 접합 133(루트5·선형124·머지4), 불변 확인
gilv3 migrate C --dry    → 사이클 153·도출 546·실패 20, 드라이런 후 notes 없음(각인0)
gilv3 migrate B --rollback → notes 삭제, 잔재 0
clone-A(오라클) 접합 133 == clone-B(명령) 접합 133 (로직 보존)
```

## ⭐ 정점 교훈 — 명령화 = 흩어진 검증 스크립트의 한 표면 통합, 오라클이 보존을 집행

C014~C016이 쓰기 축 원리를 도구 강제했듯, 마이그레이션도 도구 강제됐다. 핵심은 **새 로직을 안 쓴 것** — C020/C021/C022의 검증 함수를 import해 명령 표면만 얹었다. 오라클 대조(clone-A 스크립트 vs clone-B 명령)가 노드·엣지·notes 본문 동일을 확인해 "명령화가 동작을 바꾸지 않았다"를 집행. 도구 강제의 값어치는 재사용(다른 원장의 v2→v3)이고, 그 전제는 동작 보존이다.

## 결론 (measure-out.txt 참조)

동결백업 + 노드 소급 + 위상 접합 + 되돌림이 `gilv3 migrate` 명령군으로 승격됐고, 오라클 대조로 C022 결과·안전 계약이 보존됨을 확인한다. **마이그레이션이 사이클 산출물에서 도구 명령으로 올라섰다** — 다른 사용자의 v2→v3 이주가 이제 한 명령이다.

## 정직한 경계

- **격리 복제본만** — 우리 실제 원장은 이미 C022로 적용됨. 이 사이클은 도구화 검증.
- **대상 도구는 gilv3**(v3-build 실험 도구) — v2 gil.py(실사이클 운영)가 아니다. 마이그레이션은 v3의 눈으로 v2를 읽는 것이므로 v3 도구의 명령.
- **20 도출실패 섬 여전**(C020/C021/C022 이월) — 명령화가 도출 완전성을 늘리지 않는다. 같은 절차의 표면 통합.
- **notes 순회 성능** — M2가 `notes show`를 546회씩 호출해 느리다(측정만, 명령 자체는 빠름).
