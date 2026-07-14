# 3. 가설 검증

## 산출물

```
3-verification/
├── gil/gil.py   # v0.9.0: _changed_vs_last_tag — 태그 blob 기준 + 판정기 포함
├── tests.py     # T1(직접 실행)·T2(판정기 변경)·T3(문서-only) — 태그 상태를 구분 구성하는 샌드박스
└── runs/run1-tests.txt  # 3/3 + 회귀 26/26
```

## 재현 방법

```bash
python3 rooms/experiment/chains/loom/C018-release-baseline/3-verification/tests.py
```

## 실행 기록

- 2026-07-14. 3/3 첫 실행 통과, conformance 26/26. v0.9.0 릴리스의 성공 메시지가 새 형식("도구 변경: gil")으로 출력됨 — 수정이 자기 릴리스에서 즉시 작동.
