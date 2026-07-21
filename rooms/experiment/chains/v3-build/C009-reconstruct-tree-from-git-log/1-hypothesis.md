# 1. 가설 수립

부모: v3-build/C008-backtrack-is-a-new-commit (supported)

## 이전 사이클의 교훈

- **C008 (백트래킹=새 커밋)**: 깃=append-only 전진기록, gil=백트래킹·분기 지능. steps.yaml이 **진실원**, 깃은 그 결과를 전진 커밋으로 각인. 되돌아감 논리(목적지 조상)는 깃 커밋 부모에 0% 반영되고 steps.yaml `parent`/`backtrack` 포인터에만 산다.
- C008이 **커밋 메시지에 서술을 이미 각인**해뒀다: `s4 analyze/backtrack (backtrack to s1)`, `s5 hypothesis (new branch from s1 after backtrack)`. 이 서술이 파싱 가능하다는 것이 C008의 관찰이자 이 사이클의 재료다.
- **C003 (커서 무저장)**: 읽기(C002 derive_action)와 쓰기(C003 growing_tip+가드)가 **같은 상태기계**를 공유한다. 성장 팁은 데이터에 저장 안 하고 트리에서 계산. 순환 규칙(define→hypothesis→verify→analyze)이 명령을 강제한다.

## 문제 분할

"깃 로그로 트리 재구성"을 가장 작은 단위로 분할하면:

1. **[이 사이클] 커밋 로그 → 스텝 트리 복원**: `git log`(커밋 순서 + 메시지 서술)만으로 steps.yaml 없이 스텝 트리(노드·parent·backtrack·outcome)를 복원한다. 복원한 트리가 원본 steps.yaml과 위상 동형이면, 깃이 진짜 단일 진실원이 될 수 있음(steps.yaml=파생 캐시).
2. (이후) body 파일까지 깃에서 복원 · 복원기를 gilv3 명령으로(`gilv3 rebuild <repo>`) · v3 fsck(깃↔steps.yaml 정합, 복원이 그 검증의 엔진).

**첫 번째를 고른 이유**: 상현님이 지목했고, C008의 **직접 역방향**이다. C008은 "steps.yaml → 깃"(각인)을 실증했다. C009는 "깃 → steps.yaml"(복원)을 검증한다. 이 두 방향이 무손실 왕복이면 **깃과 steps.yaml 중 어느 하나가 잉여**임이 드러난다 — 데이터 모델의 근본 위상(무엇이 진실원인가)을 가르는 질문이다.

## 핵심 관찰 (재료 점검)

C008 git-log.txt를 직접 봤다. 커밋 메시지가 담는 정보:
- `gilv3 open case: s1 define` → 루트 (parent=null).
- `gilv3 step: sN <kind>` → open_branch 스텝. **parent 서술 없음** (s2·s3·s6·s9 등).
- `gilv3 step: sN analyze/<outcome> (backtrack to sM)` → 백트래킹 잎, 목적지 sM 명시.
- `gilv3 step: sN hypothesis (new branch from sM after backtrack)` → 새 형제 가지, parent=sM 명시.

**parent가 서술에 항상 없다** — 그러나 **C003 상태기계로 파생 가능**하다: open_branch 스텝의 parent는 직전 커밋(시간순 팁), dead_leaf(backtrack) 뒤 새 가지의 parent만 서술의 `from sM`으로. 즉 **커밋 순서(시간축) + 백트래킹 마커 + 순환 규칙 = 트리 복원**. 커밋 부모 링크는 안 쓴다(선형이라 정보 0) — 오직 시간순과 메시지 서술.

## 가설

> **가설**: C008이 각인한 깃 저장소의 `git log`(커밋 시간순 + 커밋 메시지 서술)만으로 — steps.yaml 파일을 읽지 않고 — 스텝 트리를 복원하는 파서를 짜면, 복원된 트리가 원본 steps.yaml과 **위상 동형**(같은 노드 집합·같은 parent 엣지·같은 backtrack 엣지·같은 outcome)이 된다. 즉 커밋 순서 + 메시지 서술 + C003 순환 상태기계가 트리를 무손실 복원하며, **깃이 스텝 트리의 단일 진실원이 될 수 있다**(steps.yaml은 파생 캐시).

## 기각 조건

- **K1**: 복원된 트리의 parent 엣지 집합이 원본 steps.yaml과 하나라도 다르다 (트리 구조 손실).
- **K2**: 복원된 backtrack 엣지(되돌아감 목적지) 또는 outcome이 원본과 다르다 (되돌아감 정보 손실).
- **K3**: 복원에 steps.yaml 파일 내용이나 커밋 diff(파일 스냅샷)를 읽어야 한다 — `git log`(순서+메시지)만으로 부족 (깃 로그 단독으로 불충분).
- **K4**: 커밋 순서 + 메시지가 트리를 **유일하게** 결정하지 못한다 — 같은 로그가 두 개 이상의 다른 트리로 해석될 수 있는 모호성이 존재한다 (복원 비결정).
