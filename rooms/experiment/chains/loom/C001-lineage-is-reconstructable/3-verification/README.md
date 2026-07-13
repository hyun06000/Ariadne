# 3. 가설 검증

## 산출물

```
3-verification/
├── fixtures/
│   ├── expected-graph.md          # 도구 작성 전에 고정한 정답 (절차 1)
│   ├── chains/test-maze/          # 분기·병합 포함 가상 체인, cycle.yaml x 6 (절차 2)
│   ├── broken/chains/test-broken/ # 파괴 테스트: 끊어진 parent 참조 (절차 6a)
│   └── cyclic/chains/test-cyclic/ # 파괴 테스트: 순환 참조 (절차 6b)
├── ari/ari.py                     # ari log 프로토타입 — Python 3 표준 라이브러리 전용 (절차 3)
└── runs/                          # 실행 로그 4건 (절차 4~6)
    ├── run1-fixture.txt           # 픽스처 검증
    ├── run2-realdata.txt          # 실데이터 (genesis, loom)
    ├── run3-broken-parent.txt     # 끊어진 참조 → 오류 + exit 1
    └── run4-cyclic.txt            # 순환 참조 → 오류 + exit 1
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C001-lineage-is-reconstructable/3-verification

# 1. 픽스처 검증 — 출력을 fixtures/expected-graph.md 와 대조
python3 ari/ari.py log fixtures/chains

# 2. 실데이터 검증 (레포 루트에서)
(cd ../../../../../.. && python3 rooms/experiment/chains/loom/C001-lineage-is-reconstructable/3-verification/ari/ari.py log)

# 3. 파괴 테스트 — 둘 다 명시적 오류와 exit code 1 이어야 한다
python3 ari/ari.py log fixtures/broken/chains; echo "exit: $?"
python3 ari/ari.py log fixtures/cyclic/chains; echo "exit: $?"
```

의존성: Python 3 표준 라이브러리만. 외부 패키지 없음.

## 실행 기록

- 2026-07-14, macOS (Darwin 25.2.0), Python 3 (macOS 기본). 절차 1→7 순서 준수: 정답 고정 → 픽스처 → 구현 → 검증.
- run1: 그래프 구조(root/분기/병합/간선/토폴로지 순서)가 expected-graph.md와 **첫 실행에서 일치**. 수정 반복 없었음.
- run2: 실데이터 특이사항 — 따옴표 안 쉼표 포함 title, 값 뒤 주석, 주석 전용 줄 모두 정상 파싱. 두 체인 모두 단일 노드라 그래프 구조 검증력은 낮음(픽스처가 이를 보완).
- run3/run4: 끊어진 참조·순환 참조 모두 명시적 오류 + exit 1. run4에서 순환에 갇힌 노드 목록(C001-chicken, C002-egg)까지 보고됨.
