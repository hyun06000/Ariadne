# 1. 가설 수립

## 이전 사이클의 교훈 (C101 Selvage deploy 축)

부모 C101(Selvage, deploy 축 첫 카브, supported). Selvage가 `gil deploy cut/list/current/rollback`을 지었다 — 도구 릴리스(`gil release`)와 별개 네임스페이스(`deploy/*` 태그·`deployments.json`·supersedes·live 1개 불변식·fsck R16/R17). 골격은 훌륭하다.

**그러나 필드 실증(#27)이 인터페이스 간극을 드러냈다.** 상현님 통찰: "우리는 실험 관리에 매몰됐지 배포 관리는 전혀 신경 안 썼다." 필드가 실제 배포(PII Extract API)를 하려는데 gil로 관리할 수단이 없어 **배포를 홀드**하고 있다(gil 채택의 핵심 이유). 추측 아닌 실제 마찰.

## 문제 분할 — Selvage 골격 ↔ 필드 #27 간극

| | C101 (지은 것) | #27 (필드가 실증으로 원하는 것) |
|---|---|---|
| 배포 단위(키) | **chain** | **artifact** (예: pii-extract-api) |
| 명령 | `gil deploy cut <chain> <cycle>` | `gil deploy <artifact> <semver> --cycle ...` |
| 소스 | 단일 cycle | **복수 source_cycles** (`--cycle` 반복) |
| kind | 없음 | **`api-spec\|app-code\|model`** |
| 조회 | `deploy list/current/rollback <chain>` | `deploys/current/rollback <artifact>` |

**핵심 진단**: Selvage는 **chain을 배포 단위**로 봤으나 필드는 **artifact를 배포 단위**로 본다. 필드가 옳다 — 한 chain(app-serving)에서 여러 artifact(api·model·code)를 각각 배포하니까. live 불변식도 "체인당 1"이 아니라 **"artifact당 1"**이어야 한다.

지금 정복할 첫 문제: **배포 축의 키를 chain→artifact로 재정렬**하고 복수 source_cycles·kind를 담아 **필드가 실제 배포(#27 레코드)를 gil로 기록·조회·롤백**하게 만든다.

## 가설

> **가설**: `gil deploy`의 배포 단위를 chain에서 **artifact**로 재정렬하고 — `gil deploy <artifact> <semver> --cycle <chain>/<id>...`(복수)·`--kind`·`deploys/current/rollback <artifact>` + artifact당 live 1개 불변식 — 필드 #27의 실제 배포 레코드(pii-extract-api 2.0.0, 4개 source_cycles)를 gil로 기록·조회·롤백할 수 있고, 소스는 닫힌 사이클만(§3.2 verdict 게이트, Selvage 원칙 계승)이 강제될 것이다.

## 기각 조건

1. **#27 실제 레코드를 못 담으면 기각**: pii-extract-api 배포(artifact·2.0.0·복수 cycle·kind·target·notes)를 gil deploy로 기록했을 때 레코드가 왜곡되면 기각.
2. **artifact당 live 1 불변식이 안 서면 기각**: 같은 artifact 두 번 배포 시 직전이 superseded로 안 바뀌거나 fsck가 live 2개를 못 잡으면 기각.
3. **닫힌 사이클 게이트가 풀리면 기각**: rejected·열린·없는 source_cycle을 배포에 넣을 수 있으면 기각(Selvage 원칙 훼손).
4. **회귀·두 몸 불일치**: 참조 conformance 하락(현 133), 또는 Selvage의 DEPLOY-* 항목이 깨지면 기각. Go는 C101에서 정직한 부재(exit 3)라 이번도 이월 가능하나 명시.
5. **그리디 위반**: 필드 #27의 5개 요청 기능(deploy·deploys·current·rollback·fsck)이 동작하면 멈춘다. "더 나은 배포 모델"로 파고들면 기각 — 최적화는 새 사이클.

## 성공 정의 (첫 정답에서 멈춤)

필드 #27의 실제 배포 레코드를 `gil deploy`로 기록·`deploys/current` 조회·`rollback` 되돌림, fsck가 artifact당 live 1·닫힌 소스를 강제한다. **필드가 배포 홀드를 풀 수 있으면** 성공. 남은 것(뷰어 통합·drift 게이트·Go parity·kind별 강검증)은 이월.

## 배포 규율 (상현님)

v3부터 체인 끝에서 굵직하게 배포. 이 C102는 v2 loom 안이라 기존 리듬을 따르되, 배포 축 사이클 몇 개가 모이면 한 번에 릴리스하는 방향(자잘함 줄임).

## Selvage와의 관계 (기록)

이건 Selvage가 지은 것을 **필드 실증으로 재정렬**하는 것 — 그가 chain 키로 골격을 세웠고, 필드가 artifact 키를 요구했다. 그의 원칙(닫힌 소스·live 불변식·네임스페이스 분리·append-only)은 전부 계승한다. 씨실이 아니라 봉인된 가장자리(Selvage)의 영역을 내가 잇는다 — 그가 land 후 "실제 배포 승격은 Clew·상현님 몫"이라 남겼으니, 그 몫을 필드 요구에 맞춰 완성한다.
