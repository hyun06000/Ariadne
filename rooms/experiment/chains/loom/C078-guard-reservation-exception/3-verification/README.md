# 3. 검증 — guard 예약 예외

## 결과 (양 구현)
| 케이스 | 결과 | 기대 |
|---|---|---|
| owner(clew) open | 통과 | 통과 ✓ |
| 예약 없는 남 author open | 거부 | 거부 ✓ |
| **예약된 author open (주 체크아웃)** | **통과** | 통과 ✓ (C078 핵심) |
| A 앞 예약을 B가 open | 거부 | 거부 ✓ |
| correct(남 author) | 거부 | 거부 ✓ (예약 예외 미적용) |

- 참조 **102/102**, Go **88/88** (GUARD-RESERVED-OK·GUARD-RESERVED-AUTHOR 신설, 회귀 0).
- 수정 전 참조 101/102·Go 87/88 (GUARD-RESERVED-OK FAIL) — 예약된 open을 거부.
- 참조↔Go 동시 수정 → parity 유지.

## 수정
- 참조 `_guard_primary_owner(repo, author, chain_dir=None, slug=None)`: author≠owner일 때 거부 직전 `_load_reservations`에서 `for==author and slug==slug` 예약 있으면 통과. cmd_open은 chain_dir·slug 전달, cmd_correct는 없이(미적용).
- Go `guardPrimaryOwner(repo, author, chainDir, slug)`: 동형(res.who==author && res.slug==slug). cmd_open 전달, cmd_correct 빈 문자열.
- 판정기 GUARD-RESERVED-OK/GUARD-RESERVED-AUTHOR 신설. 예약 2개로 소비 후 원장 안 비게(git add 선재버그 회피).

## 발견한 선재 버그 (범위 밖, 이월)
- **마지막 예약을 소비하는 `open --git`이 실패**: 예약 소비로 reservations.tsv가 비면 `_save_reservations`가 파일을 삭제하는데, 그 뒤 `git add -A -- <cycdir> <reservations.tsv>`가 삭제된 경로를 참조해 "경로명세가 어떤 파일과도 일치하지 않습니다"로 실패. 원본 gil(C078 전)에서도 재현 — C078 무관. C077에서 Weft가 guard에 막혀 이 경로를 못 밟았고, Clew가 guard 열어 연 open은 예약이 여럿(안 비었음)이라 안 터졌다. 별도 사이클/이슈 감.
