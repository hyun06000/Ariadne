# 4. 결과 분석

## 통계적 결과

| 판정 대상 | 이식 전 (HEAD:main.go) | 이식 후 | 기준(2-design) | 결과 |
|---|---|---|---|---|
| Go 총계 | 114/116 | **116/117** | 회귀 0 ∧ DEPLOY-NAMESPACE PASS | ✔ |
| DEPLOY-NAMESPACE | FAIL (rc=3) | **PASS** | PASS | ✔ |
| RELEASE-LIST | 미실행(게이트 닫힘) | **PASS** (새 활성) | — | ✔ |
| 참조 총계 | 134/134 | 134/134 | 무회귀 | ✔ |
| releases stdout/stderr/exit (태그+deploy+근거사이클) | — | 참조와 **바이트 동일** | 3면 동일 | ✔ |
| releases (git 부재 분기) | — | 참조와 **바이트 동일** | 동일 | ✔ |

회귀 0: 이식 전 통과하던 모든 항목이 이식 후에도 통과(WEB-DEPLOYMENTS는 이식 전에도 FAIL — 내 변경이 만든 것 아님, 아래 참조). 순증 +2(DEPLOY-NAMESPACE, RELEASE-LIST).

## 데이터 직접 관찰

- **DEPLOY-NAMESPACE의 실제 근거**: 태그 v1.0.0(도구 릴리스), deploy/art/1.0.0(배포), cycle/x/C001-y(사이클)를 함께 심은 저장소에서 Go `releases` 출력은 `gil:release 1.0.0 …` 한 줄만 내고 `deploy/art`·`svc/C001-good`·`cycle/`은 어디에도 없다. 네임스페이스 분리의 기계적 원인은 `gitReleaseTags`의 `refs/tags/v*` 글롭 + `relSemverRe`(`^\d+\.\d+\.\d+$`) 필터 — `deploy/art/1.0.0`은 `v`로 시작하지 않아 글롭에서 탈락, `cycle/x/C001-y`는 SemVer 필터에서 탈락. C103 이월 진단("네임스페이스 분리는 Go에 이미 성립, 검증 경로만 미이식 명령을 지날 뿐")이 정확했음이 실증됐다 — 이식한 것은 분리 로직이 아니라 그 분리를 관찰하는 명령 표면이다.
- **바이트 대조 인용**(runs/bytediff-go.stdout): `  v1.1.0     2026-07-21 [T·] ⚠drift  Ariadne release v1.1.0 — 태그만 drift` — 태그에만 있는 릴리스가 `[T·]`·⚠drift로, note는 태그 subject로 표기됨이 참조와 문자 단위로 일치. `gil:release 1.2.0 2026-07-20 tags=0 changelog=1 cycles=2`에서 근거사이클 2개(loom/C061, loom/C086)를 센 `cycles=2`도 일치 — 이것이 `clEntry.cycles` 델타를 채운 이유다.
- **RELEASE-LIST 활성화 관찰**(conformance.py line 1108): 이 항목은 `impl.run("help","releases").returncode==0`을 게이트로 둔다. 이식 전 Go는 `help releases`가 exit 3(notImplemented)이라 판정기가 항목을 건너뛰어 baseline 분모가 116이었다. commandTable 등록으로 `help releases`가 exit 0이 되자 게이트가 열려 분모 117 + RELEASE-LIST PASS.

## 예상과 달랐던 것

- **분모가 늘 줄 알았는데 게이트 때문에 항목이 "나타났다"**: 설계에서 "115 이상"을 예상했으나, 판정기가 releases 판정 항목(RELEASE-LIST)을 help-게이트로 조건부 실행하고 있었다. 이식은 점수만 올린 게 아니라 판정기가 보는 항목의 집합 자체를 넓혔다 — C036("판정기가 안 보는 계약은 없다")·C050("등록이 분모를 늘린다")의 재현.
- **범위 밖 선재 결함 국소화 — WEB-DEPLOYMENTS**: Go의 유일한 잔여 FAIL. 이식 전 baseline에서도 FAIL(runs/go-baseline-conformance.txt로 확인)이므로 **내 releases 이식이 만든 회귀가 아니다.** 이 항목은 사용자 산출물 배포(deployments.json)를 뷰어 gil-data에 심는 것(loom/C104, 이슈 #18)으로, 릴리스 축이 아니라 배포 축의 **뷰어** 이식이다 — Sheen이 gil.py 뷰어에서 진행한 C104의 Go 미이식분. releases 이식과 무관하며 별개 축·별 사이클의 몫이라 **고치지 않고 이월**(C036·C044·C046의 절제).

## 판정

**가설 채택.** 참조 `cmd_releases`를 Go에 이식하니 DEPLOY-NAMESPACE가 PASS, RELEASE-LIST가 새로 PASS, 참조·기존 Go 항목 회귀 0, releases 출력이 참조와 스토드아웃·스터드에러·종료코드 3면 모두 바이트 동일(git-부재 분기 포함). 기각 조건(NAMESPACE FAIL·회귀·바이트 불일치·태그 유출) 어느 것도 성립하지 않았다. C103의 이월("releases 이식하면 115/115")이 되찾아졌다 — 현 판정기 기준으로는 116/117, 잔여 1은 범위 밖 배포-뷰어 축(WEB-DEPLOYMENTS).
