# 3. 검증 — gil web 완전한 앱화 (문서 무게 제거)

## 측정 (수정 전 v2.27 vs 앱)
| 초기 DOM(브라우저 즉시 파싱·레이아웃) | 수정전 | 앱 | 감소 |
|---|---|---|---|
| `<pre>`(5스텝 전문) | 425 | 2 | 100% |
| `<td>`/`<tr>`(문서 표) | 850 | 1 | 100% |
| `<details>` | 430 | 7 | 98% |
| 전체 태그 | 5,330 | 1,433 | 73% |

초기 DOM 73% 감소. 문서는 gil-data JSON에 내장, JS가 클릭 시 그 하나만 DOM 구축.

## 상호작용 (헤드리스 Chrome, file://)
- `file://.../app.html#cycdoc-loom-C001-...` 로드 → JS 실행 → 해당 .cycbody에 메타표+5스텝(hstep 5개) 구축 확인.
- 가설 내용까지 정확히 렌더. fetch 없이 내장 JSON에서 → file://에서도 동작(자기완결).

## 회귀·계약
- flat(--flat) 바이트 동일(문서 안 담음 → 하위호환).
- 그래프·계보 무손실(85노드·29 lineage·168 SVG 원 보존).
- 참조 판정기 100/100(WEB-DOCS-EMBEDDED 신설: docs.steps 내장 + 앱 스크립트). 수정 전 gil은 99/100 FAIL.
- WEB-SELFCONTAINED 유지(JS는 인라인, 외부 리소스 0).

## 선재 버그 봉인 (표면화)
- 문서 텍스트에 `</script>` 포함(사이클이 gil web 코드 인용) → gil-data JSON에 넣자 브라우저가 스크립트 조기 종료 → JSON 파싱 실패. `_json_for_script`가 `</`→`<\/` 치환으로 봉인(JSON 값 동일, HTML 파서는 종료 태그로 안 봄).

## 이월 (범위: 참조 앱화까지)
- Go 이식(같은 앱 JS 문자열·docs 내장·_json_for_script) — 다음 사이클(C043 리듬).
