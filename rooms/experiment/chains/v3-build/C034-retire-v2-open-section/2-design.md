# 2. 실험 설계

## 상현님 확정 방향

**"v2 섹션 전진 삭제 + v3 재작성"** — 판정기를 v2 원장 모델에서 v3 계약으로 근본 이전. C033 "v2 완전 폐기"의 실행.

## 코드 실측으로 확정한 제거 경계 (C034 s2)

conformance line 318~409가 순수 open 섹션. 그 안에서:
- **v2 open을 직접 호출하는 OPEN-\* 항목** (line 325~401): OPEN-CREATE·INCREMENT·REJECT-SLUG·AUTHOR-REQUIRED·PARENT-REQUIRED·ROOT-CONFLICT·NEW-ROOT·PARENT-CLOSED-GATE·PARENT-CLOSED-OK·ROOT-EMPTY-CHAIN — **10항목, 전부 `impl.run(root, "open", ...)` 호출.** 이것이 crash 근원.
- **FSCK-MULTI-ROOT** (line 402~409): `write_cycle`로 사이클 생성 → fsck 테스트. **v2 open 독립 → 남긴다.**

crash 지점 정밀 추적: line 330 `_seal_closed(_oc)`가 첫 open(OPEN-CREATE) 실패로 cycle.yaml 못 읽음. **v2 open 10항목이 crash의 유일 근원.**

## C034가 실제로 하는 것 (전진 삭제 첫 조각)

1. **v2 open 10항목 제거** — line 325~401의 OPEN-* 블록(그 사이 `_seal_closed`·`prov()`·`make_sandbox` 헬퍼 호출 포함). FSCK-MULTI-ROOT는 보존.
2. **v3 계약 항목을 open 자리로 이동** — C033이 파일 끝(GUARD 뒤)에 세운 V3-OPEN-CREATE·V3-OPEN-REJECT-EXISTING·V3-RETIRE-GUIDANCE 3항목을 open 섹션 자리로 옮긴다. 판정기 초입에서 v3 계약을 먼저 검사(v2 open이 있던 논리적 위치).
3. **게이트 없이 통과 범위 실측** — 제거 후 게이트 없이 conformance가 open 섹션을 넘어 어디까지 가는지. crash 소멸 + close·step 등 통과 항목 수.

open-git 섹션(line 1368~, open --git 호출)·guard 섹션(2030~, open 호출)·write_cycle의 v3 전환은 **정직히 이월**(순차 카브). C034는 crash 근원 제거 + 게이트-독립 실질 전진.

## 절차

1. **baseline** — 게이트 상속 시 137/137, 게이트 없이 crash(line 330) 기록.
2. **격리 복사본에서 제거+이동** — conformance.py 사본에서 OPEN-* 10항목 제거, v3 3항목을 그 자리로 이동. 헬퍼(`prov`·`_seal_closed`)가 다른 섹션서도 쓰이면 정의는 보존.
3. **게이트 없이 실측** — crash 사라졌나, open 섹션 넘어 진행하나, 몇 항목 통과·FAIL하나.
4. **게이트 상속 실측** — 총 초록 수 회계(137 − 10 open + 0 [v3는 이미 셈] = 127 예상, 회귀 아니라 v2 제거).
5. **배포판 적용** — 실측 후.

## 준비물

- 배포판 `conformance.py`(C033에서 137항목)·`gil.py`(C032 승격).
- Python3 stdlib.

## 측정 방법

- **M1 (crash 소멸)**: 게이트 없이 conformance가 line 330에서 crash 안 함. open 섹션 넘어 진행. 기각조건 없음(핵심 성공).
- **M2 (게이트-독립 전진)**: 게이트 없이 통과하는 항목 수가 crash(0)에서 크게 늘어남. close·step 등이 게이트 없이 초록. 기각조건 2: write_cycle 층서 v2 결합 발견되면 FAIL.
- **M3 (open-git 잔여 확인)**: open-git 섹션(1368~)이 게이트 없이 여전히 crash하는지 — 하면 기각조건 1(범위 재조정, 정직히 이월).
- **M4 (v3 항목 생존)**: 이동한 v3 3항목이 새 위치서 PASS(경로 의존성 안 깨짐). 기각조건 3: 이동으로 FAIL이면 재배선.
- **M5 (회계)**: 게이트 상속 시 총 초록 = 137 − 10(제거) = 127 예상. 명시적 회계로 "제거지 회귀 아님" 확인. 기각조건 4: 설명 안 되는 감소면 회귀.

## 사용자 컨펌

설계 방향 상현님 컨펌: "v2 섹션 전진 삭제 + v3 재작성"(AskUserQuestion, C034 진입 시).

내가 정직히 좁힌 것: 전진 삭제는 판정기 거의 전체 재작성(37 open 호출·61 v2 산출물). 한 사이클엔 크다. C034는 **crash 근원(open 10항목)만 제거**해 게이트-독립을 실질 전진시키고, open-git·guard·write_cycle 전환은 순차 이월. "전진 삭제"를 작은 확실함으로 — crash 근원부터.

- [x] 컨펌 받음 (일자: 2026-07-22) — "v2 섹션 전진 삭제 + v3 재작성" 방향, 범위는 crash 근원 첫 조각
