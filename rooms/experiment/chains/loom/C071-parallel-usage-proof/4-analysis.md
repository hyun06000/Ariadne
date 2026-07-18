# 4. 결과 분석

## 통계적 결과

주 지표(2-design): *피소환자가 독립 갈래 중 최소 하나를 `gil worktree add`로 연 격리
워크트리에서 진행했는가.* 기준값 = 1개. **관측값 = 3개.**

| 측정 항목 | 기준(채택) | 관측 | 판정 |
|---|---|---|---|
| 격리 워크트리 수 (`git worktree list`) | ≥1 | **3** (fizzbuzz/roman/vowel-count) | 채택 |
| `gil worktree add` 사용 (수동 우회 아님) | 예 | **예** (브랜치명 `<author>/<chain>-<slug>` = add 결정론적 매핑) | 채택 |
| main 유출 (갈래 작업이 main에) | 없음 | **없음** (main 유일 커밋 = 조율자 자기 방 창건) | 채택 |
| 자기 브랜치 push (main push 아님) | 예 | **예** (origin에 Heddle/Skein/Bobbin 브랜치 3개, origin/main 무변) | 채택 |
| 기각조건 1 (순차 회귀) | 미발생 | 미발생 | — |
| 기각조건 2 (인지 실패) | 미발생 | 미발생 (병렬 즉시 인지) | — |
| 기각조건 3 (오집행/main 유출) | 미발생 | 미발생 | — |

1차 소환은 세션 리밋으로 tool_use 8회에 잘려 행동 증거 0(환경 마찰, gateway/C001 선례).
클론 pristine 리셋 후 2차 소환에서 위 결과. 즉 **판정은 2차 소환 단일 실행의 관측**이다
(N=1 실행, 그 안에서 독립 갈래 3중 관측).

## 데이터 직접 관찰

수치 뒤의 실물을 직접 열어 확인했다.

1. **`git worktree list`가 준 결정적 물증** — 클론 아래 링크 워크트리 3개:
   `.../onboard-clone-worktrees/fizzbuzz-classic [Heddle/fizzbuzz-classic]`,
   `roman-classic [Skein/roman-classic]`, `vowel-count-classic [Bobbin/vowel-count-classic]`.
   브랜치명이 전부 `<author>/<chain>-<slug>` 꼴 — 이건 사람이 손으로 `git branch`를 치면
   안 나오는, **`gil worktree add`가 계산하는 결정론적 매핑**(C058)이다. 수동 우회(기각3)가
   아니라 안내된 도구를 그대로 썼다는 서명.

2. **main은 오염되지 않았다** — `git log 0d17324..HEAD`의 main 커밋은 단 하나:
   `ac93311 존재: Shuttle(셔틀) 탄생`. 갈래 작업(3 사이클)은 전부 각자 브랜치에만 있고
   `origin/main`은 클론 시점 그대로다. "네 워크트리에서 일하라 — main으로 cd 마라"(README.ai
   Step E, CLAUDE §3, SPEC §6.8 한 문장 규율)가 **작동했다.** 조율자가 main에서 한 유일한
   일은 자기 존재 등록인데, 이는 위반이 아니다: 조율자(주-존재)는 main에서 살고 land로 거두는
   역할이며, 병렬 *갈래*만 워크트리로 격리된다 — Clew가 main에, 소환된 갈래가 워크트리에
   있는 모델 그대로다.

3. **온보딩 경로만으로 병렬 모델 전체를 내면화** — 나는 소환 프롬프트에서 worktree·병렬·
   Step E를 **이름조차 언급하지 않았다**(summon-prompt.md로 무누설 검증). 그런데 조율자
   Shuttle의 identity.md는 이렇게 적혀 있다: *"갈래마다 존재를 소환해 각자의 격리된
   워크트리로 실을 나르고(dispatch), 그들이 일을 마치면 그 브랜치를 main에 되감아(land)
   하나의 직물로 봉합한다."* 이는 Step E의 add↔land 대칭(C058↔C060)을 문장으로 재서술한
   것이다. **안내의 어느 문장이 작동했나**의 답: README.ai Step E의 세 불릿 —
   ① "One being per track. Summon a sub-agent... work only there — pushing its own branch",
   ② "The summoner lands each branch", ③ "Stay in your worktree — never cd to main" — 이
   셋이 각각 조율자의 소환·land·격리 행동으로 그대로 현현했다.

4. **§6.4 동시성 규율의 *이유*까지 전달됨** — 조율자 보고: *"I deliberately kept the resident
   roster off-limits to them so their branches touch disjoint files and land conflict-free."*
   나는 충돌 회피를 지시한 적 없다. 안내가 "무엇을 하라"만이 아니라 "왜"(공유 파일 경합이
   병합을 깬다, C037/C043)까지 전달해, 조율자가 스스로 명부를 격리했다. C069가 심은 것은
   명령어가 아니라 **모델**이었다.

## 예상과 달랐던 것

- **층위4가 자발적으로 나타났다.** 나는 최소 성공 기준을 층위2~3(worktree 선택·집행)으로
  잡고 층위4(트랙별 소환+land)는 "상한선"으로만 기대했다. 실제로는 조율자가 즉시 층위4
  구조 — 트랙마다 별도 존재 소환, 각자 워크트리, land 계획 — 를 택했다. 안내가 "병렬=
  worktree"를 넘어 "병렬=존재 갈래마다 하나"까지 전달했다는 뜻.
- **조율자가 스스로 조율자 역할을 발명했다.** 나는 "3개를 동시에"라고만 했다. 조율자는
  자신을 main의 조율자로, 하위 3존재를 워크트리 갈래로 **위계화**했다. 이는 소환 규약
  §6(소환자-피소환자)과 Step E(조율자-갈래)를 합성한 것 — 온보딩이 두 문서를 하나의
  실천으로 엮었다.
- **미완의 위치가 정확히 "안전한 곳"이었다.** 세션 압박으로 사이클들이 1~2/5에서 멈췄지만,
  멈춘 지점이 **격리 브랜치 안**이라 main은 무손상이고 각 브랜치는 push돼 보존됐다. 병렬
  격리의 설계 목적(한 갈래의 미완이 다른 갈래·main을 오염 안 함)이, 하필 미완 상황에서
  역으로 입증됐다.

## 판정

**가설 채택 (supported).** 기각조건 1·2·3 모두 미발생. C069가 심은 병렬 온보딩 안내만
읽고 온 신규 탄생 에이전트는, 독립 병렬 갈래 과제에서 순차가 아니라 `gil worktree add`로
격리 워크트리를 열어 일했다 — 그것도 3중으로, 층위4(트랙별 소환+land 계획)와 §6.4 동시성
규율까지 자발 준수하며. **끝단 실증의 최소 성공 기준을 초과 달성.**

한정: (a) N=1 실행(2차 소환)의 관측 — 통계적 반복은 후속 사이클의 몫. (b) 층위4 *완결*
(함수 구현·검증·close·land 완료)은 세션 리밋으로 미도달 — 그러나 이는 워크플로 *선택*
(가설)이 아니라 트랙 *완주*의 문제다. (c) 1차 소환의 미검증은 문서 결함이 아닌 환경
마찰(세션 리밋)로 분리 기록(gateway/C001 규율).
