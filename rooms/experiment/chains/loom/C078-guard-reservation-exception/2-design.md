# 2. 실험 설계

## 절차

1. **`_guard_primary_owner`에 예약 예외 추가 (참조 gil.py)**: 인자에 `chain_dir=None, slug=None` 추가. author≠owner일 때, 거부 직전에 예약 확인:
   - `chain_dir`·`slug`이 주어지고, `_load_reservations(chain_dir)`에 `for==author and slug==slug`인 예약이 있으면 → **통과**(예약된 계획된 open).
   - 그 외(예약 없음)는 기존대로 거부.
2. **호출처 갱신**:
   - `cmd_open`(669행): `_guard_primary_owner(repo, args.author, chain_dir, args.slug)` — chain_dir·slug 전달.
   - `cmd_correct`(2416행): 예약과 무관(기존 사이클 정정)하므로 chain_dir·slug 없이 호출 → 예약 예외 미적용(정정은 여전히 owner만).
3. **판정기 항목 추가**: `GUARD-RESERVED-OK`(예약된 author의 주 체크아웃 open은 통과) — 기존 `GUARD-PRIMARY-REFUSE`(예약 없는 남 author 거부)와 나란히. 예약 예외가 C050 방지를 안 뚫음을 잠근다.

## 준비물

- 참조 `gil.py`(v2.28), `conformance.py`. `_load_reservations`(이미 존재), `_is_primary_worktree`.

## 측정 방법

| 측정 | 성공 기준 |
|---|---|
| 예약된 author open (주 체크아웃) | 통과 (사이클 생성) |
| 예약 없는 남 author open | 거부 (기존 GUARD-PRIMARY-REFUSE) |
| owner 본인 open | 통과 (기존 GUARD-OWNER-OK) |
| A 예약을 B가 open | 거부 (author 일치까지 확인) |
| correct(남 author) | 거부 (예약 예외 미적용) |
| 판정기 | GUARD-RESERVED-OK PASS + 회귀 0 |

**기각선**: 위 중 하나라도 불충족(1-hypothesis 기각 조건).

## 사용자 컨펌

- 상현님이 "하고 싶은 걸 하렴"으로 자율 위임. C077이 1순위로 이월한 갭 — 내 예측이 틀렸던 지점을 도구로 메운다.

- [x] 컨펌 받음 (일자: 2026-07-19, 자율 위임)
