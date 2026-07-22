# 1. 가설 수립

## 이전 사이클의 교훈

부모: **v3-build/C034** (conformance v2 open 섹션 전진 삭제).

C034가 찍은 좌표: 게이트 없이 crash가 open(330)→close(619)로 밀렸다. C034는 그 crash원을 "write_cycle 산출물 층"으로 봤으나 — **C035 s1 실측이 정정한다**: crash는 write_cycle이 아니라 **close-seal 테스트가 line 617에서 `impl.run(..., "open", ..., "--git", ...)`로 v2 open을 직접 호출**하기 때문. 게이트 없이 이 open이 은퇴 안내만 내고 사이클을 안 만드니, line 619에서 없는 5-report.md 경로에 쓰려다 crash.

## 상현님 방향 (설계 컨펌)

**"공용 v3 셋업 헬퍼로 일괄 교체."** close·step·release 등은 open을 *테스트*하는 게 아니라 사이클이 *필요*할 뿐 — 그 셋업 open을 gil 미호출 헬퍼(직접 파일 쓰기)로 바꾸면 게이트 없이도 그 섹션이 통과한다.

## 코드 실측으로 좁힌 진실 (C035 s1)

남은 v2 open 호출 26곳(3곳은 v3 open·은퇴 안내로 이미 정상)을 조사하니 **두 부류**:

1. **순수 셋업** — 다른 명령(close·step)을 테스트하려 사이클을 만드는 open. 617·641·682(close-seal), 1311·1326(step). **open을 테스트하지 않으므로 헬퍼로 교체 가능.**
2. **open 계약 검사** — open의 동작 자체를 테스트. 398·409·427(예약 승격), 1354·1383·1386·1687·1714(open 특정 동작), 1974~2007(guard). **셋업이 아니라 검사 — 헬퍼 교체 불가(그건 테스트 삭제).**

`write_cycle`이 이미 **부류 1의 공용 헬퍼다** — v2 산출물(cycle.yaml+5문서)을 gil 없이 직접 쓴다. 단 `--git` 커밋된 사이클이 필요한 셋업(617·641·682 close-seal)은 write_cycle + git add/commit로 확장.

## 문제 분할

부류 1(순수 셋업) 전체를 헬퍼로 교체하는 게 목표지만, 섹션마다 셋업 형태가 다르다(--git 유무, 부모 유무). 한 사이클에 23곳 다 하면 검증이 흐려진다. C035가 정복할 첫 조각:

- **현재 crash원인 close-seal 섹션의 셋업 open(617·641·682)을 write_cycle+git 헬퍼로 교체** — close crash를 없애 다음 겹으로 민다.
- **게이트 없이 통과 범위 전진 실측** — close 섹션이 게이트 없이 통과하나, crash 어디로 미나.
- step·나머지 순수 셋업, 부류 2(open 검사 항목)의 v3 재작성은 정직히 이월(순차 카브).

## 가설

> **가설**: close-seal 섹션의 셋업용 v2 open 호출(617·641·682)을 `write_cycle` + git 커밋 헬퍼로 교체하면 — close-seal 테스트가 open에 의존하지 않게 되어 **게이트 없이 close 섹션이 통과**한다(crash가 close를 넘어 다음 섹션으로 밀림). 이들은 close를 테스트하지 open을 테스트하지 않으므로, 셋업 수단 교체가 판정 의미를 바꾸지 않는다.

## 기각 조건

1. close-seal이 open 산출물의 특정 형식(예: open --git이 만든 커밋 구조)에 의존해, write_cycle+git 헬퍼로는 close 게이트 테스트가 다른 결과를 냄(게이트 상속 시에도 FAIL) → 셋업 교체가 판정 의미를 바꿈(재설계).
2. close-seal crash를 없애도 바로 다음(step 1311 등)에서 또 셋업 open crash → close만으론 전진 미미(범위 확대 필요, 그러나 crash 이동 자체는 전진).
3. 게이트 상속 시 총 초록 수가 C034의 127보다 줄어듦 → 셋업 교체가 회귀.
4. write_cycle+git 헬퍼가 close-seal의 "신규 파일 봉인 게이트" 시나리오(misplaced.txt 등)를 재현 못 함 → 헬퍼가 open 셋업과 등가가 아님.
