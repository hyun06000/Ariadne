# 1. 가설 수립

부모: v3-build/C012-merge-is-lineage (supported). 조부: C011(분기)·C013(코드 아티팩트, Bobbin). 저자: Clew. main 단독·순차(C074 — 소스 수정이라 원리 증명과 달리 격리 불필요, 병렬 존재 없음).

## 이전 사이클의 교훈

C011·C012가 **깃 ≅ gil**을 분기·합류 양방향으로 닫았다. 완성표:

| gil 개념 | 깃 네이티브 | 증명 |
|---|---|---|
| 스텝 종결 | 1 커밋 | C005·C011 |
| 백트래킹 | `git checkout <조상>` + detached 커밋 | C011 |
| 위계 | 커밋 trailer 지문 | C010·C011 |
| 잎 | 태그(못) | C011 |
| lineage | 머지 커밋 다중부모 | C012 |
| 뷰어 | `git log --all --graph` | C011·C012 |

**그러나 이 매핑은 순수 깃 셸 스크립트(build_branches.sh·build_merge.sh)로 원리만 증명됐다 — 실제 `gilv3.py` 명령은 아직 이걸 강제하지 못한다.** C011·C012 두 사이클 연속 "gil 명령 자동화"가 1순위로 이월됐다.

## 문제 분할 — 그리고 발견한 긴장

최신 gilv3.py(C010판)를 읽어 델타를 확정했다:

- **이미 있음**: open/step/close가 steps.yaml 조작 + `--git`이 trailer 지문 각인(C010). backtrack 포인터도 steps.yaml 레벨엔 있음.
- **빠짐 (C011·C012 미구현)**: ① 백트래킹=`git checkout` ② 잎=태그 ③ lineage=머지 커밋.

**⭐ 핵심 긴장 발견**: C010판은 **C008의 "append-only 전진기록" 철학에 강결합**돼 있다. `_assert_forward_only`가 `checkout`을 *명시적으로 금지*한다("reset/checkout/rebase 금지", gilv3.py:59). 백트래킹조차 "새 전진 커밋"으로 선형 처리한다.

그런데 **C011이 바로 그 C008을 정정했다**: "백트래킹은 커밋이 아니라 `git checkout <조상>` + detached 커밋이다"(C011 교훈 2). C011·C012를 구현하려면 **C008의 forward-only 집행과 정면충돌**한다 — checkout으로 되돌아가면 HEAD가 "뒤로" 가므로 `_assert_forward_only`가 거부한다.

**이것이 자동화가 두 사이클 이월된 진짜 이유일 수 있다.** 단순 기능 추가가 아니라 **철학의 전환**이다.

### 이 긴장의 해소 — 무엇을 먼저 정복하나

분할하면:
1. **[이번 정복] 백트래킹=checkout을 gilv3.py에 구현하고, C008 forward-only를 C011 모델로 정정한다.** 이게 가장 근본이고, 잎=태그·lineage=머지는 그 위에 얹힌다(checkout 분기가 있어야 죽은 가지가 생기고, 그래야 잎 태그가 의미를 갖는다).
2. (이월 후보) 잎=태그 자동화 — close가 산 잎에, backtrack이 죽은 잎에 해시 태그.
3. (이월 후보) lineage=머지 — `close --lineage A,B`가 `git merge --no-ff`.

**1을 먼저 정복하는 이유**: 철학 충돌(C008↔C011)이 여기 있다. 이걸 정직히 해소하지 않으면 2·3이 잘못된 토대 위에 선다. 백트래킹=checkout이 서면 깃 그래프가 **진짜 분기**를 그리고(선형 아님), 그때 비로소 C011·C012가 셸 스크립트로 보인 그 그래프가 gilv3.py 산출물로 나온다. 원리를 도구가 강제하는 첫 조각.

## 가설

> **가설**: gilv3.py의 `step`에서 백트래킹(죽은 잎 뒤 새 형제 가지)을 **`git checkout <조상 define의 커밋>` + detached HEAD 커밋**으로 구현하고, C008의 `_assert_forward_only`를 "각 가지 내부에서만 전진 단조"로 정정하면 — ① 죽은 가지와 산 가지가 깃 그래프에서 **실제로 분기**하고(`git log --all --graph`가 선형 아닌 갈라짐을 그림), ② steps.yaml의 backtrack 포인터와 깃 그래프 위상이 **동형**이며(C011 build_branches.sh가 손으로 짠 그 구조를 도구가 자동 생성), ③ trailer 지문 복원(C009·C010)이 여전히 무손상이고, ④ append-only의 핵심 가치(닫힌 커밋 불변·히스토리 안 지워짐)는 **checkout 후에도 보존**된다(죽은 가지 커밋이 dangling으로 남아 '벽의 지도'). 그리하여 **C011의 "백트래킹=checkout"이 원리가 아니라 도구 동작이 된다.**

## 기각 조건

- **M1 기각**: checkout 백트래킹 구현 후에도 깃 그래프가 선형이다(분기 안 생김). 또는 `git log --all --graph`가 build_branches.sh와 다른 위상을 그린다.
- **M2 기각**: steps.yaml backtrack 포인터와 깃 부모 그래프가 동형이 아니다(도구가 만든 트리 ≠ 논리 트리).
- **M3 기각**: checkout 도입이 trailer 복원(C009·C010 rebuild)을 깨뜨린다 — 도구가 만든 저장소에서 rebuild_trailer가 원 트리를 복원 못 함.
- **M4 기각**: append-only의 진짜 가치가 깨진다 — 닫힌 사이클 커밋이 사라지거나(gc로 죽은 가지 소멸), checkout이 이전 스텝 커밋을 변조/삭제한다. 또는 forward-only 정정이 너무 느슨해 진짜 위반(amend·reset으로 히스토리 다시 쓰기)까지 통과시킨다.
- **회귀 기각**: 기존 gilv3 동작(선형 사이클 open→step→close, C010 trailer 각인, view)이 깨진다.

## 정직한 범위

- 이 사이클은 **백트래킹=checkout 하나**에 집중한다(철학 충돌이 여기 있으므로). 잎=태그·lineage=머지 자동화는 이 토대가 서면 다음 사이클로(그리디, C011 리듬).
- gilv3.py를 **정정**한다(C008 forward-only 집행 수정) — 이는 닫힌 사이클(C010)의 *산출물*을 고치는 게 아니라, 최신판을 이 사이클 디렉토리로 **복사 후 진화**시키는 v3-build의 확립된 규율(C003~C010이 매 사이클 그랬다). C010 원본은 불변.
