# 3. 가설 검증

## 산출물

```
3-verification/
├── gil/gil.py            # v0.4.0: 전수 grep으로 잔재 4종 정리 (커밋 접두어·CSS·JSON 훅·footer)
├── conformance.py        # 계약 준수 스위트 — 22항목, 구현은 --gil "<명령>"로만 주입 (v0.4.0에 동봉)
├── mutants/              # 변이 4종: m1(fsck 무력화)·m2(슬러그 사전 검증만 제거)·m2p(사전+사후 제거)·m3(외부 리소스 주입)
└── runs/
    ├── run0-self-open.txt
    ├── run1-reference-impl.txt  # 참조 구현 22/22
    ├── run2-mutants.txt         # m1: 8 FAIL / m2: 22/22 생존(동등 변이!) / m2p: 3 FAIL / m3: 1 FAIL
    └── run3-deployed.txt        # 배포된 패키지의 스위트 × 배포된 gil = 22/22
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C011-contract-conformance/3-verification
python3 conformance.py --gil "python3 $PWD/gil/gil.py"                 # 참조 구현 → 22/22, exit 0
python3 conformance.py --gil "python3 $PWD/mutants/m1-fsck-blind.py"   # → FAIL 다수, exit 1
python3 conformance.py --gil "python3 $PWD/mutants/m2-slug-blind.py"   # → 22/22 (동등 변이 — 아래 참조)
python3 conformance.py --gil "python3 $PWD/mutants/m2p-open-blind.py"  # → FAIL 3, exit 1
python3 conformance.py --gil "python3 $PWD/mutants/m3-external-leak.py" # → FAIL 1, exit 1
```

## 실행 기록

- 2026-07-14, macOS. run1: 참조 구현 22/22 (스위트 자체 버그 2건 — kwargs 충돌 — 을 수정하며 도달).
- run2의 발견: **m2(슬러그 사전 검증만 제거)가 22/22로 생존했다.** 원인 규명 — gil의 사후 fsck(심층 방어)가 위반 생성물을 잡아 롤백하므로 관찰 가능한 행동은 계약을 지킨다. 즉 m2는 **동등 변이**였고, 스위트는 행동이 같은 구현을 gil로 인정한 것이다 — §7 구현 독립의 의도된 판정. 행동까지 파괴한 m2p(사전+사후 모두 제거)는 3항목에서 격추됐다.
- run3: 배포된 패키지(v0.4.0)의 conformance.py로 배포된 gil.py 판정 → 22/22.
