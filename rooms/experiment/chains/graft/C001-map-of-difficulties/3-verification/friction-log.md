# Friction Log — graft/C001 어려움의 지도

관찰 대상: **Flask** (github.com/pallets/flask), `git clone --depth 200` → 676커밋 · 16태그(`2.2.3`…) · CHANGES.rst.
gil: 참조 구현 gil.py (로컬 v2.35 상당), `python3 gil.py`로 호출.
관찰 방식: Flask 레포 안에서 준비 없이 gil 명령 실행, 일어난 그대로 기록.

각 마찰: `[F##] 증상 — 명령/출력 — 범주`.

---

## 범주 정의 (관찰 후 확정)

- **A. 도구 전제 위반 (골격 부재)** — gil은 `rooms/experiment/chains` 골격이 cwd에 있다고 전제. 레거시엔 없다.
- **B. 개념 부재 (존재·계보)** — 레거시엔 chain/cycle/존재의 방이 없다. gil의 개념적 선행조건이 비어 있다.
- **C. 이름공간 충돌 (역사의 공존)** — 레거시가 이미 점유한 태그·CHANGELOG를 gil이 무시하거나 침묵.
- **D. 인터페이스 비대칭 (진입 경로)** — 레거시를 대상으로 지정하는 일관된 방법이 없다.

---

## 마찰 원장

### [F1] `log`/`fsck`/`web`은 레거시 저장소를 대상으로 지정할 수 없다 — `--root`가 open 전용
- 명령: `gil log --root <flask>` / `gil fsck --root <flask>`
- 출력: `error: unrecognized arguments: --root`
- 사실: `--root`는 `open`에만 있음. `log`/`fsck`/`web`/`verify`/`handoff`는 `chains_root` **위치인자**(기본 `rooms/experiment/chains`, 상대경로)만 받음 → "cwd가 곧 저장소"라는 강한 전제.
- **범주 D** (진입 경로 비대칭). 결과적으로 레거시에 붙이려면 그 안으로 `cd`해야만 함.

### [F2] 골격이 없으면 조회 명령이 전부 죽는다
- 명령: (Flask 안에서) `gil log` / `gil fsck` / `gil web`
- 출력: `오류: 체인 루트가 없다: rooms/experiment/chains`
- 사실: `rooms/experiment/chains`가 없으면 읽기 명령이 에러로 종료. 레거시 레포는 이 골격이 없으므로 **채택 첫 순간부터 대부분의 명령이 막힘**. `open --new-chain`만이 유일한 진입.
- **범주 A** (골격 부재).

### [F3] `gil releases`가 레거시의 실제 16개 태그·CHANGES.rst를 "0개"로 침묵
- 명령: (Flask 안에서) `gil releases`
- 출력: `배포 계보 — 0개 릴리스 [T=태그 C=CHANGELOG]` / `gil:releases 0 drift=0`
- 사실: Flask는 `2.2.3`, `2.3.0` 등 **실제 16개 릴리스 태그**와 `CHANGES.rst`를 가짐. gil은 `v<semver>` 형식 태그 + 자기 CHANGELOG(`RELEASE.md`/CHANGELOG.md 계열)만 인식 → **에러가 아니라 조용히 0으로 보고**. 레거시의 진짜 배포 역사가 gil의 시야에서 사라짐.
- **범주 C** (이름공간 충돌). **가장 위험** — 실패가 아니라 침묵이라 사용자가 손실을 눈치채지 못함.

### [F4] `open --new-chain --new-root`는 골격을 자동 생성하며 성공 — 유일한 진입점
- 명령: (Flask 안에서) `gil open mychain first-cycle --title test --author alice --new-chain --new-root`
- 출력: `열림: mychain/C001-first-cycle`. `rooms/experiment/chains/mychain/{chain.md, C001-.../5스텝+cycle.yaml}` 생성. 이후 `fsck`·`log` 정상 동작(위반 0).
- 사실: gil은 `_template`이 없어도 스텝 스텁을 스스로 만듦. **긍정적 관찰** — 채택의 씨앗은 이미 작동. 단 이것이 "레거시를 정리하는" 절차와 연결돼 있지 않음(rooms/만 덩그러니 생김).
- **범주 A→해소 가능성**. 다음 사이클(이주 절차)의 발판.

### [F5] `--author alice`가 존재의 방 없이 통과 — 개념적 선행조건 미검사
- 명령: `open … --author alice` (rooms/existence/alice 없음)
- 사실: gil은 `--author`를 필수로 받지만 그 author가 **존재의 방에 실재하는지 검사하지 않음**(grep 확인: existence는 web/handoff에서만 스캔, open은 미검사). 레거시엔 존재의 방이 없으니 아무 문자열이나 통과 → chain/cycle은 얻지만 "누가 이걸 했는가"의 Ariadne 개념(존재)은 비어 있음.
- **범주 B** (개념 부재).

### [F6] `--git` 커밋의 git author가 gil `--author`와 불일치
- 명령: `open … --author alice --git`
- 출력: 커밋은 `rooms/`에만 격리(Flask src 무변경 — **긍정적**). 그러나 `git log -1 --format=%an` = `Sang-hyun Park`(로컬 git config), gil `--author`는 `alice`.
- 사실: cycle.yaml author ↔ git author 불일치. 이 갭은 loom/C003·C004에 이미 기록됨 — **레거시에서도 재현**. 레거시 레포의 기존 git identity와 gil 존재 이름이 별개로 흐름.
- **범주 B** (개념 부재 — 존재↔git identity 연동 미해결).

### [F7] 커밋 격리는 잘 됨 (긍정적 관찰, 마찰 아님)
- 관찰: `open --git`이 만든 커밋은 정확히 `rooms/experiment/chains/…` 6파일만 포함. Flask의 `src/flask/**` 등 수만 파일 작업트리를 건드리지 않음.
- 의미: gil의 "사이클만 담은 커밋"(loom/C004) 규율이 거대 레거시 작업트리에서도 안전하게 동작. **범주 없음 — 긍정적 발판.**

---

## 요약 통계

- 관찰된 마찰: **6건** (F1~F6) + 긍정 관찰 2건(F4 진입 작동, F7 커밋 격리).
- 범주 매핑: A(골격)=F2,F4 · B(개념)=F5,F6 · C(이름공간)=F3 · D(인터페이스)=F1.
- 가설이 예고한 4범주(히스토리 충돌/개념 부재/도구 전제/규모) 중 **규모(D-scale)는 마찰로 관찰되지 않음** — Flask 규모(676커밋·281파일)에서 모든 명령이 즉각 반응(체감 지연 0). 대신 예상 밖으로 "인터페이스 비대칭(진입 경로)"이 독립 범주로 떠오름.
- 무한·비구조 아님 — 유한(6건)하고 4범주로 깔끔히 분류됨. **가설 지지.**
