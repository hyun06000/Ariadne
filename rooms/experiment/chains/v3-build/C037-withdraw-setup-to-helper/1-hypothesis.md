# 1. 가설 수립

## 이전 사이클의 교훈

부모: **v3-build/C036** (v2 open 검사 항목 제거 — 게이트 없이 75→84).

C036이 찍은 다음 crash원: **line 1476(withdraw 셋업 open)**. C035가 안전 증명한 패턴: 셋업 open(전제 구축)은 write_cycle+git 헬퍼로 교체해도 판정 의미 불변(그 명령을 테스트하지 open을 테스트하지 않으므로).

## 코드 실측으로 좁힌 진실 (C037 s1)

withdraw 섹션(1458~1494) 세 항목:
- **WITHDRAW-RETRACTS** (1465) — 열린 사이클 withdraw → 디렉토리 소멸+Revert. 셋업 open(1460).
- **WITHDRAW-REJECTS-CLOSED** (1483) — 닫힌 사이클 withdraw 거부. 셋업 open(1472)+step×5(1474)+close(1479) = 닫힌 사이클 구축. **현 crash원**(1476, close 전 5-report 씀).
- **WITHDRAW-ATOMIC** (1493) — 없는 ref withdraw 거부. 셋업 open(1488).

세 항목 다 **withdraw를 검사**하고 open은 셋업이다(부류 B). 특히 REJECTS-CLOSED는 open+step×5+close 전체를 `write_cycle(status=closed)` 한 줄로 대체하면 훨씬 간단하고 게이트-독립.

## 문제 분할

C037이 정복할 조각: **withdraw 3항목의 셋업 open(1460·1472·1488)을 write_cycle+git 헬퍼로 교체.** REJECTS-CLOSED의 step×5+close 셋업도 write_cycle(status=closed)+태그로 대체. crash원(1476) 해소해 게이트 없이 전진. 나머지 open(예약 398~497·guard 1832~)은 이월(예약·guard는 부류 재판별 필요 — 순차).

## 가설

> **가설**: withdraw 3항목의 셋업 open을 write_cycle+git 헬퍼로 교체하면 — withdraw 테스트가 open에 의존하지 않게 되어 crash원(1476)이 사라지고 게이트 없이 통과가 84에서 증가한다(crash가 withdraw 넘어 밀림). withdraw는 withdraw를 검사하지 open을 검사하지 않으므로 셋업 교체가 판정 의미를 안 바꾼다(C035 패턴).

## 기각 조건

1. withdraw가 open --git이 만든 특정 커밋 구조(Revert 대상)에 의존해, write_cycle+git 헬퍼로는 WITHDRAW-RETRACTS의 Revert 검증이 다른 결과 → 셋업 교체가 판정 의미 바꿈(재설계).
2. REJECTS-CLOSED의 "닫힌(태그된) 사이클"을 write_cycle+태그로 재현 못 함(close가 만드는 태그 형식 특수) → 셋업 교체 불충분.
3. 게이트 상속 시 withdraw 3항목 중 하나라도 FAIL → 헬퍼가 open 셋업과 비등가.
4. crash 해소돼도 통과 수 84에서 안 늘거나 줄어듦 → 전진 실패/회귀.
