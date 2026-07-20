# 1. 가설 수립

## 이전 사이클의 교훈

부모: **loom/C100-restore-lost-lineage** (잃은 계보의 복원). 그리고 나의 앞선 두 폭 —
C061(`gil releases`, 배포 계보 조회)·C072(release drift 게이트) — 은 **도구 릴리스**(`gil release`,
`v<semver>` 태그, CHANGELOG)의 계보였다. 그것은 gil 도구 **자신**이 무엇으로 언제 나갔는가의 기록이다.

이슈 #25가 드러낸 간극: 필드 사용자가 기대한 건 그게 아니라 **사용자 산출물(모델/서빙) 배포**의
추적이다 — "무엇이 지금 라이브인가 / 언제 무엇으로 교체했나 / 문제 시 무엇으로 롤백하나". 도구 릴리스와
사용자 산출물 배포는 결이 완전히 다른 두 축이다. `gil release`(도구 자신)를 그것으로 오해해 "배포 관리가
전혀 없다"는 답이 나왔다.

## 문제 분할

이슈 #25 전체 = ① `gil deploy cut`(닫힌 사이클 → 배포 버전 승격, `deploy/<chain>/<semver>` 태그) +
② append-only 배포 레지스터(`deployments.json`) + ③ `deploy list/current/rollback` 조회·롤백 +
④ fsck 무결성(닫힌 사이클 소스·live 1개 불변식).

**작게 정복한다(서약 4).** #25 전부를 한 사이클에 삼키지 않는다. 첫 카브 경계:

> **첫 카브 = `gil deploy cut` + `deployments.json` 레지스터 + `deploy list`/`current` 조회 +
> `deploy rollback` + fsck 무결성(닫힌 사이클 소스·live 1개).**

rollback은 supersedes 링크가 레지스터에 서면 자연히 얹히므로 첫 카브에 포함한다(cut→레지스터→조회→롤백→무결성의
최소 골격이 한 몸으로 닫힌다). **Go parity는 정직히 이월** — 새 `deploy` 명령군은 conformance의
HELP-COMPLETE가 exit 3으로 Go의 정직한 부재를 판정한다(C043/C061 리듬). 아티팩트 서술 필드의 풍부한
스키마(모델/양자화/vLLM/성능)는 레지스터가 자유 형식 필드로 받되, 검증은 최소만(첫 카브는 골격 우선).

## 가설

> **가설**: `gil release`(도구 자신)와 **별개의 네임스페이스** `gil deploy`를 지어 —
> `cut`이 닫힌 사이클을 소스로 요구(§3.2 출처 계약 재사용, `_resolve_source_cycle`)해 `deploy/<chain>/<semver>`
> 태그를 각인하고 append-only `deployments.json`에 supersedes 링크와 함께 레코드를 추가하며,
> `list`/`current`가 이를 조회하고 `rollback`이 supersedes로 되돌리며, fsck가 "소스는 닫힌 사이클 ∧
> live는 체인당 1개" 불변식을 집행하면 — 사용자 산출물 배포 축이 도구 릴리스와 섞이지 않고 세워질 것이다.

## 기각 조건

- cut이 rejected/열린/없는 사이클을 소스로 배포를 허용하면(출처 날조) → 기각.
- 두 번째 cut이 직전 live를 superseded로 전이시키지 못해 live가 체인당 2개가 되면 → 기각.
- fsck가 "live 2개" 또는 "열린 사이클 소스"를 위반으로 잡지 못하면 → 기각.
- `deploy`가 `release`의 태그(`v*`)·레지스터(CHANGELOG)와 섞이면(네임스페이스 오염) → 기각.
- 참조/Go conformance에 회귀가 하나라도 생기면 → 기각.
