# 3. 가설 검증 — 노드 수직 화살표 + 배포 근거 링크

## 재현
```bash
gil web --chain loom -o loom.html
# 헤드리스 Chrome으로 details 열고 cyclegraph SVG 추출 → 렌더
```

## 결과 (헤드리스 렌더로 육안 확인 + conformance)
| 항목 | 결과 |
|---|---|
| 노드 lineage 마커(위, 초록 들어오는 화살표) | PASS — C001·C009에 표시, 머리·꼬리 붙음 |
| 노드 배포 마커(아래, 파랑 나가는 화살표) | PASS — 배포된 노드마다, 노드에 붙음 |
| 노드 이름 화살표 아래로 | PASS — 겹침 없음 |
| 옛 초록 긴 글자(⇠ 이름) 제거 | PASS — 그래프 안 늘어짐 |
| 호버 툴팁 (전체 lineage·배포 버전) | PASS — <title> ⇠ lineage / ⚑ 배포 |
| 배포 패널 근거 사이클 링크(rcyc) | PASS(참조) — #cycdoc-<chain>-<id> 점프 |
| WEB-NODE-IO conformance | PASS 참조·Go |
| 참조 123/123 · Go 105/105 | PASS |

## 코드 변경
- gil.py `_render_cycle_graph_h`: lin_txt(초록 글자) → niom lin(위 화살표)·niom rel(아래 화살표, released_in) 마커 + 툴팁. 노드 번호 y 조정.
- gil.py `_build_releases_data` entries에 cycles(C086 근거), `_render_releases_panel` _row에 rcyc 링크 + CSS.
- go/main.go `renderCycleGraphH`: 동일 마커 이식(참조와 동형). Go 105/105.
- conformance WEB-NODE-IO 신설(배포 마커 존재 + 툴팁 + lineage 없으면 마커 없음).

## 미이식 (정직, 후속)
- Go 배포 패널 rcyc 링크: Go의 CHANGELOG "근거 사이클" 불릿 파싱 이식 필요(conformance 미검사). 이미지 임베드(C088)와 함께 Go parity 후속.

## 산출물
- 헤드리스 스크린샷(scratchpad): svgonly.png(전체 loom), zoom_nodes.png(C001·C002 확대 — 마커 붙음 확인).
