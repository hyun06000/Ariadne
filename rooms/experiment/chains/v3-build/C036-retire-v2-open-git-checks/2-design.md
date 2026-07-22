# 2. 실험 설계

## 상현님 확정 방향

**"v2 open 검사 항목 제거."** open --git·--push·NO-REMOTE·PATH-SYMLINK = v2 open 전용 계약(v3 대응 없음). C034 전진 삭제 패턴.

## 코드 실측 — 구조 (C036 s2)

부류 A·B 항목은 전부 **line 1024 `if args.skip_git or shutil.which("git") is None:` 의 else 블록(git 있을 때)** 안에 있다(8칸 들여쓰기). NO-REMOTE(1698)·PATH-SYMLINK(1727)만 4칸(최상위, 그 블록 밖).

제거/교체 대상:
- **부류 A (제거)** — OPEN-GIT(1303~1324)·OPEN-NEWCHAIN-COMMIT(1351~1397)·OPEN-PUSH-RENUMBER(~1450)·NO-REMOTE-GRACEFUL(1674~1701)·PATH-SYMLINK-GIT(1703~1750). 각 항목의 셋업+check 블록 정밀 제거(블록 전체 아님).
- **부류 B (STEP-GATE 셋업 교체)** — 1326~1349. 셋업 open(1331)을 write_cycle로. STEP-GATE는 step-by-step 검사지 open 검사가 아니므로 판정 불변.

## C036이 하는 것

1. **STEP-GATE(1326) 셋업 open(1331)을 write_cycle로 교체** — 현 crash원 해소. STEP-GATE는 "open이 1스텝만 스캐폴딩"을 검사하는데, 이건 write_cycle이 step 미지정 시 1-hypothesis만 만드는 것과 등가(C035 s3서 확인). 단 STEP-GATE (1)은 "open이 2-5·3-verification 부재"를 확인 → write_cycle step 미지정도 동일.
   - **주의**: STEP-GATE (1)이 open의 산출물 형태(1스텝만)를 확인한다면 이건 셋업이 아니라 open 검사일 수 있다. s3서 실측으로 판별 — 헬퍼 교체 후 STEP-GATE PASS면 셋업, FAIL이면 open 검사(그럼 STEP-GATE도 부류 A로 재분류·제거 또는 v3화).
2. **부류 A 5항목 제거** — v2 open 전용 계약, C033 매핑상 v3 대응 없음.
3. **게이트 없이 전진 실측** — crash 어디로 밀리나, 통과 75에서 증가.

WITHDRAW 셋업 교체는 crash 지나면 드러나니 이월(순차).

## 절차

1. **baseline** — 게이트 상속 127/127, 게이트 없이 crash(1342 stepgate)·75통과 기록.
2. **격리 복사본에서**: (a) STEP-GATE 셋업 open→write_cycle 교체 (b) 부류 A 5항목 제거.
3. **게이트 없이 실측** — crash 이동, 통과 수 증가.
4. **게이트 상속 실측** — STEP-GATE 판정 불변(PASS), 부류 A 제거로 127−5=122 예상, 회계.
5. **배포판 적용**.

## 준비물

- 배포판 `conformance.py`(127항목)·`gil.py`. Python3 stdlib. write_cycle 헬퍼.

## 측정 방법

- **M1 (STEP-GATE 판정 불변)**: 헬퍼 교체 후 게이트 상속 시 STEP-GATE PASS. 기각조건 2: FAIL이면 open이 검사 일부(재분류).
- **M2 (crash 전진)**: 게이트 없이 crash가 stepgate(1342) 넘어 뒤로 밀림. 통과 75에서 증가.
- **M3 (부류 A 제거 회계)**: 게이트 상속 총 = 127 − 5(부류 A) = 122. 기각조건 3: 설명 못 할 감소면 오류.
- **M4 (판정기 무결)**: 부류 A 제거·STEP-GATE 교체가 다른 항목 안 깸(게이트 상속 122 전부 PASS).
- **M5 (다음 crash 좌표)**: crash 위치 기록(withdraw 1551 등) — 다음 카브.

## 사용자 컨펌

상현님 컨펌: "v2 open 검사 항목 제거"(AskUserQuestion, C036 진입). 내가 더한 것: crash원 STEP-GATE(부류 B)는 검사 항목이 아니라 셋업이므로 제거가 아니라 헬퍼 교체(C035 패턴) — crash 해소를 위해 병행. 상현님 방향(검사 제거) + crash 해소(셋업 교체)를 함께.

- [x] 컨펌 받음 (일자: 2026-07-22) — "v2 open 검사 항목 제거", STEP-GATE 셋업 교체 병행은 crash 해소 위한 C035 패턴 재사용
