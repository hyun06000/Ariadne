# 3. 가설 검증

## 산출물

```
3-verification/
├── fixtures/
│   ├── expected-behavior.md   # 기대 행동 T1~T8 — 구현보다 먼저 고정 (절차 1)
│   └── sandbox/               # C003의 샌드박스 재사용 (테스트마다 깃 저장소로 초기화)
├── ari/ari.py                 # ari v4: log + fsck + open + close(--git) + verify (절차 2)
├── tests.py                   # 드라이버 — 독립 샌드박스 + 깃 초기화 (절차 3)
└── runs/
    ├── run0-self-open.txt     # 이 사이클은 ari open이 실전에서 연 첫 사이클이다
    ├── run1-tests.txt         # T1~T8: 8/8 통과
    ├── run2-tag-backfill.txt  # 과거의 각인: C001·C002→a111d05, C003→6d8e98e (절차 4)
    └── run3-verify-real.txt   # 실데이터 verify: 닫힌 사이클 3개, 변조 0건
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C004-git-binding/3-verification

# T1~T8 전체 (각 테스트는 독립 임시 샌드박스에서 실행 후 정리됨. 깃 CLI 필요)
python3 tests.py; echo "exit: $?"

# 실데이터 무결성 검사 (레포 루트에서)
python3 rooms/experiment/chains/loom/C004-git-binding/3-verification/ari/ari.py verify
```

의존성: Python 3 표준 라이브러리 + 깃 CLI (이 사이클로 공식 의존성이 됨).

## 실행 기록

- 2026-07-14, macOS (Darwin 25.2.0), Python 3 + git. 절차 준수: 기대 행동 고정 → 구현 → 테스트 → 백필 → 도그푸딩.
- run1: 8/8 통과, 첫 실행. 변조 탐지(T3)는 추적 파일 수정과 미추적 신규 파일 추가를 모두 잡았다.
- run2·run3: 백필 후 실데이터 verify — 닫힌 사이클 3개 전부 태그와 작업 트리 일치.
- **도그푸딩 (절차 5)**: 이 사이클 자신이 `ari close --git`으로 닫혔다. 증거는 이 저장소의 깃 역사 자체다 — `ari: close loom/C004-git-binding` 커밋과 태그 `cycle/loom/C004-git-binding`. 닫힘 이후 이 디렉토리에 파일을 추가하지 않는다(verify가 변조로 본다 — 이제 규칙이 아니라 기계적 사실이므로).
