# 4. 결과 분석

## 통계적 결과

2-design.md의 5측정(세부 9판정) 전부 성공 기준 충족 — `verify.sh` 재현 가능.

| 측정 | 기준 | 결과 | 판정 |
|---|---|---|---|
| M1 / M1b | 기본 출력 개선 전과 바이트 동일 | genesis·전체 체인 모두 `cmp` 동일 | ✅ |
| M2 | 참조 conformance 회귀 0 | **56/56**(--skip-git) · **77/77**(git 포함) | ✅ |
| M2b | WEB-* 초록 | SELFCONTAINED·JSON·REFRESH·AUTO-* 전부 PASS | ✅ |
| M3 | 외부 0 · 실행 JS 0 | 외부 0 · `<script>` 1개(=gil-data JSON) | ✅ |
| M4 / M4b | 위계 3단 구조 카운트 | 목차 1 · hchain 5/5 · hcycle 65/65 · hstep 325=65×5 · C002 앵커·메타 실재 | ✅ |
| M5 | --hierarchy + --refresh 병존 | meta refresh + bake.hierarchy&refresh, 외부 0 | ✅ |
| M6 | 자동 재굽기 hierarchy 보존 | 왕복 True, 기본 bake에 hierarchy 키 부재 | ✅ |

## 데이터 직접 관찰

- **바이트 동일의 실제**: 개선 전 gil.py(`origin/main`)와 신 gil.py를 같은 체인 데이터로 구운 두
  HTML이 `cmp`로 완전히 일치. 즉 `--hierarchy` 없는 사용자·CI·Go(불변)에게는 이 사이클이
  **관측 불가능한 변화**다 — opt-in 추가가 기존 계약면을 한 바이트도 건드리지 않았다는 실증.
  `render_web_page`의 `else` 가지를 개선 전 문면 그대로 두고 분기만 앞에 얹은 설계가 그대로 통했다.

- **위계의 실물**(`sample-hierarchy-loomlight.html`, 40KB): 상단 `<nav class="htoc">`가 체인 목록을
  요약과 함께 보인다 —
  `loom  사이클 58개 · supported 27 · 무결론 29 · partial 1 · 열림 1`. 체인 `<summary>`를 누르면
  그 **체인 하나만의** SVG 그래프 + 표가 열리고(L2), 사이클 `<summary>`를 누르면 cycle.yaml 메타표와
  5개 스텝 `<details>`가 열려(L3) 각 보고서 원문이 `<pre>`로 뜬다. C001 요약은
  `C001-gather-viewer-lineage [closed · supported] 흩어진 뷰어 사이클을 lineage로 모은…`으로,
  status·verdict·제목이 한 줄에 압축됐다.

- **B1·B2·B3 완화의 구조적 근거**: L2에서 `_render_svg({name: chain})`를 **체인 하나**에만 부른다.
  loom 한 체인은 최대 폭·최대 lineage 밀도가 5체인 합산 화면보다 근본적으로 낮다. loomlight/C001이
  만든 "10겹 lineage 점선"(B2의 첫 실증)도 그 체인을 펼칠 때만, 그 체인 안에서만 그려진다 —
  한 화면에 5체인 60여 사이클을 겹쳐 그리던 압력이 드릴다운으로 분산됐다.

- **JS 0의 확인**: 생성물의 유일한 `<script>`는 `type="application/json" id="gil-data"` —
  브라우저가 실행하지 않는 데이터 블록(기계 검증 훅). 드릴다운·펼침·앵커 이동은 전부
  `<details>/<summary>`·`<a href="#...">`라는 HTML 표준 기본 동작. 계약(C005) 무손상.

## 예상과 달랐던 것

- **판정기의 분모가 함정이었다.** M4 최초 실행에서 `find -name cycle.yaml`이 110을 셌는데 그래프
  노드는 65였다. 원인은 `rounds/` 하위의 라운드 cycle.yaml. 진실값을 **뷰어 자신의 gil-data JSON
  노드 수**로 바꿔 자기정합 판정으로 교정했다 — 뷰어의 정확성은 "원장을 반사하는가"이지 "디스크의
  모든 yaml을 세는가"가 아니다(C001 교훈 2의 재확인: 뷰어는 원장의 반사광).

- **많은 닫힌 사이클이 verdict 없이 `무결론`으로 집계됐다**(loom 29건). 이는 결함이 아니라 정직 —
  verdict 필드(C030)는 후대에 도입됐고 이전 사이클엔 소급 이주가 안 됐다. 위계 요약이 그 공백을
  **가시화**했다. 이것이 백로그 B6(verdict 결말 서사의 소급 이주)의 새 실증 압력이다 — 위계
  뷰어가 다음 사이클의 재료를 또 스스로 만들었다(C001의 자기증식 패턴 반복).

## 판정

**가설 채택 (supported).** 세 기각 조건 어느 것도 발생하지 않았다:
계약 위반 0(M3), 위계 3단 JS 없이 동작(M4·M4b + 표본 육안), 하위호환 파괴·회귀 0(M1·M2·M6).
`--hierarchy`는 JS 0·외부 0·자기완결을 지키며 체인→사이클→5스텝 드릴다운을 실현하고,
기본 경로를 바이트 그대로 보존해 참조·Go 양쪽 conformance를 초록으로 남긴다.

**정직한 미완(다음 사이클로 이월):** Go(`go/main.go`)로의 `--hierarchy` 이식. 이 워크트리엔 Go
툴체인이 없어 실측할 수 없었고, opt-in 설계가 기본 경로 바이트 동일을 보장하므로 Go 불변으로도
병합이 안전하다. 두 몸의 위계 바이트 동일(C020)은 다음 loomlight 사이클의 계약으로 남긴다.
