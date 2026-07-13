# 3. 가설 검증

## 산출물

```
3-verification/
├── schema-v0.2-draft.md       # 규칙 R1~R8 + 이주 규정 — 도구보다 먼저 고정 (절차 1)
├── fixtures/
│   ├── expected-fsck.md       # 기대 위반 10건 — 구현보다 먼저 고정 (절차 2)
│   ├── bad/chains/test-bad/   # 규칙별 위반 픽스처 (사이클 13개, 절차 3)
│   └── good/chains/           # 체인 간 lineage 정상 사례 (alpha, beta)
├── ari/ari.py                 # ari v2: log(lineage 주석) + fsck — C001 계승, stdlib 전용
└── runs/
    ├── run1-fsck-bad.txt      # 위반 10건 — 기대 목록과 정확히 일치
    ├── run2-fsck-good.txt     # OK + beta의 lineage 주석 렌더
    ├── run3-migration-diff.txt# 이주 diff (무손실 증빙)
    ├── run4-fsck-real.txt     # 🔴 실전 첫 실행: R1 위반 1건 — 이 사이클 자신의 id에 마침표
    ├── run5-log-real.txt      # loom 체인의 첫 실제 간선 C001→C002 + lineage 주석
    └── run6-fsck-real-after-rename.txt # 개명 후 OK, 위반 0건
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C002-schema-v0-2/3-verification

# 1. 위반 픽스처 — fixtures/expected-fsck.md 의 10건과 집합 일치해야 한다 (exit 1)
python3 ari/ari.py fsck fixtures/bad/chains; echo "exit: $?"

# 2. 정상 픽스처 — OK (exit 0), log에서 lineage 주석 확인
python3 ari/ari.py fsck fixtures/good/chains; echo "exit: $?"
python3 ari/ari.py log fixtures/good/chains --chain beta

# 3. 실데이터 (레포 루트에서) — fsck OK + loom의 실제 간선·lineage 렌더
(cd ../../../../../.. && python3 rooms/experiment/chains/loom/C002-schema-v0-2/3-verification/ari/ari.py fsck)
(cd ../../../../../.. && python3 rooms/experiment/chains/loom/C002-schema-v0-2/3-verification/ari/ari.py log --chain loom)
```

의존성: Python 3 표준 라이브러리만 (C001에서 계승).

## 실행 기록

- 2026-07-14, macOS (Darwin 25.2.0), Python 3. 절차 준수: 스펙 고정 → 기대 위반 고정 → 픽스처 → 구현 → 검증 → 이주.
- run1: 위반 10건, 기대 목록과 누락 0·거짓 양성 0으로 일치. 표기 위반(R3)이 해소 검사(R2/R6)로 중복 보고되지 않음도 확인.
- run3: 이주는 (a) 템플릿에 lineage 필드·규칙 주석 추가, (b) loom/C001의 주석으로만 있던 계보를 `lineage` 필드로 승격 — 삭제·의미 변경 없음.
- **run4 (예상 밖의 실전 검증)**: 실데이터 첫 fsck가 R1 위반을 잡았다 — 이 사이클 자신의 id `C002-schema-v0.2`의 마침표. 스펙을 실수에 맞춰 고치지 않고(정답 오염 방지) 열린 사이클을 `C002-schema-v0-2`로 개명. 외부 참조 없음을 grep으로 확인 후 수행.
- run6: 개명 후 실데이터 위반 0건.
