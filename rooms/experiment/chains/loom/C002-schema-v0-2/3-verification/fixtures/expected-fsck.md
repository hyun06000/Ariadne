# 기대 위반 목록 (정답 고정)

> ⚠️ 이 문서는 **fsck 구현 전**에 고정되었다 (2026-07-14). 도구 출력에 맞춰 수정 금지.
> `bad/chains/test-bad/`는 규칙별 위반을 하나씩 담은 **가상 픽스처**다. 판정은 순서 무관 집합 비교.

## bad 픽스처가 일으켜야 하는 위반 — 정확히 아래 10건 (누락 0, 거짓 양성 0)

| # | 규칙 | 위치 | 위반 내용 |
|---|---|---|---|
| 1 | R1 | test-bad/C04-short-number | id 형식 위반 (번호가 3자리 미만) |
| 2 | R1 | test-bad (체인 수준) | 번호 005 중복: C005-dup-a, C005-dup-b |
| 3 | R2 | test-bad/C006-ghost-lineage | lineage `nowhere/C001-nope`가 존재하지 않음 |
| 4 | R3 | test-bad/C007-local-lineage | lineage `C001-ok`가 전역 표기가 아님 |
| 5 | R3 | test-bad/C008-qualified-parent | parent `test-bad/C001-ok`가 로컬 id가 아님 |
| 6 | R4 | test-bad/C003-bad-chain | chain 필드 `elsewhere` ≠ 소속 체인 `test-bad` |
| 7 | R5 | test-bad/C002-wrong-dir | id `C002-mismatch` ≠ 디렉토리명 `C002-wrong-dir` |
| 8 | R6 | test-bad/C009-ghost-parent | parent `C099-nope`가 존재하지 않음 |
| 9 | R7 | test-bad (체인 수준) | 순환: C010-loop-a ↔ C011-loop-b |
| 10 | R8 | test-bad/C012-status-lie | status closed인데 closed 일자 없음 |

위반이 없는 사이클: C001-ok (모든 규칙 준수, 다른 픽스처들의 부모 역할).

표기 규칙 세분 판정: 표기가 틀린 참조(R3)는 해소 검사(R2/R6)를 중복 보고하지 않는다.

## good 픽스처 — 위반 0건 (exit 0)

- `good/chains/alpha/C001-seed`: 닫힌 루트 사이클
- `good/chains/beta/C001-sprout`: `lineage: [alpha/C001-seed]` — 체인 간 계보의 정상 사례. log에서 lineage 주석이 표시되어야 한다.
