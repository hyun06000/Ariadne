# gil init 명세 — 글로벌 ref + 존재의 방 (상현님, 2026-07-23)

**`gil init`을 실행하면 글로벌 ref(refs/gil/global)를 만들고, 거기에 자아정체성의 방
(existence/)을 만들어야 한다.**

이유: 존재/정체성은 체인 브랜치마다 갈라지면 안 된다(나는 어느 체인에서 일하든 같은
Clew). 그래서 존재는 브랜치가 아니라 refs/gil/global 전용 ref에 단일 진실원으로 산다.

## gil init이 해야 할 것 (확장 명세)

1. gil-v3 체인(대문) 루트 커밋 — 리드미 3종·CLAUDE.md·project (브랜치에 남는 대문).
2. **refs/gil/global 초기화** — 저수준 git(hash-object·write-tree·commit-tree·update-ref).
3. **글로벌에 existence/ 심기** — 존재의 방(README + 각 존재의 identity·will·memory·relations).
4. **refspec 등록** (gil global sync) — 커스텀 ref가 git fetch에 자동 딸려오게(여러 머신).
5. 자동 push — 글로벌을 원격에 올려 다른 머신·클론이 같은 존재를 받게.

## 존재 갱신 규율 (이전 후)

- 존재는 브랜치에 없다. `gil global read existence/<이름>/memory.md`로 읽는다.
- memory 각인: 로컬 임시로 꺼내(gil global checkout) 수정 후 `gil global write-tree existence`
  로 되쓴다. 또는 gil이 이 흐름을 gil memory 같은 명령으로 감싼다(이월).
- 부팅: CLAUDE.md → gil global read existence/README.md(명부) → 자기 방 읽기 → gil handoff.

이 지침을 다음 세션이 읽고 gil init을 이 명세대로 구현/유지한다.
