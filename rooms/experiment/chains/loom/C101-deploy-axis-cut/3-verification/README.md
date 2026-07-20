# 3. 가설 검증

## 구현 (참조 gil.py)

- `deploy` 명령군 추가 (cmd_deploy → cut/list/current/rollback). 도구 릴리스와 별개 네임스페이스:
  명령 `deploy`, 태그 `deploy/<chain>/<semver>`, 레지스터 `rooms/deployment/deployments.json`.
- 헬퍼: `_deployments_path`(chains_root에서 유추)·`_load/_save_deployments`(append-only JSON)·
  `_deploy_tag`·`_chain_deployments`·`_live_deployment`·`_cycle_verdict`(rejected 게이트).
- cut 사전검증: semver 형식 → `_resolve_source_cycle`로 소스 실재+closed(§3.2 재사용) → rejected verdict 거부
  → 태그 미존재 → 체인 내 단조증가 → `_fsck_or_report`. 실행: 직전 live→superseded 전이 → append(supersedes링크)
  → json 커밋 → `deploy/<chain>/<semver>` 태그(소스 cycle-id 링크). 실패 시 reset+checkout 롤백.
- fsck 확장 R16(소스=닫힌 사이클, rejected 불가)·R17(체인당 live 1개). deployments.json 없으면 규칙 불발(하위호환).

## conformance (DEPLOY-*, 5항목)

- **DEPLOY-CUT**: 닫힌 사이클 cut → 태그 ∧ json 레코드(live·소스링크); rejected/열린/없는 소스 무변화 거부.
- **DEPLOY-LIVE-INVARIANT**: 둘째 cut → 직전 live=superseded ∧ live 1개 ∧ fsck OK; 직접 조작 live 2개 → fsck 위반.
- **DEPLOY-QUERY**: list 전체 ∧ current 현 live ∧ 읽기 전용(무변화).
- **DEPLOY-ROLLBACK**: rollback → 현 live=rolled-back ∧ 직전 재활성(live 1개·fsck OK); 첫 배포는 롤백 거부.
- **DEPLOY-NAMESPACE**: deploy 태그가 releases(v*) 조회에 안 섞인다.
- `deploy`를 CONTRACT_COMMANDS에 등록 → HELP-COMPLETE가 Go의 정직한 부재(exit 3)를 판정.
- `write_cycle`에 verdict 기록 추가(rejected 게이트 테스트용, 하위호환).

## 결과

| 몸 | 이전 | 이후 | 회귀 |
|---|---|---|---|
| 참조(gil.py) | 128/128 | **133/133** (신규 DEPLOY-* 5) | 0 |
| Go(main.go) | 110/110 | **110/110** (deploy=exit 3, HELP-COMPLETE) | 0 |

수동 스모크(격리 샌드박스): rejected/열린/없는 소스 cut 전부 거부(rc≠0·무변화), 정상 cut→태그+json,
둘째 cut→supersede(live 1개), list/current 정확, rollback 정상, fsck R16/R17가 손상된 레지스터(open 소스·live 3개)를 잡음.
릴리스 v* 태그와 deploy/* 태그가 releases 조회에서 분리됨. Go 소스는 미변경(deploy 정직 이월).

**H1·H2 채택** — 사용자 산출물 배포 축이 도구 릴리스와 섞이지 않고 세워졌고, 기각 조건 어느 것도 발생하지 않았다.
