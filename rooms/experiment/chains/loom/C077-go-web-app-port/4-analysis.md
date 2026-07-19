# 4. 결과 분석

## 통계적 결과

기준값 전부 충족: 참조↔Go web 바이트 동일(hierarchy·flat·loomlight), Go 판정기 86/86(WEB-DOCS-EMBEDDED PASS, 회귀 0), `<\/` 치환 개수 동일(26).

## 데이터 직접 관찰

`webAppJS`를 참조 `_WEB_APP_JS`와 바이트 동일하게 옮긴 것이 parity의 핵심 — JS는 정적 문자열이라 언어 무관하게 같은 바이트를 내면 브라우저 동작도 같다. flat 모드는 docs를 안 담는 경로라 이식 후에도 이전과 바이트 동일(하위호환). `_json_for_script`의 `</`→`<\/` 치환도 정확히 26곳으로 일치 — 문서 텍스트의 `</script>` 봉인이 두 구현에서 동일하게 작동.

## 예상과 달랐던 것

**gil.owner guard가 예약된 open을 막았다.** 소환자 Clew의 예측("예약된 open은 저자 확인되니 통과")이 코드와 어긋났다 — `_guard_primary_owner`는 예약 여부와 무관하게 주 체크아웃에서 author≠gil.owner면 무조건 거부한다(예약 예외 없음). Weft는 우회하지 않고(gil.owner 수정·author 위조·force 안 함) 정직히 멈춰 보고했고, Clew가 guard를 임시 해제해 weft author로 이 사이클을 열어 원장에 기록했다. **guard가 보는 것은 author뿐, 예약이 아니다** — 이 갭은 개선 후보(예약된 open을 예약 대상 author가 하면 허용).

## 판정

**채택.** 기각 조건 3개(parity 미회복 / 판정기 FAIL·회귀 / flat 바이트 차이) 전부 불발. Go 앱화 완료로 "두 몸, 한 계약"이 web 앱화에서도 회복됐다.
