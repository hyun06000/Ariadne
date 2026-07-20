# 4. 결과 분석

## 통계적 결과 (측정 vs 기준)

2-design의 측정 기준과 대조:

| 측정 | 기준(성공) | 관측 | 판정 |
|---|---|---|---|
| M1 결함 재현(meta refresh) | 리로드 후 상태 소멸 확인 | `afterRefresh_hasProbe:false`, `firstDetailsOpen:false` | 재현됨 |
| M2 폴링 상태보존 | 열린 details·스크롤·토글 유지 | `A_chainOpen:true, A_step1Open:true, A_cycbodyFilled:true, A_scroll:420` | **통과** |
| M3 데이터 갱신 through 폴링 | 새 gil-data 반영 AND 상태 유지 | `chainStillOpen:true, sentinelInDom:"POLLED_V2"` | **통과** |
| M4 참조↔Go parity (C010 표면) | 폴링 JS 바이트 동일·양쪽 meta 부재 | 폴링 블록 `cmp` 무출력(62줄), 양쪽 meta 0·poll 1·ext 0 | **통과** |
| M5 conformance 회귀 0 | 참조 128, Go 110 유지 | 참조 128/128, Go 110/110 | **통과** |

기각 조건 4개 전부 미발동.

## 데이터 직접 관찰

수치 뒤로 들어가 실제 산출물과 실측 JSON을 들여다봤다:

1. **meta refresh가 DOM을 통째로 새로 쓴다 (M1의 실체).** 재현 실측에서 프로브 details의
   `hasProbe`가 리프레시 뒤 `false`가 됐다 — 단지 `open`이 꺼진 게 아니라 **요소 자체가 사라졌다**.
   전체 문서 리로드는 상태 저하가 아니라 DOM 파괴다. 반면 스크롤(`afterRefresh_scroll:500`)은
   살아남았는데, 이는 Chrome이 same-URL 리로드 시 스크롤을 복원하기 때문이지 페이지가 상태를
   지켜서가 아니다. "일부는 살아남더라"가 결함을 흐리게 만드는 함정 — details는 확실히 죽었다.

2. **폴링은 DOM을 유지한 채 데이터만 갈아끼운다 (M2·M3).** 처치 실측에서 폴링 주기를 넘긴 뒤에도
   `A_cycbodyFilled:true` — 사이클 body가 비지 않고 **새 data로 다시 채워진** 채였다. 동시에 열린
   체인·스텝·스크롤이 그대로. M3의 sentinel 실험은 이걸 결정적으로 갈랐다: 서빙 파일을 몰래
   sentinel 주입본으로 바꿨더니, 폴링이 그 새 JSON을 `#gil-data`에 반영(`sentinelInDom:"POLLED_V2"`)
   하면서도 `chainStillOpen:true`. **실시간성과 상태보존이 배타적이지 않음**을 한 실측이 증명했다.

3. **두 몸의 폴링 JS가 바이트 동일.** 참조·Go 산출물에서 `function detKey`~`startPolling` 블록을
   추출해 `cmp` — 무출력(62줄 동일). C020의 "두 몸 한 계약"이 이 사이클의 신규 표면에서도 성립.
   원문자열(Go 백틱 raw string)로 소스 바이트를 그대로 흘려 이스케이프 층위 함정을 피한 C003 규율을
   그대로 따랐다.

## 예상과 달랐던 것

1. **flat 모드에 앱 JS가 아예 마운트돼 있지 않았다.** flat body는 `#gil-data`와 `mdtoggle` 버튼을
   이미 굽고 있었지만 `<script>{_WEB_APP_JS}</script>`가 없었다 — 즉 flat의 실시간성은 **전적으로
   meta refresh에 의존**했고, mdtoggle 버튼은 flat에서 죽은 버튼이었다. meta를 빼면 flat이 실시간성을
   통째로 잃으므로, flat에도 앱 JS를 마운트해야 했다. 결함 하나를 고치다 **인접한 미배선**을 발견한 셈.

2. **mdtoggle 클릭이 열린 스텝을 이미 잃고 있었다(C088 유래, 폴링과 무관).** 검증 중 토글을 누르면
   `rebuildOpen()`이 `.cycbody`를 다시 그려 열린 `.hstep`의 open이 꺼졌다. 내 폴링 경로는 이걸
   `restoreOpen(openSnap)`로 되살리지만, **토글 클릭 자체의 열림 소실은 이 사이클 범위 밖**(C088
   토글 표면)이라 손대지 않았다. 실측이 아니었으면 "내 폴링이 스텝을 잃는다"로 오진할 뻔했다 —
   대조군(토글 없는 M2)이 정확히 이 혼동을 갈랐다.

3. **전체 `cmp` 불일치가 pre-existing이었다.** parity를 재려다 참조↔Go 전체 산출물이 line 36에서
   갈리는 걸 봤는데, pristine HEAD 빌드도 같은 지점에서 갈렸다 — `webCSS`↔`_WEB_CSS`의 CSS 줄바꿈
   drift(C088 영역). 내 변경이 낳은 게 아니라 이미 있던 것. **"parity가 깨졌다"를 내 탓으로 성급히
   결론짓지 않고 HEAD 대조로 귀속을 확인**한 게 정직의 요체였다.

## 판정

네 기각 조건 모두 미발동, 다섯 측정 전부 기준 통과. 정적 페이지의 실시간 폴링이 상태를 파괴한다는
필드 결함은, meta refresh를 자기완결 JS 폴링으로 대체함으로써 해소됐다 — 데이터는 갱신되고 사용자가
보던 자리(열린 details·스크롤·렌더 토글)는 보존된다. 두 몸 한 계약과 conformance 회귀 0도 지켰다.

> **판정: 가설 지지 (supported).**
