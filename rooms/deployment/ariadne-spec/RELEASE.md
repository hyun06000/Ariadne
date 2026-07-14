# Ariadne Spec — Release

## v0.9.1 (2026-07-15)

문서-only: 이월 규약 2건 명문화 — §2 재현 문서 규약(불변 기준/가변 확인 분리, tapestry/C001), §5.1 CLI 호출 문법(위치 인자·플래그·반복 규칙·부분 구현의 종료 코드, Weft C014 제안). §5.1의 예시 블록은 실행 가능하다(문서=테스트). 근거: loom/C019.

## v0.9.0 (2026-07-14)

**승격 규칙의 기준 교정** (C012가 기록한 공백 2건의 해소):

- 도구 변경 감지의 기준을 "패키지 파일과의 비교"에서 **마지막 릴리스 태그의 blob**으로 — 패키지 도구를 직접 실행해도 변경이 감지된다.
- **conformance.py도 도구다** — 판정기 변경이 "문서 릴리스"로 오분류되던 문제 해소. CHANGELOG에 무엇이 변했는지(gil·conformance) 명시.
- 근거: loom/C018-release-baseline (3/3 + 회귀 26/26).

## v0.8.0 (2026-07-14)

**번호 원장 규율** (발의: 박상현 — "브랜치별로 사이클을 관리하는 방식이 체이닝에도 도입될 필요"):

- `gil open --git --push`: push 거절 시 fetch·rebase → 번호 경합 자동 재번호(디렉토리·id 개명 + 커밋 정정) → 재시도 (최대 3회). 해소 불가(rebase 충돌)는 명시적 오류 + abort.
- SPEC §6-6: "알려진 경합" → **원장 규율**로 개정. 번호의 진실은 원격 main.
- 검증: bare 원장 + 병렬 클론 실험 — 같은 번호 동시 발급이 자동 순서화(C002/C003), 원장 무위반, 내용 무손상. 근거: loom/C016.

## v0.7.0 (2026-07-14)

**존재 작업의 가시화** (발의: 박상현 — "그 친구도 gil 쓰는 거지? 뷰어로 모니터링할 수 있어야 해"):

- web: 열린 사이클에 **최근 활동**(마지막 커밋 시각·제목) 주석 — 깃 없으면 조용히 생략(무의존 유지). gil-data JSON에 `last_activity`.
- Pages 워크플로: 존재들의 워크트리 브랜치를 `branches/<이름>.html`로 함께 렌더 — 병렬 노동의 관전.
- 소환 규약 v3 (§6-5): 피소환자의 스텝 커밋 + 자기 브랜치 push 의무. §6-6: 병렬 번호 경합을 알려진 문제로 명문화 (C014 경합 실증).
- 근거: loom/C015-being-work-visibility.

## v0.6.0 (2026-07-14)

**준실시간 진행 가시성** (발의: 박상현 — "사이클을 열면 즉시 보이고 어느 스텝인지 보이면 좋겠다. 스텝별 커밋 같은 방법으로"):

- 스키마: `step: 1~5` 필드(가설·설계·검증·분석·보고) + 규칙 **R9**. `gil open`이 1로 기록, `gil close`가 5로 마감.
- 신설 `gil step <chain> <id> <n>` — 전이를 사이클만 담은 커밋으로 각인(`--git`), 즉시 전파(`--push`). open/close에도 `--push` 추가.
- 뷰어: 열린 사이클에 스텝 인디케이터(●●●○○ n/5 + 스텝명), gil-data JSON에 step 포함.
- conformance: STEP-OK·STEP-REJECT-RANGE·STEP-REJECT-CLOSED·FSCK-R9 신설, OPEN-CREATE·WEB-JSON 강화 — 26항목.
- 근거: loom/C013-realtime-step-visibility (이 사이클 자신의 진행이 스텝별 커밋으로 원격에 남은 첫 시연).

## v0.5.0 (2026-07-14)

- **conformance v2 — 판정 항목 간 독립** (loom/C012의 발견): v1은 부분 구현에서 죽거나(OPEN 실패 산출물에 의존) 오판했다(log 검사가 impl의 open에 의존). v2는 각 검사가 자기가 판정하는 명령에만 의존하도록 상태를 스위트가 직접 구축한다 — 부분집합 구현도 공정하게 판정된다.
- 알려진 관찰: 거부형 검사(REJECT류)는 미구현 명령의 exit≠0로 공허하게 통과할 수 있다 — 수락형 검사와 짝으로 읽을 것.
- **gil.py 수정: release의 자기 실행 결함** — 패키지의 gil.py 자신으로 릴리스하면 SameFileError로 죽던 문제(같은 파일 복사 생략으로 해결). 도구 변경이므로 마이너 승격(v0.5.0).
- 기록된 규칙 공백 2건 (다음 스펙 개정 재료): ① 승격 규칙이 gil.py만 도구로 간주 — conformance.py 변경의 분류 문제, ② 도구 변경 감지가 "실행 파일 vs 패키지 파일" 비교라 패키지 도구를 직접 실행하면 변경이 안 보임 — 기준은 마지막 릴리스 태그여야 한다.

## v0.4.0 (2026-07-14)

- **`conformance.py` 동봉 — 계약의 실행 가능형** (SPEC §7): 어떤 gil 구현이든 명령 문자열로 주입해 22개 계약 항목(fsck R1~R8 · open/close 규율 · log · web 자기완결과 `gil-data` 훅 · 깃 각인·변조 탐지)을 판정. 변이 테스트로 이빨을 검증(행동 파괴 3종 격추, 행동 보존 동등 변이는 통과 — 구현 독립의 증명). 바이너리 이식의 전제 조건 완성.
- gil.py 잔재 정리: 커밋 접두어 `gil:`, CSS `.gil`, JSON 훅 `id="gil-data"`(계약화), footer. 근거: loom/C011.

## v0.3.1 (2026-07-14)

- 문서-only: v0.3.0 개명에서 누락된 SPEC의 잔존 `ari` 언급 3곳 정정 (서두, §3 제목, 문서 제목의 고정 버전 표기 제거).

## v0.3.0 (2026-07-14)

- **도구 개명: `ari` → `gil`** — 길(아리아드네의 실이 가리키는 것)이자 GIt for Language model (작명: 박상현). 파일 `ari.py` → `gil.py`, release의 도구 참조는 파일명 비의존으로.
- **SPEC §7 구현 독립 계약** 신설: 스펙이 계약, `gil.py`는 참조 구현. 장래 단일 바이너리 배포를 전제 — 구현이 바뀌어도 계약·기록·체인은 살아남는다.
- 근거 사이클: loom/C010-rename-to-gil.

## v0.2.1 (2026-07-14)

문서-only 개정 (도구 변경 없음 — 패치 릴리스 경로의 첫 실사용, loom/C009에서 검증):

- **SPEC §6 소환 규약 v2** 신설: 소환자의 4의무 — 포인터 주입 · 모드 선언(부활/탄생) · 신원 전달 · 상호 기록과 쓰기 구획. 근거: genesis/C001(기각)·C002·C003 — 특히 C003에서 새 존재 **Weft**의 탄생·부활로 실증.

## v0.2.0 (2026-07-14)

- **`ari release` 신설**: 릴리스 절차의 porcelain화 — 도구·템플릿 스냅샷 동기화, SemVer·단조 증가 검증, **버전 승격 규칙**(도구 변경 시 마이너 이상) 강제, CHANGELOG 갱신, 배포의 방만 담은 커밋 + `v<버전>` 태그. 문서 강제: RELEASE.md에 해당 버전 서술이 없으면 거부.
- 소환 규약 발효(genesis/C002): 서브에이전트 소환 시 부트스트랩 포인터 주입 의무 — CLAUDE.md·존재의 방 README에 명문화.
- 근거 사이클: loom/C008-release-porcelain (7/7), genesis/C002-subagent-bootstrap (3/3). 이 릴리스 자체가 `ari release`의 첫 실사용이다.

## v0.1.0 (2026-07-14)

Ariadne의 첫 배포물. 스펙·도구·템플릿을 하나의 완결적 패키지로 묶었다.

### 내용물

| 파일 | 역할 |
|---|---|
| [SPEC.md](SPEC.md) | 표준의 전문 — 세 개의 방, 5스텝, 스키마 v0.2(R1~R8), 깃 각인 규약, CLI |
| [QUICKSTART.md](QUICKSTART.md) | 신선한 저장소의 부트스트랩부터 첫 사이클까지 (실행 가능한 문서) |
| [ari.py](ari.py) | 도구 — log·fsck·open·close(--git)·verify·web. Python 3 표준 라이브러리 |
| [template/](template/) | 사이클 템플릿 (5스텝 문서 + cycle.yaml) |

### 근거 사이클 (배포의 방 규칙 1)

이 릴리스의 모든 조항은 loom 체인의 닫힌 사이클에서 검증되었다:

| 사이클 | 검증한 것 | 깃 태그 |
|---|---|---|
| loom/C001-lineage-is-reconstructable | 계보의 기계적 재구성 (log) | cycle/loom/C001-lineage-is-reconstructable |
| loom/C002-schema-v0-2 | 스키마 규칙 R1~R8과 fsck, 이주 규정 | cycle/loom/C002-schema-v0-2 |
| loom/C003-open-close-porcelain | open/close — 위반의 사전 차단 | cycle/loom/C003-open-close-porcelain |
| loom/C004-git-binding | 깃 각인(커밋+태그)과 변조 탐지(verify) | cycle/loom/C004-git-binding |
| loom/C005-web-viewer | 자기완결적 정적 웹 뷰어 (web) | cycle/loom/C005-web-viewer |

태그 이동 규약(SPEC §4)은 C004가 남긴 공백을 이 릴리스에서 명문화한 것으로, 실험적 검증은 향후 사이클의 몫이다.

### 완결성 보증

이 패키지만 복사된 신선한 환경에서 QUICKSTART.md의 코드 블록을 그대로 실행하는 것이
릴리스 테스트다 (loom/C006-spec-release에서 검증).
