# 3. 검증 — Go 앱화 이식 parity

## 결과 (Weft 이식 + Clew 독립 재검증)
- 참조↔Go web **바이트 동일**: hierarchy(기본, 5체인 1.46MB)·**flat**·per-chain(loomlight) 전부 `diff` 0.
- gil-data JSON 양쪽 파싱 OK, 5체인 모두 docs 내장, `<\/` 치환 26개로 동일.
- 무수정 `conformance.py`에서 Go **86/86** (WEB-DOCS-EMBEDDED PASS, 회귀 0). 이식 전 이 항목 FAIL.

## 방법
- 임시 모듈 빌드: main.go 복사 → `go mod init gil && go build -o gil-go`.
- `python3 gil.py web [--flat|--chain X] -o py.html` vs `gil-go web … -o go.html` → `diff`.
- `python3 conformance.py --gil gil-go`.

## 이식 조각 (go/main.go, 142+/10−)
webJSONPayload(chainsRoot+docs) · renderCycleMount · renderHierarchyBody · webAppJS(참조와 바이트 동일) · renderWebPage(_json_for_script 치환) · hhint 갱신.
