# 2. 실험 설계 — _mk_src_repo에 RELEASE.md 추가

## 절차
1. `_mk_src_repo`가 `_mk_release_repo` 호출 직후, `rooms/deployment/ariadne-spec/RELEASE.md`에 `## v1.1.0` 서술을 쓴다(release가 봉인 전 요구, C038).

## 측정 방법
- 전체 conformance(CI 재현, /tmp/gilbin/gil)가 122/122 완주.
- RELEASE-CYCLE-SOURCE PASS + RELEASE-DRIFT-GATE 무회귀.

## 사용자 컨펌
- C092에서 이월한 후속. 원인 규명(RELEASE.md 누락) 완료 후 진행.
- [x] 컨펌 받음 (일자: 2026-07-20)
