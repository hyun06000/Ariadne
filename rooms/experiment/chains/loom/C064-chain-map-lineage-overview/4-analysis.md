# 4. 결과 분석

## 통계적 결과

| 측정 | 기준값 | 실측 | 판정 |
|---|---|---|---|
| 참조 conformance | 90/90 | **90/90** | ✅ |
| Go conformance | 83/83 | **83/83** | ✅ |
| 바이트 parity(무옵션=위계+체인맵) | byte-identical | 동일(sha fc83934a…) | ✅ |
| 바이트 parity(`--flat`=평면) | byte-identical | 동일(sha 03b5d0b0…) | ✅ |
| 체인맵 요소 | chainnode·chainbody 각 5 | 5·5 | ✅ |
| 드릴다운(#chainbody-loom) | loom 펼쳐짐 | 펼쳐짐(스크린샷) | ✅ |

## 데이터 직접 관찰

- 렌더 스크린샷에서 **loom(63)이 허브로 중앙**에 오고, 초록 점선 화살표가 좌우 대칭으로 뻗는다. loomlight↔loom이 `10`·`4` 두 아치로 가장 진하게(양방향·최다 건수) 드러나, "loomlight가 loom에서 가장 많이 배웠고 loom도 loomlight를 참조한다"는 관계가 수치 없이 한눈에 읽힌다.
- `gil-data` JSON은 체인맵 추가로 **바뀌지 않았다** — 지도는 순수 렌더층. 그래서 WEB-JSON·WEB-HIERARCHY-DEFAULT 등 계약 판정기가 무수정 통과.
- 삼각함수 교체 검증: `math.atan2/cos/sin` 판을 벡터 정규화(sqrt-only)로 바꾼 전후의 **참조 렌더가 시각적으로 동일**했고(스크린샷 대조), 이후 Go와 바이트까지 동일. sqrt는 IEEE correctly-rounded 보장이라 Python `math.sqrt`↔Go `math.Sqrt`가 비트 동일 — 이것이 parity의 근거.

## 예상과 달랐던 것

- **삼각함수가 parity의 숨은 지뢰였다.** 처음엔 좌표를 atan2/cos/sin으로 냈는데, 이는 IEEE가 correctly-rounded를 강제하지 않는 초월함수라 Python libm과 Go math가 마지막 ULP에서 갈릴 수 있고, `%.1f` 포맷 경계에서 바이트가 어긋난다. 렌더는 계약이 아니지만 **양 구현 바이트 동일**은 이 레포의 깊은 계약이라, 렌더 좌표조차 IEEE 보장 연산(sqrt·사칙)으로만 짜야 했다. 벡터 정규화로 같은 기하를 삼각함수 없이 표현해 해소.
- 체인맵은 계약을 넓히지 않았다(JSON 불변) — conformance 무수정 통과가 그 증거. 잠글 것은 렌더 구조가 아니라 parity(바이트)뿐이라, 별도 판정기 대신 parity 대조를 검증 산출물로 남겼다.

## 판정

**가설 채택.** 기각 조건 셋 모두 미발동: 바이트 불일치 0(무옵션·`--flat`), 기존 판정기 회귀 0, 드릴다운 동작. sqrt-only 기하로 lineage 개관 그래프를 위계 위에 얹으면서 양 구현 바이트 동일을 지켰다.
