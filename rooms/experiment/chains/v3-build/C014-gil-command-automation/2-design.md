# 2. 검증 설계

## 철학 충돌의 정확한 해소 (C008 ↔ C011)

이 사이클의 설계 핵심은 코드가 아니라 **개념 정정**이다. C008은 "깃=append-only 전진기록"을 세우며 `_assert_forward_only`가 HEAD 전진 단조성을 집행했다 — 그런데 그 집행이 **두 가지 다른 것을 뭉뚱그렸다**:

- **(A) 커밋을 지우지 않음** — `reset --hard`·`amend`·`rebase`·`push --force`가 하는 것. 히스토리 재작성. **이것이 append-only의 진짜 가치다** (닫힌 커밋 불변, '벽의 지도' 보존).
- **(B) HEAD를 뒤로 옮기지 않음** — `checkout <조상>`이 하는 것. 그러나 **커밋은 하나도 안 지운다** — HEAD 포인터만 이동한다.

C008은 (A)를 지키려고 (B)까지 금지했다. **C011의 정정은**: 백트래킹=checkout은 (B)를 하지만 (A)는 절대 안 한다 — 되돌아간 조상에서 새 커밋을 치면 깃이 **새 가지**를 칠 뿐, 죽은 가지 커밋은 dangling으로 그대로 산다. 그래서 **append-only의 진짜 계약은 "커밋 도달가능성 단조 증가"** — 커밋 집합은 오직 늘어난다(줄지 않는다). checkout은 이걸 지키고, reset/amend는 깬다.

→ **`_assert_forward_only`를 `_assert_append_only`로 정정**: "각인 후 이전에 있던 모든 커밋이 여전히 존재하는가"(도달가능성 보존)를 집행. HEAD 전진이 아니라 **커밋 불소멸**을 본다. checkout 백트래킹은 통과, reset/amend는 거부.

## 구현 설계 — gilv3.py C014판

C010판을 C014 디렉토리로 복사 후 진화(v3-build 규율). 변경 4곳:

### (1) 커밋↔스텝 id 매핑 기억
checkout할 조상을 알려면 "s1이 어느 커밋인가"가 필요하다. build_branches.sh는 `remember`/`ci` 헬퍼로 했다. gilv3는 **각 스텝 커밋의 trailer(`Step-Id`)를 역인덱스**로 조회 — steps.yaml에 커밋 해시를 저장하지 않는다(C005 "steps.yaml에 깃 메타 안 넣음" 유지). `git log --all --format=%H` + trailer로 sid→hash 맵 구성.

### (2) step의 백트래킹 분기 = checkout + 커밋
`state == "dead_leaf"` 이고 새 형제 가지(`--to <ancestor-define>`)일 때:
- 지금(C010): 그냥 다음 커밋을 선형으로 쌓음 → 깃 그래프 선형.
- C014: **먼저 `git checkout <조상 커밋>`**(detached HEAD) → 그 위에서 새 스텝 커밋 → 깃이 자동 분기. build_branches.sh의 `git checkout $(ci s1)` 그대로.
- 단 이때 `_assert_append_only`는 checkout으로 HEAD가 뒤로 가도 **커밋 집합이 안 줄었으니 통과**.

### (3) analyze/backtrack outcome 시 checkout 준비
`outcome == "backtrack"` 커밋(죽은 잎)을 친 뒤, **다음 step이 새 가지를 열 것**이므로 이 시점엔 아무것도 안 함(죽은 잎도 전진 커밋). checkout은 그 다음 step(새 hypothesis)에서 일어난다 — C011 build_branches.sh 순서와 동일(analyze backtrack 커밋 → checkout → 새 hypothesis).

### (4) `_assert_forward_only` → `_assert_append_only` 정정
- before: 각인 전 `git rev-list --all` 커밋 집합 스냅샷.
- after: 각인 후 그 집합이 **부분집합으로 보존**되는가(모든 이전 커밋 여전히 존재).
- 위반 시 거부: "커밋이 사라졌다 — 히스토리 재작성(reset/amend/rebase) 금지". checkout은 커밋을 안 지우니 통과.

## 검증 (measure.py — 순수 깃 감사 + rebuild 재사용)

C011 build_branches.sh가 손으로 짠 그 트리(체인·사이클·백트래킹 3층, 죽은 잎 2·산 잎 1)를 **이번엔 gilv3.py 명령으로만** 재현한다. build_case.sh가 `gilv3 open`·`gilv3 step`만 호출(생 git checkout 0 — 도구가 안에서 함).

- **M1 — 깃 그래프 분기**: 도구가 만든 저장소에서 `git log --all --graph`가 선형이 아닌 분기를 그린다. 죽은 가지 2 + 산 가지 1 = 세 갈래가 s1에서 갈라짐. build_branches.sh 그래프와 위상 대조.
- **M2 — steps.yaml ↔ 깃 그래프 동형**: steps.yaml의 parent/backtrack 포인터로 만든 논리 트리 == 깃 커밋 부모 그래프(trailer Step-Id로 라벨). 도구가 만든 두 표현이 일치.
- **M3 — trailer 복원 무손상**: C010 rebuild_trailer.py를 도구 저장소에 걸어 원 트리 복원 → steps.yaml과 동형. checkout 도입이 복원을 안 깸.
- **M4 — append-only 보존 + 정정 집행**: ① 도구 실행 전 과정에서 커밋 집합 단조 증가(죽은 가지 커밋 안 사라짐, `git rev-list --all` 추적). ② **음성 대조**: 정정된 `_assert_append_only`가 진짜 위반(강제로 reset/amend 시도)을 여전히 거부하는가. ③ 죽은 가지가 태그 없이도 이 시점엔 `--all`에 보임(브랜치 팁이라) — 잎=태그 자동화는 다음 사이클이므로 여기선 도구가 만든 브랜치 ref로 생존 확인.
- **M5 — 회귀 0**: 선형 사이클(백트래킹 없는 open→step×N→close)이 C010과 동일 동작. trailer 각인·view·close 봉인 불변.

## 재현성

- gilv3.py C014판 + build_case.sh + measure.py를 3-verification/에.
- 임시 저장소는 세션 스크래치(메인 레포 밖).
- C010 rebuild_trailer.py를 경로 참조로 재사용(재구현 금지, C005 정신).

## 성공 기준

M1~M5 ALL PASS → supported: 백트래킹=checkout이 도구 동작이 됐고, C008이 C011로 정직하게 정정됐으며(append-only의 진짜 계약=커밋 불소멸), 회귀 0. 하나라도 기각 → 가설/설계 수정.
