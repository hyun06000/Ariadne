# 5. 결과 보고 — v3-build/C009-reconstruct-tree-from-git-log

부모: v3-build/C008-backtrack-is-a-new-commit (supported). 저자: Clew. 소환자: 없음 (main 단독·순차, C074에 따라 워크트리 미사용). 판정: **supported (채택)**.

## 요약

C008의 역방향을 검증했다: `git log`(커밋 시간순 + 메시지 서술)만으로 — steps.yaml 파일도, 커밋 diff도 읽지 않고 — 스텝 트리를 복원하는 `rebuild.py`를 짰더니, 복원된 트리가 원본 steps.yaml과 **위상 동형**이고 왕복(복원→steps.yaml)이 **바이트 동일**이었다. 4측정 ALL PASS, 산 잎(s10) 복원 도달 → **닫는다**. 결론: **깃 로그가 스텝 트리의 단일 진실원이 될 수 있고, steps.yaml은 파생 캐시다.**

## 무엇을 했나

1. **rebuild.py** (순수 stdlib): 오직 `git log --reverse --format=%s`만 읽는 복원기. C003 순환 상태기계의 **거울** — 쓰기 때 "팁 자동/`--to` 명시"였던 것이 읽기 때 "직전 계승/`from` 파싱"이 된다. 커밋 subject를 배타적 정규식으로 파싱(open/step/close).
2. **입력**: C008 build.sh로 C012→C014 10노드 트리(백트래킹 2개)를 임시 깃 저장소(메인 레포 밖, C005 규율)에 각인.
3. **measure.py** (4측정): M1 노드·parent 동형·M2 backtrack·outcome 동형·M3 깃 로그 단독(정적 감사)·M4 유일 결정성+왕복 무손실 — ALL PASS.

## 교훈

1. **깃이 진짜 단일 진실원이 될 수 있다.** C008은 "steps.yaml=진실원, 깃=각인 결과"라 정리했으나, C009는 그 역이 무손실임을 보였다. 왕복(steps.yaml→깃→steps.yaml)이 **바이트 동일**이니 둘 중 하나는 잉여다. 커밋 메시지 서술을 각인해두면(C008이 이미 함) **깃 로그가 트리를 완전히 담는다** — steps.yaml은 재생 가능한 편의 캐시. C008 정리의 정련.
2. **정보의 국소성 — 트리의 비자명한 정보는 극소.** 10노드에서 순환 규칙(C003)이 8노드의 parent를 결정하고, 저장해야 할 "비자명한 정보"는 딱 2곳(s5·s8의 parent=s1, 백트래킹 후 착지점)이었다. **시간순(깃이 공짜로 줌) + 규칙(C003) + 예외만 명시 = 트리.** C002 "id=시간순, 트리=포인터"의 심화.
3. **되돌아감이 "떠남"과 "도착" 두 커밋에 이중 각인돼 복원이 견고하다.** s4의 `(backtrack to s1)`(죽은 잎의 되돌아감 선언)과 s5의 `(new branch from s1)`(그 착지점)이 같은 s1을 가리킨다. 복원기는 전자로 backtrack 엣지를, 후자로 parent를 세운다.
4. **읽기·쓰기가 한 상태기계에서 나온다** (C003 원리의 세 번째 실증). C002 derive_action(읽기)·C003 growing_tip(쓰기)에 이어, C009 rebuild(깃→트리 복원)도 같은 순환 규칙을 쓴다. 데이터 모델이 뿌리면 각인·복원·판정이 한 규칙에서 파생된다.

## 다음 사이클을 위한 제안 (이 보고서가 부모)

- **C0xx — 커밋 메시지를 계약면으로 (trailer 스키마)**: 지금 서술(`(backtrack to sM)`)은 자연어에 가깝고 복원이 이에 의존하니 **사실상 스키마**다. 이를 엄격한 trailer(`Backtrack-To: s1`·`Branch-From: s1`)로 각인하면 파싱이 견고해지고 v3 fsck가 계약으로 검증 가능. C009 rebuild가 그 파서의 프로토타입.
- **C0xx — v3 fsck (깃↔steps.yaml 정합)**: 이제 복원이 있으니 fsck = "깃 로그로 복원한 트리 == steps.yaml 캐시"를 검사하면 된다. 불일치 시 캐시가 낡음(또는 손상). C009 measure.py의 M1·M2·M4가 그 엔진.
- **C0xx — body까지 깃에서 복원 / `gilv3 rebuild` 명령화**: 지금은 트리 구조만 복원(body는 커밋 diff에). rebuild를 gilv3 서브명령으로 승격하고 body(steps/*.md)까지 복원 범위 확장.
- 그 뒤(이월): 결과 잎 노드화(C002 재개, 상현님 이월 2순위) · BFS 팁 모호 · fail 일원화 · 포기 상태 · 뷰어 후속(Sheen) · v2 백업+rooms 보존.

## 정직한 경계

- **body(steps/*.md)는 복원 범위 밖**이다 — 이 사이클은 트리 **구조**(노드·parent·backtrack·outcome)만 깃 로그에서 복원했다. body 내용은 커밋 diff/스냅샷에 있고 `git log --format=%s`엔 없다. "깃이 단일 진실원"은 구조에 대해 참이고, body까지는 다음 사이클(git show/diff 사용)이 확장할 몫.
- 실사례는 C012→C014 **한 트리**만(백트래킹 2개, 단일 루트). 중첩 백트래킹·다중 루트·BFS 순서 각인의 복원은 미검증 — C008과 동일한 그리디 DFS 전제.
- 커밋 메시지 서술 형식에 복원이 의존한다(위 첫 제안이 이를 계약화로 굳히는 후속). 서술 형식이 바뀌면 rebuild.py 정규식도 바뀌어야 함 — 현재는 C008 각인 형식에 결합.

## 사이클 닫기

- [x] 4측정 ALL PASS, supported
- [ ] `cycle.yaml` status: closed (gil close가 처리)
- [ ] memory.md 기록
- [ ] 커밋·퍼블리시
