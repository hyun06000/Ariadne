# 3. 가설 검증 — 형제 라벨 겹침 해소

## 재현 방법

### 불변 기준 (분기 픽스처)
분기 그래프(형제 A·B가 같은 depth)를 gil web으로 렌더 → 형제 노드 x 좌표 측정:
- 개선 전 `_COL_W=26`: 형제 x 간격 26px, 왼쪽 라벨(x+16~x+246)이 오른쪽 노드(x+26) 덮음 → **겹침**.
- 개선 후 `_COL_W=260`: 형제 x 간격 **260px** ≥ 라벨 끝(x+246) → **겹침 해소** (H1).

### 가변 확인 (실 저장소)
```bash
git show HEAD:.../gil.py > /tmp/before.py    # 개선 전 (절대 경로 — C028·C043)
python3 /tmp/before.py web "$ROOT" -o /tmp/b.html --chain genesis
python3 gil.py         web "$ROOT" -o /tmp/a.html --chain genesis
cmp /tmp/b.html /tmp/a.html                   # 선형 genesis 바이트 동일 (H2)
```
- **H2 선형 불변**: genesis(선형, col0만) 바이트 동일 — `col*_COL_W=0`이라 상수 변화 무영향.

### 두 구현 (H3)
```bash
go build -o /tmp/gil-go go/main.go
cmp <(python3 gil.py web "$ROOT" -o /dev/stdout) <(/tmp/gil-go web "$ROOT" -o /dev/stdout)
```
- 실 저장소·분기 픽스처 모두 참조 = Go **바이트 동일**. conformance 참조 72/72·Go 64/64 회귀 0.

## 실행 기록
- 2026-07-15. H1(형제 간격 260≥246)·H2(genesis 동일)·H3(두 구현 동일) 전부 통과.
- SVG 좌표는 §3.1 비계약 — 정확성은 픽스처 x 측정 + 두 구현 cross-check로 보증.
