# 2. 실험 설계

## 절차

1. **참조 `gil.py` `cmd_open` 수정** (783-785행): reservations.tsv 경로를 paths에 넣는 조건을 좁힌다.
   - 현재: `if consumed: paths.append(res_path if os.path.isfile(res_path) else _reservations_path(...))` — 삭제돼도 무조건 넣음.
   - 수정: consumed이고 **파일이 존재**하면 그 경로를 넣는다. 삭제됐으면(마지막 예약) **tracked일 때만** 넣는다(삭제 스테이징). tracked도 아니면 제외(git add가 거부하는 경로).
   - tracked 판정: `git ls-files --error-unmatch <path>` 종료코드 0 = tracked. 헬퍼 `_git_tracked(repo, rel)`.
2. **Go `cmd_open` 동형 수정** (parity — C078 교훈: 참조·Go 동시).
3. **판정기 항목**: `OPEN-LAST-RESERVATION`(마지막 예약을 소비하는 open --git이 정상 각인 — 디렉토리 생성 ∧ 커밋 존재 ∧ 원장 파일 삭제) 신설. 예약 1개만 두고 소비.

## 준비물

- 참조 `gil.py`(v2.29), Go `main.go`, `conformance.py`. `_git`(있음), `git ls-files`.

## 측정 방법

| 측정 | 성공 기준 |
|---|---|
| 마지막 예약 소비 open --git | 성공 (사이클 디렉토리 ∧ 커밋에 그 사이클 포함 ∧ reservations.tsv 삭제) |
| 커밋된 예약 소비 | 삭제가 커밋에 포함 (유령 예약 잔존 0) |
| 예약 여럿 소비 | 기존대로 정상 (원장에 남은 예약 유지) |
| 무예약 open, chain.md 첫 커밋 | 불변 |
| 참조↔Go | parity (동작 동일) |
| 판정기 | OPEN-LAST-RESERVATION PASS + 회귀 0 |

**기각선**: 위 중 하나라도 불충족.

## 사용자 컨펌

- 상현님 "자율로 고고" — C078이 이월한 선재 버그를 자율로 정복. "미완을 정직히 남기면 다음 가설의 재료"(C009).

- [x] 컨펌 받음 (일자: 2026-07-19, 자율 위임)
