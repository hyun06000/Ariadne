# 2. 설계 — 잎 못을 태그로 정식화

## 설계 원칙

- **원본 불변, 복사 후 진화**: C015판(567줄)을 C016으로 복사해 진화.
- **재구현 0**: C011·C012 build 스크립트가 쓴 태그 규칙(`gil/leaf/<short>`·`cycle/<name>/solved`)을 도구가 그대로 낸다.
- **한 헬퍼로 통일**: 브랜치 못이 4곳에 흩어져 있으니, 태그 못을 헬퍼 함수 하나로 모아 일관·중복 제거.

## 무엇을 바꾸나 — 브랜치 못 4곳 → 태그 못

현재 C015 도구의 브랜치 못:
| 위치 | 현재 (브랜치) | 목적 |
|---|---|---|
| cmd_step 백트래킹 (dead_leaf) | `git branch gil/dead/<sid>` | 죽은 잎 dangling 방지 |
| cmd_step 백트래킹 (live_leaf) | `git branch gil/live/<sid>` | 산 잎 두고 떠날 때 방지 |
| cmd_close (각 산 잎) | `git branch gil/live/<sid>` | 산 잎 dangling 방지 |
| cmd_close (종결) | `git branch gil/sealed/<cyc>` | close 커밋 dangling 방지 |

정식화 후 (태그):
| 위치 | 정식 (태그) | 근거 |
|---|---|---|
| cmd_step 백트래킹 (dead·live 공통) | `git tag gil/leaf/<short-hash>` | C011: 모든 잎=해시 태그 |
| cmd_close (각 산 잎) | `git tag gil/leaf/<short-hash>` | 동일 규칙 |
| cmd_close (종결) | `git tag cycle/<cyc>/solved` | C011: 사이클 종결 태그 |

### 헬퍼 신규 — `tie_leaf` / `tie_sealed`

```python
def tie_leaf(dir_, commit):
    """잎 커밋을 gil/leaf/<short-hash> 태그로 못박는다 (C011: 잎=불변 시점=태그).
    해시 이름 — 논리 id(sid)는 커밋 trailer(Step-Id)가 담으므로 못 이름엔 불필요.
    이미 있으면 무해(idempotent) — 같은 커밋에 같은 이름이라 재-못박기 안전."""
    short = git rev-parse --short <commit>
    tag = "gil/leaf/%s" % short
    # -f 없이: 이미 있으면 조용히 통과 (잎은 불변이라 재못박기=동일)
    git tag <tag> <commit>   (실패=이미존재는 무시)

def tie_sealed(dir_, cyc, commit):
    """사이클 종결을 cycle/<name>/solved 태그로 못박는다 (C011)."""
    git tag "cycle/%s/solved" % cyc <commit>   (실패=이미존재는 무시)
```

### 왜 태그가 브랜치보다 정확한가 (H1d 불변성)
브랜치는 그 위에 커밋하면 **따라 움직인다**. 잎은 불변 시점(더 이상 자라지 않는 죽은/산 가지 끝)이므로, 못이 움직이면 안 된다. 태그는 커밋에 고정 — 후속 커밋이 태그를 안 옮긴다. C015 백트래킹에서 `git branch -f`로 강제 이동시킨 것 자체가 브랜치의 가변성 증거였다. 태그는 `-f` 불필요(불변).

### dangling 방지 등가성 (H1c)
태그도 ref다 — `git log --all`·`rev-list --all`이 태그가 가리키는 커밋을 도달가능으로 본다. 따라서 브랜치 못과 dangling 방지가 **등가**이되, 태그가 더 정확(불변·push 생존). C011 M3가 "어떤 ref든 못이면 가지가 산다"를 실측했고, 태그가 그 ref다.

### idempotent 처리
같은 잎을 두 번 못박을 수 있다(백트래킹에서 떠날 때 + close에서 다시). 브랜치는 `-f`로 덮었지만, 태그는 같은 커밋·같은 이름이면 이미 존재 → 조용히 통과(무해). 다른 커밋에 같은 이름은 불가하나, `gil/leaf/<short-hash>`는 해시가 이름이라 충돌 불가.

## 측정 설계 (build_case + measure)

C015 build_case(두 산 잎 → lineage 머지)를 태그판으로 재실행 + C014 백트래킹 케이스도.
- M1 잎=태그: 모든 잎 커밋이 `gil/leaf/<short>` 태그, `git branch --list gil/*` 0.
- M2 종결=태그: `cycle/<cyc>/solved` 태그 존재.
- M3 dangling 방지: 모든 잎·머지·close 커밋 `rev-list --all` 생존.
- M4 불변성: 태그가 잎 커밋 해시에 정확히 고정(git rev-parse <tag> == 잎 커밋).
- M5 회귀: C015 lineage 5측정 + C014 백트래킹이 태그판에서도 통과(다중부모·trailer·append-only 불변).

## 정직한 경계
- 잎 이름=해시(C011). 논리 id 매핑은 trailer가 담음.
- 태그 삭제/이동 안 다룸(불변). gil v2 태그 삭제 금지 규율 일관.
- 뷰어 재배선 밖(Sheen 축).
