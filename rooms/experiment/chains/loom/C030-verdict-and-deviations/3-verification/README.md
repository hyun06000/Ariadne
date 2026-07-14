# 3. 가설 검증

산출물: 참조 구현 v0.3(verdict·deviations·R10·log 표시/집계·web 색), Go 미러링(Weft, 병렬), SPEC v0.3, runs/(issue-1 원문 + 참조 검증 + Go 대조).

## 실행 기록 (2026-07-15)

- run1 (참조 8/8): log 표시(`[closed · supported]`·`[closed · rejected ⚠1]`)·집계(`결말: supported 1 · rejected 1 · 이탈 1건`) — maru가 이슈에 그린 모습 그대로. fsck R10(잘못된 verdict 위반, deviations 파일 없음 위반, 이탈 경고 개별). web JSON·기각 색.
- 실데이터 fsck: 기존 34사이클(verdict 없음) → 경고 34건(요약 한 줄)·위반 0·exit 0 — R10 유예 정확. conformance 26/26.
- Go 미러링(Weft): 별도 사이클로 병렬 직조, 참조와 fsck·log 대조 — run에 병합 후 기록.
