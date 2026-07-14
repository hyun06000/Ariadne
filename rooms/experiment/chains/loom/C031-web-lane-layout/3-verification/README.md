# 3. 가설 검증

산출물: _layout_columns/layoutColumns 재작성(안정적 레인), runs/(issue-2 + 참조 배치 + 회귀 + Go 대조). 릴리스 v1.5.0.

## 실행 기록 (2026-07-15)

- run1 (참조): maru 재현 케이스 — C006이 x=64(다른 열), 첫째 갈래(C003~C005)는 x=38. 분기 가시. rejected 색 확인.
- run2 (회귀): 실데이터 loom — C012→C013(상속)·C014(다른 열) 분기 가시, 노드 36개 전부 유일 좌표(겹침 없음), fsck·conformance 26/26.
- run3 (Go 대조): maru 케이스 배치 두 구현 바이트 동일, 분기 가시·rejected 색 양쪽, conformance 26/26.
