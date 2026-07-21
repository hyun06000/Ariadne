# 4. 결과 분석

## 통계적 결과

- 이식 전 Go 110/110 → 이식 후 **114/115** (참조 133/133 무회귀).
- DEPLOY-* 5항목 중 4항목(CUT·LIVE-INVARIANT·QUERY·ROLLBACK) PASS, DEPLOY-NAMESPACE FAIL.
- 분모가 110→115로 +5: Go가 `help deploy`==0을 내며 conformance의 deploy 블록이
  "부분 구현 합법" 게이트를 통과, 5항목이 판정 대상으로 편입됐다.

## 데이터 직접 관찰

- **원장급 parity**: 동일 입력의 `deployments.json`이 Go↔참조 **바이트 동일**(diff 0).
  `saveDeployments`의 `json.NewEncoder` + `SetEscapeHTML(false)` + `SetIndent("", "  ")` +
  Encode 자동 끝 개행이 파이썬 `json.dump(ensure_ascii=False, indent=2)` + `f.write("\n")`와
  정확히 일치. `supersedes`를 `*string`으로 두어 null(첫 배포)과 값(대체)을 구분.
- **거부 4종**이 전부 exit 1 + 저장소 무변화: rejected/open/없는 소스, 비단조 버전. R16
  메시지도 fsck에서 참조와 바이트 동일.
- **불변식 전이**: 둘째 cut이 직전 live를 in-place로 superseded 전이(인덱스 기반
  `artifactDeployments`/`liveDeployment`), rollback이 현 live→rolled-back·직전→live 재활성.
  append-only(과거 레코드 미삭제) 보존.

## 예상과 달랐던 것

- **DEPLOY-NAMESPACE는 deploy가 아니라 release를 판정한다.** 이 항목은 `gil releases`가
  배포 태그를 릴리스 조회에 안 섞는지를 본다 — 판정 대상 명령이 `releases`다. Go는
  `releases`를 애초에 구현하지 않으므로(referenceOnly, C036 이래 릴리스 축은 참조 전용)
  exit 3 → FAIL. 이식 대상(deploy artifact 축)의 결함이 아니라 **판정 항목이 두 축을
  결합**한 결과다. C046("남은 8항목은 예약 계열")의 재현: 목표 수치를 분해하니 미달분이
  이식 범위 밖(별개 축)의 의존이었다.
- 네임스페이스 분리 자체는 Go에서 성립한다 — `gitReleaseTags`의 SemVer 필터가 `deploy/*`를
  이미 배제하고, deploy는 `deploy/<artifact>/<semver>` 별 네임스페이스에 태그를 찍는다.
  검증 항목만 미이식 `releases`를 경유할 뿐, 실제 분리는 깨지지 않았다.

## 판정

**가설 부분 채택.** deploy artifact 축의 이식은 완결·검증됐다: DEPLOY 4/5 통과, 원장·문자면
바이트 parity(C036 원장급 기준 충족), R16/R17 집행. 미달 1항목은 미이식 `releases`에 대한
판정기의 결합 의존으로 deploy 이식의 결함이 아니다 — 우회·억지 통과 없이 정직히 이월한다.
DEPLOY-NAMESPACE 통과는 별개 사이클(release 축 Go 이식)의 몫으로 제안한다.
