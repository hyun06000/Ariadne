# 1. 가설 수립

## 이전 사이클의 교훈 (부모: loom/C012)

1. **두 몸, 한 계약.** 스펙 §4·§5와 참조 구현만으로 Go 이식(fsck·log)이 가능했다.
   구현 교체 가능성은 이미 실물이다.
2. **스위트 v2는 판정 항목 간 독립이다.** close 검사 등은 스위트가 `write_cycle`로
   상태를 직접 구축하므로, 명령 하나씩 추가하는 부분 이식 로드맵이 가능해졌다 —
   이번 사이클은 그 로드맵의 첫 이행이다 (부모 보고서의 제안 B).
3. **거부형 검사는 수락형과 짝일 때만 의미가 있다.** C012에서 OPEN-REJECT-SLUG·
   CLOSE-TEMPLATE-REJECT·CLOSE-DOUBLE-REJECT는 미구현의 exit≠0로 **공허 통과**했다.
   수락형(OPEN-CREATE·CLOSE-OK)이 함께 통과할 때에야 이 거부형들의 PASS가 실질이 된다.

사용자 박상현님의 방향: "파이썬에서 벗어나 바이너리로, 정말 깃처럼."

## 문제 분할

C012의 Go 바이너리는 **읽기 명령**(fsck·log)만 구현했다. 남은 계약을 쪼개면
① 쓰기 porcelain(open·close), ② 깃 바인딩(close --git·verify), ③ web, ④ release다.
지금 정복할 첫 문제는 **①**이다 — 저장소를 변경하는 첫 Go 명령이며, 참조 구현의
쓰기 규율(사전 검증 → 변경 → 사후 fsck → 실패 시 원상 복구)의 이식이 관건이라
가장 작으면서도 다음 단계(②)의 전제가 된다.

②~④는 이번 폭의 범위 밖이다. 범위 밖 명령·플래그(`--git` 포함)는 C012의 방식대로
정직하게 "미구현"을 알리고 exit 3 한다.

## 가설

> **가설**: C012의 Go 바이너리에 open·close를 추가하면, 무수정 conformance.py
> (v0.5.0 배포본)가 OPEN-CREATE · OPEN-INCREMENT · OPEN-REJECT-SLUG ·
> CLOSE-TEMPLATE-REJECT · CLOSE-OK · CLOSE-DOUBLE-REJECT 6항목을 전부 PASS로
> 판정하고, C012가 통과한 11항목(FSCK-CLEAN·R1~R8·LOG-OK·LOG-BROKEN)의 PASS가
> 유지될 것이다.

## 기각 조건

- 목표 17항목(기존 11 + 신규 6) 중 하나라도 FAIL이면 기각.
- 실데이터 교차 검증에서 Go open·close의 동작(생성물의 fsck 판정, 닫기 전이 결과)이
  파이썬 참조 구현과 다르면 기각.
- 범위 밖 항목(WEB-*, GIT-CLOSE, VERIFY-CLEAN)의 FAIL은 판정에 넣지 않되 정직하게
  기록한다. VERIFY-TAMPER 등 거부형의 공허 통과도 기록한다.
