# 3. 가설 검증

GUARD 섹션(conformance.py 1816~1849)을 v2 open→correct(author-경로)로 재작성하고,
셋업 부모(C001-mine)를 write_cycle 헬퍼로 지어 crash원(1840 `_seal_closed`)을 없앴다.

## 산출물

- `conformance.py` — 편집된 배포판 판정기 스냅샷(GUARD 섹션 v3화).
- `log-gated.txt` — `GIL_V2_OPEN=1` 실행 로그(게이트 상속, 무회귀 확인).
- `log-gateless.txt` — 게이트 없이 실행 로그(crash 소멸·통과 수 확인).

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec
GIL="python3 $(pwd)/gil.py"
# M4 무회귀 (게이트 상속): 121/121 기대
GIL_V2_OPEN=1 python3 conformance.py --gil "$GIL"
# M1·M2·M3 (게이트 없이): Traceback 0, 109 통과 기대
python3 conformance.py --gil "$GIL"
python3 conformance.py --gil "$GIL" 2>&1 | grep -c Traceback   # → 0
```

## 실행 기록

- 실행: 2026-07-22, macOS(Darwin 25.5.0), Python 3.9. gil.py **무변경**(conformance.py만).

### 측정 결과

- **M1 crash 소멸 — PASS(이정표).** 게이트 없이 Traceback **0**. crash 사슬
  open(330)→close(619)→step(1342)→withdraw(1476)→guard(92)가 여기서 **끊겼다**.
  판정기가 처음으로 게이트 없이 끝(2020)까지 완주한다. guard 섹션 셋업이 write_cycle로
  바뀌어 `_seal_closed`가 읽을 cycle.yaml이 항상 존재.
- **M2 게이트 없이 통과 — PASS.** 106 → **109**(+3). guard 3항목이 crash 대신 실제 PASS.
- **M3 guard 은퇴 독립 — PASS(핵심 성과).** 게이트 없이도 GUARD-PRIMARY-REFUSE가
  guard 거부 메시지 지문("주 작업공간")으로 PASS. 은퇴 안내("gil open은 이제 v3")와
  지문이 달라 **은퇴 우연 통과가 아니라 진짜 guard 동작**임이 판정으로 증명. OWNER-OK·
  LINKED-OK도 거부 메시지 부재로 guard 통과 검증. correct는 v3에서 은퇴하지 않는
  author-경로라 v2 open 은퇴와 무관하게 guard를 태운다.
- **M4 무회귀 — PASS.** 게이트 상속 conformance **121/121** 유지. (초기 120/121 회귀는
  write_cycle에 `closed` 날짜 누락 → R8 fsck 위반 → reserve 실패였고, `closed="2026-01-02"`
  추가로 해소 — 확립된 닫힌-사이클 헬퍼 관행.)
- **M5 다음 좌표 — 확정.** crash가 완전히 소멸했으므로 다음은 "crash 좌표"가 아니라
  게이트 없이 남은 **12개 FAIL 항목**(전부 v2 open 결합):
  GUARD-RESERVED-OK(예약 예외 open 전용) · OPEN-PROMOTES-OWNER · OPEN-SKIPS-RESERVED ·
  OPEN-LAST-RESERVATION-GIT · ROUND-OPEN · ROUND-OPEN-GIT · ROUND-CLOSE-VERDICT ·
  ROUND-LIST-SAFE · WORKTREE-SPAWN · WORKTREE-LAND · NO-GIT-GRACEFUL · FSCK-R15.
  crash 사슬이 아니라 **병렬 FAIL 목록** — 예약·라운드·워크트리축의 v3 재설계가 남은 일.
