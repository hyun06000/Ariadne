# 2. 실험 설계

오직 H1(원격 부재 우아화)·H2(네트워크 자세 문서화)를 검증하기 위한 실험.

## 절차

### A. 참조 구현(gil.py) — 단일 push 관문

1. `_git_available`/`_warn_git_missing_once` 바로 아래에 원격판 3종을 신설:
   - `_has_push_remote(repo)`: `git -C <repo> remote` 출력이 비지 않으면 True. (git 없으면 애초에
     이 경로에 도달 안 함 — 커밋 자체가 안 되므로.)
   - `_warn_no_remote_once()`: 프로세스당 한 번, 원인 지목: *"ℹ 원격이 없어 push를 건너뛴다 —
     커밋은 로컬에 저장됐다. 원격 연결(git remote add origin <URL>) 후 공유·뷰어 배포가 켜진다."*
     (C052 `_warn_git_missing_once`와 대칭.)
   - `_push(repo, *extra)`: 관문. `if not _has_push_remote(repo): _warn_no_remote_once(); return`
     아니면 `_git(repo, "push", *extra)`.
2. 평범 push 호출부를 전부 `_push`로 치환:
   - open non-newchain (766), reserve/unreserve (786), `_refresh_viewers` (1374),
     close `--follow-tags` (1854 → `_push(repo, "--follow-tags")`), step (1899),
     round --open/--close (1974·2012).
3. `_push_with_renumber`: 최상단에 `if not _has_push_remote(repo): _warn_no_remote_once(); return cid`
   (원격 없으면 경합할 원장이 없으니 재번호 불필요, cid 불변 반환 — fetch origin 날것 fatal 제거).
4. `correct --push` (1683-1685): `_git(repo, "push")` + `push --force origin <tag>` 두 줄.
   원격 없으면 둘 다 건너뛰고 경고 한 번 → `_push`로 첫 줄, 태그 강제 push는 관문 안에서
   원격 있을 때만. 최소 변경: 앞에 `if not _has_push_remote(repo): _warn_no_remote_once()` 가드,
   있을 때만 두 push.

### B. Go 구현(go/main.go) — 대칭 이식

5. `gitAvailable`/`warnGitMissingOnce` 옆에 `hasPushRemote(repo)`/`warnNoRemoteOnce()`/`push(repo, extra...)`.
6. 참조와 같은 호출부 치환: `gitRun(repo,"push")`·`gitChecked(repo,"push",…)`·`pushWithRenumber`·correct.
7. 경고 문면은 참조와 **동일 문자열**(사용자가 보는 안내면이나, 대칭 유지 — C052도 동일 문면).

### C. 판정기(conformance.py) — NO-REMOTE-GRACEFUL

8. `NO-GIT-GRACEFUL` 바로 뒤에 신설. 샌드박스를 만들고 **git init + 최초 커밋**(원격 없음)한 뒤
   `open demo first-try --new-chain --git --push` 실행. 판정: rc0 ∧ cycle.yaml 생성 ∧
   로컬 커밋 존재(`git log`에 gil open 커밋) ∧ 무크래시(Traceback/panic 없음).

### D. 문서(H2) — 네트워크 자세

9. README.md·README.ko.md에 짧은 "네트워크 자세 / Network posture" 절 추가:
   자체 호출 0·텔레메트리 0, 외부 통신은 `--push` 시 사용자가 설정한 자기 원격으로의 git push/fetch뿐,
   원격 없으면 로컬 커밋만(아무것도 안 나감). C053 감사 근거.

## 준비물

- 참조: python3, gil.py (rooms/deployment/ariadne-spec/gil.py)
- Go: go build (go/main.go)
- 판정기: conformance.py, `--gil "python3 <abs>/gil.py"` / `--gil "<abs>/gil-bin"` (**절대경로** — C028·C043·C045 함정)
- 릴리스: `gil release` (도구 blob 변경 → 마이너 승격 예상: v2.13.0)

## 측정 방법

1. **원격 부재 우아화 (H1)**: git-있음·원격-없음 저장소에서 open·step·close·reserve·round·correct
   `--push`를 실행 → 전부 rc0, 커밋 보존, 경고 한 줄, 무크래시. 양 구현 동일.
2. **회귀 0 (기각 c)**: 원격-있음 저장소(이 저장소 실사용 + conformance)에서 양 구현 전체 통과,
   기존 항목 회귀 0. 원장 규율 재번호 픽스처 통과.
3. **NO-REMOTE-GRACEFUL**: 양 구현 신설 항목 PASS. 가드 제거 변이 → FAIL(계약이 실제로 판정).
4. **두 구현 동형 (기각 d)**: 원격 부재 강등 행동이 양 구현에서 같다.
5. **문서 (H2)**: README·README.ko에 네트워크 자세 절 존재, C053 감사와 일치.

성공: 기각 조건 (a)~(d) 전부 거짓 + NO-REMOTE-GRACEFUL 양 구현 PASS + 문서 반영.

## 사용자 컨펌

- 생략 — 전권 위임(2026-07-14, "사이클을 멈추지 말고 계속 돌려줘") + 이 사이클은 상현님이
  C053 보고에서 직접 발의한 (A) 추천의 이행. 설계는 C052 아크의 확립된 패턴(우아한 강등)을 따른다.

- [x] 컨펌 받음 (일자: 2026-07-14 전권 위임 + C053 발의로 갈음)
