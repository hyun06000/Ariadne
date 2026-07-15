# 2. 실험 설계

## 근본 원인 (실측 확정)

git 부재 시 크래시의 정체는 좁고 명확하다:

- 참조: `_repo_root`([gil.py:1380](../../../../deployment/ariadne-spec/gil.py))가 `subprocess.run(["git", ...])`를 호출하는데, git 미설치 시 이 호출이 `FileNotFoundError`를 던진다. 반환 코드 실패가 아니라 **예외**라 `if r.returncode == 0` 가드가 못 잡는다 → 미포착 크래시.
- **그런데 그 아래 커밋 경로는 이미 우아하다**: C033 자동 커밋은 `repo = _repo_root(...); if repo: <commit>` — `_repo_root`가 `None`이면(=git 없는 저장소) **그냥 건너뛴다.** 즉 "git 있으나 저장소 아님"은 이미 우아하게 강등된다.
- **유일한 결함**: `_repo_root`가 git 부재를 `None`이 아니라 **예외**로 돌려준다. Go는 크래시 대신 하류 뷰어 경고("렌더할 체인이 없다")로 원인을 오도한다.

→ **최소 수정**: `_repo_root`가 git 부재(`FileNotFoundError`)를 잡아 `None`을 반환하게 하면, 모든 호출부(14곳)가 즉시 기존의 우아한 "저장소 아님 → 건너뜀" 경로로 수렴한다. 크래시가 사라진다. 여기에 **정확한 안내 한 줄**을 더한다(오도 경고 대신 "git 없음").

## 절차

1. **참조 수정** (gil.py):
   - `_git_available()` 헬퍼: `shutil.which("git") is not None`.
   - `_repo_root`: `git` 호출을 `try/except FileNotFoundError` (또는 사전 `_git_available()` 검사)로 감싸 부재 시 `None` 반환.
   - `_warn_git_missing_once()`: 프로세스당 한 번만 stderr에 친절한 안내. 문안(렌더): *"ℹ git이 없어 각인을 건너뛴다 — 사이클 파일은 저장됐다. git 설치(https://git-scm.com) 후 이력·되감기·뷰어 자동갱신이 켜진다."*
   - 커밋 의도가 있는 명령(open/step/close/supersede/correct/reserve)에서 `repo`가 `None`이고 git이 부재면 안내 호출. `open`의 명시적 `--git` + git부재도 하드에러(`raise`) 대신 안내+강등(단, git 있는데 저장소 아님은 기존 하드에러 유지 — 그건 진짜 사용자 오류).
2. **Go 수정** (go/main.go): `exec.LookPath("git")`로 부재 감지 → 커밋 스킵 + 동일 취지 안내(문면은 렌더, 자유). 하류 뷰어 경고가 git부재를 덮지 않도록 앞단에서 처리.
3. **판정기 신설** `NO-GIT-GRACEFUL` (conformance.py):
   - `Impl.run(cwd, *cli, env=None)`에 `env` 인자 추가.
   - 헬퍼: 런처(argv[0])를 `shutil.which`로 **절대경로화**하고 `PATH`를 빈 임시 디렉토리로 설정 → 런처는 절대경로라 실행되고 `git`은 부재(실측으로 확인된 기법).
   - `gil open <chain> <slug> --new-chain --author x` 를 git-부재 env로 실행 → **rc == 0 ∧ cycle.yaml 생성 ∧ stderr에 "Traceback" 없음**. (의미 계약: 완주·파일·무크래시. 문면은 렌더라 단언 안 함 — C051.)
4. **회귀 검증**: git **있는** 환경에서 참조·Go 각각 재판정 → 새 항목 포함 74/74, 기존 73 회귀 0.
5. **수신자 재연**: 빈 폴더 + git 부재에서 `open`→`step`→`close`가 트레이스백 없이 완주하고 파일이 남는지 손으로 확인(친구의 경로).

## 준비물
- 참조 gil.py, Go(go1.26, `GO111MODULE=off go build -o /tmp/gil-go go/main.go`).
- conformance.py. `--gil`은 절대경로.
- git-부재 시뮬레이션: 절대경로 런처 + `PATH`=빈 디렉토리 (1-hypothesis 실측에서 검증됨).

## 측정 방법 — 기대 행동

| # | 자극 | 기대 |
|---|---|---|
| T1 | 수정 후, git 부재 env × 참조 `open --new-chain` | rc 0 ∧ cycle.yaml 존재 ∧ 트레이스백 없음 ∧ git부재 안내 |
| T2 | 수정 후, git 부재 env × Go 동일 | rc 0 ∧ 파일 ∧ 무크래시 ∧ 안내(하류 뷰어 경고 아님) |
| T3 | git 있는 env × 참조 conformance | 74/74 (신 항목 + 기존 73 회귀 0) |
| T4 | git 있는 env × Go conformance | 74/74 |
| T5 | 수신자 재연: 빈 폴더·git부재 open→step→close | 3연속 rc 0, 파일 누적, 트레이스백 0 |
| T6 | 변이: `_repo_root`가 부재를 다시 예외로 흘림 | `NO-GIT-GRACEFUL` FAIL (판정기가 문다) |

성공: **T1·T2·T5 완주 ∧ T3·T4 회귀 0 ∧ T6 격추.** git-있음 정상(회귀 0)과 git-없음 완주가 함께 서야 성공 — 한쪽만이면 실패(C038 쌍 검증). 수치(74)는 관측값, 판정은 회귀·완주·변이로.

## 사용자 컨펌

- [x] 착수 승인 받음 (2026-07-15, AskUserQuestion "A부터 지금"). 스코프 A 확정, B~D(Windows)는 후속 사이클. 설계 세부는 전권 위임(C008).
