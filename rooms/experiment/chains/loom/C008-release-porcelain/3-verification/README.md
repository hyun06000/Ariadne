# 3. 가설 검증

## 산출물

```
3-verification/
├── fixtures/expected-release-tool.md  # 기대 행동 T1~T7 — 구현보다 먼저 고정
├── ari/ari.py                         # ari v6: + release (자기 자신을 패키지로 동기화)
├── tests.py                           # 샌드박스(깃+구버전 패키지+태그 v0.1.0) 드라이버
└── runs/
    ├── run0-self-open.txt             # 배포된 v0.1.0 도구가 연 사이클
    ├── run1-tests.txt                 # 7/7 통과 (1차)
    ├── run2-tests-after-verify-fix.txt# 설계-구현 드리프트(verify 사전 검증 누락) 수정 후 7/7
    └── run3-real-release.txt          # 도그푸딩: v0.2.0 실릴리스 (도구의 첫 자기 릴리스)
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C008-release-porcelain/3-verification
python3 tests.py; echo "exit: $?"
git tag -l v0.2.0   # 실릴리스 각인 확인
```

## 실행 기록

- 2026-07-14, macOS, Python 3 + git. run1: 7/7. 이후 **자체 발견 드리프트 1건**: 설계·가설은 사전 검증에 fsck·verify를 명시했으나 구현이 fsck만 확인 — verify 호출을 추가하고 재실행(run2: 7/7).
- run3: 실제 레포에서 `ari release 0.2.0` — verify(9사이클 무변조) 통과 → 도구·문서 동기화 → CHANGELOG `[0.2.0]` → 배포의 방만 담은 커밋 → 태그 v0.2.0. 패키지 ari.py와 실행 도구의 sha 동일(드리프트 0).
