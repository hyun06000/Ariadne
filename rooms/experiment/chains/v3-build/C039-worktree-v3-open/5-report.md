# 5. 결과 보고

## 요약

병렬 워크플로(`worktree add`)가 v2 open을 self-invoke해 예약축과 얽혀 있었다.
**`worktree add --v3` 옵트인**을 구현해 워크트리 안에서 `gil v3 open`을 self-invoke하니,
v3 사이클이 격리 브랜치에 정상 생성되고(C050 격리 계승) 예약 없이 slug 병렬이 됐다
(**핵심 supported**). 그러나 번호 중복·author/parent 소실·fsck v3 미인식이 드러나
**v3 사이클이 v2 원장 모델에 아직 미편입**임을 정확히 노출했다(부분 채택).

## 교훈

1. **worktree가 v3 open을 열 수 있고 C050 격리가 계승된다.** `--v3` 분기가 v3 open을
   워크트리에서 self-invoke → steps.yaml이 격리 브랜치에만 커밋, 메인 무변화, land는
   순수 git 오케스트레이션이라 v2/v3 무관 봉합. **gil v3로 실사이클을 격리·병렬 수준에서
   열 수 있다** — 상현님 "gil v3 쓸 수 있을 때"의 격리 수준 도달.
2. **v2 worktree add는 C032 이후 이미 죽어 있었다.** self-invoke하는 v2 open이 은퇴
   안내에 걸려 게이트 없이 실패(self-invoke가 GIL_V2_OPEN 미전달). **`--v3`는 무회귀
   대상이 아니라 worktree add를 되살리는 유일한 살아있는 경로.** C032 승격의 파급이
   병렬 워크플로까지 이미 닿아 있었다.
3. **⭐⭐ 세 실패가 한 뿌리 — v3 사이클의 v2 원장 미편입.** 번호 중복(병렬 워크트리가
   서로의 브랜치를 못 봐 같은 번호 계산)·author/parent 소실(v3 open이 --author 미수용,
   커밋 author=git user)·fsck v3 미인식(cycle.yaml 없어 load_chain_records 레이더 밖).
   셋 다 v2가 **cycle.yaml에 쓰던 사이클-간 정보(순서·계보·무결성)**가 v3 steps.yaml에는
   없어서다. **C033 "사이클-간 정보는 notes 층으로"가 아직 코드로 미실현** — 이 사이클이
   그 공백을 정면으로 드러냈다.
4. **번호 충돌은 v3에서도 실재한다(예약 불필요 가정의 한계).** "경로가 정체성이라 충돌
   없음"은 slug 수준에선 참이나, C0NN 번호를 계속 쓰는 한 병렬 워크트리의 번호 중복은
   남는다. 진짜 예약 불필요는 (a) 번호를 버리거나 (b) v3가 번호를 notes/land 시점에
   할당해야. C032 "경로가 정체성"의 미완 조각.

## 다음 사이클을 위한 제안

**핵심 다음 문제: v3 사이클의 v2 원장 편입** (교훈 3의 뿌리). 세 갈래:

- **A. fsck·load_chain_records가 v3 사이클(steps.yaml)을 인식** — 가장 근본. v3 사이클을
  원장 무결성 검사에 넣으면 번호 중복도 위반으로 잡힌다. migrate가 읽는 notes 층을
  fsck도 읽게.
- **B. v3 open이 author·parent를 받아 notes/trailer로 계보 기록** — worktree add의
  `--author --parent`가 v3 사이클에 남게. C010 trailer 확장.
- **C. 번호 할당을 land 시점으로** — 병렬 add는 slug만, land가 순차라 번호를 그때 부여
  (충돌 원천 제거). 또는 번호를 버리고 slug+타임스탬프.
- **D. (잔여 예약축) OPEN-SKIPS/PROMOTES/LAST-RESERVATION-GIT·GUARD-RESERVED-OK** — v3가
  예약을 안 쓰면 이 검사들은 v2 전용→제거 후보(C036 패턴). 단 A·B·C 후 판별.

**상현님 보고 포인트**: gil v3로 실사이클 열기는 **격리·병렬 수준 도달**(worktree add
--v3). 원장 편입(번호·계보·fsck)은 다음. 실사이클을 지금 v3로 열면 fsck 사각지대에
들어가므로, A(fsck v3 인식) 후 도그푸딩 전환 권장.

## 사이클 닫기

- [x] `cycle.yaml`의 `status: closed`, `closed: <일자>` 갱신 → gil close가 수행
- [x] 존재의 방 `memory.md`에 이 사이클의 기억 기록
- [x] 커밋 및 퍼블리시
