# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 모든 것이 저장된다: 코드는 `gil.py`(참조 구현)·`conformance.py`(판정기)에 있고, 여기엔 산출물·재현 절차를 남긴다.

## 산출물

- `conformance-reference.txt` — 참조 구현 전체 판정 결과 (**96/96**, THREADS-\* 6항목 포함).
- `demo-this-worktree.txt` / `.json` — 이 워크트리(clew/loom-threads)에서 `gil threads` 실증 출력. C070이 open이라 그 예약은 소비되어 제외되고, C071(weft)·C072(selvage)가 "진행 중 병렬"로, C070이 열린 사이클로 나온다. 상현님 요청("병렬로 뭐가 도나")의 직접 응답.

## 재현 방법

```bash
# (레포 루트 또는 이 워크트리에서)
G=rooms/deployment/ariadne-spec/gil.py
C=rooms/deployment/ariadne-spec/conformance.py

# 1. 실증 — 열린 실 조회 (사람용 + 기계 계약면)
python3 $G threads
python3 $G threads --json

# 2. 판정기 — 참조 구현 전체 (THREADS-* 6항목 포함, 96/96 기대)
python3 $C --gil "python3 $(pwd)/$G"

# 3. 변이 격추 — 소비-예약 필터(이중계상 방지)를 제거하면
#    THREADS-CONSUMED-EXCLUDED가 FAIL해야 판정기가 계약을 실제로 본다 (C038)
#    cmd_threads의 "if any(...startswith(prefix)...): continue" 블록을 제거 → 95/96

# 4. 회귀 — fsck 위반 0 (경고는 기존 유예-경고), web은 threads와 무관해 바이트 불변
python3 $G fsck
```

## 측정 결과

| 측정 | 기준 | 결과 |
|---|---|---|
| 참조 conformance | THREADS-\* 전부 PASS, 회귀 0 | **96/96** (90 기존 + THREADS 6) ✔ |
| THREADS-JSON-SHAPE | reserved·open·*_count 유효 JSON, exit0 | PASS |
| THREADS-RESERVED | 미소비 예약이 정확히(num·for·slug) | PASS |
| THREADS-CONSUMED-EXCLUDED | 소비된 예약 제외(지어냄 방지) | PASS |
| THREADS-OPEN | open만, closed 제외 | PASS |
| THREADS-OPEN-MATCHES-SCAN | threads open == 직접 스캔 open | PASS |
| THREADS-EMPTY | 빈 상태 정직(`[]`, exit0) | PASS |
| 변이(소비 필터 제거) | THREADS-CONSUMED-EXCLUDED FAIL | 95/96 ✔ 격추 |
| fsck 회귀 | 위반 0 | 위반 0 (경고 37, 전부 기존 유예) ✔ |
| 실증 | 이 세션 병렬 상태를 정확히 반영 | C071·C072 진행 중 + C070 열림 ✔ |

## 실행 기록

- 일시: 2026-07-19. 환경: darwin (macOS), Python 3, gil 2.25.0 기반 (이 브랜치에서 threads 추가).
- 특이사항: Go 구현은 threads 미구현 — HELP-COMPLETE가 정직한 부재를 판정(CONTRACT_COMMANDS 등록). Go 이식은 후속 사이클로 이월(C043 리듬).
