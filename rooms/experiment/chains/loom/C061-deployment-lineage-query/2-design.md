# 2. 실험 설계

H1(배포 계보를 두 기록 대조로 조회) + H2(새 명령 표면의 정직한 부재 판정)만을 검증한다.

## 설계할 명령 — `gil releases`

읽기 전용. 저장소를 변경하지 않는다.

**입력**
- `--package` (기본 `rooms/deployment/ariadne-spec`): CHANGELOG를 `<package>/../CHANGELOG.md`에서 찾는다 (`cmd_release`와 동일 규칙).
- `--root` (기본 `rooms/experiment/chains`): `_repo_root`로 저장소를 유추해 태그를 읽는다.

**두 기록의 수집**
1. **깃 태그** — `git for-each-ref refs/tags/v*` → `v<semver>`만(`_SEMVER_RE` 필터). 각: 버전·태그일자(creatordate)·subject. `cycle/…` 태그는 `v*` 글롭·semver 필터로 자동 배제. git 부재/비저장소면 태그 수집 생략(우아한 강등, C052의 결).
2. **CHANGELOG** — `## [X.Y.Z] — 날짜` 헤더만 매칭(`## [Unreleased]`는 버전이 아니므로 제외). 헤더 아래 첫 `- ` 불릿을 노트로, `- 도구 변경:`/`- 도구 동기화:` 줄을 도구변경으로.

**대조·출력**
3. 두 기록의 버전 합집합을 semver 내림차순 정렬.
4. 각 릴리스: 버전 · 일자(CHANGELOG 우선, 없으면 태그일자) · 노트 · 도구변경 · **존재 표식 `[TC]`**(T=태그, C=CHANGELOG, 한쪽만이면 `·`).
5. **기계 훅**: 릴리스마다 `gil:release <버전> <일자> tags=<0|1> changelog=<0|1>`, 말미에 `gil:releases <총수> drift=<n>`.
6. **drift**(한 기록에만 있는 릴리스) 건수를 세어 stderr로 경고. `git tag -l`이 못 하는 대조가 이 카브의 핵심 값.
7. 종료 코드 0 (조회/렌더 프리미티브 — `gil log`와 같은 성격). drift는 실패가 아니라 드러낼 정보다.

## 등록 (자기보고·판정)
- `gil.py`: 서브파서 `releases` 추가 → `gil help`가 자동 목록화(단일 소스 §7.2).
- `conformance.py`: `CONTRACT_COMMANDS`에 `"releases"` 추가 → Go의 정직한 부재(exit 3)를 HELP-COMPLETE가 판정(C043 리듬).
- Go: 이번 범위 밖 — `release`처럼 참조 전용. Go는 미지 명령에 exit 3으로 정직히 답하므로 HELP-COMPLETE 통과.

## 절차 (검증)

1. 참조 구현에 `gil releases` 구현.
2. **실저장소 스모크**: 이 저장소에서 `gil releases` 실행 → 실제 릴리스 목록(태그+CHANGELOG 대조)이 나오는가, 저장소 무변화인가(`git status` 전후 동일).
3. **conformance 신규 판정** `RELEASE-LIST`: 샌드박스 git repo에 CHANGELOG 2엔트리 + 태그 1개(=drift 1건 유도) → `gil releases`가 ① exit 0 ② 두 버전 모두 렌더 ③ `gil:release` 훅 2줄 ④ drift 표식/카운트 ⑤ 저장소 무변화.
4. **회귀**: Python·Go 양 구현 conformance 전 항목 재실행 (기준 78/78).
5. **비-git 우아화**: 비저장소 cwd에서 `gil releases` → 크래시 없이 exit 0(태그 대조 생략 안내).

## 측정 방법 · 성공/기각 기준

- H1 성립: 스모크에서 실제 릴리스가 두 기록 대조로 나오고, 저장소 무변화, 지어낸 계보 0.
- H2 성립: `RELEASE-LIST` PASS, Go가 `releases`에 exit 3(HELP-COMPLETE PASS).
- 회귀 0: Python 78→79(신규 1항목), Go 78→79 유지(전 항목 PASS). 하나라도 후퇴하면 기각.

## 사용자 컨펌

생략 — 비파괴 읽기 전용 조회 프리미티브이며, 방향(#3 추적층)은 상현님이 이미 발의. 릴리스 실행 경로·계약을 바꾸지 않으므로 사전 컨펌 불요.

- [x] 컨펌 불요 (사유: 읽기 전용·비파괴·기존 발의 방향)
