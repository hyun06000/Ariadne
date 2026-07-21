# 2. 실험 설계

가설: 배포 축을 chain→artifact 키로 재정렬하면 필드 #27 실제 레코드를 gil로 관리할 수 있다.

## 하위호환 판단 (재정렬 정당성)

deployments.json에 **실데이터가 아직 없다**(필드가 배포 홀드 중, 방금 확인). conformance DEPLOY-* 항목만 chain-키를 검증한다. 즉 **하위호환 부담 없이 artifact-키로 갈아탈 적기**다. Selvage의 chain-키는 실증 전 가정이었고, 필드 실증이 artifact-키를 요구했다. 이건 파괴적 변경이 아니라 **아직 안 쓰인 인터페이스의 정렬**이다.

## 재정렬 매핑 (Selvage 로직 골격 재사용, 키만 교체)

| 요소 | C101 (chain) | C102 (artifact) |
|---|---|---|
| 명령 | `deploy cut <chain> <cycle> --version` | `deploy <artifact> <semver> --cycle <c>/<id>...` |
| 레코드 키 | `chain` | `artifact` + `kind` |
| 소스 | `source_cycle`(단수) | `source_cycles`(복수 배열) |
| 조회 | `deploy list/current/rollback <chain>` | `deploys/current/rollback <artifact>` |
| R17 | live_count[chain] | live_count[artifact] |
| 태그 | `deploy/<chain>/<semver>` | `deploy/<artifact>/<semver>` |

Selvage의 로직(live 전이·supersede·단조증가·태그·닫힌소스 게이트·append-only)은 **전부 계승**하고, 키 축만 chain→artifact.

## 절차 (참조 gil.py)

1. **레코드 스키마**: `{artifact, kind, version, source_cycles:[...], target, params, performance, deployed_at, supersedes, status, notes}`. #27 필드 반영(target·kind·notes 추가).
2. **`_deploy_cut` → artifact 키**: 
   - 인자: `<artifact>` positional + `<semver>` + `--cycle`(append, 복수) + `--kind` + `--target` + `--notes`.
   - 소스 검증: **각 source_cycle**을 `_resolve_source_cycle`로 닫힘·비rejected 확인(복수 순회).
   - live 전이: `_live_deployment(deployments, artifact)`(artifact별) → supersede.
   - 단조증가: 그 artifact의 마지막 버전보다 커야.
   - 태그: `deploy/<artifact>/<semver>`.
3. **조회 헬퍼**: `_chain_deployments`→`_artifact_deployments(deployments, artifact)`, `_live_deployment`도 artifact 키.
4. **명령 이름**: 필드 #27은 `gil deploy <artifact>...`·`gil deploys`·`gil current`·`gil rollback`. 단 `current`/`rollback`은 최상위면 다른 명령과 충돌 위험 → **`gil deploy` 하위로 통일**하되 artifact 키: `deploy <artifact> <semver>`(cut 겸), `deploy list [artifact]`(=deploys), `deploy current <artifact>`, `deploy rollback <artifact> <semver>`. (필드엔 이 매핑을 안내.)
5. **fsck R16**: `source_cycles` **배열 순회** 검증(각각 닫힘·비rejected·실재). R17: live_count를 **artifact별**로.
6. **conformance**: DEPLOY-* 항목을 artifact 키로 갱신 + 복수 source_cycles·kind 검증 추가.

## Go
- C101에서 deploy는 정직한 부재(exit 3). 이번도 참조 먼저 완성하고 Go는 이월(HELP-COMPLETE 유지) — 명시.

## 준비물
- gil v2.49.0. #27 실제 레코드(pii-extract-api 2.0.0, source_cycles 4개, kind api-spec).
- 단 #27의 source_cycles(app-serving/C020~C023)는 **이 저장소에 없다**(필드 저장소 것). → 검증은 이 저장소의 닫힌 사이클로 대체하되, 스키마·동작이 #27 레코드를 담을 수 있음을 확인.

## 측정 방법

| # | 측정 | 기준 |
|---|---|---|
| M1 | #27 형태 배포 기록(artifact·복수cycle·kind) | 레코드가 왜곡 없이 deployments.json에 (kill 1) |
| M2 | 같은 artifact 2번 배포 | 직전 superseded·fsck artifact live 1 (kill 2) |
| M3 | rejected/열린/없는 source_cycle | 거부 (kill 3) |
| M4 | deploy list/current/rollback | artifact 키로 정확 조회·롤백 |
| M5 | conformance | ≥133 유지(재정렬 반영), DEPLOY-* 초록 (kill 4) |
| M6 | 그리디 | #27 5기능 동작하면 멈춤 (kill 5) |

## 검증분석 분기 (미리)
- M1~M5 통과 → 성공 잎: 배포 축 artifact 재정렬 완성. 닫고 배포 판단(굵직하게 — 배포축 사이클 모이면).
- M1 왜곡 → 스키마 재설계. M3 게이트 풀림 → Selvage 로직 재확인.

## 사용자 컨펌
- 생략 — 상현님 "배포 관리 일단 만들자" + 필드 #27 실증이 명확한 요구. 이 설계가 그 직접 실행.
- [x] 컨펌 불요 (2026-07-21)
