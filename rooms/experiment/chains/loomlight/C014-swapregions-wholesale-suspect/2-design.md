# 2. 실험 설계

가설: swapRegions가 `.mapchains`(열린 카드 담긴 영역)를 통째 replaceChild하는 것이 상태 파괴 근원. 최소변경으로 바꾸면 열린 노드가 살아남는다.

## 근원 분석 (코드 확정)

`swapRegions`(gil.py:1696)는 `POLL_SEL`의 각 셀렉터를 `replaceChild`로 통째 교체한다. `POLL_SEL[0]=".mapchains"` — 이 영역이 **6개 체인 카드(`<details class="hchain">`) 전부 + 그래프 SVG + cycdoc 마운트**를 담는다. 통째 교체하면 사용자가 연 카드 노드가 새것으로 바뀌고(step1 탐침 `chainNodeReplaced:true` 확정), detKey는 open 불린만 복원할 뿐 노드 정체성·리스너·네이티브 토글 상태는 소실.

**폴링이 실제로 갱신해야 하는 것**: 원장이 바뀌면 그래프 노드·집계 수치가 변한다. 그러나 **사용자가 연 카드의 열림 구조는 갱신 대상이 아니다.** 즉 `.mapchains` 통스왑은 과하다 — 카드 컨테이너는 보존하고 내부 갱신분만 반영하면 된다.

## 설계 — 최소변경 (가장 작은 안전한 수정)

`.mapchains`를 통스왑에서 빼고, 그 안에서 **열린 카드를 건드리지 않는 국소 갱신**만 한다.

**접근 (택1, 설계에서 가장 작은 것):**

- **A. `.mapchains`를 POLL_SEL에서 제거 + 내부 그래프만 국소 교체**: `.mapchains` 자체는 안 갈고, 그 안의 갱신 필요 요소(`.hmap > svg` 그래프, 집계 텍스트)만 개별 replaceChild. 단 이미 `.hmap > svg`가 POLL_SEL에 따로 있음 → `.mapchains`만 빼면 카드 컨테이너 보존. cycdoc 마운트도 `.mapchains` 안이라 함께 보존됨(현재는 통스왑 후 build로 재구축하던 것이 불필요해짐).
- **B. 열린 카드만 골라 보존하며 나머지 갱신**: 복잡. A가 더 작다.

→ **A 채택.** `POLL_SEL`에서 `.mapchains` 제거. 그러면 폴링은 `.mapchains` 밖 영역(header 통계·htoc·releases·beings·hmap svg 미니맵 등)만 갱신하고, 카드·그래프·cycdoc은 **노드 정체성 보존**.

**단 확인 필요**: `.mapchains` 안에도 폴링으로 갱신돼야 할 게 있나? — 큰 그래프 SVG(`.mapchains` 안)와 미니맵(`.hmap > svg`, 밖). 원장 변경 시 큰 그래프도 노드가 늘 수 있다. 하지만 **열린 카드 보존 > 그래프 실시간 갱신**이 사용자 가치(C010의 본래 목적은 상태 보존). 그래프 실시간성은 다음 리로드/새 폴링에서. 이 트레이드오프를 검증에서 확인(데이터는 gil-data로 갱신되니 열면 최신).

## 절차

1. **참조 gil.py**: `POLL_SEL`에서 `.mapchains` 제거. poll의 build 재구축 루프는 유지(cycdoc이 안 갈리면 재구축도 대부분 no-op이지만 안전망). swapRegions 주석 갱신.
2. **Go main.go**: `webAppJS`의 POLL_SEL 동일 수정(바이트 동일).
3. **헤드리스 검증**: step1 탐침 재사용 — 폴링 후 chain-loom 노드 마커 생존(`chainNodeReplaced:false`) 확인.
4. **데이터 갱신 확인**: 폴링 후 gil-data가 갱신되고, 열린 카드는 보존, 새로 여는 사이클은 최신 데이터.
5. **회귀**: C010 상태보존(steps-same)·C011 detKey·conformance 133·Go parity.

## 준비물

- gil v2.48.0. 헤드리스 CDP(C010 cdp.py). Go 세션-로컬 빌드.
- 탐침: step1의 JS 마커 방식(노드 정체성 = 마커 생존).

## 측정 방법

| # | 측정 | 기준 |
|---|---|---|
| M1 | 폴링 후 열린 카드 노드 마커 | 생존(chainNodeReplaced:false) — kill 2 |
| M2 | 폴링 후 데이터 갱신 | gil-data 갱신됨, 새 사이클 열면 최신 — kill 3 |
| M3 | 열린 details 보존 | chain·cycdoc open 유지 — 회귀 |
| M4 | conformance | 참조 133·Go parity — kill 4 |
| M5 | POLL_SEL 참조↔Go | 바이트 동일 |

## 검증분석 분기 (미리 정함)

- M1 마커 생존 + M2 갱신 유지 → **억셉트**: 통스왑이 근원 확정, 최소변경이 노드 보존. 실브라우저 검증은 다음(상현님 손)이나, 헤드리스 아키텍처 수준 해결.
- M1 여전히 교체 → 통스왑 밖 다른 원인 → 되돌아가 rejected.
- M2 데이터 안 갱신 → 최소변경이 과함 → 접근 B나 절충 재설계.

## 사용자 컨펌

- 생략 — 리젝트 체인 끝 가설의 자기검증, 내 손 안 계측기. 상현님 "길을 걸어가보자".

- [x] 컨펌 불요 (2026-07-20)
