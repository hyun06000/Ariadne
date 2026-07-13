# 3. 가설 검증

## 산출물

```
3-verification/
├── tests.py                 # T1(패치)·T1b(마이너 대조) — 도구 미변경 샌드박스
└── runs/
    ├── run0-self-open.txt   # 열기 (lineage: genesis/C003 — 두 번째 체인 간 계보)
    ├── run1-tests.txt       # 2/2 통과
    └── run2-real-release.txt# v0.2.1 실릴리스: 문서-only 확인 (도구 sha 전후 동일)
```

검증 대상 본체: [SPEC.md §6](../../../../../deployment/ariadne-spec/SPEC.md) (소환 규약 v2), CLAUDE.md v2, 릴리스 커밋 `ari: release v0.2.1`.
이 사이클은 도구를 수정하지 않았다 — 실행 도구는 부모(C008)의 것.

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C009-doc-patch-release/3-verification
python3 tests.py; echo "exit: $?"
git tag -l v0.2.1 && grep -A3 "## 6" rooms/deployment/ariadne-spec/SPEC.md | head -4
```

## 실행 기록

- 2026-07-14, macOS. run1: 2/2 첫 실행 통과. run2: verify(11사이클) 통과 후 v0.2.1 — CHANGELOG에 "도구 동기화: 없음 (문서 릴리스)", 커밋 경로는 배포의 방 문서 3개뿐, 패키지 ari.py sha 전후 동일.
- CLAUDE.md v2 갱신은 배포의 방 밖이므로 릴리스 커밋에 포함되지 않음(경로 격리의 정상 동작) — 부속 커밋으로 퍼블리시.
