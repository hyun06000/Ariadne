# 3. 검증 — _layout_columns 무한 스핀

재현·수정·회귀·종료·parity를 재현 가능하게 박제.

## 산출물
- `probe_layout.py` — 원본 알고리즘 계측판. eda 44 parent 그래프로 무한 루프 포획(GUARD>100000 → node=C032 row=12 col=0, tracks 전부 None인데 (12,0) occupied).
- `probe_fix.py` — 수정안(단조 증가 통합) 검증. eda 종료 + 정상 그래프 3종(linear·simplebranch·merge) 좌표 바이트 동일.
- `find_spin.py` — loom prefix 36에서 스핀 최초 발생 확인, 판정기 박제용 순수 위상(parent 인덱스) 추출.

## 결과 (재현치)
| 검증 | 원본 | 수정(참조 py) | 수정(Go) |
|---|---|---|---|
| eda 44 web | 무한 스핀(25s+ kill) | 2s 종료 | 2s 종료 |
| loom(+C075/C076) web | 무한 스핀 | 2s 종료 | 2s 종료 |
| 판정기 | 98/99 (LAYOUT-TERMINATES FAIL) | 99/99 | 85/85 |
| 정상 체인 회귀(genesis·gateway·tapestry·loomlight) | — | 전부 바이트 동일 | — |
| parity 수정 참조↔Go (loomlight·eda) | — | 바이트 동일 | 바이트 동일 |

## 수정
- 참조 `gil.py` `_layout_columns`: `while (row,col) in occupied: col=free_slot()` → occupied면 `col`을 단조 증가시켜 미점유 좌표 확보(트랙 확장 포함).
- Go `main.go` `layoutColumns`: 동형 수정.
- 판정기 `conformance.py`: `WEB-LAYOUT-TERMINATES` 신설(스핀 유발 위상 박제 + 30s 타임아웃). `Impl.run`에 optional `timeout` 추가.

## 긴급 대응 기록
- 소비자 저장소 2ndRound에서 maru의 eda 작업 중 Go v2.25 gil이 이 스핀으로 종료 못 해 **50개 프로세스 누적 → CPU 100%**. 프로세스 정리 + 워치독(15s+·40%+ gil 자동 kill) 임시 방어 후 근본 수정.
