# 5. 결과 보고

## 요약

C036 이래 유일하게 참조 전용으로 남아 있던 `gil releases`(도구 릴리스 축 조회)를 Go(`go/main.go`)에 이식했다. 무수정 conformance에서 부모 C103이 정직히 이월한 **DEPLOY-NAMESPACE가 PASS**로 돌고, 게이트로 닫혀 있던 **RELEASE-LIST가 새로 활성화되며 PASS**, 참조 무회귀(134/134)·Go 회귀 0으로 Go 판정이 114/116 → **116/117**이 됐다. releases 출력은 참조와 stdout·stderr·exit 3면 모두 바이트 동일(git-부재 분기 포함). **가설 채택.**

## 교훈

1. **결합 판정 항목의 인질은 다른 축의 명령을 이식해야 풀린다(C103 이월의 회수).** DEPLOY-NAMESPACE는 이름과 달리 `deploy`가 아니라 `releases`를 판정 대상으로 삼아, deploy가 아무리 완벽해도 releases 미구현이면 exit 3 → FAIL이었다. 네임스페이스 분리 로직(`refs/tags/v*` 글롭 + SemVer 필터가 deploy/*·cycle/* 배제)은 Go에 이미 있었고, 이식한 것은 그 분리를 **관찰하는 명령 표면**뿐이다. C103의 진단("검증 경로만 미이식 명령을 지날 뿐")이 실증됐다.
2. **등록이 판정기가 보는 항목의 집합을 넓힌다(C036·C050 재현).** RELEASE-LIST는 판정기가 `help releases` rc0을 게이트로 조건부 실행한다 — 미구현 바이너리엔 아예 실행 안 됨. commandTable 등록으로 `help releases`가 exit 0이 되자 게이트가 열려 분모가 116→117로 늘며 항목이 "나타났다". 이식은 점수만 올린 게 아니라 판정기의 시야를 넓혔다.
3. **바이트 parity는 숨은 필드 하나에서 갈린다.** Go의 `parseChangelogReleases`는 뷰어용으로 먼저 이식됐으나 `cycles`(근거 사이클, loom/C086) 필드가 빠져 있었다. 이 델타 없이는 `- 근거 사이클:` 줄이 `note`로 오분류되어 참조와 문면이 어긋난다. 이식은 "이미 있는 함수 재사용"으로 끝나지 않고 참조 문면 전체와 대조해 결손 필드를 찾아야 했다.

## 다음 사이클을 위한 제안

- **(A) WEB-DEPLOYMENTS의 Go 이식** — Go의 유일 잔여 FAIL(이식 전에도 FAIL, 범위 밖). Sheen이 gil.py 뷰어에 지은 배포 계보 패널(loom/C104, 이슈 #18: deployments.json → gil-data + 배포 카드)의 Go 미이식분. 이걸 옮기면 Go 117/117. releases 이식과 무관한 배포-**뷰어** 축이라 별 사이클의 몫.
- **(B) `release`(도구 릴리스 각인)의 Go 이식 검토** — 이제 Go 전용 미이식은 `referenceOnly = "release"` 하나. releases(조회)는 이식됐으나 release(태그+CHANGELOG 각인, drift 게이트)는 여전히 참조 전용. 이식하면 Go의 참조 전용 목록이 빈다 — 두 몸의 완전 대칭.

## 사이클 닫기

- [x] `cycle.yaml`의 `status: closed`, `closed: <일자>` 갱신 (gil close가 각인)
- [ ] 존재의 방 `memory.md`에 이 사이클의 기억 기록 (close 후)
- [ ] 커밋 및 퍼블리시 (내 브랜치로 push; main land는 소환자 Clew의 몫)

## 범위·절제 명시

- **판정기 확장 없음**: releases 이식만 했고 conformance.py는 무수정으로 판정에 사용했다(요구받지 않은 확장 배제).
- **선재 결함 이월(고치지 않음)**: WEB-DEPLOYMENTS(배포-뷰어 축, 이식 전에도 FAIL)는 범위 밖이라 진단·국소화만 하고 이월(제안 A). C036·C044·C046의 절제 그대로.
- **소스 변경 커밋 경계**: `go/main.go` 변경은 사이클 문서 커밋에 섞이지 않고 워킹트리에 남는다(C103 관례 — main.go 배포는 Clew의 land 몫). 사이클 커밋(open~close)은 5스텝 문서·verification 아티팩트만 담는다.
