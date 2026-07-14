# 3. 가설 검증

## 산출물

```
3-verification/
├── gil/gil.py       # v0.8.0: _push_with_renumber — 원장 규율
├── tests.py         # bare 원장 + 병렬 클론 3종 실험
└── runs/            # run1(T3 픽스처 결함 발견) · run2(3/3 + 회귀 26/26)
```

## 재현 방법

```bash
python3 rooms/experiment/chains/loom/C016-number-ledger/3-verification/tests.py
```

## 실행 기록

- 2026-07-14. run1에서 T3 실패 — 원인은 구현이 아니라 **테스트 픽스처의 결함**: 충돌 재료를 원장에 올리는 push가 non-FF로 조용히 거절되어 충돌이 성립하지 않았다(최소 재현으로 격리 진단). 픽스처에 pull --rebase + push 확인을 추가해 run2에서 3/3.
- 병행 사건: Weft의 C014 병합(무충돌, 20사이클 위반 0) — 병렬 존재 협업의 첫 병합이 이 사이클 검증 중에 일어났다.
