# 2-design — Go web 배포 패널 이식 설계 (목업 먼저, C067)

부모: loom/C104-deploy-viewer-panel. 참조 gil.py의 web 배포 패널 행동을 Go main.go에 동형 이식한다.
렌더는 §3.1 계약 아님 → 정확성은 **참조↔Go 바이트 동일 + conformance WEB-DEPLOYMENTS PASS**로 증명한다.

## 이식 대상 (참조 gil.py → Go main.go)

1. **_build_deployments_data(chains_root)** → `buildDeploymentsData(chainsRoot) *deploymentsData`
   - deployments.json 없음 → nil (키 부재, 바이트 동일)
   - 파일 있으나 배포 0 → `{groups: []}` (빈 상태 카드)
   - 아티팩트별 그룹(첫 등장 순서 보존), 각 그룹 records는 **최신 우선(reversed)**
   - group: {artifact, kind(최신 non-empty kind), live(최신 live version or ""), records[]}
   - record: {version, kind, status, deployedAt, supersedes, notes, cycles(=source_cycles)}

2. **_render_deployments_panel(deployments)** → `renderDeploymentsPanel(*deploymentsData) string`
   - nil → ""  (배포 안 쓰는 저장소는 카드 부재)
   - groups 빈 → `<section class="card deployments"><h2>배포 계보</h2><p class="deployshint">아직 배포된 산출물이 없다.</p></section>`
   - 정상 → 그룹별 artgroup + deplist. 각 dep row: depstat(mark)·depver·depdate·depnote·depsup·depcycs
   - mark: live→● superseded→· rolled-back→↩ (기타→?)
   - 근거 링크: `<a class="depcyc" href="#cycdoc-{ref-slashes→dashes}">⚑ {ref}</a>`

3. **JSON payload**: releases 키 뒤(참조 순서: beings·releases·deployments)에 top-level `deployments` 키.
   dict 순서: `{"groups": [{"artifact","kind","live","records":[{"version","kind","status","deployed_at","supersedes","notes","cycles":[...]}]}]}`
   live가 None이면 참조는 `json.dumps` → `null`. Go도 live 빈문자→ null 내야 바이트 동일.
   무deployments.json / flat → 키 부재.

4. **CSS**: 참조 gil.py 1838~1861행의 .deployments 블록을 webHierCSS(또는 인접 CSS 상수)에 문자 동일 삽입.
   단 참조는 이 CSS가 _WEB_CSS/_WEB_HIER_CSS 어디 있는지 확인해 같은 위치에 넣어 바이트 동일.

5. **배선**: renderHierarchyBody에서 releases 패널과 beings 패널 **사이**에 deployments 패널 삽입
   (참조: `{releases}\n{deployments}\n{beings}`). Go 현재는 `{releases}\n{beings}` — 사이에 한 줄 추가.

## live=None 직렬화 주의 (참조 대조)
참조 `_build_deployments_data`의 group live는 `next(...live..., None)`. json.dumps(None)=`null`.
Go: live 필드를 `*string`으로 두거나, 직렬화 시 빈문자면 `null` 출력. 바이트 동일의 열쇠.
records[].supersedes: 참조는 `d.get("supersedes") or ""` → 빈문자열이면 `""`. deployRecord.Supersedes는 *string(null 가능)
→ 참조 build에서 `or ""`로 문자열화하므로 Go도 nil→"" 문자열로 담아 `""` 출력.

## 검증
- `deployments.json` 실재하는 이 워크트리 + judge sandbox 둘 다에서 참조↔Go web byte-diff (cmp 무출력)
- conformance --gil Go → WEB-DEPLOYMENTS PASS, 회귀 0 (WEB-* 무회귀, C014 폴링)
- 무deployments.json sandbox: Go web에 deployments 키·카드 부재 (회귀 0)
