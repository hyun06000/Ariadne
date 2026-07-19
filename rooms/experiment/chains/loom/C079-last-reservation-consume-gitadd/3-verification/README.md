# 3. 검증 — 마지막 예약 소비 open --git 각인

## 결과 (양 구현)
| 케이스 | 수정 전 | 수정 후 |
|---|---|---|
| 마지막 예약 소비 open --git | git add 실패, 커밋 누락(디렉토리만) | 정상 각인(디렉토리 ∧ 커밋 ∧ 원장 비움) |
| 커밋된(tracked) 예약 소비 | — | 삭제가 git에 반영(유령 없음) |
| 예약 여럿 중 하나 소비 | 정상 | 정상(나머지 유지) |

- 참조 **103/103**·Go **89/89** (OPEN-LAST-RESERVATION-GIT 신설, 회귀 0).
- 수정 전 참조 102/103·Go 88/89 (FAIL: committed=False).

## 수정
- 참조 `cmd_open`(783-785 →): consumed 시 reservations.tsv 경로를, **파일 존재 OR tracked(`git ls-files --error-unmatch`)**일 때만 add/commit paths에 포함. 삭제·미tracked면 제외(git add pathspec 거부 회피).
- Go `cmd_open`(1087 →): 동형(`os.Stat` OR `ls-files` code==0).
- 판정기 OPEN-LAST-RESERVATION-GIT 신설(git 저장소 resv_sandbox, 예약 1개 소비, 커밋 포함·유령 없음 검증).

## 근본 원인
`git add -A -- <path>`는 tracked 파일 삭제는 스테이징하나, **tracked인 적 없는 부재 경로는 `fatal: pathspec did not match`로 거부**한다(실측). 예약이 커밋 전(untracked) 소비·삭제되면 그 경로를 넘겨 커밋 통째 실패.

## 부수 관찰 (수정으로 자연 해소)
수정 전엔 이 실패가 `exit=0`으로 오보됐다(에러 메시지는 나오나 종료코드 0). 수정으로 실패 경로가 사라져 해소. `_refresh_viewers` 등 후속 단계가 예외를 삼켰을 가능성 — 별도 점검 후보(open의 부분 실패 시 exit 전파).
