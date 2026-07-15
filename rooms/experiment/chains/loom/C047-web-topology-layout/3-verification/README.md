# 3. 가설 검증 — 토폴로지 레이아웃

## 재현 방법

### 불변 기준 (분기 픽스처 — 시점 무관)

분기 그래프 P→{A→A1→A2, B}(5노드, 최장경로 depth 3)를 만들어 SVG height를 측정한다(gil open으로 P·A·B·A1·A2, gil web 렌더):

- **개선 전**: height 386 (5노드 = 5행, order 인덱스가 row).
- **개선 후**: height **322** (최장경로 depth 3 = 4행). 형제 A(depth1)·B(depth1)가 같은 행. → **H1 세로 압축.**
- 그래프 노드 5개, 유일 좌표 5개, 고유 행(cy) 4개 → **H3 무충돌.**

### 가변 확인 (실 저장소)

```bash
ROOT=$(pwd)/../../experiment/chains
git show HEAD~N:.../gil.py > /tmp/before.py   # 개선 전 (절대 경로 — C028·C043 함정)
python3 /tmp/before.py web "$ROOT" -o /tmp/before.html --chain genesis
python3 gil.py         web "$ROOT" -o /tmp/after.html  --chain genesis
cmp /tmp/before.html /tmp/after.html          # 선형 genesis: 바이트 동일 (H2)
```

- **H2 선형 불변**: genesis(선형)는 개선 전/후 **바이트 동일** — depth = order 인덱스라 좌표 불변(하위호환).
- **loom 압축**: height 3074 → **2498** (분기·병합 덕). 분기 많은 저장소일수록 극적.

### 두 구현 (H4)

```bash
go build -o /tmp/gil-go go/main.go
python3 gil.py web "$ROOT" -o /tmp/ref.html --title T
/tmp/gil-go   web "$ROOT" -o /tmp/go.html  --title T
cmp /tmp/ref.html /tmp/go.html   # 바이트 동일
```

- 실 저장소·분기 픽스처 모두 참조 = Go **바이트 동일** ✔. Go는 `children`의 역으로 parents를 구해 depth 계산(map 순회 비결정적이나 깊이는 max라 무관, pos는 order 슬라이스 순회로 결정적).
- **conformance**: 참조 72/72, Go 64/64, **회귀 0**. SVG 좌표는 §3.1 계약면이 아니라(렌더=비계약) WEB-JSON은 무영향.

## 실행 기록

- 환경: macOS, Python 3, Go(표준 라이브러리), 2026-07-15.
- 결과: H1(386→322)·H2(genesis 바이트 동일)·H3(무충돌)·H4(두 구현 동일) 전부 통과. loom 3074→2498px.
