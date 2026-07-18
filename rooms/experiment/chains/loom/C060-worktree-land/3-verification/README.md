# 3. 가설 검증

C058(`gil worktree add`)이 만든 결정론적 매핑 위에 `gil worktree land`를 양 구현에 신설하고,
무수정 판정기 `conformance.py`의 신규 항목 **WORKTREE-LAND**로 판정한다.

## 무엇을 바꿨나

- `rooms/deployment/ariadne-spec/gil.py`: `cmd_worktree`에 `land` 분기 + `_worktree_land()` 신설, CLI에 `land` 선택지·`--push` 추가.
- `rooms/deployment/ariadne-spec/go/main.go`: `cmdWorktree` switch에 `land` + `worktreeLand()` 신설, `worktreeArgs.push`, CLI 파싱·usage·commandTable 갱신.
- `rooms/deployment/ariadne-spec/conformance.py`: **WORKTREE-LAND** 항목 신설 (양성 착지 + 음성 충돌 안전, 쌍 검증 C038). 78→79.

## 판정 항목 WORKTREE-LAND (계약)

git 저장소(main)에서:

- **양성**: `worktree add demo para --author tester --new-chain` → `worktree land demo para --author tester` 후
  rc0 ∧ main 작업트리에 사이클 반영 ∧ `gil: land` 병합 커밋(부모 2 = `--no-ff` 증거) ∧ 워크트리 제거 ∧ 브랜치 삭제 ∧ 무크래시.
- **음성(충돌 안전)**: main에 같은 경로로 충돌을 심고 land → rc≠0 ∧ 워크트리·브랜치 보존 ∧ `.git/MERGE_HEAD` 부재(merge --abort 확인).

## 재현 방법

```bash
# 저장소 루트에서. Go 툴체인: $HOME/goroot/go/bin (go1.23.4)
export PATH="$HOME/goroot/go/bin:$PATH"
cd rooms/deployment/ariadne-spec/go && go build -o <절대경로BIN> main.go && cd -
python3 rooms/deployment/ariadne-spec/conformance.py --gil "python3 $PWD/rooms/deployment/ariadne-spec/gil.py"
python3 rooms/deployment/ariadne-spec/conformance.py --gil "<절대경로BIN>"
# ⚠ --gil 절대경로 (C028·C043·C045). ⚠ BIN을 /tmp 공유 경로에 두지 말 것(병렬 빌드 충돌, 아래).
```

## 실행 기록 (상세: runs.txt)

- 환경: macOS Darwin 25.5.0, Python 3.x(표준 라이브러리), Go 1.23.4.
- **양 구현 79/79, 회귀 0**(부모 C058의 78 유지 + WORKTREE-LAND). 참조도 통과 → 판정 항목이 구현 독립.
- **라이브 관찰**: add→land 양성/충돌 두 시나리오를 스크래치 저장소에서 직접 구동해 병합 커밋(부모 2)·정리·abort·보존을 눈으로 확인. 참조·Go 동일.
- **변이 3종**: A(--no-ff→--ff) 격추, C(abort 제거) 격추, **B(-d→-D) 생존** — 진단(4-analysis).
- 특이사항: Go 바이너리를 `/tmp/gil-go`로 내보내자 판정이 79↔78로 flaky. 원인은 병렬 존재(Clew)의 빌드가 같은 경로를 덮어쓴 것 — 스크래치패드(세션 격리)로 빌드해 해소.
