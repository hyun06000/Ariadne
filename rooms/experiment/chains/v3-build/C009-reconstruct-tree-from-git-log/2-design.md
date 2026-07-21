# 2. 실험 설계

가설(1-hypothesis): `git log`(커밋 시간순 + 메시지 서술)만으로 steps.yaml 없이 스텝 트리를 복원하면 원본과 위상 동형이 된다 = 깃이 단일 진실원 가능.

## 설계 개요

C008이 각인한 깃 저장소(build.sh로 재생성)를 입력으로, **`git log`만 읽는 복원기** `rebuild.py`를 짜서 스텝 트리를 복원하고, 복원본을 원본 steps.yaml과 위상 대조한다. 복원기는 **steps.yaml 파일도, 커밋 diff도 읽지 않는다** — 오직 `git log --reverse --format=%s`(커밋 시간순 + subject)만. C003의 순환 상태기계를 복원 방향으로 재사용한다.

## 복원 알고리즘 (rebuild.py)

입력: `git log --reverse --format=%s` (오래된→최신 커밋 subject 리스트).
상태: 시간순으로 커밋을 순회하며 트리를 재구성. **성장 팁을 커서 없이 계산**(C003 원리의 복원판).

각 커밋 subject를 파싱:
1. `gilv3 open …: sN define` → 루트 노드 `{id:sN, kind:define, parent:null}`.
2. `gilv3 step: sN <kind>` (백트래킹 마커 없음) → **open_branch 계승**: parent = 직전 노드(시간순 팁). analyze면 outcome을 파싱.
3. `gilv3 step: sN analyze/<outcome> (backtrack to sM)` → 죽은 잎: `{outcome:backtrack, backtrack:sM}`. parent = 직전 노드.
4. `gilv3 step: sN hypothesis (new branch from sM after backtrack)` → 새 형제 가지: parent = sM (서술 명시). 이것이 **되돌아감을 복원하는 유일한 지점** — 여기서만 parent가 시간순 직전이 아니다.
5. `gilv3 step: sN analyze/success` → 산 잎: `{outcome:success}`.
6. `gilv3 close …` → 봉인(트리 구조 무관, 무시).

**핵심**: parent는 대개 "시간순 직전 노드"(순환 계승)이고, **예외는 백트래킹 후 새 가지뿐**(서술의 `from sM`). 이것이 C003 상태기계의 거울 — 쓰기 때 팁 자동/`--to` 명시였던 것이 읽기 때 직전계승/`from` 파싱이 된다.

## 절차

1. **입력 재생성**: C008 build.sh로 임시 깃 저장소에 C012→C014 트리를 각인(메인 레포 밖 스크래치패드).
2. **rebuild.py** (순수 stdlib): 위 알고리즘. `git log --reverse --format=%s`만 subprocess로 읽어 노드 리스트 복원. **steps.yaml·git show·diff 접근 0** (코드로 보장 — git 하위명령을 log만 쓴다).
3. **measure.py** 대조:
   - **M1 (노드·parent 동형)**: 복원 노드 집합 == 원본, parent 엣지 집합 == 원본. K1.
   - **M2 (backtrack·outcome 동형)**: 복원 backtrack 엣지·outcome == 원본. K2.
   - **M3 (깃 로그 단독)**: rebuild.py가 호출하는 git 하위명령이 `log`뿐(steps.yaml·show·diff·cat-file 0)임을 정적 감사. K3.
   - **M4 (유일 결정성)**: 같은 로그가 유일한 트리를 낳는가 — 복원 알고리즘이 각 커밋에서 분기 없이 결정적임을 확인(파싱이 애매어 없이 케이스 배타적). 추가로 **왕복 무손실**: 복원 트리를 다시 steps.yaml로 직렬화하면 원본 built-steps.yaml과 동일. K4.

## 준비물

- C008 build.sh·gilv3.py (입력 각인, 기존 경로 호출).
- rebuild.py, measure.py (이 사이클 신규, 순수 stdlib).
- C008 built-steps.yaml (원본 진실원 — 대조 기준).
- 임시 깃 저장소: 스크래치패드 (메인 레포 밖, C005 규율).

## 측정 방법

| # | 측정 | 기각 조건 | PASS 기준 |
|---|---|---|---|
| M1 | 노드·parent 엣지 동형 | K1 | 복원 == 원본 (노드 10, parent 엣지 동일) |
| M2 | backtrack·outcome 동형 | K2 | backtrack {s4→s1, s7→s1}·outcome 동일 |
| M3 | 깃 로그 단독 (정적 감사) | K3 | rebuild.py의 git 하위명령 = log만 |
| M4 | 유일 결정성 + 왕복 무손실 | K4 | 파싱 배타적·복원→steps.yaml == 원본 |

네 측정 PASS면 supported (깃 단일 진실원 가능). 하나라도 K 발동이면 rejected/partial.

## 사용자 컨펌

- 갈래(깃 로그로 트리 재구성)는 상현님이 AskUserQuestion으로 선택. 세부 설계는 C008 역방향의 표준 절차(복원기+동형 대조)라 추가 컨펌 불필요.

- [x] 컨펌 받음 (일자: 2026-07-21, 갈래 선택 = 깃 로그로 트리 재구성)
