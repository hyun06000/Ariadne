# 2. 실험 설계

부모: v3-build/C002 (steps.yaml 스키마 확정). 저자: Sheen. 소환자: Clew.
오직 1-hypothesis.md의 가설 하나(세 형제 가지·backtrack 엣지·잎 두 운명을 한 자기완결
SVG로 동시에 그려 헤드리스로 구별 검출)를 검증한다.

## 산출물

`3-verification/` 아래:
- `steptree.py` — 순수 stdlib 생성기. `steps.yaml` 경로 → 자기완결 단일 HTML(문자열).
- `render.py` — CLI 진입점: steps.yaml을 읽어 `out.html`을 쓴다(재현 가능).
- `measure.py` — 헤드리스 실측. 생성 HTML을 stdlib `html.parser`로 파싱해 요소/클래스/
  좌표를 뽑아 K1~K4(=M1~M4)를 판정. SVG는 정적 마크업이라 브라우저 없이 파서 실측으로
  충분하되, "브라우저가 볼 DOM"과 동형이도록 표준 태그/속성만 쓴다.
- `out.html` — 생성 결과(커밋해 재현물로 남김).

## 절차

1. `steptree.py` 작성: steps.yaml 로드(stdlib 자작 파서, C002 roundtrip.py와 동일
   서브셋) → 트리 복원(parent 인접 리스트) → depth×형제 좌표 계산 → SVG 문자열 조립
   (parent line · backtrack path · kind별 node · 잎 표식 · 범례 · 헤더) → 자기완결 HTML.
2. `render.py` 실행: `case-c012-c014/steps.yaml` → `out.html` 생성.
3. `measure.py` 실행: out.html 파싱해 M1~M4 판정, 결과를 stdout에 표.
4. 육안 확인용으로 out.html을 커밋(재현물). 헤드리스 실측이 1차 근거.

## 레이아웃 — 스텝 트리를 좌표로

트리를 **깊이(세로) × 형제(가로)** 로 배치한다:

```
depth 0:            s1(define)
                   /    |    \
depth 1:      s2(hyp) s5(hyp) s8(hyp)     ← s1의 세 자식 = 세 형제 가지
depth 2:      s3(ver) s6(ver) s9(ver)
depth 3:      s4(ana) s7(ana) s10(ana)
                 ↑죽은잎  ↑죽은잎   ↑산잎
```

- **depth = 루트에서 parent 체인 길이.** 순수 위상 — id(시간순)와 독립(C002 불변식).
- **가로 위치 = 형제 순서.** 같은 부모의 자식들을 부모 아래 균등 분배. 이 데이터는 각
  가지가 선형이라 균등 분배로 충분(일반 tidy 배치는 후속 여지).
- 좌표는 정수 그리드(콜=형제 슬롯, 로우=depth)로 계산해 헤드리스에서 좌표 검증 가능.

## 엣지 두 종류 — 시각적으로 갈린다 (M2의 핵심)

| 엣지 | 데이터 출처 | SVG 요소 | 스타일 | 마커 |
|---|---|---|---|---|
| **parent (가지)** | 각 노드 `parent` | `<line class="edge-parent">` | 실선, 중립색, 직선(부모→자식 아래로) | 없음 |
| **backtrack (되돌아감)** | `outcome=backtrack` 노드 `backtrack` | `<path class="edge-backtrack">` | 파선, 경고색(주황), **곡선**(가지 밖으로 우회해 잎→조상 define으로 올라감) | 화살촉(marker-end) |

두 엣지를 **다른 태그(line vs path)·다른 class·다른 색·곡선 vs 직선·마커 유무**로
갈라, 헤드리스 파서가 class 집합만으로도 구별 검출 가능하게 한다. backtrack은 가지
사이/밖 빈 공간으로 크게 곡선을 그려 parent 실선 위를 겹치지 않게 한다(시각 혼선 방지).

## 노드 — kind 색 + 잎 운명 표식 (M3의 핵심)

- **노드 몸통**: `<g class="node kind-<kind>">` 안에 `<rect>` + `<text>`(id·kind 라벨).
  kind별 색: define(파랑)·hypothesis(보라)·verify(청록)·analyze(회색).
- **잎 운명 표식** — analyze 노드 outcome으로 갈린다:
  - `outcome=success` → class에 `leaf-live`. 초록 테두리 + 채운 배지 + "✓ 산 잎
    (success)" 라벨. 사이클을 닫는 노드.
  - `outcome=backtrack` → class에 `leaf-dead`. 회색 점선 테두리(바랜 느낌) + "✕ 죽은
    잎 · 벽의 지도(backtrack→s1)" 라벨 + 되돌아갈 대상 id.
  - outcome=null → 표식 없음.

죽은 잎은 **바래되 지워지지 않는다** — chain.md "리젝트가 자산", s4·s7 본문이 스스로를
"벽의 지도"라 부른 그대로. 산 잎만 도드라지되 죽은 잎도 읽히게.

## 범례 + 헤더

상단에 범례(두 엣지·세 잎상태·네 kind 색)와 사이클 헤더(chain/cycle id·노드 수·산 잎
도달 → close 가능 여부). 사람이 표식의 뜻을 즉시 읽게.

## 준비물

- Python 3(stdlib만 — yaml 미의존, C002 roundtrip.py와 같은 자작 파서). 외부 패키지 0.
- 입력: `../C002-design-v3-data-model/3-verification/case-c012-c014/steps.yaml`(10노드).
- 환경: 이 워크트리. 브라우저 불요(파서 실측).

## 측정 방법

| # | 측정 | 통과 기준 (기각=K1~K4) |
|---|---|---|
| M1 | 구조 무왜곡 (K1) | 파싱한 parent 엣지 집합 == steps.yaml parent 인접 리스트; s1 자식=3(형제 가지 3개) |
| M2 | backtrack 가시·구별 (K2) | `edge-backtrack` 정확히 2개, class·마커로 parent와 구별; s4→s1·s7→s1 각각 잎→조상 방향(도착 y < 출발 y, 위로) |
| M3 | 잎 운명 구별 (K3) | `leaf-dead` 2개(s4·s7)·`leaf-live` 1개(s10), 서로 다른 class/표식 |
| M4 | 자기완결 (K4) | 외부 리소스 참조 0 (`http`/`src=`/`<link`/`fetch` 부재), UTF-8 단일 파일 |

M2·M3이 이 뷰어가 v2와 다른 이유의 핵심 — 하나라도 실측에서 구별 안 되면 기각.

## 사용자 컨펌

병렬 세션(Clew는 main에서 C003 명령 구현 병렬 진행)이라 실시간 컨펌 불가. 가장
보수적 선택을 이 설계에 명시(정적 SVG·JS 0·외부 리소스 0·v2 자기완결 계약 계승)해
land 검토의 근거로 남긴다. 갈래가 나뉘면(예: 상호작용 요구) 우회 없이 보고.

- [x] 컨펌 생략 — 병렬 세션, 보수적 기본을 목업(이 설계)으로 명시 (일자: 2026-07-21)
