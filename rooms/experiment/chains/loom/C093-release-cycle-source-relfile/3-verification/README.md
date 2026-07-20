# 3. 가설 검증 — RELEASE.md 추가

## 재현
```bash
python3 rooms/deployment/ariadne-spec/conformance.py --gil /tmp/gilbin/gil
```

## 결과
| 항목 | 전 | 후 |
|---|---|---|
| RELEASE-CYCLE-SOURCE | FAIL(release rc=1, RELEASE.md 없음) | PASS |
| RELEASE-DRIFT-GATE | PASS | PASS(무회귀) |
| 전체 | 121/122 | **122/122 "이 구현은 gil이다"** |

## 코드 변경
- `_mk_src_repo`: `_mk_release_repo` 후 RELEASE.md에 `## v1.1.0` 서술 추가.

## 원인
`_mk_release_repo`는 RELEASE-DRIFT-GATE(봉인 전 단계)용이라 RELEASE.md를 안 만든다. RELEASE-CYCLE-SOURCE는 release를 실제 봉인까지 성공시켜야 하는데 release는 RELEASE.md 버전 서술을 요구(C038) → C086에서 테스트 추가 시 누락. 격리 재현이 통과한 건 수동으로 RELEASE.md를 넣었기 때문(재현의 함정).
