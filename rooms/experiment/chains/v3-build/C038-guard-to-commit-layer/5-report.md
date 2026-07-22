# 5. 결과 보고

## 요약

GUARD 섹션(C050 병렬 안전 검사)이 v2 open 위에 지어져 있어 v2 open 은퇴 시 crash·의미
붕괴를 일으켰다. **guard 동작 검사를 v2 open이 아니라 v3에서 살아남는 author-경로
`correct`로 재작성**하고 셋업 부모를 write_cycle 헬퍼로 지으니, 게이트 없이 **crash가
완전히 소멸**(판정기 첫 완주)하고 통과 106→109, 게이트 상속 121/121 유지, guard가 v2
open 은퇴에 독립해 C050 안전이 버전 무관하게 검증됐다. **채택(supported).**

## 교훈

1. **guard는 open의 기능이 아니라 커밋-층 계약이다.** `_guard_primary_owner(repo, author)`는
   "author가 이 주 체크아웃에 커밋할 자격이 있는가"를 판정하는 순수 함수로, open·correct
   두 진입점서 호출된다. v2 open이 은퇴해도 correct(v3에서 살아남는 author-필수 명령)가
   guard를 태우므로 안전 계약은 온전히 검증된다. **인터페이스(open→correct)는 바뀌어도
   계약(주 체크아웃 소유)은 불변** — C032 "인터페이스 정체성 전환"의 guard판.
2. **은퇴 우연 통과를 지문으로 구별하라.** 게이트 없이 open으로 guard를 검사하면 은퇴
   안내("gil open은 이제 v3")가 rc≠0을 내 검사가 우연히 초록이 된다(guard 아니라 은퇴를
   검사). correct는 은퇴 안 하므로 rc≠0이 오직 guard에서만 오고, 거부 메시지 지문("주
   작업공간이다")으로 진짜 guard 동작임을 판정에 못박는다.
3. **crash 사슬은 "즉시 파일 소비 셋업"의 목록이었고, 그게 다 떨어지면 끝난다.**
   C034~C037의 crash 이동 사슬(open→close→step→withdraw→guard)이 여기서 종결.
   crash는 "v2 open을 파일 읽기로 즉시 소비하는 셋업"에서만 났고, guard가 마지막 고리였다.
   **다음 정신모델은 "crash 최전선"이 아니라 "게이트 없이 남은 12개 병렬 FAIL 목록"**
   (예약·라운드·워크트리·open축) — 순차가 아니라 독립 처리 가능.
4. **닫힌-사이클 셋업 헬퍼는 fsck 계약을 지켜야 한다.** write_cycle(status=closed)에
   `closed` 날짜를 안 주면 R8 위반 → 하류 reserve가 fsck에서 거부 → 검사 붕괴(계측기
   오염, 반증 아님). 확립된 관행: `status="closed", closed="<일자>"`를 항상 함께.

## 다음 사이클을 위한 제안

crash가 소멸했으므로 여정의 국면이 바뀐다 — 이제 "게이트 없이 남은 12 FAIL"을 축별로
v3화하는 병렬 작업이다:

- **A. 예약축 v3 재설계** (GUARD-RESERVED-OK·OPEN-PROMOTES-OWNER·OPEN-SKIPS-RESERVED·
  OPEN-LAST-RESERVATION-GIT) — 매듭 순서 2번과 통합. 예약 예외는 open 전용이라 v3 open이
  author·예약을 받는 표면을 설계해야. **사이클-간 계보(번호 선점)를 v3가 어느 층에서
  다루는가**의 핵심 질문.
- **B. 라운드축 v3화** (ROUND-OPEN·ROUND-OPEN-GIT·ROUND-CLOSE-VERDICT·ROUND-LIST-SAFE) —
  라운드가 v2 open으로 사이클을 여는 부분.
- **C. 워크트리축** (WORKTREE-SPAWN·WORKTREE-LAND) — 병렬 소환의 v2 open 결합.
- **D. 잔여** (NO-GIT-GRACEFUL·FSCK-R15) 개별 판별.
- **E. 게이트 완전 제거** — A~D 완료로 게이트 없이 초록 시 GIL_V2_OPEN 자체 제거 =
  완전 버전리스.

## 사이클 닫기

- [x] `cycle.yaml`의 `status: closed`, `closed: <일자>` 갱신 → gil close가 수행
- [x] 존재의 방 `memory.md`에 이 사이클의 기억 기록
- [x] 커밋 및 퍼블리시
