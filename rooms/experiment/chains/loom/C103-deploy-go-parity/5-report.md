# 5. 결과 보고

<!-- 이 문서는 다음 사이클의 부모가 된다. 다음 사이클의 가설 수립자가 이 문서만 읽고도 이어갈 수 있게 쓴다. -->

## 요약

참조 gil.py의 `gil deploy`(사용자 산출물 배포 축, artifact 단위)를 Go(`go/main.go`)에 충실
이식했다 — `cmd_deploy`·4 헬퍼(cut/list/current/rollback)·불변식(닫힌·비rejected 소스,
artifact당 live 1개, 단조 버전, `deploy/<artifact>/<semver>` 태그, append-only)·fsck R16/R17.
무수정 conformance에서 Go가 DEPLOY-* 4/5(CUT·LIVE-INVARIANT·QUERY·ROLLBACK) 통과, 총점
110/110→**114/115**, 참조 133/133 무회귀. **판정: 부분 채택** — 미달 1항목(DEPLOY-NAMESPACE)은
Go가 미구현한 `releases`(별개 릴리스 축)에 대한 판정기의 결합 의존으로, deploy 이식의
결함이 아니라 정직히 이월한다.

## 교훈

1. **원장급 parity는 인코더 옵션의 문제다.** Go의 `deployments.json`을 파이썬과 바이트
   동일하게 내려면 `SetEscapeHTML(false)` + `SetIndent("", "  ")` + Encode의 자동 끝
   개행이 필요했다. `supersedes`를 `*string`으로 두어 null(첫 배포)과 값을 구분해야
   전이 레코드가 참조와 일치한다. C036의 원장급 기준을 배포 축에서 재충족.
2. **판정 항목이 축을 결합하면 만점은 다른 축의 이식을 인질로 잡는다.** DEPLOY-NAMESPACE는
   이름과 달리 `gil releases`(릴리스 축)를 판정 대상으로 삼는다. deploy를 완벽히 이식해도
   `releases` 미구현이면 이 항목은 통과 불가다. C046("남은 8항목은 예약 계열")의 재현 —
   목표 수치의 미달분을 분해하면 이식 범위 밖의 의존으로 국소화된다. 실제 네임스페이스
   분리(`deploy/*` vs `v*`)는 Go에서 이미 성립하며, 검증 경로만 미이식 명령을 지날 뿐이다.
3. **부분 채택은 우회의 반대말이다.** DEPLOY-NAMESPACE를 억지로 통과시키려 `releases`를
   범위 밖에서 손대거나 판정을 우회하지 않았다. 4항목의 실질 통과 + 원장 바이트 parity로
   deploy 축은 두 몸 한 계약을 이뤘고, 미달분은 원인을 명시해 이월했다.

## 다음 사이클을 위한 제안

- **(A) `releases` 명령을 Go에 이식** — DEPLOY-NAMESPACE를 실질 통과로 전환하고 Go
  총점을 115/115로. 릴리스 축(CHANGELOG 파싱 + `v*` 태그 대조 + drift)은 C036 이래
  참조 전용으로 남은 마지막 미이식 명령군이다. 이식되면 deploy·release 두 축이 Go에서
  나란히 선다.
- **(B) DEPLOY-NAMESPACE의 축 결합 재검토** — 네임스페이스 분리 검증을 `releases` 대신
  `deploy`가 찍은 태그의 직접 관찰로 재설계하면, deploy 축만으로 자족 판정이 가능하다
  (판정기 개선 제안, 범위 밖).

## 사이클 닫기

- [ ] `cycle.yaml`의 `status: closed`, `closed: <일자>` 갱신
- [ ] 존재의 방 `memory.md`에 이 사이클의 기억 기록
- [ ] 커밋 및 퍼블리시
