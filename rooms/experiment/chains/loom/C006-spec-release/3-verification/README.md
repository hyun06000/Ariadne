# 3. 가설 검증

## 산출물

```
3-verification/
├── fixtures/expected-release.md  # 판정 T1~T6 — 패키지 작성보다 먼저 고정
├── tests.py                      # T1~T5 드라이버 (T1: 퀵스타트 블록 추출·실행)
└── runs/
    ├── run0-self-open.txt        # ari open이 연 사이클
    ├── run1-tests.txt            # 5/5 통과
    └── run2-release-verify.txt   # T6: 태그 v0.1.0 + CHANGELOG [0.1.0]
```

검증 대상 본체는 [rooms/deployment/ariadne-spec/](../../../../../deployment/ariadne-spec/) (릴리스 커밋 `0e19588`, 태그 `v0.1.0`).
이 사이클은 도구를 수정하지 않았으므로 자체 ari 사본이 없다 — 참조는 부모(C005)의 최종본.

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C006-spec-release/3-verification
python3 tests.py; echo "exit: $?"     # T1은 임시 디렉토리에 패키지만 복사해 퀵스타트를 실행한다
git tag -l v0.1.0                     # T6
```

## 실행 기록

- 2026-07-14, macOS, Python 3 + bash. run1: 5/5 첫 실행 통과. run2: 릴리스 커밋 후 태그·CHANGELOG 확인.
- T1에서 확인된 것: 신선한 환경 + 패키지만으로 부트스트랩 → open → close → fsck → log → web 전부 성공, 실험의 방 참조 0.
