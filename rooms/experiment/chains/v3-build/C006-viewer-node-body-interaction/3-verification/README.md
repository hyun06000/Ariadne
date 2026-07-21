# 3. 가설 검증 — v3 스텝 트리 뷰어 · 노드 클릭→본문 펼침 (C006 상호작용)

부모: v3-build/C005 (뷰어 배선). 저자: Sheen. 소환자: Clew.
이 디렉토리에 실험 실행에 쓴 모든 것이 있다: 생성기·CLI·정적 실측기·CDP 상호작용 실측기·산출물.

## 무엇을 검증하나

1-hypothesis.md의 가설: C004 생성기를 확장해 각 노드의 본문 steps/<id>.md를 HTML에 인라인
임베드하고 노드 클릭에 본문 패널 토글을 배선하면 — (a) C004 트리 회귀 0, (b) 노드 클릭으로
본문 펼침, (c) 외부 리소스 0(fetch 없이 인라인), (d) 다중 열림 상태보존(다른 노드 조작이
이미 열린 본문을 안 지움).

## 산출물 (모두 순수 stdlib · 외부 패키지 0)

- `steptree.py` — C004 생성기를 **복사 후 확장**(닫힌 사이클 C004 원본 불변). 추가: 본문
  인라인 임베드(`<article class="stepbody" hidden>` + escape된 `<pre>`), 노드를 클릭
  가능하게(`clickable`·`role=button`·`tabindex`·`data-body`), 인라인 JS(클릭→`hidden`
  토글, 각 패널 독립·통스왑 없음 = 상태보존), 열린 노드 SVG 강조(`.node.open`).
- `render.py` — C002 steps.yaml + steps/*.md → out.html. `base_dir`로 본문 파일을 읽어 임베드.
- `measure.py` — 정적 헤드리스 실측(stdlib html.parser): M1~M4(C004 회귀 0) + M5(본문
  임베드·진실원 일치) + M4b(상호작용 자기완결). 진실원 steps/*.md를 독립으로 다시 읽어 대조.
- `interact.py` — **실 Chrome(headless) raw-WebSocket CDP** 실측(C010 계보): M6a 클릭→펼침,
  M6b 둘째 클릭에도 첫 본문 유지(상태보존), M6c 닫기 국소성. 정적 파서로는 관찰 불가한
  클릭 실행을 실 DOM 상태로 확인.
- `out.html` — 생성 결과(재현물, 17696 bytes).

## 입력 데이터 출처

`../../C002-design-v3-data-model/3-verification/case-c012-c014/` — steps.yaml(10노드) +
steps/*.md(각 노드 본문). 봉인된 C002 산출물을 복제하지 않고 상대경로로 가리켜 읽는다
(닫힌 사이클 불변 R4·R5). 본문도 임베드 시점에 원본에서 읽어 escape만 하고 담는다.

## 재현 방법

```bash
cd rooms/experiment/chains/v3-build/C006-viewer-node-body-interaction/3-verification
python3 render.py          # steps.yaml + steps/*.md → out.html
python3 measure.py         # 정적 실측 → M1~M5·M4b, exit 0=ALL PASS
python3 interact.py        # 실 Chrome CDP → M6a~c 상호작용·상태보존, exit 0=PASS
open out.html              # (선택) file:// 육안 확인 — 노드 클릭→본문 펼침, 서버 불요
```

## 실행 기록

- 실행: 2026-07-21, macOS(Darwin 25.5.0), Python 3(stdlib만), Chrome headless, 이 워크트리.
- `render.py` → `out.html` 17696 bytes.
- `measure.py` → **ALL PASS ✓** (M1~M5·M4b), exit 0.
- `interact.py` → **M6 ALL PASS ✓** (M6a·M6b·M6c), exit 0.

## 실측 결과 — ALL PASS ✓

### 정적 (measure.py)

| # | 측정 | 결과 |
|---|---|---|
| M1 | 구조 무왜곡 (K1) | ✅ parent 엣지 9==9 진실원 일치; s1 형제 가지 3 (C004 회귀 0) |
| M2 | backtrack 가시·구별 (K2) | ✅ 2개 (s4→s1·s7→s1), 잎→조상 방향, 마커, path/line 구별 (회귀 0) |
| M3 | 잎 운명 구별 (K3) | ✅ 죽은 잎 2·산 잎 1, 클래스 분리 (회귀 0) |
| M4 | 자기완결 (K4) | ✅ 외부 리소스 0 |
| M5 | 본문 임베드·진실원 일치 (K2) | ✅ 노드 10·클릭가능 10·패널 10, 노드↔패널 배선 OK, 본문 진실원 일치 10/10 |
| M4b | 상호작용 자기완결 (K3) | ✅ 인라인 script 1(외부 src 0), fetch/xhr/websocket/import/eval 0 |

### 상호작용 (interact.py — 실 Chrome CDP)

| # | 측정 | 결과 |
|---|---|---|
| M6a | 클릭→본문 펼침+노드강조 | ✅ 초기 모두 hidden → s1 클릭 후 body-s1 보임, 노드 `.open` |
| M6b | 상태보존 (K4) | ✅ s10 클릭해도 **body-s1 여전히 보임**, 두 노드 다 `.open` |
| M6c | 닫기 국소성 | ✅ s1 ✕ → body-s1만 닫힘, body-s10 유지 |

## 자기완결 계약 (K3/K4) 확인

out.html은 단일 UTF-8 파일(17696 bytes). `<style>`·`<svg>`·본문 `<article>`·`<script>`
전부 인라인. 외부 `<link>`/`<script src>`/원격 이미지/fetch/xhr/websocket **0**. 본문 .md는
render 시점에 파일에서 읽어 escape 후 문서에 임베드 — `file://`로 열어도 본문이 이미 안에
있어 서버·네트워크 의존 0. C004·v2 뷰어 자기완결 계약을 상호작용에서도 잇는다.

## 상태보존 설계 (C010/C014 계보)

각 본문 패널은 독립 `<article>`이고, 클릭은 그 패널의 `hidden` 속성 하나만 뒤집는다.
어떤 상호작용도 다른 패널을 통스왑·재생성하지 않는다("무엇을 스왑하지 않을지의 설계",
C010). 그래서 여러 노드를 동시에 열어도, 다른 노드를 클릭해도 이미 열린 본문이 상태를
잃지 않는다(M6b 실측). "자리를 잃은 화면"을 정적 상호작용에서 막았다.
