# Ariadne Spec — Release

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
