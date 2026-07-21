# 2. 설계

## 실험 설계 (재현 가능하게)

C004 생성기(`steptree.py`)를 **닫힌 사이클 불변 규율**에 따라 이 사이클
`3-verification/`으로 복사한 뒤 확장한다. 원본(C004)은 건드리지 않는다.

산출물 배치 (`C006-.../3-verification/`):
- `steptree.py` — C004에서 복사 후 확장 (본문 임베드 + 상호작용).
- `render.py` — C002 steps.yaml + steps/*.md → out.html.
- `measure.py` — C004 M1~M4(회귀 0) + 새 M5(본문 임베드·진실원 일치)·M6(상태보존).
- `out.html` — 재현물.

## 확장의 축 (C004 대비)

### A. 본문 인라인 임베드 (자기완결 계약 유지)
각 노드의 `body: steps/<id>.md`를 render 시점에 **파일에서 읽어 HTML-escape** 후
`<article class="stepbody" id="body-<id>" hidden>` 안에 인라인한다. fetch/XHR 0 —
file://로 열어도 본문이 이미 문서 안에 있다. C010의 "본문 .md를 HTML에 임베드" 계약을
정적 트리에 이식.

### B. 노드를 클릭 가능하게
각 노드 `<g class="node ...">`에 `clickable` 클래스 + `role="button"` +
`tabindex="0"` + `data-id` 부여(data-id는 C004에 이미 있음). 커서 포인터.

### C. 클릭 → 본문 토글 (최소 자기완결 JS)
인라인 `<script>`(외부 src 0)로:
1. 각 노드 `<g.clickable>`에 click/keydown(Enter/Space) 리스너.
2. 클릭 시 `#body-<id>`의 `hidden` 속성만 토글 (다른 패널은 안 건드림).
3. **상태보존(K4/C010·C014)**: 각 본문 패널은 독립. 노드 A를 열고 노드 B를 클릭해도
   A의 `hidden`은 그대로 — 통스왑·재생성 없이 `hidden` 속성 하나만 뒤집는다.
   "무엇을 스왑하지 않을지의 설계"(C010)를 그대로 적용: 열린 것은 손대지 않는다.
4. 열린 노드는 SVG에서도 시각 표시(`.node.open` → node-box 강조)해 어떤 본문이 열렸는지
   트리에서 보이게 한다.

### D. `<details>` fallback 여부
임무는 "순수 자기완결 JS **또는** `<details>`"를 허용한다. SVG 노드 클릭↔본문 연동은
`<details>`만으론 (SVG `<g>`를 `<summary>`로 못 씀) 불가하므로 **최소 JS**를 택한다.
단 JS가 비활성이어도 본문이 소실되지 않도록, 본문 패널은 문서에 항상 존재하고 `hidden`
속성으로만 감춘다(진보적 향상). fetch 없음 = file:// 안전.

## 측정 계획

- **M1~M4 (회귀 0)**: C004 measure.py의 판정을 그대로 실행 — parent 9엣지·backtrack 2·
  잎 운명·자기완결. 하나라도 FAIL이면 K1 발동.
- **M5 (본문 임베드·진실원 일치)**: 10노드 각각 `#body-<id>`가 존재하고, 그 텍스트가
  진실원 `steps/<id>.md`와 일치(정규화 후). 노드 수 == 본문 패널 수 == 10.
- **M6 (상호작용·상태보존)**: 헤드리스 실브라우저(stdlib raw-WebSocket CDP, C010 방식)로
  (a) 노드 클릭 → 본문 hidden=false 확인, (b) 두 번째 노드 클릭 → **첫 본문 여전히 열림**
  (K4 상태보존), (c) 열린 노드 SVG 강조 표시 확인.
- **M4b (자기완결 재확인)**: 새 JS/본문에 http(s)·fetch·xhr·link·script src 0.

## 기각선

M1~M4 회귀 0 AND M5 10/10 일치 AND M6 상태보존 통과 → 산 잎. 하나라도 실패면 그 K.
