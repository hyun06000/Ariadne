# 3. 가설 검증

산출물: cmd_handoff/cmdHandoff(참조·Go), close 핸드오프 힌트, README.ai.md 규율, runs/run1-handoff.txt. 릴리스 v1.6.0.

## 실행 기록 (2026-07-15)

- T1: 실데이터 handoff에 다섯 요소(존재 clew·weft, 체인 상태, 부활 경로, 다음 실, 세션 정리 요청) 전부.
- T2: 빈/깃없는 저장소에서 우아(존재 없음·체인 없음 고지, 크래시 없음).
- T3: close 핸드오프 힌트 출력(동작 불변).
- T4: 두 구현 handoff 출력 **바이트 동일**.
- T5: conformance 26/26 (양 구현).
