# 1. 가설 수립

## 이전 사이클의 교훈

부모: **v3-build/C033** (conformance를 v3 계약으로 재정의 — v3 계약 첫 항목).

C033이 찍은 관문: 완전 버전리스(게이트 없이 초록)는 v3 항목 추가만으로 안 되고, **판정기가 v2 crash에 견디거나 v2 항목을 실제 제거**해야 한다. 게이트 없이 돌리면 **첫 v2 open(OPEN-CREATE, line 330 `_seal_closed`)에서 crash → 순차 실행 전체 무너짐.**

## 상현님 방향 (설계 컨펌)

- **"v2 섹션 전진 삭제 + v3 재작성"** — 판정기를 v2 원장 모델에서 v3 계약으로 근본 이전.
- 배경: conformance 137항 중 37곳이 v2 open 호출, 61곳이 v2 산출물(cycle.yaml·5문서) 전제. 판정기 거의 전체가 v2 모델 위. "v2 완전 폐기"의 대담한 길.

## 코드 실측으로 좁힌 진실 (C034 s1)

crash 지점을 정밀 추적했다:
- **crash는 오직 open 섹션(line 325~485)의 v2 open 호출 때문** — line 330 `_seal_closed`가 첫 open 실패로 cycle.yaml 못 읽음.
- **close 섹션은 v2 open을 호출하지 않는다** (line 607–608 실측) — `write_cycle`(cycle.yaml 직접 쓰는 헬퍼)로 사이클을 만들고 `close`만 테스트. 61곳의 v2 산출물 전제는 대부분 `write_cycle`이지 v2 open 호출이 아니다.

**핵심 함의**: v2 open을 *직접 호출*하는 건 open 섹션(+ open-git·guard 섹션)뿐. close·step·verify 등은 `write_cycle`로 사이클을 만들어 v2 open과 독립. 따라서 **open 섹션만 v3로 재작성하면 crash 지점이 사라지고, 게이트 없이 판정기가 훨씬 멀리(어쩌면 대부분) 통과**할 수 있다.

## 문제 분할

전진 삭제의 전체는 open·guard·open-git 섹션 재작성 + write_cycle의 v2 산출물을 v3 steps.yaml로 전환. 크다. C034가 정복할 첫 조각:

- **open 섹션(line 325~410 핵심 10항목: OPEN-CREATE·INCREMENT·REJECT-SLUG·AUTHOR·PARENT·ROOT 등)을 제거**하고, C033이 파일 끝에 세운 v3 계약 항목을 이 자리로 옮겨 crash 지점을 없앤다.
- **게이트 없이 통과 범위를 실측** — open 섹션 제거 후 게이트 없이 conformance가 어디까지 가는지. crash가 사라지고 close·step 등이 게이트 없이 초록인지.
- open-git·guard 섹션의 v2 open 호출, write_cycle의 v3 전환은 정직히 이월(순차 카브).

## 가설

> **가설**: conformance의 v2 open 섹션(핵심 10항목)을 제거하고 그 자리에 v3 계약 항목을 두면 — crash 지점(line 330 `_seal_closed`)이 사라져 **게이트 없이 판정기가 open 섹션을 넘어 진행**한다. close 등 뒤 섹션이 `write_cycle`로 v2 open과 독립이므로, 게이트 없이 통과하는 항목 수가 crash(0 통과)에서 크게 늘어난다 — 버전리스의 실질 전진.

## 기각 조건

1. open 섹션 제거 후에도 open-git 섹션(line 1368~, `impl.run(..., "open", "--git", ...)`)이 여전히 게이트 없이 crash → open 섹션만 제거로 불충분, 그 섹션도 함께 처리해야(범위 재조정).
2. close·step 등이 `write_cycle`로 만든 사이클이지만 실행 중 어딘가서 v2 open을 암묵 호출하거나 v2-전용 산출물 형식에 의존해 게이트 없이 crash/FAIL → v2 결합이 write_cycle 층까지 깊음(다음 카브).
3. v3 계약 항목을 앞으로 옮기니 make_sandbox·work 경로 의존성이 깨져 v3 항목이 FAIL → 이동이 단순 cut-paste가 아님(재배선 필요).
4. 게이트 상속 시 총 초록 수가 C033의 137보다 줄어듦(제거가 순감) → 재작성이 회귀. (open 10항목 제거 + v3 유지면 137−10+α, 명시적 회계 필요)
