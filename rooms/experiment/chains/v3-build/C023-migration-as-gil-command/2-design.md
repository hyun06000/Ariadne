# 2. 실험 설계

오직 1-hypothesis.md의 가설 — **C022 실증 절차를 gilv3 migrate 명령군으로 승격하되 결과·안전 계약을 바이트 보존** — 을 검증한다.

## 정답을 도구보다 먼저 고정한다

명령화의 "정답"은 **C022 스크립트의 출력**이다. 그것이 기준(oracle)이고, `gil migrate`가 같은 것을 내면 통과다. 새 로직을 발명하지 않는다.

## 절차

1. **로직 통합.** C019 gilv3.py(최신 v3 도구) 위에 마이그레이션 로직을 얹는다:
   - C020 `derive_fingerprint`·`full_ledger_migrate`(노드 소급) 로직.
   - C021 `splice_topology`(위상 접합) 로직.
   - C022 백업/되돌림(freeze_backup·rollback) 로직.
   - 흩어진 함수를 gilv3.py 안 `cmd_migrate`로 통합. 재사용이 목표이므로 **동작은 그대로, 표면만 명령으로**.
2. **세 서브명령 표면.**
   - `gilv3 migrate <repo> --dry` → 도출·접합 수 보고, 각인 0(notes 안 생김).
   - `gilv3 migrate <repo>` → 동결백업 + 노드 소급 + 위상 접합, refs/notes 각인 + 불변 게이트.
   - `gilv3 migrate <repo> --rollback` → 백업 ref로 리셋 / notes 삭제, 잔재 0.
3. **오라클 대조 검증.** 격리 복제본 2개(clone-A, clone-B)를 뜬다.
   - clone-A: C022 스크립트(apply_migration.py 등)로 마이그레이션.
   - clone-B: 새 `gilv3 migrate`로 마이그레이션.
   - 두 결과의 DAG(노드·엣지·머지)·notes 내용을 대조 → 바이트/구조 동일이면 명령화가 로직 보존.
4. **안전 계약 검증.** clone-B에서 커밋 SHA·cycle.yaml 불변, `--rollback` 후 notes 잔재 0, `--dry`가 notes 안 만듦.

## 준비물

- `gilv3.py`(C023판) — C019판 + `cmd_migrate` + 마이그레이션 헬퍼 통합.
- C020/C021/C022 스크립트(오라클 기준) — 검증 디렉토리에 복사.
- `build_case.sh` — clone-A(스크립트)·clone-B(명령) 두 격리 복제본 생성·실행.
- `measure.py` — 5측정(오라클 대조 + 안전 계약).
- 환경: Python 3(stdlib만), git. 격리 복제본만(우리 실제 원장 안 건드림 — 이미 C022로 적용됨).

## 측정 방법 (5측정)

| 측정 | 확인 | 통과 기준 |
|---|---|---|
| **M1 오라클 대조 (적용)** | `gil migrate` DAG == C022 스크립트 DAG (노드·엣지·머지) | 구조 동일 |
| **M2 notes 내용 동일** | 두 클론의 notes 본문(지문·Cycle-Parent) 대조 | 동일 |
| **M3 안전 계약** | `gil migrate` 후 커밋 SHA·cycle.yaml 불변 | 바이트 동일 |
| **M4 되돌림 명령** | `gil migrate --rollback` 후 notes 잔재 0 | 잔재 0 |
| **M5 드라이런 계약** | `gil migrate --dry`가 각인 안 함(notes 부재 유지), 수 보고만 | notes 안 생김 |

## 안전 철칙

1. **격리 복제본만.** 우리 실제 원장은 이미 C022로 적용됐고, 이 사이클은 도구화 검증이라 복제본에서만 실행.
2. **동작 보존이 최우선.** 명령화가 C022 결과를 한 톨이라도 바꾸면 기각. 오라클 대조가 이를 집행.
3. **새 로직 금지.** 검증된 함수를 옮길 뿐, 마이그레이션 알고리즘을 재설계하지 않는다.

## 사용자 컨펌

상현님이 "순서대로하자"로 이월 순서를 따르도록 지시했고, 이 사이클(이월 2순위 gil 명령화)이 그 순서다. 격리 복제본만 쓰고 실제 원장·원격을 안 건드리므로(도구화 검증) 위임 범위 안에서 자율 진행.

- [x] 컨펌 받음 (일자: 2026-07-22, "순서대로하자" — 이월 2순위, 격리만)
