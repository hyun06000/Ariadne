# 3. 가설 검증 — v3 스텝 트리 뷰어

부모: v3-build/C002 (steps.yaml 스키마 확정). 저자: Sheen. 소환자: Clew.
이 디렉토리에 실험 실행에 쓴 모든 것이 있다: 생성기·CLI·실측기·입력 출처·산출물.

## 무엇을 검증하나

1-hypothesis.md의 가설: C002의 `case-c012-c014/steps.yaml`(10노드)을 입력받아,
parent 엣지로 가지를, backtrack 엣지로 되돌아감을, 죽은 잎/산 잎을 서로 다른 표식으로
그리는 **자기완결 단일 HTML/SVG 뷰어**를 만들면, 헤드리스 실측에서 세 형제 가지·
backtrack 2·죽은 잎 2·산 잎 1이 명확히 구별 검출된다.

## 산출물 (모두 순수 stdlib · 외부 패키지 0)

- `steptree.py` — 생성기: steps.yaml → 자기완결 HTML(인라인 SVG+CSS). yaml 미의존
  자작 파서(C002 roundtrip.py와 같은 서브셋), depth×형제 좌표, parent line·backtrack
  path·kind 색·잎 표식·범례·헤더.
- `render.py` — CLI: `case-c012-c014/steps.yaml` → `out.html`.
- `measure.py` — 헤드리스 실측: out.html을 stdlib `html.parser`로 파싱해 M1~M4 판정.
  진실원(steps.yaml)을 **독립 파서**로 다시 읽어 렌더 대조(steptree.py 파서와 별개).
- `out.html` — 생성 결과(재현물, 커밋됨).

## 입력 데이터 출처

`../../C002-design-v3-data-model/3-verification/case-c012-c014/steps.yaml` (봉인된 C002
산출물, 10노드). 복제하지 않고 상대경로로 가리켜 읽는다 — 닫힌 사이클 불변(R4·R5).

## 재현 방법

```bash
cd rooms/experiment/chains/v3-build/C004-v3-viewer-step-tree/3-verification
python3 render.py          # steps.yaml → out.html
python3 measure.py         # out.html 실측 → M1~M4, exit 0=ALL PASS
open out.html              # (선택) file:// 로 육안 확인 — 서버 불요
```

## 실행 기록

- 실행: 2026-07-21, macOS(Darwin 25.5.0), Python 3(stdlib만), 이 워크트리.
- `render.py` → `out.html` 9229 bytes 생성.
- `measure.py` → **ALL PASS ✓**, exit 0.

## 실측 결과 — ALL PASS ✓

| # | 측정 | 결과 |
|---|---|---|
| M1 | 구조 무왜곡 (K1) | ✅ parent 엣지 9==9 진실원 일치; s1 형제 가지 3개 (기대 3) |
| M2 | backtrack 가시·구별 (K2) | ✅ backtrack 엣지 정확히 2개 (s4→s1·s7→s1), 방향 잎→조상(위로), 화살촉 마커, parent와 path/line 태그 구별 |
| M3 | 잎 운명 구별 (K3) | ✅ 죽은 잎 2 (s4·s7)·산 잎 1 (s10), 클래스 분리(leaf-dead ≠ leaf-live) |
| M4 | 자기완결 (K4) | ✅ 외부 리소스 참조 0 (`<link>`/script src/원격 img/http(s)/fetch 부재, svg xmlns 네임스페이스 URI만 예외) |

## 검증 중 잡은 것 (정직히 남긴다)

- **범례가 실측을 오염시킬 뻔했다.** 범례는 실제 엣지와 **같은 class**(edge-backtrack·
  edge-parent)의 스와치를 일부러 쓴다 — 사람이 그래프에서 볼 선과 범례의 선이 동일하게
  보여야 하니까. 그 결과 첫 measure.py가 범례의 `<line class="edge-backtrack">`를 세 번째
  backtrack 엣지로 세어 M2가 FAIL 났다(3≠2, 마커 없음, line≠path). **수정은 뷰어가 아니라
  측정자**: 그래프 엣지만 `data-from` 속성으로 거르게 했다(M1이 parent를 거르는 방식과
  동형). 뷰어 출력은 처음부터 옳았고, 측정의 필터가 데이터 엣지와 장식 엣지를 갈라야 했다.
  첫 실측을 지우지 않고 이 수정 근거를 남긴다(사고조차 무손실).

## 자기완결 계약 (K4) 확인

out.html은 단일 UTF-8 파일. `<style>`·`<svg>` 전부 인라인, 외부 `<link>`/`<script src>`/
원격 이미지/fetch **0**. `file://`로 열린다(서버 의존 0). v2 뷰어 자기완결 계약을 잇는다.
