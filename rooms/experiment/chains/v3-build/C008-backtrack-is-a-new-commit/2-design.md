# 2. 실험 설계

가설(1-hypothesis): 백트래킹 스텝을 `--git`으로 각인하면 깃엔 reset/checkout/revert 없이 새 전진 커밋만 쌓이고, 죽은 가지는 히스토리에 보존되며(벽의 지도), 되돌아감 논리는 steps.yaml 포인터에만 담긴다 = **백트래킹=새 커밋**.

## 설계 개요

C006의 gilv3 v0.3을 **닫힌 사이클 불변 규율**에 따라 복사 후 확장(gilv3 v0.4)한다. 이 사이클의 각인 경로가 **전진만** 함을 코드·정적 감사·런타임 실측 세 겹으로 검증한다. 실사례는 백트래킹이 실제로 있는 트리 — C002 이래 쓴 **C012→C013→C014 재현**(s7의 backtrack→s1, s4의 backtrack→s1, 두 죽은 잎)을 gilv3 명령으로 처음부터 지어 각인한다.

이 사이클의 핵심은 새 기능이 아니라 **성질의 각인**이다. `git_imprint`는 이미 add+commit만 하므로(잠재), 이 사이클은 ① 그 잠재를 명시적 계약으로 승격(코드 주석·거부 가드 추가로 append-only를 문서화)하고 ② 세 겹 측정으로 실증한다.

## 절차

1. **gilv3 v0.4 준비**: C006 gilv3.py를 이 사이클 `3-verification/gilv3.py`로 복사한다. 확장:
   - `git_imprint`에 **append-only 계약 주석**을 명문화하고, 방어적 가드로 `_assert_forward_only(repo, before_head)`를 추가한다 — 각 각인 후 `HEAD`가 이전 커밋의 **자손**임을(부모로 연결됨) 확인해, 만약 어떤 경로가 HEAD를 뒤로 옮기면 즉시 거부. (전진 단조성을 코드가 스스로 집행.)
   - 백트래킹 각인 커밋 메시지에 되돌아감 목적지를 드러낸다: `gilv3 step: s8 hypothesis parent=s1 (backtrack from s7)` — 깃 로그가 "어느 조상으로 되돌아가 새 가지를 열었는지"를 사람 눈에 보이게(단, 이는 서술일 뿐 진실원은 steps.yaml).
2. **실사례 트리 각인** (build.sh): 임시 깃 저장소(스크래치패드, 메인 레포 밖 — C005 규율)에서 `gilv3 open/step … --git`으로 C012→C014 10노드 트리를 처음부터 짓는다. s4·s7 두 죽은 잎, s7→s1·s4→s1 백트래킹, s10 산 잎 → close.
3. **측정** (measure.py, 순수 stdlib):
   - **M1 (append-only 코드 감사)**: gilv3.py 소스에서 각인 경로가 호출하는 git 하위명령을 정적 수집. `add`·`commit`만 있고 `reset`·`checkout`·`revert`·`amend`·`push --force`·`rebase`가 **0회**여야 K1 반증.
   - **M2 (전진 단조성 실측)**: 각인 완료 후 `git reflog`를 파싱해 HEAD 이동이 **전부 전진**(각 이동의 이전 HEAD가 새 HEAD의 조상)임을 확인. 뒤로 간 이동 0 → K4 반증. 커밋 수 == 스텝 수(open 1 + step 9 + close 1 = 11), `git log` 순서가 s1→s10→봉인 시간순 → K2 반증.
   - **M3 (벽의 지도 보존)**: 죽은 가지 스텝(s4·s7과 그 조상 가지)의 커밋이 `git log`에 전부 살아있음을 확인 — 백트래킹 후에도 죽은 잎 커밋이 사라지지 않음(K2의 후반). 죽은 잎 body 파일(steps/s4.md·s7.md)이 워킹트리에 그대로.
   - **M4 (역할 분리)**: 되돌아감 목적지(s7.backtrack=s1, s4.backtrack=s1)가 **steps.yaml에만** 존재하고 깃 구조(브랜치·머지커밋·부모 다중링크)엔 없음을 확인 — `git log --graph`가 **한 줄 선형**(분기 0)인데도 steps.yaml은 트리(형제 3가지). 깃=선형 전진, gil=트리 지능 → K3 반증.

## 준비물

- gilv3 v0.4 (C006 v0.3 복사 확장), Python 3 stdlib만.
- C004 steptree.py (view용 import, 기존 경로).
- 임시 깃 저장소: 스크래치패드 `/private/tmp/claude-501/.../scratchpad/c008-imprint/` (메인 레포 밖, 중첩 .git 방지 — C005 규율).
- 실사례 데이터: C002/C003이 쓴 C012→C014 10노드 트리(build.sh가 gilv3 명령으로 재생성).

## 측정 방법

| # | 측정 | 기각 조건 | PASS 기준 |
|---|---|---|---|
| M1 | 각인 경로 git 하위명령 정적 감사 | K1 | reset/checkout/revert/amend/force/rebase = 0 |
| M2 | reflog 전진 단조성 + 커밋수·순서 | K2·K4 | 뒤로 간 HEAD 0, 커밋 11개 시간순 |
| M3 | 죽은 가지 커밋 보존 | K2 | 죽은 잎 커밋·body 전부 생존 |
| M4 | 되돌아감 논리 위치 (steps.yaml vs 깃) | K3 | 깃 그래프 선형(분기0), steps.yaml 트리 |

네 측정 전부 PASS면 supported. 하나라도 해당 K 발동이면 rejected/partial.

## 사용자 컨펌

- 갈래(백트래킹=새 커밋)는 상현님이 AskUserQuestion으로 이미 선택함. 세부 실험 설계는 v2 방법론의 표준 절차(실사례 재현+3겹 측정)이라 추가 컨펌 불필요.

- [x] 컨펌 받음 (일자: 2026-07-21, 갈래 선택 = 백트래킹=새 커밋)
