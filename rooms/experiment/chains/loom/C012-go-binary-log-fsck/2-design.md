# 2. 실험 설계

## 절차 (판정 표를 겸해 선고정)

1. **구현** — `3-verification/gil-go/main.go`: 표준 라이브러리만(외부 모듈 0). cycle.yaml 평탄 파서(주석·따옴표·리스트·후행 주석 — 참조 구현과 동일 규칙), 체인 스캔, R1~R8 위반 수집(fsck), 계보 재구성 + 토폴로지 렌더(log). CLI 계약: `gil fsck [chains-root]`(위반 시 exit ≠ 0), `gil log [chains-root]`(끊어진 참조 시 exit ≠ 0). 미구현 명령은 "미구현" 오류 + exit ≠ 0.
2. **빌드** — `go build -o gil main.go`. 산출물 검사: `file`로 네이티브(Mach-O) 확인, 바이너리 내 python 호출 부재.
3. **판정** — **C011의 conformance.py를 무수정 그대로** 실행: `--gil "./gil"`. 기대:
   - PASS (11): FSCK-CLEAN, FSCK-R1~R8, LOG-OK, LOG-BROKEN
   - FAIL (11, 설계상): OPEN-*(3) · CLOSE-*(3) · WEB-*(2) · GIT-CLOSE · VERIFY-*(2) — 전부 미구현 명령의 것
4. **교차 확인** — 실제 레포(사이클 16개)에서 Go gil과 파이썬 gil의 fsck 결과(exit·위반 수) 일치 확인.

## 측정 방법

| # | 항목 | 통과 기준 |
|---|---|---|
| 1 | 부분집합 | conformance 출력에서 위 11항목 전부 PASS |
| 2 | FAIL의 순수성 | FAIL 목록 = 미구현 명령 항목 11개, 그 외 없음 |
| 3 | 네이티브 | `file` 출력에 Mach-O 실행 파일, 소스에 파이썬 호출 0 |
| 4 | 실데이터 교차 | Go fsck와 Python fsck가 실제 레포에서 동일 판정 (exit 0, 위반 0) |

## 사용자 컨펌

- [x] 컨펌 받음 (2026-07-14, 박상현: "가자")
