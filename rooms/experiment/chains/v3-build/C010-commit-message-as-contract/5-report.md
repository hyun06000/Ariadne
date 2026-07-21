# 5. 결과 보고 — v3-build/C010-commit-message-as-contract

부모: v3-build/C009-reconstruct-tree-from-git-log (supported). 저자: Clew. 소환자: 없음 (main 단독·순차, C074에 따라 워크트리 미사용). 판정: **supported (채택)**.

## 요약

C009가 남긴 정직한 경계 — "복원이 커밋 subject의 자연어 서술에 결합돼 있다" — 를 갚았다: 스텝 메타(Step-Id·Kind·Parent·Outcome·Backtrack-To)를 **git trailer**로 커밋 본문에 각인해 계약면을 자연어에서 **구조**로 승격했다. trailer 복원이 C009와 동일 트리(왕복 바이트 동일)를 내면서, **subject의 자연어를 망가뜨려도 불변**임을 견고성 대조로 실증했다(같은 조건에서 C009 자연어 복원은 세 형제 가지가 선형으로 붕괴). 4측정 ALL PASS → **닫는다**.

> **명명 정정 (상현님, 이 사이클 중)**: 이 도구는 별개 프로토타입 gilv3가 아니라 **gil 그 자체의 v3 궤도**다. 이 사이클의 확장은 **gil v3.5**. gil v2(v2.50.0)가 사이클 단위였다면 gil v3는 스텝 트리 단위. (파일명은 프로토타입 단계라 gilv3.py 유지.)

## 무엇을 했나

1. **gil v3.5** (C008 v0.4 복사 확장, 닫힌 사이클 원본 불변): `git_imprint`가 `trailers` 인자를 받아 커밋 본문에 `Key: Value`로 각인. open/step이 스텝 메타를 trailer로 전달(close는 봉인이라 trailer 없음). append-only(add·commit만)·`_assert_forward_only`(C008) 유지. `GILV3_SCRAMBLE_SUBJECT` 견고성 대조 모드.
2. **rebuild_trailer.py**: `git log --format=%(trailers:key=…,valueonly)`만 읽어 트리 복원 — subject 자연어 파싱 0. C009 rebuild의 후계.
3. **measure.py** (4측정): M1 동형+왕복·M2 subject 무오염·M3 견고성 대조(변조 subject)·M4 append-only — ALL PASS.

## 교훈

1. **계약면은 자연어가 아니라 구조여야 한다.** C009 복원은 subject 서술(`(backtrack to s1)`)에 결합돼 있어, 서술을 바꾸면 트리가 붕괴한다(M3: s5·s8 parent가 s1→s4·s7로 무너짐). trailer는 `Parent: s1`을 직접 담아 서술과 무관하게 불변. **git trailer가 v3 스텝 계약면의 그릇이다** — git이 이미 표준 지원(`%(trailers)`)하므로 새 파일 포맷이 불필요. v2 원장이 커밋 메시지에 메타를 담던 정신의 표준화판.
2. **한 커밋이 두 독자를 섬긴다.** subject(사람용 서술)와 trailer(기계용 계약)가 한 커밋에 공존하며 서로 오염 0. `%s`는 서술만, `%(trailers)`는 계약만. **기계엔 최소·정확을(C009 국소성), 사람에겐 서술 잉여를(가독)** — 두 요구가 한 커밋에서 분리돼 충족된다.
3. **국소성(C009)과 자기완결성(C010)은 트레이드오프다.** C009는 순환 규칙으로 parent를 파생해 저장을 최소화했고(규칙 결합), C010은 모든 커밋이 Parent를 명시해 복원을 규칙에서 풀었다(잉여 저장·규칙 독립). **계약면으로 삼으려면 자기완결이 옳다** — 각 커밋이 스스로 진실을 담아야 계약이 견고하다.
4. **계약 승격이 append-only를 안 건드렸다** (C008 유지). trailer는 커밋 본문에 줄을 더할 뿐이라 add+commit 한 번으로 각인. reset/amend/force 불필요.

## 다음 사이클을 위한 제안 (이 보고서가 부모)

- **C0xx — v3 fsck (깃 trailer ↔ steps.yaml 정합)**: 이제 계약면이 구조(trailer)이니 fsck가 이를 검증할 수 있다 — ① 필수 trailer 존재(Step-Id·Kind·Parent), ② trailer 값 정합(Kind가 순환 규칙 준수, Backtrack-To가 조상 define), ③ **trailer 복원 트리 == steps.yaml 캐시**(불일치=캐시 낡음/손상). C010 rebuild_trailer + C009 measure가 그 엔진. **이제 fsck의 선행 조건(계약면 구조화)이 갖춰졌다** — C009→C010이 갚은 빚의 수확점.
- **C0xx — body까지 trailer/커밋에서 복원 / `gilv3 rebuild` 명령화**: 지금은 트리 구조만 복원(body는 커밋 스냅샷에). rebuild를 gil 서브명령으로 승격하고 body 복원 범위 확장.
- **C0xx — trailer 스키마 문서화·버저닝**: 계약면이 됐으니 스키마(키 목록·필수/선택·값 도메인)를 명문 문서로. gil v3 스펙의 일부.
- 그 뒤(이월): 결과 잎 노드화(C002 재개, 상현님 2순위) · BFS 팁 모호 · fail 일원화 · 포기 상태 · 뷰어 후속(Sheen: 상태 배지·3층 드릴다운·Go) · v2 백업+rooms 보존.

## 정직한 경계

- **파일명은 여전히 gilv3.py**다 — 상현님의 "gil v3.5" 명명은 버전 서사에 반영했으나(헤더·문서), 파일명·명령 문자열(`gilv3 open`)은 프로토타입 단계라 유지. 도구가 rooms/deployment로 배포될 때 gil 본체와의 통합 명명을 정할 몫.
- **body(steps/*.md)는 여전히 복원 범위 밖** (C009와 동일 경계) — 이 사이클은 트리 **구조** 계약만 trailer로. body는 커밋 스냅샷/diff에.
- 실사례는 C012→C014 **한 트리**(백트래킹 2개). trailer 스키마가 중첩 백트래킹·다중 루트·fail outcome에서도 충분한지는 미검증 — 그 케이스가 나오는 다음 사이클이 확장.
- Parent 명시가 저장 잉여를 늘린다(C009 국소성 대비) — 계약 견고성을 위한 의도적 선택이나, 대규모 트리에서 커밋 본문 크기 증가는 실측 안 함.

## 사이클 닫기

- [x] 4측정 ALL PASS, supported
- [ ] `cycle.yaml` status: closed (gil close가 처리)
- [ ] memory.md 기록
- [ ] 커밋·퍼블리시
