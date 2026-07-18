# 2. 실험 설계

> 복구 메모(2026-07-19): 이 문서가 작업 중 템플릿 스텁으로 되돌아간 것을 발견해, 작성자(clew)가 원 설계 내용을 복원했다. 재현성은 존재 조건이라 스텁 설계로는 사이클을 닫지 않는다.

가설: `gil worktree add`가 워크트리+브랜치+사이클 열기를 원자적으로 묶어, 격리 작업공간을 한 명령으로 주고 메인 오염을 구조적으로 봉인한다.

## 핵심 설계 — spawn은 얇게, open은 재사용

`gil worktree add`는 open 로직을 **복제하지 않는다.** 워크트리+브랜치만 만들고, 그 워크트리 안에서 **gil 자신을 self-invoke해 `gil open`을 실행**한다. 두 가지 이득:
- **양 구현 발산 최소화**: spawn은 "git worktree add + 자기 재호출"뿐. open의 계약(번호 규율·fsck·스키마)은 이미 검증된 한 곳에 있다.
- **C050 사고의 구조적 봉인**: open이 **워크트리 안에서** 실행되므로(git toplevel = 워크트리), 커밋이 물리적으로 그 브랜치에만 간다. "메인에 잘못 open"이 불가능해진다 — cwd 계약을 도구가 강제한다.

## 절차 (구현)

1. **`gil worktree` 명령 신설** (서브커맨드 `add`; 이후 `land`/`list` 확장 여지). 양 구현.
2. **`worktree add <chain> <slug> --author X [--parent P]... [--lineage L]... [--new-chain] [--root R]`**:
   - a. `repo = repo_root(root)`. 깃 저장소 아니면 거부(rc≠0).
   - b. **결정론적 유도**: 브랜치 `<author>/<chain>-<slug>`, 워크트리 경로 `<repo부모>/<repo이름>-worktrees/<chain>-<slug>`. 이미 있으면(브랜치 또는 경로) 거부.
   - c. `git worktree add -b <branch> <wt_path> HEAD` — 새 브랜치로 격리 체크아웃.
   - d. 워크트리 안 chains 경로(`<wt_path>/<root의 repo-상대>`)를 **`--root`로 지정해 gil self-invoke**: `<self> open <chain> <slug> --author X [플래그] --git --no-web --root <wt_chains>`. open이 그 브랜치에 사이클 커밋.
   - e. **원자성**: open이 실패(rc≠0)하면 `git worktree remove --force <wt_path>` + 브랜치 삭제로 잔여 없이 되돌리고 실패 전파.
   - f. 성공 시 워크트리 경로 + 브랜치명 출력(존재가 cd할 좌표).
3. **self-invoke 경로**: 참조 `[sys.executable, abspath(__file__), ...]`, Go `os.Executable()`. 각 구현이 자기 자신을 재호출(참조→참조 open, Go→Go open) — 도구가 자기 이름을 하드코딩 안 함(§7).
4. **CLI 등록** + `CONTRACT_COMMANDS`·양 구현 help 목록에 `worktree` 추가(판정기·능력탐침이 표면을 보게 — C051/HELP-COMPLETE).

## 판정기 (conformance.py) — `WORKTREE-SPAWN` 신설

git 저장소(init+커밋)에서 `gil worktree add demo para --author tester --new-chain` 실행 후:
- **원자·격리 계약**: rc0 ∧ 워크트리에 `demo/C001-para/cycle.yaml`(open) ∧ 브랜치 `tester/demo-para` ∧ **메인 작업트리 격리**(demo 없음) ∧ **메인 log에 open 커밋 없음**(C050 봉인) ∧ 무크래시.
- 쌍 검증(C038): 음성으로 **비저장소에서 거부**(rc≠0).
- 변이: self-invoke의 `--root`를 메인 chains로 바꾼 변이 → 격리 위반으로 WORKTREE-SPAWN FAIL(77/78).

## 준비물

- 참조/Go gil, conformance.py. Go 툴체인(go1.23.4 로컬). git.
- 회귀 기준: 착수 직전 양 구현 conformance 총계(77) + fsck 위반 0.

## 측정 방법

- 기각조건 1(원자성): 실패 주입 시 워크트리·브랜치 잔여 0.
- 기각조건 2(메인 오염): 판정기 격리 검사(main 작업트리·log) + 수동 재현.
- 기각조건 3(번호 규율): 워크트리 사이클 fsck 통과.
- 기각조건 4(회귀): 양 구현 78/78, 기존 77 유지.
- 기각조건 5(두 몸): 참조·Go 동일 관측(WORKTREE-SPAWN 양쪽 PASS).

## 사용자 컨펌

- 생략 — 상현님 아크 발의(#1)+"권장하자"까지 위임. 병렬 구조·스코프는 AskUserQuestion으로 확정("#2+#1 동시").

- [x] 컨펌 받음 (일자: 2026-07-19, 아크 발의로 갈음)
