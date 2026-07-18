# 2. 실험 설계

가설(1-hypothesis)에만 초점을 맞춘 절차 중심 설계. **`gil show <chain>/<id>`** — 한 노드의 완전한 국소 이웃(신원 + 정방향 엣지 + 백링크)을 전체 스캔 없이 반환하는 원자 프리미티브. 지식그래프(#4)의 machine-facing 조회면.

## A. 코드 실측 — 무엇이 이미 있고 무엇이 없나 (C040 "도구는 이미 보고 있다")

참조 `gil.py`(2807줄) 실측으로 확인한 것:
- `parse_cycle_yaml(path)` — cycle.yaml 평탄 파서(§3.1). 단일 노드 읽기에 그대로 재사용.
- `load_chain_records(chain_dir)` — 한 체인의 모든 cycle.yaml 수집, 각 레코드에 `parents`(=`_as_list(parent)`)·`lineage_list`(=`_as_list(lineage)`) 정규화. **백링크 스캔의 재료.**
- `build_graph(chain_name, cycles)` — **체인 내 parent 엣지만** 그린다(끊어진 parent면 ChainError). lineage는 그리지 않는다(cross-chain).
- `_build_web_data` JSON 계약면 — 각 사이클에 `parents`·`lineage`를 담지만 **① 전체 그래프이고 ② 백링크가 없다.** ← 없는 것이 정확히 이것.
- `cmd_goto` — `<chain>/<id>` ref 파싱 + 미존재 시 `ChainError("사이클이 없다: …")`. **show의 ref 문법·부재 처리를 그대로 계승**(일관성).

**결론**: 정방향 엣지(parent·lineage)는 이미 데이터에 있다. 없는 것은 (a) 노드 단위 조회 표면, (b) **엣지 반전 = 백링크**. show는 새 파서를 만들지 않고 이 둘만 더한다.

## B. 두 종류의 백링크 (핵심 설계 — 엣지의 방향성)

- **parent 백링크** (체인 내): 같은 체인에서 이 노드를 `parent`로 나열한 사이클들. `load_chain_records(<chain>)`를 훑어 `cid in rec["parents"]`.
- **lineage 백링크** (cross-chain): **모든 체인**에서 이 노드를 `lineage`(전역 표기 `<chain>/<id>`)로 나열한 사이클들. 모든 체인의 `load_chain_records`를 훑어 `"<chain>/<id>" in rec["lineage_list"]`.

이 이원성이 지식그래프의 값이다. 실증 데이터: loomlight/C001이 loom의 뷰어 사이클 10개를 lineage로 가리킨다 → `gil show loom/<그중하나>`가 backlinks.lineage에 loomlight/C001을 보여야 한다(전체 스캔 없이 "무엇이 이 노드를 인용하나"에 답). 이것이 #4가 요구한 백링크의 실물.

## C. 인터페이스

```
gil show <chain>/<id> [--json] [--root ROOT]
```
- **읽기 전용**(log·goto 무-checkout과 동급). 커밋·상태 변경 0. 안전한 탐침(§7.2 정신).
- 기본: 사람용 텍스트 렌더. `--json`: 기계 계약면.

## D. 절차 (cmd_show)

1. **ref 파싱**: `/` 없으면 `ChainError("ref는 <chain>/<id> 형식이어야 한다")`. 있으면 `chain, cid = ref.split("/",1)`.
2. **노드 위치**: `<root>/<chain>/<cid>/cycle.yaml`. 없으면 `ChainError("사이클이 없다: <ref>")` — **지어내지 않고 명확히 거부**(기각조건 2, C040 P2). exit 코드는 main의 ChainError 매핑을 실측해 확정(예상 1).
3. **신원 수집**: `parse_cycle_yaml`로 노드 필드 전부(id·chain·title·author·status·verdict·step·opened·closed·parent·lineage·deviations·corrections·superseded_by·rounds — 있는 것만).
4. **정방향 엣지**:
   - parents(체인 내 로컬 id): 각각 전역 ref `<chain>/<parent>`로 표기 + 존재 해석(`<root>/<chain>/<parent>/cycle.yaml` 존재?).
   - lineage(cross-chain 전역 ref): 각각 존재 해석(`<root>/<c2>/<id2>/cycle.yaml` 존재?). **끊어진 참조는 `exists:false`로 정직히 표시**(fsck R6 정신, C044).
5. **백링크** (B절): parent 백링크(같은 체인 스캔) + lineage 백링크(전 체인 스캔). 결과는 전역 ref 정렬 리스트.
6. **보고서 포인터**: `<root>/<chain>/<cid>/5-report.md` 경로(내용으로의 링크 — 노드 요약 추출은 이번 범위 밖, 다음 카브).
7. **렌더**: 텍스트(기본) 또는 JSON(`--json`).

## E. JSON 계약면 (지식그래프의 계약 — 판정기가 보는 표면)

```json
{
  "ref": "loom/C029-time-machine",
  "node": { "id": "...", "chain": "loom", "title": "...", "status": "closed",
            "verdict": "...", "parent": ["C028-..."], "lineage": ["..."], "...": "..." },
  "forward": {
    "parents":  [ {"ref": "loom/C028-...", "exists": true} ],
    "lineage":  [ {"ref": "loomlight/C001-...", "exists": true} ]
  },
  "backlinks": {
    "parents":  [ "loom/C030-..." ],
    "lineage":  [ ]
  },
  "report": "rooms/experiment/chains/loom/C029-time-machine/5-report.md"
}
```
- 계약면 = **엣지 집합**(forward.parents/lineage의 ref+exists, backlinks.parents/lineage의 ref). 텍스트 렌더는 계약 아님(C021).
- **양방향 정직성**: forward의 exists가 대상 실재를 정직히 반영, backlinks는 실재하는 인용자만.

## F. 판정기 (conformance.py — 같은 커밋에 등록, C043 예방 리듬)

합성 픽스처(결정론적 — 저장소 진화 무관, C047·C051 방식)로 작은 그래프를 만들어 판정한다: 체인 α에 A←B←C(parent 체인), 체인 β의 X가 lineage로 α/A를 가리킴.

| 항목 | 판정 |
|---|---|
| `SHOW-NODE` | `show α/A --json` → exit 0, node.id=A, node.chain=α |
| `SHOW-FORWARD` | `show β/X --json`의 forward.lineage에 `{ref:"α/A", exists:true}` |
| `SHOW-BACKLINKS-PARENT` | `show α/B --json`의 backlinks.parents에 `α/C` (C가 B를 parent로) |
| `SHOW-BACKLINKS-LINEAGE` | `show α/A --json`의 backlinks.lineage에 `β/X` (X가 A를 lineage로) |
| `SHOW-EDGES-MATCH-GRAPH` | show의 forward.parents 집합 == 같은 노드에 대해 web JSON(build_graph)이 그리는 parent 엣지 (기각조건 1 — 두 표면이 다른 그래프를 말하면 실패) |
| `SHOW-MISSING` | `show α/C999-ghost` → exit≠0, JSON node 미생성(지어냄 없음, 기각조건 2) |
| `HELP-COMPLETE` | `CONTRACT_COMMANDS`에 `show` 추가 → Go(미구현)가 exit 3으로 정직한 부재 보고 |

- 변이 격추(C041 "다른 방어선이 침묵하는 입력"): ① 백링크 계산을 제거한 변이 → SHOW-BACKLINKS-* FAIL. ② lineage 스캔을 같은 체인으로 국한한 변이 → SHOW-BACKLINKS-LINEAGE FAIL. ③ 부재 노드에 빈 이웃을 조용히 반환하는 변이 → SHOW-MISSING FAIL.
- **회귀 0**: 기존 항목 전부 유지(show는 순수 신규 읽기 명령, 기존 표면 무변경). 새 항목으로 분모가 느는 것은 회귀 아님.

## G. 재사용·범위

- **재사용**: `parse_cycle_yaml`·`load_chain_records`·`_as_list`. 새 파서 0. 백링크 = 기존 로더 결과의 반전.
- **효율**: 백링크는 전 체인 스캔(현 65 노드에서 무시할 비용 — 도구의 내부 비용이지 질의자의 비용이 아니다). 질의자(LLM)는 파일 하나 안 읽고 한 노드+양방향 이웃을 얻는다 = 표적 탐색 달성. **효율 인덱스는 규모가 요구할 때의 다음 카브**(C007: 규모를 가정 말고 확인 — 지금은 불요).
- **범위 밖(이번 사이클)**: `trace`(N홉), 노드 요약 추출, 효율 인덱스, **Go 이식**. Go는 `show`를 CONTRACT_COMMANDS에 등록해 HELP-COMPLETE가 정직한 부재를 판정하게 하고 후속 사이클로(C043 리듬).

## H. 검증 산출물 (3-verification/)

- `gil.py` 패치(cmd_show + 서브파서 등록), `conformance.py` 패치(SHOW-* + CONTRACT_COMMANDS).
- 픽스처 생성 스크립트 + 판정 실행 로그(참조·Go 양쪽), 변이 격추 로그.
- **실저장소 스모크**: `gil show loom/C029-time-machine`(정정된 노드), lineage 백링크 실증(loomlight/C001 ⇠ loom 뷰어 사이클), SHOW-EDGES-MATCH-GRAPH를 실데이터에서도 확인.
- 재현: 절대 경로 `--gil`(C028·C043·C045 함정 명시).

## 사용자 컨펌

- 생략 — 상현님 전권 위임("사이클을 멈추지 말고 계속 돌려줘", 설계 컨펌 갈음). 병렬 진행은 상현님이 명시 요청·선택(3트랙). 설계는 커밋으로 관전 가능하며 방향 수정 시 개입 가능.
- [x] 컨펌 받음 (일자: 2026-07-19, 위임으로 갈음)
