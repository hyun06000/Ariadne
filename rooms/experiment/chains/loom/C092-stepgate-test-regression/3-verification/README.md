# 3. 가설 검증 — write_cycle 정합 + 연쇄 수정

## 재현 (CI = gil-gate와 동일 환경)
```bash
# gil을 PATH·--gil로 실제 실행(CI 재현). python3 절대경로 래퍼로 PATH 비움 문제 회피.
cat > /tmp/gilbin/gil <<'SH'
#!/bin/sh
exec /usr/bin/python3 <레포>/rooms/deployment/ariadne-spec/gil.py "$@"
SH
chmod +x /tmp/gilbin/gil
python3 rooms/deployment/ariadne-spec/conformance.py --gil /tmp/gilbin/gil
```

## 결과
| 항목 | C092 전 | C092 후 | 판정 |
|---|---|---|---|
| sum(RESULTS) TypeError | 크래시(조기중단) | 완주 | ✅ 해소 |
| OPEN-CREATE | FAIL | PASS | ✅ |
| STEP-OK | FAIL | PASS | ✅ |
| STEP-SCOPE | FAIL | PASS | ✅ |
| NO-GIT-GRACEFUL | FAIL(래퍼 python3) | PASS | ✅ |
| WEB-AUTO-PURE-COMMIT | 리스트-cond 크래시 원인 | PASS | ✅ |
| STEP-GATE (C090 신규) | PASS | PASS | ✅ 무회귀 |
| **RELEASE-CYCLE-SOURCE** | **FAIL** | **FAIL** | **스코프 밖(기존 버그)** |

최종: 121/122. 유일 FAIL은 RELEASE-CYCLE-SOURCE — **C092 수정 전에도 FAIL**(git stash로 확인)이라 C090/C092가 만든 회귀가 아닌 별개 버그. C093으로 이월.

## 코드 변경 (conformance.py)
- `write_cycle`: step=N(닫힘=5)이면 스텝 1..N 파일을 실질 내용으로 생성(C090 가드 정합).
- OPEN-CREATE: 1스텝만 스캐폴딩 검증(5-report 부재).
- STEP-OK: 순차 2→3(각 스텝 실질작성 후 전이).
- STEP-SCOPE: 1-hypothesis 실질작성 후 step 2.
- WEB-AUTO-PURE-COMMIT: `bool(cycle_commit)`로 빈 리스트 cond 방어.

## 원인 진단 (RELEASE-CYCLE-SOURCE, 이월)
전체 실행 시 release가 rc=1: "RELEASE.md에 1.1.0 서술 없다". 격리 실행에선 통과 → 앞 테스트(RELEASE-DRIFT-GATE)와의 상태 간섭(work 경로·RELEASE.md 공유) 의심. C093에서 조사.
