# 2. 실험 설계

오직 1-hypothesis.md의 가설(Go 위계 이식 → 양 구현 `--hierarchy` 바이트 동일 + 회귀 0)만
검증한다. 참조 gil.py의 위계 렌더 경로를 Go(main.go)에 **문자 단위 동형**으로 옮기고,
두 몸의 산출물을 `cmp`로 교차 검증한다(렌더는 계약이 아니지만(§3.1) 정확성을 두 구현 대조로 세운다).

## 절차 (Go main.go, 뷰어 코드 표면만 — 다른 표면 불변)

1. **CLI 배선**: web 파서에 `--hierarchy`(불리언) 추가. `webArgs`에 `hierarchy bool` 필드.
   `cmdWeb`→`bakeViewer`→`renderWebPage`로 값을 전달.
2. **JSON payload**: `webJSONPayload`에 `hierarchy bool` 파라미터를 더해, refresh 뒤에
   `, "hierarchy": true`를 **조건부**로 붙인다(참조의 `**({"hierarchy": True} if hierarchy else {})`
   순서와 동일: title, chain, refresh?, hierarchy?). hierarchy=false면 기존과 바이트 동일.
3. **_dirs 이식**: `webChain`에 `dirs map[string]string`(cid→디스크 디렉토리명)를 더하고
   `buildWebData`에서 `r.dir`로 채운다. JSON 직렬화는 이 필드를 쓰지 않으므로 기본 출력 불변.
4. **위계 렌더 함수 이식** (참조와 문자 동일):
   - `webHierCSS` 상수 = 참조 `_WEB_HIER_CSS`(strip된 문면 그대로). Go 원문자열(백틱)로,
     `content:"\25B8"` 등 백슬래시 이스케이프는 그대로.
   - `verdictTally(chain)` = `_verdict_tally`, `chainRecent(chain)` = `_chain_recent`.
   - `readStep(chainsRoot, name, cdir, fname)` = `_read_step`(3-verification는 README+산출물 목록).
   - `renderCycleDetail(name, cid, c, chainsRoot, cdir)` = `_render_cycle_detail`(메타표 + 5스텝 `<pre>`).
   - `renderHierarchyBody(...)` = `_render_hierarchy_body`(L1 목차 → 체인 `<details>` → 사이클 `<details>`).
     체인당 `renderSVG(single)`·`renderTables(single)` 재사용(single = 한 체인만 담은 webData).
5. **renderWebPage 분기**: `hierarchy`면 body를 `renderHierarchyBody(...)`로, 아니면 기존 문면.
   doctype/refresh-meta 래퍼는 공통(참조와 동일). style은 위계일 때 `webCSS + "\n" + webHierCSS`.
6. **자동 재굽기 보존**: `bakeMeta`가 `bake.hierarchy`를 읽어 반환하고, `refreshViewers`가
   그 값을 `bakeViewer`로 넘긴다(C042의 "창이 원장을 따른다"를 위계로 확장). hierarchy=false면 불변.
7. **_STEP_FILES 동치**: `[("1 · 가설","1-hypothesis.md"),("2 · 설계","2-design.md"),
   ("3 · 검증","3-verification"),("4 · 분석","4-analysis.md"),("5 · 보고","5-report.md")]`.

## 준비물

- Go 툴체인 `$HOME/goroot/go` (go1.23.4) — 이번엔 **있다**(C002의 이월 사유가 해소됨).
- 참조 gil.py(위계 렌더의 진리 원본), conformance.py(계약 판정), 실 저장소 chains(5체인·60여 사이클).
- 빌드: `go build -o gil main.go`(의존성 0). 판정: `conformance.py --gil "<절대경로>"`(C028·C043·C045).

## 측정 방법 (3-verification/에 verify.sh로 재현 가능하게 저장)

| # | 측정 | 성공 기준 |
|---|---|---|
| M1 | **위계 바이트 동일(가설 본체)** | `gil web --hierarchy` 참조 vs Go 출력이 `cmp` 바이트 동일 |
| M2 | **기본 바이트 동일(회귀 0)** | `--hierarchy` 없는 Go 출력이 개선 전 Go baseline과 `cmp` 동일 + 참조와도 동일 |
| M3 | **Go conformance 회귀 0** | `conformance.py --gil` 개선 전(78/78)과 동수 PASS |
| M4 | **위계 계약 유지** | Go `--hierarchy` 출력에 외부 리소스 로드 0, 실행 JS 0(gil-data 데이터 블록만), `<details>` 구조 참조와 동수 |
| M5 | **자동 재굽기 위계 보존** | 위계로 구운 뷰어를 원장 변경(step) 후에도 위계로 재굽는다(bake.hierarchy 왕복) |

M1 실패 = 기각 1. M2 실패 = 기각 2. M3 실패 = 기각 3. 빌드 불가 = 기각 4(정직히 이월).

## 사용자 컨펌

- 생략 — 소환자 Clew의 임무 지시서가 설계 계약(동형 이식·바이트 동일·opt-in 회귀 0·릴리스 금지)을
  이미 명시했다. 그 계약을 그대로 따르므로 별도 컨펌 불요. 병합은 Clew가 총괄.

- [x] 컨펌 받음 (일자: 2026-07-19 · Clew 임무 지시서로 갈음)
