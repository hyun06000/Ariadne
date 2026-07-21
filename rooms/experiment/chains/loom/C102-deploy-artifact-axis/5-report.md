# 5. 결과 보고

**사이클**: loom/C102-deploy-artifact-axis · **부모**: loom/C101-deploy-axis-cut (Selvage) · **저자**: clew

## 요약

Selvage가 chain 키로 세운 deploy 축(C101)을, 필드 실증(#27)이 요구한 **artifact 키**로 재정렬했다. `gil deploy cut <artifact> <semver> --cycle <chain>/<id>...`(복수)·`--kind` + `deploy list/current/rollback <artifact>` + artifact당 live 1 불변식(fsck R17). 필드의 실제 배포 레코드(pii-extract-api 2.0.0, 복수 소스, kind api-spec)를 gil로 기록·조회·롤백함을 격리 샌드박스로 실증. 참조 133/133·Go 110/110(정직한 부재) 무회귀로 **채택**.

## 교훈

1. **틀린 건 축이었지 구조가 아니었다.** Selvage의 불변식(닫힌 소스·live 1·supersede·append-only·네임스페이스 분리)은 전부 옳았고, 키만 chain→artifact로 옮기니 그대로 작동했다. 실증 전 가정(chain 단위)이 필드에서 교정됐다 — 골격을 올바르게 세우면 축 이동은 값싸다.
2. **배포 단위는 artifact다(필드가 가르침).** 한 chain(app-serving)에서 여러 artifact(api·model·code)를 각각 배포하니, live 불변식도 "체인당 1"이 아니라 "artifact당 1". 실험 계보(chain)와 배포 계보(artifact)는 축이 다르다 — source_cycles가 둘을 잇는다(복수 사이클→한 배포).
3. **상현님 통찰의 실물**: "실험 관리에 매몰, 배포 관리 방치." 우리가 100+ 사이클로 실험 구조를 판 동안, 필드는 배포를 gil로 못 해 홀드하고 있었다. 이 사이클이 그 홀드를 푼다 — 필드가 실제로 원한 것.

## 다음 사이클을 위한 제안 (이월)

1. **Go parity** — deploy 명령군 이식(현 exit 3). 배포 축이 커졌으니 큰 카브.
2. **뷰어 통합** — Sheen web에 배포 계보(#18의 뷰어 절반).
3. **태그↔json drift 게이트** — release C072의 배포판.
4. **kind별 강검증·아티팩트 스키마** — 지금 자유 형식.
5. **배포 규율(상현님)**: C101·C102 배포축 사이클이 모였으니 다음에 굵직하게 릴리스.

## 산출물
- `rooms/deployment/ariadne-spec/gil.py` — cmd_deploy artifact 재정렬 + _artifact_deployments·_DEPLOY_KINDS·_src_str + fsck R16(복수 소스)/R17(artifact live 1) + 파서.
- `rooms/deployment/ariadne-spec/conformance.py` — DEPLOY-* 5항목 artifact-키 갱신.

## 사이클 닫기
- [ ] status closed·verdict supported
- [ ] memory 기록
- [ ] 커밋·퍼블리시 (배포는 굵직하게 — 다음 배포축 사이클과 함께)
