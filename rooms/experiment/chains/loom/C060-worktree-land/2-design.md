# 2. 실험 설계

가설: `gil worktree land <chain> <slug> --author X`가 add의 결정론적 매핑을 역산해 브랜치를 main에 `--no-ff`로 병합하고, 충돌은 되돌려 거부(워크트리 보존)하며, 성공 시에만 워크트리+브랜치를 정리하면 — 병렬 사이클의 머지백이 한 원자 명령이 된다.

## 인터페이스 — add와 대칭

```
gil worktree land <chain> <slug> --author <이름> [--root R] [--push]
```

`add`와 **동일한 위치 인자**(`<chain> <slug> --author`)를 받는다. 이유: add가 이 셋으로 브랜치·워크트리 경로를 결정론적으로 만들었으니, land는 같은 셋으로 그것을 역산한다. 사람이 새 정보를 기억할 필요가 없다 — 열 때 쓴 좌표가 곧 닫을 때 쓰는 좌표다.

- `--push`: 병합 성공 후 main을 push (`_push`/`gitPush` 단일 관문 재사용 — 원격 없으면 우아하게 강등, C054).
- `--root`: land가 병합해 들어갈 **대상 저장소**의 chains 경로. `repo_root(root)`가 main 저장소(병합 목적지)를 준다.
- `--date`는 land엔 불필요(병합 커밋은 git이 타임스탬프). 인자 표면 최소화.

## 절차 (구현) — 얇은 오케스트레이터, git 명사에 올라탄다

`add`가 "git worktree add + self-invoke open"이었듯, `land`는 "git merge --no-ff + git worktree remove + git branch -d"뿐이다. open/close 로직을 복제하지 않는다. self-invoke도 불필요 — land는 순수하게 git 오케스트레이션이다(사이클 파일을 만들지 않으므로).

1. **`cmd_worktree`에 `land` 분기 추가** (기존 `add`-only 옆에). 양 구현.
2. **`worktree land <chain> <slug> --author X [--root R] [--push]`**:
   - a. git 필요·`repo = repo_root(root)`·author 필수·slug 형식(R1) — add와 동일 사전검증.
   - b. **역산**: 브랜치 `<author>/<chain>-<slug>`, 워크트리 경로 `<repo부모>/<repo이름>-worktrees/<chain>-<slug>` (add와 **동일 공식**).
   - c. 브랜치가 없으면 거부(rc≠0) — 되돌릴 것이 없다.
   - d. **--no-ff 병합**: `git merge --no-ff --no-edit -m "gil: land <chain>/<slug> (<branch>)" <branch>`.
     - 병합 실패(충돌 등, rc≠0) → `git merge --abort`로 되돌리고 **거부**(rc≠0). 워크트리·브랜치는 **그대로 보존**(사람이 충돌 해소). 충돌을 삼키지 않는다.
   - e. **정리(성공 시에만)**: 워크트리 경로가 있으면 `git worktree remove --force <wt_path>`, 이어 `git branch -d <branch>`(안전 삭제 — 병합 안 됐으면 git이 거부하나, 방금 병합했으니 성공. `-d`는 "정말 병합됐나"의 마지막 단언).
   - f. 병합 커밋 SHA + 정리 결과 출력. `--push`면 main push.
3. **원자성 경계**: 병합 전 사전검증(a~c)은 저장소를 안 건드린다. 병합이 충돌하면 abort로 무흔적 복귀. 정리는 병합 성공 후이므로, 정리 단계 실패(예: 워크트리에 미커밋 잔재)가 나도 **병합은 이미 landed** — 이땐 정리 실패를 보고하되 병합 성공은 유지(되돌리면 오히려 landed 작업을 잃는다). `--force` 제거로 정리 완주를 보장한다.
4. **CLI 등록**: 양 구현 usage/help·commandTable 설명에 `land` 추가(HELP-COMPLETE·능력탐침이 표면을 보게). `worktree` 최상위 명령은 이미 CONTRACT_COMMANDS에 있음 — land는 하위명령이라 새 최상위 등록 불필요.

## 왜 --no-ff인가

fast-forward 병합은 병합 커밋을 안 남겨 병렬 작업의 경계가 이력에서 사라진다. `--no-ff`는 "여기서 한 병렬 사이클이 되돌아왔다"를 항상 한 커밋으로 각인한다 — add가 브랜치를 갈랐듯 land가 그 갈래를 명시적으로 봉합한다. C058 spawn ↔ C060 land의 대칭이 이력에도 새겨진다.

## 판정기 (conformance.py) — `WORKTREE-LAND` 신설

git 저장소(init+커밋, main)에서:

- **양성(정상 착지)**: `worktree add demo para --author tester --new-chain` → `worktree land demo para --author tester` 실행 후:
  - rc0 ∧ main 작업트리에 `demo/C001-para/cycle.yaml` 존재(병합 반영) ∧ main log에 `gil: land` 병합 커밋(부모 2개 = --no-ff 증거) ∧ 워크트리 경로 제거됨 ∧ 브랜치 `tester/demo-para` 삭제됨 ∧ 무크래시.
- **음성(충돌 안전, 쌍 검증 C038)**: add로 브랜치 생성 후, main에서 **같은 경로에 다른 내용**을 커밋해 충돌을 심고 land → rc≠0 ∧ 워크트리·브랜치 **보존** ∧ main이 MERGING 상태로 안 남음(merge --abort 확인: `.git/MERGE_HEAD` 부재).
- **변이(3-verification에서)**: `--no-ff`를 `--ff`로 바꾼 변이 → 병합 커밋 부재로 LAND FAIL. `git branch -d`를 `-D`로 바꾼 변이 → (병합 안 된 브랜치도 지워지므로) 음성 케이스에서 안전 삭제 단언 실패.

## 준비물

- 참조/Go gil, conformance.py. Go 툴체인(go1.23.4 로컬, `$HOME/goroot/go/bin`). git.
- 회귀 기준: 착수 직전 양 구현 conformance 총계 + fsck 위반 0. (착수 시 측정해 3-verification에 기록.)

## 측정 방법 (기각 조건 대응)

- 기각1(병합 무결성): 양성 케이스의 병합 커밋 부모 수·main 반영.
- 기각2(충돌 안전): 음성 케이스 rc≠0 + 워크트리·브랜치 보존 + MERGE_HEAD 부재.
- 기각3(정리 정확성): 양성 후 워크트리·브랜치 부재; 음성 후 보존.
- 기각4(회귀): 양 구현 총계 = 기존+1(LAND), 기존 항목 유지.
- 기각5(두 몸): 참조·Go 동일 관측(WORKTREE-LAND 양쪽 PASS).

## 사용자 컨펌

- 생략 — 상현님 아크 발의 #1(병렬 사이클 모드) + "권장하자"에 위임. 부모 C058 제안 (A)의 직접 구현. 인터페이스는 add와의 대칭으로 확정.

- [x] 컨펌 받음 (일자: 2026-07-19, 아크 발의 #1 + C058 제안 A로 갈음)
