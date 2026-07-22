# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 **모든 것**이 저장된다: 코드, 스크립트, 입력 데이터(또는 그 출처와 해시), 실행 로그, 연산 결과, 생성된 아티팩트.

## 대상

배포판 `conformance.py`의 withdraw 섹션 3항목 셋업 open을 write_cycle+git 헬퍼로 교체(C035 패턴):
- WITHDRAW-RETRACTS·ATOMIC: `open --git` → `write_cycle` + git commit.
- WITHDRAW-REJECTS-CLOSED: `open+step×5+close` → `write_cycle(status=closed, step=5)` + git commit + `git tag cycle/demo/C001-to-seal`.
셋업 open은 withdraw 게이트를 테스트할 사이클이 필요할 뿐 open 미검사. `gil.py` 무변경.

## 재현 방법

```bash
D=rooms/experiment/chains/v3-build/C037-withdraw-setup-to-helper/3-verification
G="$(pwd)/$D/gil.py"

# M3+M4: 게이트 상속 — withdraw 3항목 PASS, 총 121 유지
GIL_V2_OPEN=1 python3 $D/conformance.py --gil "python3 $G" | grep -E "WITHDRAW|준수"

# M1+M2: 게이트 없이 — crash(1476) 소멸→guard(_seal_closed 92)로 밀림, 106 PASS
python3 $D/conformance.py --gil "python3 $G" ; echo "PASS: $(python3 $D/conformance.py --gil "python3 $G" 2>&1 | grep -c '^PASS')"
```

## 실행 기록

- 실행: 2026-07-22, Darwin 25.5.0, Python3 stdlib.
- **M1 crash 소멸**: 게이트 없이 crash 1476(withdraw)→**line 92 `_seal_closed`(guard 섹션 셋업 open, ~1832)** 이동.
- **M2 게이트-독립 전진**: 게이트 없이 **84→106 PASS** (+22 대폭).
- **M3 판정 불변**: WITHDRAW-RETRACTS·REJECTS-CLOSED·ATOMIC 전부 PASS. RETRACTS의 Revert 검증(디렉토리 소멸)도 헬퍼 셋업 위에서 통과 — write_cycle+git commit이 open --git과 등가.
- **M4 회계**: 게이트 상속 **121/121 유지**.
- **M5 다음 crash 좌표**: guard 섹션(1832~) — C050 병렬 안전(open guard 검사), 셋업 아니라 v3 재작성 필요.
- 배포판 적용: gil.py 무변경, conformance +10/−12. 상세·판정은 [4-analysis.md](../4-analysis.md).
