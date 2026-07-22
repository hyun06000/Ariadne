# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 **모든 것**이 저장된다: 코드, 스크립트, 입력 데이터(또는 그 출처와 해시), 실행 로그, 연산 결과, 생성된 아티팩트.

## 대상

배포판 `conformance.py`에서 v2 open 전용 검사 6항목 제거:
**OPEN-GIT·STEP-GATE·OPEN-NEWCHAIN-COMMIT·OPEN-PUSH-RENUMBER·NO-REMOTE-GRACEFUL·PATH-SYMLINK-GIT.**
모두 v2 open의 사이클-간 커밋 구조·번호 재번호·환경 우아화를 검사 — v3에 대응물 없음(C033 매핑).
STEP-GATE의 (1)"open이 1스텝만"은 V3-OPEN-CREATE가, (2)(3) step 검사는 STEP-OK·STEP-REJECT-*가 담당.
`gil.py` 무변경.

## 재현 방법

```bash
D=rooms/experiment/chains/v3-build/C036-retire-v2-open-git-checks/3-verification
G="$(pwd)/$D/gil.py"

# M3+M4: 게이트 상속 — 127-6=121/121 (부류A 5 + STEP-GATE 1 제거)
GIL_V2_OPEN=1 python3 $D/conformance.py --gil "python3 $G"

# M2: 게이트 없이 — crash가 stepgate(1342)→withdraw(1476)로 밀림, 84 PASS
python3 $D/conformance.py --gil "python3 $G" ; echo "PASS: $(python3 $D/conformance.py --gil "python3 $G" 2>&1 | grep -c '^PASS')"
```

## 실행 기록

- 실행: 2026-07-22, Darwin 25.5.0, Python3 stdlib.
- **M1 STEP-GATE 재분류**: STEP-GATE는 "open이 1스텝만 + step 검사"가 섞임 → open 검사부는 V3-OPEN-CREATE와 중복, step 검사부는 STEP-OK 등에 있어 제거 정합.
- **M2 게이트-독립 전진**: 게이트 없이 crash 1342(stepgate)→**1476(withdraw 셋업)** 이동, **75→84 PASS**.
- **M3 회계**: 게이트 상속 **121/121** = 127 − 6(부류A 5 + STEP-GATE 1). 정확한 회계.
- **M4 무결**: 121 전부 PASS(제거가 다른 항목 안 깸).
- **M5 다음 crash 좌표**: line 1476 = withdraw 셋업 open(1563) — 부류 B, 다음 카브 헬퍼 교체.
- 배포판 적용: gil.py 무변경, conformance −155/+8. 상세·판정은 [4-analysis.md](../4-analysis.md).
