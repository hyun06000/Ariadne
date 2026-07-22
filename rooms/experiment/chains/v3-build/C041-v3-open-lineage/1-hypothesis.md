# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C040**(fsck가 v3 사이클 인식). C039가 노출한 세 경계(번호·계보·fsck) 중
**번호·fsck는 C040이 해소**(v3 사이클 0→1개 인식, 번호중복 R1로 검출). **계보(author·
parent 소실)만 남았다** — C039 M5에서 v3 사이클 커밋 author가 git user일 뿐 `--author`가
안 남고, parent도 steps.yaml에 null. 이게 풀리면 실사이클을 gil v3로 여는 도그푸딩
전환의 마지막 전제가 채워진다(상현님이 기다리는 지점).

## 문제 분할

**계보를 어디 담을지 실측 — trailer가 정답.** 세 후보:
- steps.yaml 루트 노드 필드: `dump`가 `FIELDS`(id·kind·parent·outcome·backtrack·body)만
  써서 임의 필드 유실 + 전 노드에 퍼짐(사이클-간 메타인데 노드 속성됨). 부적합.
- git notes: migrate 층과 동일하나 fsck가 notes를 안 읽어(C040은 steps.yaml만) 별도 로딩.
- **git 커밋 trailer(C010)**: `git_imprint`가 이미 trailer를 남긴다(현재 Step-Id·Kind·
  Parent = 스텝 트리). 실측: v3 open 커밋에 `Step-Id: s1 / Kind: define / Parent: null`.
  여기 **사이클-간 계보용 `Cycle-Author`·`Cycle-Parent` trailer 추가**가 최소·정합.
  steps.yaml 불변, C010 패턴 일관, 복원은 `git log --format=%(trailers)`.

첫 정복 문제: **v3 open이 `--author`·`--parent`를 받아 루트 define 커밋에 Cycle-Author·
Cycle-Parent trailer로 각인.** worktree add는 이미 `--author --parent`를 받으니(C039)
그걸 v3 open에 넘기면 계보가 v3 사이클에 남는다. 커밋 author(워크트리 git config)도
이중 안전.

## 가설

> **가설**: v3 open에 `--author`·`--parent` 옵션을 더해 루트 define 커밋에 `Cycle-Author`·
> `Cycle-Parent` trailer로 각인하고 worktree add가 이를 넘기면, v3 사이클의 사이클-간
> 계보(누가 열었나·부모가 무엇인가)가 git 커밋에 보존되어 `git log --format=%(trailers)`로
> 복원 가능하고, steps.yaml·fsck(C040)·conformance(121/121)는 무회귀한다.

## 기각 조건

1. trailer가 커밋에 안 붙거나 복원이 안 되면 → 계보 각인 실패(기각).
2. `--author --parent` 추가가 기존 v3 open(인자 없는 호출)을 깨거나 conformance가
   121/121 아래로 → 무회귀 실패(기각).
3. worktree add가 계보를 v3 open에 못 넘겨 C039 소실이 그대로면 → 통합 실패(기각).
