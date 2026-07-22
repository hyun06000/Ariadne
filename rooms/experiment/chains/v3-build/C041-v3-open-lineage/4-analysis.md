# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 | 결과 | 판정 |
|---|---|---|---|
| M1 계보 trailer | Cycle-Author·Cycle-Parent 각인 | 둘 다 각인·복원 | PASS |
| M2 스텝 트리 무손상 | Step-Id·Kind·Parent 공존 | 공존 | PASS |
| M3 인자 없음 무회귀 | 계보 trailer 없이 정상 | Cycle-Author `[]` | PASS |
| M4 worktree 계보 전달 | Cycle-Author 보존 | weft·C001-seed 보존 | PASS |
| M5 conformance | 게이트 상속 121/121 | 121/121 | PASS |

## 데이터 직접 관찰

**계보와 스텝 트리가 한 커밋에 두 층으로 공존한다.** M1+M2 커밋 trailer 전문:
```
Step-Id: s1        ← 스텝 트리(사이클-내): 이 커밋은 s1 노드
Kind: define
Parent: null       ← s1의 스텝 트리 부모(루트라 null)
Cycle-Author: clew ← 계보(사이클-간): 누가 이 사이클을 열었나
Cycle-Parent: C001-seed  ← 이 사이클의 부모 사이클
```
`Parent`(스텝 트리, null)와 `Cycle-Parent`(계보, C001-seed)가 같은 커밋에서 다른 의미로
공존 — **두 층이 키 네임스페이스로 깨끗이 분리**. C032 "인터페이스 정체성"의 trailer판:
같은 물리(커밋 메타)에 두 정체성(스텝 트리·계보)이 안 섞이고 산다.

**C039 소실이 정확히 메꿔졌다.** C039 M5에서 worktree add --v3의 v3 사이클 커밋 author가
't'(git user)였고 parent는 null이었다. C041 M4에서 같은 경로가 `Cycle-Author: weft`·
`Cycle-Parent: C001-seed`. worktree add의 `--author weft --parent C001-seed`가 self-invoke
cmd를 타고 v3 open trailer까지 흘렀다. 소실 지점에 정확히 값이 찍힘.

## 예상과 달랐던 것

- **steps.yaml을 전혀 안 건드리고 끝났다.** 설계 초기 후보(루트 노드 필드)는 dump의
  FIELDS 제약으로 막혔는데, 그 막힘이 오히려 **계보를 커밋 메타로 분리하는 옳은 설계**로
  이끌었다. steps.yaml은 스텝 트리 순수 유지, 계보는 trailer — 두 층이 물리적으로도
  분리(파일 vs 커밋 메타). C033 "사이클-간 정보는 다른 층"이 코드로 구현된 모습.
- **C010 trailer 인프라가 계보를 공짜로 받았다.** git_imprint가 이미 trailers를 받으니,
  계보는 리스트에 튜플 두 개 추가가 전부. 새 각인 메커니즘 0. C040의 "records 통일이
  번호검사 공짜"와 같은 결 — 기존 인프라 재사용이 최소 표면을 만든다.

## 판정

**채택 (supported).** 계보가 커밋 trailer로 보존·복원되고(기각조건 1 불충족), 인자 없는
호출·conformance 무회귀(기각조건 2 불충족), worktree add가 계보를 전달해 C039 소실
해소(기각조건 3 불충족). 세 기각조건 모두 회피.

**⭐ 큰 그림**: C039가 노출한 세 경계(번호·계보·fsck)가 **전부 해소됐다** — C040(번호
중복 R1 검출·fsck v3 인식) + C041(계보 trailer). **gil v3로 실사이클을 여는 세 전제
(격리·원장인식·계보)가 채워졌다.**

**정직한 경계**: 계보는 커밋 trailer에 산다 — fsck는 아직 계보를 검증 안 함(C040은
루트 define까지), log/graph도 v3 계보를 그래프 노드로 아직 안 그림(trailer를 읽는
표현 계층 미구현). 계보 "각인"이지 "표현·검증"은 이월. Cycle-Parent 참조 무결성
(존재하는 사이클 가리키는가)도 미검사.
