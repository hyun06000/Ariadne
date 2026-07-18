# 2. 실험 설계

가설 하나만을 위한 절차 설계: **주 체크아웃 소유 guard** — 주 체크아웃(공유 main)에서 `--author ≠ gil.owner`인 뮤테이션을 커밋 이전에 거부한다.

## A. 메커니즘

- **주인 기록**: 저장소 config `gil.owner`(주 체크아웃의 주인 이름). 설정: `git config gil.owner <이름>`(문서화). **미설정이면 guard 미적용**(opt-in — 기존 저장소·CI 무파손, 우리 저장소는 설정한다).
- **주 체크아웃 판별**: `git rev-parse --git-dir` == `git rev-parse --git-common-dir`. 링크드 워크트리(harness·gil 생성)는 `--git-dir`이 `.../worktrees/<name>`이라 다르다 → guard 미적용(존재의 정당한 공간, 오탐 0).
- **guard 규칙**: `repo ∧ 주체크아웃 ∧ gil.owner 설정됨 ∧ author ≠ gil.owner` → **ChainError 거부.** 뮤테이션의 **최초**(파일 생성·커밋 이전)에 호출 → 저장소 무변화(원자성).

## B. 적용 지점 (첫 카브)

`--author`를 선언하며 현재 브랜치에 직접 커밋하는 명령: **open · reserve · correct.** (worktree add는 새 워크트리 안에서 커밋하므로 main 유출 없음 → 미적용. step·close·round는 --author 없음, 카브 2.)

정확한 사고 벡터는 `gil open --author <being>`(세 번 다 open). 우선 open을 확실히 막고 reserve·correct에 동형 적용.

## C. 절차 (구현)

1. 참조 `gil.py`에 헬퍼 두 개:
   - `_is_primary_worktree(repo)` → `_git(repo,"rev-parse","--git-dir")` == `_git(repo,"rev-parse","--git-common-dir")` (realpath 정규화, C055).
   - `_guard_primary_owner(repo, author)` → 위 조건 위반 시 `raise ChainError(처방 메시지)`.
2. `cmd_open`·`cmd_reserve`·`cmd_correct`의 최상단(repo 확정 직후, 쓰기 이전)에서 `_guard_primary_owner(repo, args.author)` 호출.
3. Go(`main.go`)에 동형 이식 — 회귀 0을 위해 양 구현(behavior라 참조만 하면 Go가 판정에서 FAIL). Go 툴체인 `$HOME/goroot/go/bin/go`.
4. 거부 메시지(처방): `"이 체크아웃은 '<owner>'의 주 작업공간이다 — author '<X>'로 여기서 커밋할 수 없다. 네 워크트리에서 실행하라 (gil worktree add …)."`

## D. 판정기 (conformance.py — 3항목, 쌍 검증 C038)

샌드박스 저장소에 `git config gil.owner owner-x` 설정 후:

| 항목 | 판정 |
|---|---|
| `GUARD-PRIMARY-REFUSE` | 주 체크아웃에서 `open --author intruder` → exit≠0 ∧ **사이클 디렉토리 미생성** ∧ **HEAD 커밋 무증가**(저장소 무변화) |
| `GUARD-OWNER-OK` | 주 체크아웃에서 `open --author owner-x` → exit 0, 정상 생성 (주인은 통과) |
| `GUARD-LINKED-OK` | `git worktree add`로 만든 링크드 워크트리에서 `open --author someone` → exit 0 (오탐 0 — 존재의 공간) |

- 변이 격추: guard를 제거한 변이 → GUARD-PRIMARY-REFUSE FAIL. 주체크아웃 판별을 상수 True로 한 변이 → GUARD-LINKED-OK FAIL(오탐). **거부와 허용이 함께 서야 성공**(C038 쌍).
- gil.owner 미설정 샌드박스에서 기존 open 계열 판정 **회귀 0**(opt-in 실증).

## E. 산출물·범위

- 재현: `conformance.py --gil "<절대경로>"` 양 구현. 실사고 재연 스모크(주 체크아웃에서 남의 author open 거부).
- 범위 밖: 링크드 워크트리 소유 표식(카브 2), step·close 등 비-author 뮤테이션(카브 2), 소환 문서 규율(카브 3).

## 사용자 컨펌

- 생략 — 상현님이 "사고를 도구로 막자"를 명시 발의(설계 방향 승인). 전권 위임 + 커밋 관전으로 방향 수정 가능.
- [x] 컨펌 받음 (일자: 2026-07-19, 발의로 갈음)
