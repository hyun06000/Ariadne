# 2. 실험 설계

## 네임스페이스 분리 (도구 릴리스와 절대 안 섞는다)

| 축 | 명령 | 태그 | 레지스터 |
|---|---|---|---|
| 도구 릴리스 (gil 자신) | `gil release` / `gil releases` | `v<semver>` | `rooms/deployment/CHANGELOG.md` |
| **사용자 산출물 배포 (신규)** | `gil deploy cut/list/current/rollback` | `deploy/<chain>/<semver>` | `rooms/deployment/deployments.json` |

두 축은 명령·태그 글롭·레지스터 파일이 전부 다르다. `_git_release_tags`는 `refs/tags/v*`만 보고 SemVer
필터를 하므로 `deploy/*` 태그를 자동 배제한다 — releases 조회가 배포 태그에 오염되지 않는다.

## deployments.json 스키마 (append-only)

배포의 방(`rooms/deployment/deployments.json`)에 산다 — 도구 릴리스 파일(CHANGELOG)과 안 섞이게 별 파일.

```json
{
  "version": 1,
  "deployments": [
    {
      "chain": "loom", "version": "1.0.0",
      "source_cycle": "loom/C042-quantize",
      "artifact": "Llama-3-8B AWQ-4bit / vLLM 0.5.1",
      "params": "concurrency=32",
      "performance": "p50=120ms tput=45req/s",
      "deployed_at": "2026-07-20",
      "supersedes": null,
      "status": "live"
    }
  ]
}
```

append-only 규율: 과거 레코드는 지우지 않는다. 새 cut은 배열 끝에 append하고, 직전 live 레코드의 status를
`live`→`superseded`로 전이(제자리 수정이되 삭제 아님). rollback도 전이만: 현 live→`rolled-back`,
supersedes가 가리키는 직전 배포→`live` 재활성. 태그(`deploy/<chain>/<semver>`)는 깃의 진실, json은 운영 원장.
태그↔json drift 게이트는 이월(첫 카브는 골격; release drift는 C072가 이미 함).

## 명령 설계

- **`gil deploy cut <chain> <cycle-id> --version <semver> [--artifact][--params][--perf]`**
  사전 검증(저장소 건드리기 전 전부): ① semver 형식 ② `_resolve_source_cycle`로 소스 사이클 실재+`closed`
  (rejected/열림/없음 거부 — §3.2 출처 계약) ③ `deploy/<chain>/<semver>` 태그 미존재 ④ 그 체인의 기존 배포
  버전보다 큰 semver ⑤ `_fsck_or_report`(깨진 저장소 위엔 배포 안 함).
  실행: 직전 live→superseded 전이 → 새 레코드 append(supersedes=직전 live version) → json 커밋 →
  `deploy/<chain>/<semver>` 태그 각인(소스 cycle-id를 태그 메시지에 링크). 실패 시 롤백.
- **`gil deploy list <chain>`** — 그 체인 배포 레코드 최신 우선. 훅 `gil:deploy` + 요약 `gil:deploys <n> live=..`. 읽기 전용.
- **`gil deploy current <chain>`** — 현 live 레코드 하나. 없으면 "(없음)". 읽기 전용.
- **`gil deploy rollback <chain>`** — 현 live→rolled-back, supersedes가 가리키는 직전 배포→live 재활성.
  직전 배포 없으면(supersedes=null) 거부(되돌릴 곳 없음).

## fsck 확장 (무결성 불변식)

`fsck_collect`에 배포 검사(chains_root 있을 때만 파일을 본다 — R10·R13·R14 패턴). deployments.json은
chains_root에서 `../../deployment/deployments.json` 유추. chains_root=rooms/experiment/chains →
rooms/deployment/deployments.json.

- **R16 소스 무결성**: 각 배포 `source_cycle`은 실재하는 **닫힌** 사이클. 열림/없음/rejected → 위반.
- **R17 live 불변식**: 체인당 `status==live` 최대 1개. 2개↑ → 위반.

신규 규칙이라 유예할 과거 없고, cut/rollback이 항상 불변식을 지켜 정당한 탈출구 없음(R13·R14 선례).
deployments.json 없으면 규칙 불발(하위호환).

## conformance (DEPLOY-*)

`deploy`를 CONTRACT_COMMANDS에 등록(Go 미구현 → HELP-COMPLETE가 exit 3 정직성 판정).
`help deploy`가 0일 때만 판정(부분 구현 합법):

- **DEPLOY-CUT**: 닫힌 사이클 cut → `deploy/<chain>/<semver>` 태그 ∧ json 레코드 ∧ live ∧ 소스 링크.
  열린/rejected/없는 소스 → 무변화 거부.
- **DEPLOY-LIVE-INVARIANT**: 둘째 cut → 직전 live=superseded ∧ live 1개 ∧ fsck OK. 직접 조작으로 live 2개 → fsck 위반.
- **DEPLOY-QUERY**: list 전체 ∧ current 현 live ∧ 읽기 전용.
- **DEPLOY-ROLLBACK**: rollback → 현 live=rolled-back ∧ 직전 재활성 ∧ live 1개.
- **DEPLOY-NAMESPACE**: deploy 태그가 releases(`v*`) 조회에 안 섞인다.

## 측정 방법

종료코드·파일시스템 관찰(태그·json)·산출물 텍스트(훅)로만 판정. 성공 = 참조 conformance 신규 DEPLOY-* 전부
PASS ∧ 기존 회귀 0 ∧ Go는 HELP-COMPLETE로 정직한 부재. 기각 = 출처 날조 허용·live 불변식 붕괴·네임스페이스 오염 중 하나.

## 사용자 컨펌

- 카브 경계(cut+레지스터+조회+rollback+fsck, Go/drift게이트 이월)는 소환자 Clew의 위임 지침과 일치 —
  별도 컨펌 생략(위임 범위 내). 경계 근거는 1-hypothesis·본 문서에 기록.
- [x] 컨펌 받음 (Clew 위임 지침, 일자: 2026-07-20)
