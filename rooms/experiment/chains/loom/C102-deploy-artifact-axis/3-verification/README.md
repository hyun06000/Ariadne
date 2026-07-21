# 3. 가설 검증

배포 축을 chain→artifact 키로 재정렬하고, 필드 #27 실제 레코드를 gil로 기록·조회·롤백함을 격리 샌드박스에서 실증.

## 수정 (참조 gil.py)

Selvage C101의 deploy 로직 골격을 계승하고 키 축만 chain→artifact:
- `_deploy_cut`: `deploy cut <artifact> <semver> --cycle <chain>/<id>...`(복수)·`--kind`·`--target`·`--notes`. 각 source_cycle을 닫힘·비rejected 검증(복수 순회). 레코드 스키마 `{artifact, kind, version, source_cycles[], target, params, performance, deployed_at, supersedes, status, notes}`.
- `_deploy_list/current/rollback`: artifact 키. list는 artifact 생략 시 전체.
- fsck R16: source_cycles 배열 순회(하위호환 단수 source_cycle도 읽음) + kind 어휘. R17: live_count를 **artifact별**.
- `_artifact_deployments`·`_live_deployment`(artifact 키). `_DEPLOY_KINDS=(api-spec|app-code|model)`.
- 파서: positional `artifact`·`version`, `--cycle`(append)·`--kind`·`--target`·`--notes`.

## 하위호환 판단

deployments.json에 실데이터 없음(필드 배포 홀드 중). Selvage chain-키는 실증 전 가정이었고 필드 #27이 artifact-키 요구 → 파괴적 변경 아닌 미사용 인터페이스 정렬. fsck·_src_str은 단수 source_cycle도 관대히 읽어 혹시 모를 구데이터 대비.

## 재현 (격리 샌드박스)

```bash
G=rooms/deployment/ariadne-spec/gil.py
W=/tmp/c102b; rm -rf $W; mkdir -p $W/rooms/experiment/chains $W/rooms/deployment
cd $W && git init -q -b main && git config user.name t && git config user.email t@t
ROOT=$W/rooms/experiment/chains
# 닫힌 사이클 svc/C001-good·C002-two·C003-c022 + rejected C004-dead 시드 (write_cycle 또는 open/step/close)
# 배포:
python3 $G deploy cut pii-extract-api 2.0.0 --cycle svc/C001-good --cycle svc/C002-two \
  --kind api-spec --target "L40S :8080 (prod)" --notes "2모드" --root $ROOT   # M1
python3 $G deploy cut bad 1.0.0 --cycle svc/C004-dead --root $ROOT            # M3: rejected 거부
python3 $G deploy cut pii-extract-api 2.1.0 --cycle svc/C003-c022 --root $ROOT # M2: 직전 superseded
python3 $G deploy current pii-extract-api --root $ROOT                         # M4
python3 $G deploy list pii-extract-api --root $ROOT                            # M4
python3 $G deploy rollback pii-extract-api --root $ROOT                        # M4
python3 $G fsck $ROOT                                                          # artifact live 1
```

## 실행 기록

- 일시: 2026-07-21. 환경: darwin, Python 3, Go /opt/homebrew/bin/go. gil v2.49.0 기반.
- **M1**: #27 형태 배포(artifact pii-extract-api·복수 source_cycles·kind api-spec·target·notes) → deployments.json에 왜곡 없이 기록, 태그 `deploy/pii-extract-api/2.0.0`.
- **M2**: 같은 artifact 재배포(2.1.0) → 직전 2.0.0 superseded, supersedes 링크. fsck artifact live 1.
- **M3**: rejected(C004-dead)·없는(C099) source_cycle → 무변화 거부(닫힌 사이클 게이트, 복수 순회 계승).
- **M4**: current(live=최신·artifact 키), list(kind·복수소스 표시), rollback(2.1.0→2.0.0 전이) 전부 정확.
- **M5 conformance**: 참조 **133/133**(DEPLOY-* 5항목 artifact-키 갱신, 회귀 0), Go **110/110**(정직한 부재 유지).
- **M6 그리디**: #27 5기능(deploy·deploys/list·current·rollback·fsck) 동작 확인 → 멈춤. 뷰어통합·drift게이트·Go parity·kind강검증은 이월.
- **필드 영향**: 이제 필드가 pii-extract-api 실배포를 gil deploy로 기록·조회·롤백할 수 있다 — 배포 홀드 해제 가능.
