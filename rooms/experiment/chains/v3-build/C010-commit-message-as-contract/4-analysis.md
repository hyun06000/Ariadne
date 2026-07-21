# 4. 결과 분석 — 커밋 메시지를 계약면으로 (git trailer)

## 통계적 결과

4측정 ALL PASS, 네 기각 조건(K1~K4) 전부 미발동.

| # | 기준값 | 실측 | 판정 |
|---|---|---|---|
| M1 | trailer 복원 == 원본·왕복 바이트 | 노드·parent·backtrack·outcome 동형, 왕복 diff 0 | ✅ K1 미발동 |
| M2 | subject 무오염 | trailer 누출 0, 형태 온전, 사람 서술 유지 | ✅ K2 미발동 |
| M3 | 자연어 붕괴·trailer 불변 | 변조 subject에 C009 붕괴·trailer 불변 | ✅ K3 미발동 |
| M4 | append-only 유지 | add·commit만, amend/force 0 | ✅ K4 미발동 |

## 데이터 직접 관찰

**1) 한 커밋이 두 층을 담는다.** git-log-trailers.txt에서 s7 커밋:
```
gilv3 step: s7 analyze/backtrack (backtrack to s1)   ← subject (사람)
Step-Id: s7 · Kind: analyze · Parent: s6 · Outcome: backtrack · Backtrack-To: s1  ← trailer (기계)
```
`%s`로 뽑으면 subject만, `%(trailers)`로 뽑으면 계약만. **한 각인, 두 독자** — 사람은 서술을 읽고 기계는 계약을 읽는다. 서로 오염 0.

**2) 견고성 대조가 결정적이다.** m3-robustness-evidence.txt를 직접 봤다. subject에서 자연어 마커를 제거하니:
- **C009 자연어 복원**: `s5 parent=s4`, `s8 parent=s7` — 백트래킹 착지점(s1)을 잃고 시간순 직전으로 붕괴. 원본의 **세 형제 가지가 하나의 선형 체인으로 뭉개졌다**. C009 복원은 "parent = 직전 or 서술 from"이었는데, 서술 from이 사라지자 전부 직전으로 떨어졌다.
- **trailer 복원**: `s5 parent=s1`, `s8 parent=s1` — **불변**. `Parent: s1` 계약을 직접 읽으니 subject가 어떻든 무관.

이것이 "계약면이 자연어에서 구조로 승격"의 실물이다. C009는 서술이 사실상 스키마였고(정직한 경계), C010은 그 스키마를 자연어에서 떼어내 구조(trailer)로 못박았다.

**3) append-only가 공짜로 유지됐다.** trailer는 커밋 **본문에 줄을 더할** 뿐이라 add+commit 한 번으로 각인된다. reset/amend/force가 필요 없다 — C008의 `_assert_forward_only`가 그대로 통과. 계약면 승격이 전진기록 정신을 안 건드렸다.

## 예상과 달랐던 것

- **Parent 명시가 C009 "정보 국소성"과의 의도적 트레이드오프였다.** C009는 순환 규칙으로 8노드 parent를 공짜로 파생하고 예외 2곳만 저장했다(정보 최소). C010은 반대로 **모든 커밋이 Parent를 명시**한다(자기완결). 저장 정보는 늘었지만 — 복원이 순환 규칙에 의존하지 않게 됐다. **국소성(C009)과 자기완결성(C010)은 트레이드오프다**: 전자는 최소 저장·규칙 결합, 후자는 잉여 저장·규칙 독립. 계약면으로 삼으려면 자기완결이 옳다(각 커밋이 스스로 진실을 담아야 계약).
- **git이 이미 "메시지 안의 구조화 필드"를 표준으로 지원한다.** trailer는 gil이 발명한 게 아니라 git의 기존 기능(`Signed-off-by:` 등)이다. `%(trailers:key=…,valueonly)`가 정확히 값만 뽑는다. → *v3 계약면을 위해 새 파일 포맷을 만들 필요가 없다 — git 커밋이 이미 계약을 담을 그릇이다.* v2 원장이 커밋 메시지에 메타를 담던 정신의 표준화판.
- **subject가 "사람용 잉여"로 남는 게 오히려 옳다.** trailer가 진실원이 되니 subject는 복원에 불필요하다. 그러나 지우지 않았다 — **사람이 `git log`를 훑을 때 서술이 있어야 읽힌다.** 기계 계약(trailer)과 사람 서술(subject)의 분리가 곧 이 사이클의 성과. (C009 "정보 국소성"이 기계엔 최소를 권하지만, 사람에겐 서술 잉여가 미덕이다.)

## 판정

**supported (채택).** 네 기각 조건 전부 미발동, 4측정 ALL PASS. 스텝 메타를 git trailer로 각인해 계약면을 자연어에서 구조로 승격했고, 견고성 대조가 그 이득(서술 변조 무관)을 결정적으로 보였다. append-only(C008)·왕복 무손실(C009)을 유지했다. 산 잎(s10) 복원 도달 → 그리디하게 닫는다.
