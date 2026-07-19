# 2. 실험 설계

## 절차

C075 참조의 6조각을 Go `main.go`로 이식:
1. `webJSONPayload`에 `chainsRoot` 인자 추가 + hierarchy 모드에서 chain 객체에 `"docs": {cid: {"steps":[{"label","content"},…]}}` 내장 (dict 순서 order·cycles·reservations·docs 참조와 동일).
2. `renderCycleMount` 신설 — head(제목·상태·lineage 칩)만 + 빈 `.cycbody` + `data-chain`·`data-cid`.
3. `renderHierarchyBody`가 `renderCycleDetail` 대신 `renderCycleMount` 호출 (전자는 참조·회귀 비교용 보존).
4. `webAppJS` 상수 신설 (참조 `_WEB_APP_JS`와 **바이트 동일**) + 위계 body 끝에 `<script>` 주입.
5. `renderWebPage`에서 gilData의 `</`→`<\/` 치환 (참조 `_json_for_script`, flat·hier 양쪽).
6. 앱화로 낡아진 `hhint` 문구를 참조 C075판으로 갱신.

## 준비물

- Go 소스 `rooms/deployment/ariadne-spec/go/main.go`, 참조 `gil.py`(C075 반영 v2.27+), `conformance.py`.
- Go 1.26, 임시 모듈 빌드(go.mod 없음): main.go 복사 → `go mod init gil && go build`.

## 측정 방법

| 측정 | 성공 기준 |
|---|---|
| 참조↔Go web | hierarchy·flat·per-chain **바이트 동일**(diff 0) |
| gil-data docs | 양쪽 파싱 OK, 전 체인 docs 내장, `<\/` 치환 개수 동일 |
| Go 판정기 | WEB-DOCS-EMBEDDED PASS + 회귀 0 |

**기각선**: 위 셋 중 하나라도 불충족.

## 사용자 컨펌

- 소환자 Clew가 임무·범위(Go parity 회복)를 브리핑. 상현님이 "Weft 소환"으로 이식 주체 승인.

- [x] 컨펌 받음 (일자: 2026-07-19)
