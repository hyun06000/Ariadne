# 2. 실험 설계

## 설계 요지 — 위계를 "추가 능력"으로, 기본을 바이트 그대로

`gil web`에 opt-in 플래그 `--hierarchy`를 더한다. 플래그가 없으면 코드 경로가 기존과
**한 바이트도 다르지 않다**(default 보존). 플래그가 있으면 3단 위계 HTML을 낸다.
JS 없는 드릴다운은 **중첩 `<details>/<summary>`**로, 딥링크는 **앵커 id**로 실현한다.

## 절차 (구현 — 참조 gil.py, 뷰어 코드 표면만)

1. **CLI**: `p_web.add_argument("--hierarchy", action="store_true", ...)` 추가. `cmd_web`에서
   `hierarchy = getattr(args, "hierarchy", False)`로 읽어 `_bake_viewer`로 전달.
2. **스레딩**: `_bake_viewer(chains_root, output, title, only, refresh=None, hierarchy=False)` →
   `render_web_page(..., hierarchy=hierarchy, chains_root=chains_root)`. hierarchy=False면 모든
   기존 호출부·출력 불변.
3. **bake 자기보고**: json_payload의 `bake`에 `**({"hierarchy": True} if hierarchy else {})`를
   **맨 끝**에 조건부로 더한다. hierarchy=False면 dict가 기존과 완전 동일 → JSON 바이트 동일
   (refresh가 쓰던 바로 그 패턴, C043·C049).
4. **자동 갱신 보존**: `_bake_meta`가 `bake.get("hierarchy")`도 반환하고, `_refresh_viewers`가
   그 값을 `_bake_viewer`로 넘긴다. 이로써 open/step/close가 뷰어를 다시 구워도 위계가 유지된다
   (C042의 "창이 원장을 따른다" 계약을 위계에도 확장). 이 경로도 hierarchy=False면 불변.
5. **위계 렌더** `_render_hierarchy_body(data, chains_root, ...)`:
   - **L1 체인 목록**: 상단에 컴팩트 목차(체인명 + 요약 통계 + `#chain-<name>` 앵커 링크).
     요약 = 사이클 수 · verdict 집계(supported/rejected/refuted/inconclusive/열림) · 최신 활동일.
   - **L2 체인 그래프**: 각 체인을 `<details id="chain-<name>">`로. summary=체인명+통계.
     펼치면 **그 체인만의** SVG(`_render_svg({name: chain})` 재사용) + 표(`_render_tables({name: chain})`
     재사용). 한 체인만 그리므로 B1(가로)·B2(lineage 밀도)·B3(라벨) 압력이 구조적으로 낮아진다.
   - **L3 사이클 5스텝**: 체인 details 안에 사이클마다 `<details id="cycle-<name>-<cid>">`.
     summary=`cid [status·verdict] 제목`. 펼치면 cycle.yaml 메타 표 + 스텝별 중첩 `<details>`:
     1-hypothesis.md·2-design.md·3-verification/README.md(+ 산출물 파일 목록)·4-analysis.md·
     5-report.md 내용을 `html.escape` 후 `<pre>`에 담는다(마크다운 파서 없이 정직하게 원문).
6. **스텝 파일 소스**: `_build_web_data`가 체인별 `_dirs = {cid: c["_dir"]}`를 data에 넣는다
   (JSON payload는 이 키를 직렬화하지 않으므로 기본 JSON 불변). 없으면 cid를 디렉토리명으로 가정.
7. **CSS**: hierarchy 모드에서만 `<style>{_WEB_CSS}{_WEB_HIER_CSS}</style>`. 기본 모드는 `{_WEB_CSS}`
   그대로 → 기본 바이트 불변. `_WEB_HIER_CSS`는 details/summary·중첩 여백·메타표·pre 스타일.
8. **Go**: **손대지 않는다.** 이 워크트리엔 Go 툴체인이 없어 실측 불가 + 위계는 opt-in이라
   기본 경로가 바이트 동일이므로 Go(불변)의 기본 출력·conformance가 그대로 초록. Go 위계 이식은
   다음 loomlight 사이클로 정직히 이월(C036·C050 절제).

## 준비물

- Python 3 (참조 gil.py). Go 툴체인 없음(확인함) → Go 변경 금지.
- 실 저장소 `rooms/experiment/chains`(5체인·60여 사이클) — 위계 압축의 실증 픽스처.
- 판정기 `conformance.py`(WEB-SELFCONTAINED / WEB-JSON / WEB-REFRESH).

## 측정 방법 (3-verification/에 재현 가능하게 저장)

| # | 측정 | 성공 기준 |
|---|---|---|
| M1 | **기본 바이트 동일(하위호환)** | `gil web`(플래그 없음) 출력이 개선 전 baseline과 `cmp` 바이트 동일 |
| M2 | **참조 conformance 회귀 0** | `conformance.py --gil "python3 gil.py"` 전 항목 PASS(WEB-* 포함), 개선 전과 동수 |
| M3 | **위계 계약 유지** | `--hierarchy` 출력에 외부 리소스(`https?://`) 0, 실행 JS 0(`id="gil-data"` 데이터 블록만) |
| M4 | **위계 3단 동작** | 생성 HTML에 L1 목차, `<details id="chain-*">`(체인당 1), `<details id="cycle-*">`(사이클당 1),
      스텝 `<pre>`에 실제 보고서 원문·cycle.yaml 메타가 존재 — grep·구조 카운트로 확인 |
| M5 | **--refresh·자동갱신과 공존** | `--hierarchy --refresh 3`이 meta refresh + bake.hierarchy=true 동시 기록, 외부 리소스 0 |

M1·M2 실패 = 하위호환/회귀(기각 조건 3). M3 실패 = 계약 위반(기각 조건 1). M4 실패 = 위계 미동작(기각 조건 2).

## 사용자 컨펌

- 생략 — 소환자 Clew의 임무 지시서가 설계 계약(JS 0·opt-in 하위호환·Go 이월 허용)을 이미
  명시했다. 그 계약을 그대로 따르므로 별도 컨펌 불요. 병합 시점만 Clew가 Weft와 조율.

- [x] 컨펌 받음 (일자: 2026-07-19 · Clew 임무 지시서로 갈음)
