# 2. 실험 설계

## 방향

C035 패턴(셋업 open→write_cycle+git 헬퍼)의 withdraw 섹션 적용. 상현님이 확립한 "v2 완전 폐기 + 셋업은 헬퍼" 방침의 기계적 반복. crash원(1476) 해소.

## 코드 실측 — withdraw 셋업의 세 형태 (C037 s2)

1. **WITHDRAW-RETRACTS (1460)**: `open --git`으로 열린 사이클 1개(커밋됨) → withdraw가 그 커밋 revert. **교체**: write_cycle + git add/commit(사이클을 별도 커밋으로) → withdraw가 그 커밋 revert 가능.
2. **WITHDRAW-REJECTS-CLOSED (1472+step×5+close)**: 닫힌(태그된) 사이클 → withdraw 거부. **교체**: write_cycle(status="closed", step="5") + git commit + `git tag cycle/demo/C001-to-seal`(close가 만드는 봉인 태그를 직접). C036 close-seal에서 write_cycle+태그가 봉인 재현됨을 이미 실증.
3. **WITHDRAW-ATOMIC (1488)**: 열린 사이클 1개 → 없는 ref withdraw 거부. **교체**: write_cycle + git commit.

## 핵심 고려 — WITHDRAW-RETRACTS의 Revert 검증

withdraw는 "사이클을 만든 커밋을 revert"한다. open --git은 사이클을 한 커밋으로 만든다. write_cycle+git commit도 사이클을 한 커밋으로 만드니 **withdraw가 revert할 대상이 동일하게 존재**한다. 단 write_cycle은 chain.md도 만드니 커밋에 함께 담김 — withdraw의 revert가 사이클 디렉토리를 지우는지가 검사 대상(RETRACTS는 `not os.path.isdir(cdir)` 확인). s3서 실측.

## 절차

1. **baseline** — 게이트 상속 121/121, 게이트 없이 crash(1476)·84통과.
2. **격리 복사본에서 withdraw 3항목 셋업 교체**:
   - 1460·1488: `open --git` → `write_cycle` + git add/commit.
   - 1472~1479: `open+step×5+close` → `write_cycle(status="closed", step="5")` + git commit + `git tag cycle/demo/C001-to-seal`.
3. **게이트 없이 실측** — crash 사라졌나, 어디로 밀리나, 통과↑.
4. **게이트 상속 실측** — withdraw 3항목 PASS(판정 불변), 총 121 유지.
5. **배포판 적용**.

## 준비물

- 배포판 `conformance.py`(121항목)·`gil.py`. Python3 stdlib. write_cycle·make_sandbox.

## 측정 방법

- **M1 (crash 소멸)**: 게이트 없이 line 1476 crash 안 함, crash 뒤로 밀림.
- **M2 (전진)**: 게이트 없이 통과 84에서 증가.
- **M3 (판정 불변)**: 게이트 상속 시 WITHDRAW-RETRACTS·REJECTS-CLOSED·ATOMIC 전부 PASS. 기각조건 1·2·3: 하나라도 FAIL이면 헬퍼가 비등가.
- **M4 (회계)**: 게이트 상속 총 121 유지(셋업 교체는 항목 수 불변).
- **M5 (다음 crash 좌표)**: crash 위치 기록 — 다음 카브.

## 사용자 컨펌

생략 — C035에서 상현님이 "공용 v3 셋업 헬퍼로 일괄 교체"를 컨펌했고, C037은 그 확립된 패턴의 기계적 반복(같은 셋업→헬퍼 변환, 판정 의미 불변). 새 설계 결정 없음. 갈래가 나뉘지 않는 순차 카브.

- [x] 생략 (사유: C035 컨펌한 패턴의 반복, 새 결정 없음)
