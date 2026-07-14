# 2. 실험 설계

가설(1-hypothesis)만을 검증한다: **구현 수정 + fsck R14 + conformance 항목**의 삼위일체로 "chain.md가 커밋되었다"를 데이터로 만든다.

## 변경 목록 (6곳 + SPEC)

| # | 파일 | 변경 |
|---|---|---|
| 1 | `gil.py` `cmd_open` | 커밋 `paths`에 `chain.md` 추가 (`new_chain`일 때만) |
| 2 | `gil.py` `fsck_collect` | **R14** 신설 — 체인 디렉토리는 `chain.md`를 가져야 한다 (위반) |
| 3 | `go/main.go` `cmdOpen` | 커밋 경로에 `chain.md` 추가 (`newChain`일 때만) |
| 4 | `go/main.go` fsck | **R14** 미러링 |
| 5 | `conformance.py` | **OPEN-NEWCHAIN-COMMIT** + **FSCK-R14** 신설 (양 구현 대상) |
| 6 | `gil.py`/`go` help | fsck 설명 `R1~R13` → `R1~R14` (양방향 진실성, §7.2) |
| — | `SPEC.md` | R14 규칙 표 등재 + open의 chain.md 커밋 계약 명시 + fsck 표기 갱신 |

**설계 원칙 — R14는 위반이지 경고가 아니다.** R12(다중루트)는 `--new-root`라는 정당한 탈출구가 있어 경고다. 하지만 `chain.md` 없는 체인에는 정당한 이유가 없다 — `open --new-chain`이 항상 만든다. R13의 선례를 따른다: **v0.6에서 태어나 유예할 과거가 없다** (네 체인 모두 이미 chain.md 보유 — 4-analysis 전 확인 완료). 위반이므로 fsck exit 1로 CI 게이트가 막는다.

**설계 원칙 — 구조가 아니라 파일 위치로 안전.** R14 검사는 `chains_root`가 있을 때만 파일시스템을 본다(R10·R13과 동일 패턴). `_scan_chains`가 chains-root 아래 모든 디렉토리를 체인으로 등록하므로(사이클 0개여도) 빈 체인의 누락도 잡힌다.

## 절차

1. **기준선 포획.** 현재 참조 62/62, Go 54/54 확인. `git stash` 없이 깨끗한 트리에서 시작.
2. **결함 재현 (수정 전).** 임시 저장소에서 `gil open newchain slug --new-chain --git --author me` → `git status`로 `chain.md`가 미추적으로 남는지 확인. 양 구현. → **1-hypothesis의 결함 실증.**
3. **수정 #1·#3 (구현).** 양 구현의 open 커밋 경로에 chain.md 포함.
4. **수정 #2·#4 (fsck R14).** 양 구현에 R14 추가.
5. **수정 #5 (판정기).** OPEN-NEWCHAIN-COMMIT + FSCK-R14 신설. OPEN-GIT(참조 항목) 구조를 참고.
6. **수정 #6·SPEC (계약 문서).** help·SPEC 갱신.
7. **판정.** 참조 64/64, Go 56/56. 우리 저장소 `gil fsck` 위반 0 (회귀 + 과잉검출 없음).
8. **교차 검증.** 같은 저장소에 대해 두 구현의 fsck stdout 바이트 동일.
9. **변이 격추.** M1~M4 각각이 대응 항목에서만 FAIL (샌드박스 독립 — C040·C041 교훈).

## 기대 행동표 (정답 — 도구보다 먼저 고정)

| ID | 명령/상황 | 기대 결과 | 대상 |
|---|---|---|---|
| **T1** | `open X s --new-chain --git` (새 체인) | `chain.md`가 HEAD 커밋에 포함, 작업 트리에 미추적 `chain.md` **없음** | 참조·Go |
| **T2** | 체인의 `chain.md` 삭제 후 `fsck` | **R14 위반**, exit 1 | 참조·Go |
| **T3** | 정상 저장소(4체인 chain.md 보유) `fsck` | 위반 **0** (과잉검출 없음) | 참조·Go |
| **T4** | `conformance OPEN-NEWCHAIN-COMMIT` | PASS | 참조·Go |
| **T5** | `conformance FSCK-R14` | PASS | 참조·Go |
| **T6** | 회귀 — 기존 판정 항목 전부 | 참조 62 유지, Go 54 유지 (→ +2씩) | 판정기 |
| **T7** | 두 구현 fsck stdout (같은 저장소) | 바이트 동일 | 교차 |

## 변이 (역감지 — "이 계약이 없으면 무엇이 통과하나")

| ID | 변이 | 기대 FAIL 항목 |
|---|---|---|
| **M1** | `gil.py` 커밋 paths에서 chain.md 제거 | OPEN-NEWCHAIN-COMMIT (참조) |
| **M2** | `gil.py` fsck R14 제거 | FSCK-R14 (참조) |
| **M3** | `go/main.go` 커밋에서 chain.md 제거 | OPEN-NEWCHAIN-COMMIT (Go) |
| **M4** | `go/main.go` fsck R14 제거 | FSCK-R14 (Go) |

각 변이는 **자기 항목에서만** FAIL하고 동반 실패 0이어야 한다(C040의 눈먼 테스트 교훈 — 항목별 샌드박스 독립).

## 준비물

- Python 3, Go (표준 라이브러리; `cd go && go build -o /tmp/gil-go main.go` — go.mod 없음, C037 확인)
- 판정기 `conformance.py`, 참조 `gil.py`, Go `go/main.go`
- **함정 주의**: `--gil`에 **절대 경로**를 준다 (C028·C043이 두 번 문서화 — 상대 경로는 web 무더기 FAIL).

## 측정 방법

- **성공**: T1~T7 전부 기대대로 + M1~M4 각 격추. 회귀 0.
- **기각**: 1-hypothesis의 네 기각 조건 중 하나라도 발생.
- 버전: 도구 blob 변경(구현·판정기·SPEC) → **마이너 승격 v2.4.0** (§7 승격 규칙).

## 사용자 컨펌

생략 — 상현님이 사이클 자율 진행 전권을 위임(loom/C008)했고, 이 사이클은 C043 보고서 추천 (A)를 그대로 착수한다. 외부 쓰기(이슈 #14 답글·닫기)만 승인 대기로 남긴다.

- [x] 컨펌 갈음: 전권 위임 + 보고서 추천 (2026-07-15)
