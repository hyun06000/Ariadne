# 3. 가설 검증

## 산출물

```
3-verification/
├── fixtures/
│   ├── expected-behavior.md   # 기대 행동 T1~T11 — 구현보다 먼저 고정 (절차 1)
│   └── sandbox/               # 실제 레포 구조를 본뜬 미니 저장소 (절차 2)
├── ari/ari.py                 # ari v3: log + fsck + open + close — stdlib 전용 (절차 3)
├── tests.py                   # 테스트 드라이버 — 독립 샌드박스 + 무변화 스냅샷 검사 (절차 4)
└── runs/
    ├── run1-tests.txt         # T1~T11: 11/11 통과
    └── run2-self-close.txt    # 도그푸딩: C003 자신을 ari close로 닫은 기록 (절차 5)
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C003-open-close-porcelain/3-verification

# T1~T11 전체 (각 테스트는 독립 임시 샌드박스에서 실행 후 정리됨)
python3 tests.py; echo "exit: $?"

# 도그푸딩 재현은 불가(이미 닫혔으므로 재실행 시 "이미 닫힌 사이클" 거부가 정상) —
# 대신 그 거부 자체가 T10의 실전판임을 확인할 수 있다 (레포 루트에서):
python3 rooms/experiment/chains/loom/C003-open-close-porcelain/3-verification/ari/ari.py \
  close loom C003-open-close-porcelain
```

의존성: Python 3 표준 라이브러리만 (계승).

## 실행 기록

- 2026-07-14, macOS (Darwin 25.2.0), Python 3. 절차 준수: 기대 행동 고정 → 샌드박스 → 구현 → 테스트 → 도그푸딩.
- run1: 11/11 통과. 거부 케이스 7건 전부 exit ≠ 0 + 저장소 스냅샷(전 파일 sha256) 무변화 확인.
- run2: 실제 레포에서 `ari close loom C003-open-close-porcelain --date 2026-07-14` 실행 — 도구가 만든 첫 실전 상태 전이가 자기 자신의 닫힘이었다. 직후 fsck 위반 0건.
