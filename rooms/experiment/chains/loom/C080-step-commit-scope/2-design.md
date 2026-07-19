# 2. 실험 설계

## 절차 (상현님 결정: 스텝 경계로 자르기 — A)

1. **참조 `cmd_step` 수정** (2931-2933행): `git add`/`commit` 경로를 사이클 디렉토리 전체 → **cycle.yaml + 스텝 ≤N 파일**로 좁힌다.
   - paths = [cycle.yaml 상대경로] + `_STEP_FILES[:n]`의 각 파일/디렉토리 상대경로 중 **디스크에 존재하는 것**.
   - `_STEP_FILES[i]`는 (라벨, 파일명). 파일명이 `3-verification`이면 디렉토리(하위 산출물째 `git add -A -- <dir>`가 담음).
   - 존재 확인: 스캐폴드가 아직 안 만든 파일은 건너뜀(정상 흐름 보존).
   - `git add -A -- <paths>` → 스텝 >N 파일은 paths에 없어 안 담김. cycle.yaml은 항상 포함(step 전이 기록).
2. **Go `cmdStep` 동형 수정** (parity — C078·C079 리듬: 참조·Go 동시).
3. **판정기 항목**: `STEP-SCOPE`(step N 커밋이 스텝 ≤N 파일 + cycle.yaml만 담고, 미리 만든 스텝 >N 파일은 제외) 신설.

## 준비물

- 참조 `gil.py`(v2.30), Go `main.go`, `conformance.py`. `_STEP_FILES`, `_rel_to_repo`.

## 측정 방법

| 측정 | 성공 기준 |
|---|---|
| 뒷 스텝 파일 미리 작성 후 step 2 | 커밋에 4·5 파일 없음, cycle.yaml·1·2만 |
| cycle.yaml 전이 | 항상 커밋 (step 필드 갱신 보임) |
| 정상 흐름(스텝마다 작성→전이) | 그 스텝 파일 정상 커밋, 누락 0 |
| step 3 전이 | 3-verification/ 하위 산출물째 커밋 |
| 참조↔Go | parity (동작 동일) |
| 판정기 | STEP-SCOPE PASS + 회귀 0 |

**기각선**: 위 중 하나라도 불충족(1-hypothesis 기각 조건).

## 사용자 컨펌

- 상현님 AskUserQuestion: "스텝 경계로 자르기(추천)" 선택. step N 커밋 = cycle.yaml + ≤N 파일.

- [x] 컨펌 받음 (일자: 2026-07-19)
