# 2. 실험 설계

오직 1-hypothesis.md의 가설 — **C023 검증 migrate 로직을 배포판 gil.py에 통합, 동작 바이트 보존** — 을 검증한다.

## 정답을 도구보다 먼저 고정한다

정답 = **C023 gilv3 migrate의 출력**(오라클). 배포판 `gil migrate`가 같은 DAG·notes를 내면 통합이 로직을 보존한 것. 새 로직 발명 금지.

## ⭐ 통합 전략 — 인라인 (자기완결 배포 계약)

배포판 gil.py는 **단일 자기완결 파일**이 계약(SPEC §7: 참조 구현, release는 파일명 비의존). 따라서 migrate 백엔드(derive_fingerprint 102 + full_ledger_migrate 138 + splice_topology 97 + retro_imprint 88 + snapshot 66 ≈ 490줄)를 **gil.py 안에 인라인**한다 — 외부 모듈 import 0. 배포판이 다른 파일에 의존하면 배포 계약이 깨진다.

- 함수명 충돌 방지: migrate 헬퍼는 `_mig_` 접두어 또는 명확한 이름으로.
- 배포판 기존 git 헬퍼(subprocess 패턴) 재사용 가능하면 재사용, 아니면 인라인.

## 절차

1. **백엔드 인라인.** C023판 5스크립트의 함수를 gil.py에 통합(동작 보존, 재구현 아닌 이식).
2. **`cmd_migrate` + 서브파서 추가.** C023 gilv3 cmd_migrate 구조 그대로(--dry·적용·--rollback), 배포판 argparse(4999줄 근처)에 등록.
3. **오라클 대조 검증.** 격리 복제본 2개:
   - clone-A: C023 gilv3 migrate.
   - clone-B: 배포판 gil migrate.
   - DAG·notes 본문 바이트 대조(C023 measure 패턴 재사용).
4. **계약·회귀 검증.** --dry(각인0)·--rollback(잔재0)·커밋 불변 + 배포판 기존 명령(open/step/close/web/fsck) 회귀 0(conformance 스위트).

## 준비물

- 배포판 gil.py(통합 본체) + C023판 migrate 스크립트(오라클 겸 이식 원본).
- conformance.py(배포판 회귀 검증) — 기존 명령 안 깨짐 확인.
- 격리 복제본(우리 원장 조회만).

## 측정 방법 (5측정)

| 측정 | 확인 | 통과 기준 |
|---|---|---|
| **M1 오라클 대조** | 배포판 gil migrate DAG == C023 gilv3 migrate DAG | 구조 동일 |
| **M2 notes 바이트 동일** | 두 구현 notes 본문 대조 | 바이트 동일 |
| **M3 계약 보존** | --dry 각인0 · --rollback 잔재0 · 커밋·cycle.yaml 불변 | 전부 성립 |
| **M4 회귀 0** | 통합 후 conformance 스위트(배포판 기존 명령) 통과 | 회귀 0 |
| **M5 자기완결** | gil.py가 외부 모듈 import 없이 migrate 동작(단일 파일 계약) | import 0 |

## 안전 철칙

1. **격리 복제본만** — migrate 실행은 조회·측정. 실제 원장은 이미 C022로 각인됨.
2. **동작 보존이 최우선** — 오라클 대조가 집행. 배포판 기존 명령 회귀 0이 게이트.
3. **인라인이되 재구현 아님** — C023 검증 함수를 옮길 뿐, 알고리즘 재설계 금지.
4. **web 통합은 이 카브 밖**(다음 사이클) — migrate만. 범위 절제.

## 사용자 컨펌

상현님이 "먼저 배포판 통합부터"로 이 순서를 지시했다. 실제 배포판 gil.py를 수정하나, C023 검증 로직 이식이고 오라클 대조·회귀 스위트로 안전 집행하며 격리에서 검증 후 커밋한다. 위임 범위 안 자율 진행.

- [x] 컨펌 받음 (일자: 2026-07-22, "먼저 배포판 통합부터" — v3 눈 뿌리를 하나의 gil로)
