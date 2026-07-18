# 4. 결과 분석

## 통계적 결과

| 판정 항목 | 결과 |
|---|---|
| SHOW-NODE (노드 신원 반환) | PASS |
| SHOW-FORWARD (정방향 lineage 엣지 + 존재해석) | PASS |
| SHOW-BACKLINKS-PARENT (체인 내 cited-by) | PASS |
| SHOW-BACKLINKS-LINEAGE (cross-chain cited-by) | PASS |
| SHOW-EDGES-MATCH-GRAPH (show 엣지 == build_graph/web JSON) | PASS |
| SHOW-MISSING (부재 노드 지어냄 없음, exit≠0) | PASS |
| 참조 conformance 전체 | **86/86** (회귀 0) |
| Go conformance 전체 | **79/79** (show 미구현 → HELP-COMPLETE가 정직한 부재 판정) |
| fsck / verify | 위반 0건(69사이클) / 변조 0건(68닫힘) |

합성 픽스처(3-verification/show_probe.py) 6/6 + 실저장소 스모크 전부 통과. 기각 조건 5개 전부 방어됨. 재현: `python3 conformance.py --gil "<절대경로>"`.

## 데이터 직접 관찰

- **lineage 백링크가 실데이터에서 값을 증명했다.** `gil show loom/C013-realtime-step-visibility`가 backlinks.lineage에 `loomlight/C001-gather-viewer-lineage`를 즉시 반환했다 — loomlight/C001이 뷰어 사이클 10개를 lineage로 모았다는 사실(Sheen의 C001)을, **질의자가 65개 파일을 읽지 않고** 한 노드에서 역방향으로 본다. "무엇이 이 노드를 인용하나"는 `git tag -l`이 못 하듯 `gil log`도 못 하던 질문인데, show가 한 명령으로 답한다.
- **backlinks.parents도 실증**: 같은 노드가 `← parent loom/C015-being-work-visibility`를 반환 — C013의 교훈에서 C015가 태어났다는 계보를 역방향으로. 정방향 log와 역방향 show가 같은 엣지의 두 방향이다.

## 예상과 달랐던 것

- **정방향과 백링크는 비대칭 비용이다.** 정방향(parent·lineage)은 노드 자신의 cycle.yaml에 있어 공짜다. 백링크는 **엣지 반전** — 전 체인 스캔이 필요하다. 이 비대칭이 #4의 세 성질(백링크·표적·인덱스)의 순서를 설명한다: 백링크가 가장 비싼 질문이고, 효율 인덱스는 그 비용이 규모에서 아플 때의 다음 카브다. 65 노드에선 스캔이 무시할 만해 인덱스를 유예한 판단(C007)이 옳았다.
- **web JSON 최상위 구조**: `{version, bake, chains}` — `chains` 아래에 체인이 산다. 프로브 첫 실행이 `data['loom']`로 KeyError를 냈고, 실제 구조를 확인해 `data['chains']['loom']`으로 교정(C007 "전제는 확인하라"의 소소한 재실천).

## 판정

**채택 (supported).** 가설의 (a)~(d) 전부 실증: (a) 한 노드+양방향 이웃을 파일 스캔 없이, (b) 백링크가 한 명령으로, (c) 엣지가 build_graph/web과 일치(SHOW-EDGES-MATCH-GRAPH), (d) 판정기가 계약면을 관측(참조 86/86, Go 정직한 부재). 기각 조건 5개 어디에도 걸리지 않음.

## 정직한 기록 — 병렬 사고

이 사이클의 참조 구현(cmd_show)이 미커밋 상태일 때, 병렬 존재(Selvage·Weft)가 공유 main 체크아웃으로 cd해 `gil open`을 실행하며 main 작업 트리를 정리 → 내 WIP가 discard됐다(C050 재발, 이번엔 하네스 워크트리 격리로도 못 막음 — 에이전트가 워크트리 밖으로 cd 가능했으므로). 내 컨텍스트에 온전해 재적용·즉시 커밋(a180c29)으로 무손실 복구. **이 사고 자체가 상현님의 "도구로 막자" 발의의 실물 근거이자, #1 병렬 모드(add→land→guard)가 완성돼야 하는 이유다** — 다음 사이클(cd-to-main guard).
