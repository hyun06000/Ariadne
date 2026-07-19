# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C075**가 참조 구현(gil.py)을 "완전한 앱"으로 앱화했다: 5스텝 문서를 초기 HTML 인라인에서 gil-data JSON 내장으로 옮기고, 인라인 JS 앱이 노드 클릭 시 그 하나의 DOM을 구축(초기 DOM 73%↓). C075는 **범위를 참조 앱화까지로 한정**하고 Go 이식을 정직히 이월했다(C043 리듬). 그 결과 참조↔Go parity가 깨졌고(Go는 문서 인라인본), **gil-gate CI가 Go의 WEB-DOCS-EMBEDDED FAIL로 깨진 상태**다.

## 문제 분할

이번 사이클의 문제는 단일하다: **C075 앱화를 Go(main.go)에 이식해 parity(web 바이트 동일)를 회복**한다. "두 몸, 한 계약"(v1.0.0)이 web 앱화에서도 유지되어야 한다 — 한 구현만 앱이면 계약이 갈라진다.

## 가설

> **가설**: C075가 참조에 넣은 6조각(docs 내장·`renderCycleMount`·`webAppJS`·`_json_for_script` 치환·hierarchy body 조립·hhint 갱신)을 Go에 동형 이식하면, 참조↔Go web 출력이 **바이트 동일**해지고(hierarchy·flat·per-chain), Go 판정기가 WEB-DOCS-EMBEDDED를 PASS하며(회귀 0), gil-gate가 초록으로 돌아온다.

## 기각 조건

- 이식 후 참조↔Go web이 한 경우라도 바이트 다르면 → parity 미회복, 기각.
- Go 판정기가 WEB-DOCS-EMBEDDED FAIL이거나 기존 항목 회귀 → 기각.
- flat 모드가 바이트 달라지면(문서 안 담는 경로인데) → 하위호환 위반, 기각.
