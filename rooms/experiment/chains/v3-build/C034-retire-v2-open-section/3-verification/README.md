# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 **모든 것**이 저장된다: 코드, 스크립트, 입력 데이터(또는 그 출처와 해시), 실행 로그, 연산 결과, 생성된 아티팩트.

## 대상

배포판 `conformance.py`에서 **v2 open 10항목(OPEN-CREATE·INCREMENT·REJECT-SLUG·AUTHOR·
PARENT-REQUIRED·ROOT-CONFLICT·NEW-ROOT·PARENT-CLOSED-GATE·PARENT-CLOSED-OK·ROOT-EMPTY-CHAIN)
+ prov() 헬퍼를 제거**하고, C033이 파일 끝에 세운 **v3 계약 3항목을 그 자리(판정기 초입)로 이동**.
이 제거로 게이트 없이 crash하던 line 330 `_seal_closed` 지점이 사라진다(C033 M5 관문). `gil.py`는 무변경.

## 재현 방법

```bash
D=rooms/experiment/chains/v3-build/C034-retire-v2-open-section/3-verification
G="$(pwd)/$D/gil.py"

# M1+M2: 게이트 없이 — crash가 open(330)→close(619)로 밀림, 40항목 PASS
python3 $D/conformance.py --gil "python3 $G" ; echo "PASS수: $(python3 $D/conformance.py --gil "python3 $G" 2>&1 | grep -c '^PASS')"

# M4+M5: 게이트 상속 — v3 3항목 PASS, 총 127/127 (137-10 제거, 회귀 아님)
GIL_V2_OPEN=1 python3 $D/conformance.py --gil "python3 $G"
```

## 실행 기록

- 실행: 2026-07-22, Darwin 25.5.0, Python3 stdlib.
- **M1 crash 소멸**: 게이트 없이 crash 지점이 line 330(open)→line 619(close)로 이동. **open 섹션 crash 사라짐.**
- **M2 게이트-독립 전진**: 게이트 없이 **40항목 PASS**(crash 때 0). FAIL은 OPEN-SKIPS-RESERVED·PROMOTES-OWNER·LAST-RESERVATION-GIT(예약 섹션, v2 open 호출)·ROUND-*·FSCK-R15 — crash 아니라 정상 FAIL로 강등.
- **M4 v3 이동 생존**: v3 3항목이 새 위치(초입)서 PASS(경로 의존성 안 깨짐).
- **M5 회계**: 게이트 상속 **127/127 ✔** = 137 − 10(제거). 제거지 회귀 아님(명시적 회계 일치).
- 배포판 적용: gil.py 무변경, conformance.py만 −116/+31. 배포판 = 검증본 바이트 동일.
- 상세·판정은 [4-analysis.md](../4-analysis.md).
