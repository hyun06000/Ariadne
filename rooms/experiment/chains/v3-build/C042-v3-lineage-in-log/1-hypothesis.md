# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C041**(v3 open 계보 trailer). C039 세 경계(번호·계보·fsck)가 전부 해소되고,
gil v3 실사이클의 세 전제(격리·원장인식·계보)가 완성됐다. C041 정직한 경계: 계보는
trailer에 "각인"이지 **"표현"은 이월** — log/graph가 v3 계보를 그래프 노드로 아직
안 그린다.

## 문제 분할

**실측 — log가 v3 사이클을 세지만 계보를 (root)로 그린다.** v3 사이클 둘(C001-root,
C002-child --parent C001-root)을 만들고 `gil log` → "사이클 2개"로 세지만 계보는
`C001-root ← (root)` · `C002-child ← (root)` — **child의 부모가 안 그려진다**. 원인:
C040의 `load_chain_records` v3 분기가 `parents=[]`(빈 값)로 넣음. 계보는 커밋 trailer에
있는데 record엔 없다.

**실측 — trailer는 git으로 깔끔히 읽힌다.** `git log --format='%(trailers:key=Cycle-Parent)'
-- <cyc_dir>/steps.yaml` → 루트 define 커밋의 `Cycle-Parent: C001-root`·`Cycle-Author:
clew`. 루트 커밋 하나에 계보가 산다.

첫 정복 문제: **load_chain_records의 v3 분기가 계보 trailer를 읽어 record의 parents·
author를 채운다.** 이러면 build_graph가 v3 계보를 그리고 log 그래프에 부모가 나타난다.
도그푸딩 전환의 "눈" — 관전자가 v3 사이클 계보를 본다.

## 가설

> **가설**: load_chain_records의 v3 분기가 그 사이클 커밋의 Cycle-Parent·Cycle-Author
> trailer를 읽어 record의 parents·author를 채우면, gil log가 v3 사이클을 (root)가 아니라
> 실제 부모로 연결해 그리고(C002-child ← C001-root), v2 사이클 인식·fsck(C040)·
> conformance(121/121)는 무회귀한다.

## 기각 조건

1. trailer를 읽어도 log 그래프가 여전히 (root)로 그리면 → record 채움이 build_graph에
   안 닿음(기각).
2. git 호출이 비-git 저장소나 실저장소에서 실패·오염하면 → 로딩 안정성 실패(기각).
3. trailer 읽기가 v2 인식·fsck·conformance를 깨면 → 무회귀 실패(기각).
