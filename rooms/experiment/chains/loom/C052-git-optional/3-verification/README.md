# 3. 가설 검증

git 부재 환경을 재현하려면 **런처를 절대경로로 실행하고 `PATH`를 빈 디렉토리로** 둔다 — 런처는 실행되고 gil 내부의 `git` 조회만 실패한다(1-hypothesis에서 검증한 기법, conformance의 `run_nogit`이 이를 구현).

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec
GO111MODULE=off go build -o /tmp/gil-go go/main.go     # go1.26

# T3·T4: git 있는 환경, 신 항목 포함 회귀 0
python3 conformance.py --gil "python3 $(pwd)/gil.py"   # 74/74 (NO-GIT-GRACEFUL PASS)
python3 conformance.py --gil "/tmp/gil-go"             # 74/74

# T1·T2·T5: git 부재 수동 재연 (빈 폴더 + PATH 비움 + 절대경로 런처)
#   open --git → step → close 가 rc0·파일생성·무크래시·친절한 한 줄 안내
#   (아래 파이썬 하네스로 실행; PATH='<빈dir>', argv[0]=절대경로)

# T6: 변이 — _repo_root의 git-부재 가드 제거 → NO-GIT-GRACEFUL FAIL (73/74)
```

## 실행 기록

- 일시: 2026-07-15. 환경: darwin 25.2.0(arm64), go1.26.2, python3(CommandLineTools). git 부재는 `PATH=빈디렉토리`로 시뮬레이션.
- **근본 원인 (수정 전 실측)**: 참조 `_repo_root`가 git 미설치 시 `subprocess.run(["git",...])`의 `FileNotFoundError`를 미포착 → `rc=1` 트레이스백. Go는 `exec.Command`가 `*exec.Error`를 반환해 `code=-1`로 처리하므로 크래시는 없었으나(rc 0), git부재 원인 대신 하류 뷰어 경고("렌더할 체인이 없다")를 뱉었다.
- **T1 (참조 수정 후, git부재)**: `open --git`·`step`·`close` 모두 **rc 0, 트레이스백 0, 파일 생성·닫힘 확인.** stderr는 친절한 한 줄("ℹ git이 없어 각인을 건너뛴다 …")만. 뷰어 헛경고 제거됨(검색 루트를 cwd→저장소 루트로 고정).
- **T2 (Go 수정 후, git부재)**: 동일 — rc 0, panic 0, 파일 생성·닫힘, 같은 취지 안내. 하류 뷰어 경고 사라짐.
- **T3·T4 (git 있음)**: 참조·Go conformance **74/74** (기존 73 + NO-GIT-GRACEFUL, 회귀 0). 실 저장소 fsck 위반 0·verify 변조 0.
- **T5 (수신자 재연)**: 빈 폴더·git부재에서 open→step→close 3연속 rc 0, 파일 누적, 트레이스백 0. 친구의 경로가 이제 완주한다.
- **T6 (변이)**: `_repo_root`의 `if not _git_available(): return None` 가드를 제거하니 `NO-GIT-GRACEFUL`이 `FAIL [rc=1 crash=True Traceback...]`, **73/74.** 판정기가 회귀를 문다.
- 판정: T1·T2·T5 완주 ∧ T3·T4 회귀 0 ∧ T6 격추 — **채택**. 기각 조건 불성립.

### 수정 범위 (구현)
- 참조 `gil.py`: `_git_available()`·`_warn_git_missing_once()` 신설, `_repo_root`가 git부재를 `None`으로, `_refresh_viewers` 검색 루트를 저장소 루트에 고정, open/step/close/reserve의 커밋 분기에 git부재 안내·강등.
- Go `go/main.go`: `gitAvailable()`·`warnGitMissingOnce()` 신설, `refreshViewers` 루트 고정, cmdOpen/cmdStep/cmdClose/reserveCommitPush에 동일 가드. (`repoRoot`는 `exec.Error`를 이미 ""로 강등하고 있었다.)
- `conformance.py`: `Impl.run(env=)`·`run_nogit()` 신설, `NO-GIT-GRACEFUL` 항목(73→74).
