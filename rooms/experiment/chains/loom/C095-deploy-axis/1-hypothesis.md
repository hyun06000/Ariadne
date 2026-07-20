# 1. 가설 수립

> **[홀드 노트, 2026-07-20]** 이 사이클은 1/5에 **홀드**됐다. 여는 도중 상현님이 "같은 체인 내 다중 부모"를 지적 — 조사 결과 다중부모는 이미 gil에 완전 구현돼 있고(내 오해의 근원은 README.ai.md 문서 갭), 과거 잃은 계보 4건도 발견됐다. deploy 축보다 **문서 개선 → 계보 복원**이 먼저라, 그 사이클들을 먼저 돌린다. C095는 `gil threads`가 계속 추적하며, 그것들이 닫히면 재개한다. (재개 시: deploy 축 인프라 조사 완료본은 세션 기록 참조 — `_resolve_source_cycle` 재사용, `gil deploy cut`, `deploy/<chain>/<semver>` 태그.)

## 이전 사이클의 교훈

부모 = loom/C091(노드 입출력 마커 — 배포↔근거사이클 뷰어 연결). 계보상 뿌리는 **loom/C086**(`gil release --cycle` — "배포는 반드시 닫힌 사이클을 근거로")이다. C086이 필드 이슈 **#25**의 카브 #1(§4의 무결성 조항)을 뗐고, 그 코멘트에서 나(Clew)는 명시적 신호를 걸어뒀다:

> "사용자 산출물 배포의 실제 마찰이 실증되는 순간 별도 축을 연다. `deployments.json` 스키마를 이슈에 붙여주면 축 설계를 앞당기겠다."

이슈 #25 본문 §2에 레코드 필드가 이미 명세돼 있고(상현님 owner), 필드 유저가 임시 `app-serving/deployments.json`으로 동일 스키마를 운영 중 — **마찰이 실증됐다.** 상현님의 "이어서 배포 관리 하자"가 신호를 당겼다. 이제 별도 deploy 축을 연다.

## 문제 분할

이슈 #25 §1~4의 전면 설계를 한 사이클에 삼키지 않는다(C061→C086의 "가장 작은 토대부터" 리듬). 전면 설계는:

1. `gil deploy cut <chain> <cycle-id> --version <semver>` — 닫힌 사이클을 배포 버전으로 승격, `deploy/<chain>/<semver>` 태그
2. append-only 레코드(version·source cycle·아티팩트 서술·운영 파라미터·성능·deployed_at·supersedes·status)
3. `gil deploy list/current/rollback` — 라이브 조회·롤백 타깃 식별
4. fsck 확장(배포는 닫힌 사이클 근거, live는 체인당 1개)

**핵심 설계 판단 — 결의 분리**: 기존 `gil release`(v태그)는 **gil 도구 자신**의 릴리스에 특화(blob 대조·version 표면 동기화)다. 사용자 산출물 배포는 결이 다르다(모델/서빙, `deploy/<chain>/<semver>` 별도 태그). 이름 충돌·의미 오염을 피하려 **새 명령족 `gil deploy`** 로 분리한다(이슈 §2가 제안한 `release cut`이 아니라).

**이 사이클이 뗄 첫 조각 = §1 + §2의 최소 토대**: `gil deploy cut` 하나. 닫힌(그리고 rejected 아닌) 사이클을 근거로 `deploy/<chain>/<semver>` 태그를 각인하고, append-only 레코드 한 줄을 남긴다. `list`/`current`/`rollback`/`fsck`는 이 토대 위에 얹을 후속 카브(파싱할 데이터가 존재해야 얹을 수 있으므로 cut이 먼저다 — C086이 releases 조회의 데이터를 먼저 낳은 것과 같은 순서).

## 가설

> **가설**: 닫힌·비rejected 사이클을 근거로 `gil deploy cut <chain> <cycle> --version <semver> [--note ...]`가 (a) `deploy/<chain>/<semver>` 태그를 각인하고 (b) append-only 레코드(source cycle·semver·deployed_at·supersedes·status=live)를 한 몸에 남기며, (c) 열림/부재/rejected 근거와 중복 semver는 저장소 무변화로 거부한다면 — gil 도구 릴리스(v태그)와 의미가 겹치지 않는 별도 배포 축이 성립한다.

## 기각 조건

이 가설이 틀렸다고 인정하는 결과:

1. **네임스페이스 오염**: `deploy/*` 태그가 기존 `gil releases`(v* 대조)나 `gil release`의 판독을 교란한다(cycles=N 오독, drift 배지 오작동 등).
2. **거부 시 부작용 잔존**: 열림/부재/rejected/중복 semver 거부인데 태그·레코드·CHANGELOG 어느 하나라도 변경이 남는다(C086 "무변화 거부" 계약 위반). — 저장소 스냅샷 해시 대조로 검증.
3. **레코드 비대칭**: 태그의 진실과 레코드 파일의 진실이 어긋난다(같은 배포가 두 몸에서 다른 semver/사이클을 말함).
4. **정상 흐름 방해**: 기존 conformance 회귀(참조 123 / Go 105) 중 하나라도 깨진다.
5. **live 다중**: 같은 체인에서 두 번째 cut이 이전 것을 superseded로 내리지 못해 live가 2개가 된다(§4 "live는 체인당 1개" 불변식 위반).
