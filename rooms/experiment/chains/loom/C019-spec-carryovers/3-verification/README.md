# 3. 가설 검증

산출물: SPEC §2 보강·§5.1 신설 (릴리스 v0.9.1에 각인), runs/run1-tests.txt.

## 재현 방법

```bash
# §5.1의 예시 블록을 추출해 샌드박스에서 실행 (run1의 T1 스크립트 참조)
grep -A8 "실행 가능한 예시" rooms/deployment/ariadne-spec/SPEC.md
git tag -l v0.9.1
```

## 실행 기록

- 2026-07-15. T1(예시 5행 전부 실행) ✓, T2(마커 3종) ✓, T3(문서 릴리스 분류 — C018의 새 기준이 정확히 판정) ✓.
