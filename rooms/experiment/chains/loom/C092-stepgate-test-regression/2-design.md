# 2. 실험 설계 — write_cycle 정합 + 연쇄 테스트 수정

## 절차

### A. 근본: 테스트 헬퍼 write_cycle 정합 (한 곳)
1. `write_cycle(step=N)`(또는 status=closed → 5)이 스텝 1..N 파일을 **실질 내용**으로 생성하게 한다. "step=N 상태"라는 헬퍼 의미가 C090 가드와 정합 → write_cycle+step 테스트가 전이 가드에 안 걸린다.

### B. 연쇄: C090 새 계약에 맞게 개별 테스트 수정
2. **OPEN-CREATE**: "5-report 존재" → "1-hypothesis만 존재 + 5-report 부재"(open 1스텝 스캐폴딩 검증).
3. **STEP-OK**: "1→3 직접" → 순차(2 실질작성 → 3). 전이 가드 반영.
4. **STEP-SCOPE**: 1-hypothesis 실질작성 후 step 2(가드 통과) → 커밋에 2-design 포함·4·5 제외 검증.

### C. 방어: 리스트-cond가 sum(RESULTS)를 터뜨리지 않게
5. **WEB-AUTO-PURE-COMMIT**: `cycle_commit and ...` → `bool(cycle_commit) and ...`. 빈 리스트가 cond로 새면 `sum(RESULTS)`가 `int+list` TypeError. 근본은 A가 막지만, 방어선.

## 측정 방법
- CI 방식(gil 실제 실행)으로 conformance 끝까지 완주(TypeError 0).
- OPEN-CREATE·STEP-OK·STEP-SCOPE·NO-GIT-GRACEFUL PASS.
- STEP-GATE 등 C090 신규 테스트 계속 PASS.
- RELEASE-CYCLE-SOURCE는 **스코프 밖**(기존 별개 버그, 1-hypothesis에서 확정) — C093으로.

## 재현 환경
gil이 PATH에 없어 로컬 conformance가 조기 실패하던 문제를, `/tmp/gilbin/gil`(python3 절대경로 래퍼)를 PATH·--gil로 줘 CI(gil-gate)와 동일하게 완주시켜 검증한다.

## 사용자 컨펌
- 상현님 "차근차근 발자취 남기며". 스코프를 "C090이 깬 회귀"로 좁히고 RELEASE-CYCLE-SOURCE는 별개 사이클로 — 합의.
- [x] 컨펌 받음 (일자: 2026-07-20)
