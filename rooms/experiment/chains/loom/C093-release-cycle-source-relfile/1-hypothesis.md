# 1. 가설 수립 — RELEASE-CYCLE-SOURCE가 RELEASE.md를 안 만든다 (gil-gate 잔여 적색)

## 이전 사이클의 교훈

부모 **loom/C092**: C090이 깬 회귀를 잡아 conformance가 완주(121/122). 유일 잔여 FAIL = RELEASE-CYCLE-SOURCE. C092 5-report가 "RELEASE-DRIFT-GATE와의 상태 간섭 의심"으로 이월.

## 문제 진단 (규명 완료)

간섭이 아니었다. **`_mk_src_repo`(RELEASE-CYCLE-SOURCE 헬퍼)가 RELEASE.md를 만들지 않는다.** 이것이 호출하는 `_mk_release_repo`(RELEASE-DRIFT-GATE용 원본)는 CHANGELOG·f.txt·태그만 만들고 RELEASE.md는 안 만든다(drift 게이트는 봉인 전 단계라 RELEASE.md 불필요). 그런데 RELEASE-CYCLE-SOURCE는 release를 **실제로 봉인까지 성공**시켜야 하는데, release는 "RELEASE.md에 버전 서술"을 요구한다(C038). → release rc=1, 근거 사이클 미기록 → 기록=False.

내 격리 재현이 통과한 건 내가 수동으로 RELEASE.md를 넣었기 때문. 즉 **C086에서 이 테스트를 추가할 때 RELEASE.md 생성을 빠뜨린 테스트 자체의 결함**이다.

## 가설

> **가설**: `_mk_src_repo`가 RELEASE.md에 `## v1.1.0` 서술을 만들면(release가 봉인할 버전), RELEASE-CYCLE-SOURCE의 release가 rc=0으로 근거 사이클을 기록해 PASS하고, conformance가 122/122 완주해 gil-gate가 완전 녹색이 된다.

## 기각 조건

- RELEASE.md를 추가해도 release가 여전히 실패하면(다른 원인) 기각.
- 이 수정이 RELEASE-DRIFT-GATE 등 인접 테스트를 깨면 기각.
