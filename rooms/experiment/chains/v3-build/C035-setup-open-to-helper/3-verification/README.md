# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 **모든 것**이 저장된다: 코드, 스크립트, 입력 데이터(또는 그 출처와 해시), 실행 로그, 연산 결과, 생성된 아티팩트.

## 대상

배포판 `conformance.py`의 close-seal·close-seal-free·step-scope 섹션 셋업 open(617·641·682)을
`write_cycle` + git 커밋 헬퍼로 교체. 이들은 close/step 게이트를 테스트할 **커밋된 사이클이 필요**할
뿐 open을 검사하지 않으므로, gil 미호출 헬퍼로 셋업하면 게이트 없이도 그 섹션이 통과한다. `gil.py` 무변경.

## 재현 방법

```bash
D=rooms/experiment/chains/v3-build/C035-setup-open-to-helper/3-verification
G="$(pwd)/$D/gil.py"

# M3+M4: 게이트 상속 — close-seal 3항목·STEP-SCOPE PASS, 총 127 유지(판정 의미 불변)
GIL_V2_OPEN=1 python3 $D/conformance.py --gil "python3 $G" | grep -E "CLOSE-SEAL|STEP-SCOPE|준수"

# M1+M2: 게이트 없이 — close-seal crash(619) 소멸→stepgate(1342)로 밀림, 75항목 PASS
python3 $D/conformance.py --gil "python3 $G" ; echo "PASS: $(python3 $D/conformance.py --gil "python3 $G" 2>&1 | grep -c '^PASS')"
```

## 실행 기록

- 실행: 2026-07-22, Darwin 25.5.0, Python3 stdlib.
- **M1 close-seal crash 소멸**: 게이트 없이 crash 지점 619(close-seal)→**1342(stepgate 셋업 open)** 이동.
- **M2 게이트-독립 전진**: 게이트 없이 **75항목 PASS** (C034 40 → 75, 대폭 증가).
- **M3 판정 의미 불변**: 게이트 상속 시 CLOSE-SEAL-GATE·SEAL-ALLOW·SEAL-VERIFICATION-FREE·STEP-SCOPE 전부 PASS(헬퍼가 open 셋업과 등가).
- **M4 회계**: 게이트 상속 **127/127 유지**(셋업 교체는 항목 수 불변).
- **M5 다음 crash 좌표**: line 1342 = stepgate 섹션(1326 셋업 open) — 다음 카브.
- 배포판 적용: gil.py 무변경, conformance만 +8/−3. 상세·판정은 [4-analysis.md](../4-analysis.md).
