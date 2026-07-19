# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C078**(guard 예약 예외)이 예약된 존재가 main에서 자기 사이클을 열 수 있게 하면서, 그 검증·실측 중 **선재 버그**를 발견해 정직히 이월했다: 마지막 예약을 소비하는 `open --git`이 실패한다. C078은 이 버그를 우회(예약 2개)해 검증했고, 이번 사이클이 그 이월을 갚는다.

## 문제 분할

`cmd_open`이 예약을 소비할 때(consumed) reservations.tsv를 원장에서 지운다. 마지막 예약이면 `_save_reservations`가 **파일을 삭제**한다. 그런데 `--git` 경로가 그 삭제된 파일 경로를 `git add -A -- <paths>`에 넘긴다.

- **git add `-- <path>`의 동작 (실측)**: tracked 파일의 삭제는 스테이징된다(정상). 그러나 **tracked인 적 없는 경로가 부재하면** `fatal: pathspec did not match`로 **거부**한다.
- 예약이 아직 커밋된 적 없이(untracked) 소비·삭제되면 → git add가 그 경로를 거부 → **커밋 통째 실패**.

이번 사이클의 문제: **삭제됐고 tracked도 아닌 reservations.tsv 경로를 git add/commit paths에서 제외**해, 마지막 예약 소비 open도 각인되게 한다.

### 재현 (스텝1에서 확인)
```
open demo first --new-chain --git;  reserve demo only --for clew;
open demo only --author clew --parent C001-first --git
→ 오류: git add -A -- …/C002-only …/reservations.tsv 실패:
  fatal: 'reservations.tsv' 경로명세가 어떤 파일과도 일치하지 않습니다
```
- **사이클 디렉토리는 생성됐으나 커밋 안 됨** — 원장(파일시스템)엔 열렸는데 깃엔 미각인. 불일치 상태.
- **exit=0으로 오보** — 에러 메시지는 나오나 종료코드 0(도구가 실패를 성공으로 보고). 이중 결함.
- 원본 gil에서도 재현 — C078 무관한 선재 버그.

## 가설

> **가설**: `cmd_open`의 `--git` 경로에서 reservations.tsv를 add/commit paths에 넣는 조건을, "consumed면 무조건"에서 **"consumed이고 (파일이 존재하거나 tracked이면)"**으로 좁히면, (a) 마지막 예약 소비 open이 정상 각인되고(디렉토리·커밋 일치), (b) 커밋된 예약을 소비하는 경우엔 삭제가 여전히 스테이징되며, (c) 기존 정상 경로(예약 여럿·무예약·chain.md)는 불변이다.

## 기각 조건

- 수정 후에도 마지막 예약 소비 open이 실패하거나 커밋이 안 되면 → 기각.
- 커밋된 예약(tracked)을 소비할 때 삭제가 커밋에서 누락되면(원장에 유령 예약 잔존) → 기각.
- 예약 여럿·무예약·chain.md 첫 커밋 등 기존 경로가 하나라도 깨지면 → 회귀, 기각.
- 판정기가 이 버그(마지막 예약 소비 실패)를 관측·판정 못 하면 → 계약 미봉인.
