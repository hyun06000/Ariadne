# 2. 실험 설계

## 상현님 확정 방향

**"공용 v3 셋업 헬퍼로 일괄 교체."** 셋업용 v2 open을 gil 미호출 헬퍼로 교체. C034 두 번째 겹(게이트 없이 초록)의 실행.

## 코드 실측 — close-seal 셋업 open이 하는 일 (C035 s2)

line 617: `impl.run(csg, "open", "demo", "cyc", "--author", "t", "--new-chain", "--git", "--root", csgr)`
- **만드는 것**: `demo/C001-cyc` 사이클 디렉토리(cycle.yaml + 1-hypothesis.md) + chain.md + **git 커밋**(--git).
- close-seal 테스트는 그 뒤 5-report.md·misplaced.txt를 추가하고 **close --git이 신규 파일 봉인 게이트를 거는지** 테스트. **open 자체는 검사 대상 아님** — close 게이트가 검사 대상.

`write_cycle`은 cycle.yaml+5문서를 gil 없이 직접 쓰지만 **git 커밋은 안 한다.** close-seal은 "커밋된 사이클 위에 신규 파일"을 봉인 게이트로 검사하므로, 대체 헬퍼 = `write_cycle` + git add/commit.

## C035가 실제로 하는 것

close-seal 3개 셋업 open(617·641·682) 각각을:
```python
# 전: impl.run(csg, "open", "demo", "cyc", "--author","t","--new-chain","--git","--root",csgr)
# 후: write_cycle(csg, "demo", "C001-cyc")           # cycle.yaml+5문서+chain.md, gil 미호출
#     csgg("add", "-A"); csgg("commit", "-q", "-m", "seed cycle")   # 커밋된 사이클
```
- 682는 step-scope 섹션의 셋업(같은 패턴 — step-seal용). 함께 교체.
- close-seal 테스트가 5-report.md를 별도로 쓰는데(619·643), write_cycle이 이미 5-report.md를 만드니(status=open이면 step까지 문서 생성 — 확인 필요), 중복/충돌 없게 조정.

부류 2(open 검사 항목: 예약·guard·open 특정 동작)와 step 섹션 나머지 셋업은 **정직히 이월**(순차 카브). C035는 crash원(close-seal) 제거로 게이트 없이 통과 전진.

## 절차

1. **baseline** — 게이트 상속 127/127, 게이트 없이 crash(line 619 close-seal) 기록.
2. **격리 복사본에서 close-seal 셋업 open 교체** — 617·641·682을 write_cycle+git 커밋으로. 5-report 중복 조정.
3. **게이트 없이 실측** — close-seal crash 사라졌나, crash 어디로 미나, 통과 항목 수 증가.
4. **게이트 상속 실측** — close-seal 3항목(SEAL-GATE·SEAL-ALLOW·SEAL-VERIFICATION-FREE) + step-scope가 여전히 PASS(판정 의미 불변), 총 127 유지.
5. **배포판 적용** — 실측 후.

## 준비물

- 배포판 `conformance.py`(C034에서 127항목)·`gil.py`.
- Python3 stdlib. write_cycle·make_sandbox 헬퍼.

## 측정 방법

- **M1 (close-seal crash 소멸)**: 게이트 없이 line 619(close-seal)에서 crash 안 함. crash가 close 넘어 다음으로 밀림. 기각조건 4: 헬퍼가 봉인 게이트 시나리오 재현 못 하면 반증.
- **M2 (게이트-독립 전진)**: 게이트 없이 통과 항목 수가 C034(40)보다 늘어남(close-seal 3 + 그 사이 항목).
- **M3 (판정 의미 불변)**: 게이트 상속 시 close-seal 3항목 여전히 PASS(SEAL-GATE 거부·SEAL-ALLOW 승인·VERIFICATION-FREE). 기각조건 1: 헬퍼로 판정 결과 바뀌면 반증.
- **M4 (회계)**: 게이트 상속 총 = 127 유지(셋업 교체는 항목 수 불변). 기각조건 3: 줄면 회귀.
- **M5 (다음 crash 좌표)**: crash가 어디로 밀렸는지 기록(step 1311 등 다음 셋업 open) — 다음 카브 좌표.

## 사용자 컨펌

설계 방향 상현님 컨펌: "공용 v3 셋업 헬퍼로 일괄 교체"(AskUserQuestion, C035 진입).

내가 정직히 좁힌 것: "일괄 교체"는 부류 1(순수 셋업 ~15곳) 전체지만, 섹션마다 셋업 형태가 달라 한 사이클엔 크다. C035는 **현재 crash원(close-seal 3개)만** 헬퍼 교체해 게이트-독립을 전진시키고, step·나머지·부류 2는 순차 이월. 부류 2(open 검사 항목)는 헬퍼 교체 불가(테스트 삭제라) — v3 재작성 카브로. "일괄 교체"를 crash 순서대로 작은 확실함으로.

- [x] 컨펌 받음 (일자: 2026-07-22) — "공용 v3 셋업 헬퍼로 일괄 교체", 범위는 crash원부터
