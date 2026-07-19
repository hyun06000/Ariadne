# 2. 실험 설계

## 절차

1. **수정 적용 (참조 `gil.py`)**: `_layout_columns`의 while 루프(occupied 회피)를 **좌표 기준 통합**으로 교체.
   - 현재(결함): `while (row,col) in occupied: ... col = free_slot()` — free_slot은 빈 **track**을 찾으므로, tracks가 비었는데 그 좌표가 점유되면 같은 col을 무한 반환.
   - 수정: occupied면 원 col의 track 예약을 회수하고 **col을 단조 증가(+1)** 시켜 미점유 `(row,col)`을 확보한다. tracks 리스트는 필요 시 None으로 확장. 단조 증가라 유한 DAG에서 반드시 종료.
   ```python
   if (row, col) in occupied:
       if tracks[col] == node:
           tracks[col] = None
       while (row, col) in occupied:
           col += 1
       while len(tracks) <= col:
           tracks.append(None)
   ```
2. **동형 수정 (Go `main.go`의 `layoutColumns`)**: 같은 좌표 산식을 Go에 이식(양 구현 계약). — **Weft(Go 주인) 소환** 또는 Clew가 직접, 판단은 스텝3 진입 시.
3. **판정기 항목 신설**: `_layout_columns`가 분기·병합 반복 그래프(eda류)에서 **유한 시간에 종료**함을 관측하는 conformance 항목(타임아웃 가드). "판정기가 안 보는 계약은 없는 계약"(Weft).

## 준비물

- 참조 구현 `rooms/deployment/ariadne-spec/gil.py` (현 v2.26.0), Go 소스 `go/`.
- 재현 데이터: `3-verification/probe_layout.py`에 박제한 eda 44 parent 그래프(2ndRound에서 스냅, 읽기 전용). 정상 그래프 3종(linear·simplebranch·merge)은 좌표 불변 회귀 기준.
- 실측 대상: 이 저장소 실데이터(loom 119·loomlight 등) — 수정 전후 `gil web` 출력 **바이트 동일** 확인(하위호환).

## 측정 방법

- **종료(availability)**: eda 44로 `gil web`이 **2초 내 정상 종료**(현재 25초+ 스핀). probe_layout.py의 GUARD 미발동.
- **하위호환(회귀 0)**: 이 저장소 실데이터로 수정 전/후 `gil web` HTML **바이트 동일**. 정상 그래프 3종 좌표 동일(probe_fix.py로 선확인 완료: linear·simplebranch·merge 전부 동일).
- **parity**: 참조↔Go 수정 후 같은 데이터에서 좌표(=web 바이트) 동일.
- **판정기**: 종료 항목이 수정 전 바이너리(스핀)를 FAIL, 수정 후를 PASS로 가른다.
- **기각선**: 위 넷 중 하나라도 불충족(1-hypothesis 기각 조건).

## 사용자 컨펌

- 상현님이 "새 loom 사이클로 정석 수정"을 선택(AskUserQuestion). 스핀은 사용자 실작업을 막는 가동중단 문제라 C075(web 무게)보다 우선. 워치독으로 임시 방어 중.
- Go 이식을 Weft에게 맡길지 Clew 직접 할지는 스텝3 진입 시 판단(참조 수정·검증이 먼저).

- [x] 컨펌 받음 (일자: 2026-07-19)
