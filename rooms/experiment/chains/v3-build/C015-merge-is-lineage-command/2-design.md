# 2. 설계 — close --lineage 를 git merge --no-ff 로 도구화

## 설계 원칙 (계승)

- **원본 불변, 복사 후 진화** (v3-build 규율): C014판 gilv3.py(474줄)를 C015로 복사해 진화. C014 원본은 안 건드림.
- **재구현 0**: 백트래킹=checkout(C014)의 인프라(`_commit_of_sid`·`_assert_append_only`·산 잎 못 `gil/live/`)를 그대로 재사용. lineage 머지는 그 위에 얹는 얇은 조각.
- **한 계약면에 한 등급** (C057): `--lineage`는 close의 opt-in 인자. 없으면 C014 선형 봉인과 완전 동일(회귀 0).

## 무엇을 바꾸나 — 정확히 한 곳

`cmd_close`에 `--lineage <sidA>,<sidB>[,...]` 인자를 더한다. 나머지 명령·헬퍼는 불변.

### 현재 cmd_close (C014) 흐름
1. `cycle_state` 계산 (in_progress면 거부).
2. 산 잎들을 `cycle.yaml`에 봉인.
3. `--git`이면: 각 산 잎을 `gil/live/<sid>` 브랜치로 못박음 → **빈 봉인 커밋**(`git commit --allow-empty`) → `gil/sealed/<cycle>` 못.

### C015 변경 — --lineage가 주어지면 봉인 커밋을 머지 커밋으로
빈 봉인 커밋 대신 **다중부모 머지 커밋**을 친다:

```
close --lineage sA,sB --git:
  1. state 게이트 (불변)
  2. cycle.yaml 봉인 (불변) — lineage 사이클도 산 잎 ≥2 이면 multi_solution 경고
  3. --git 경로:
     a. 각 산 잎 gil/live/<sid> 못박음 (불변, C014)
     b. ⭐ lineage 머지:
        - 지정 sid들을 커밋으로 역인덱스 (_commit_of_sid, C014 재사용)
        - 첫 산 잎으로 checkout (HEAD = parent[0])
        - 나머지 산 잎들을 git merge --no-ff (다중부모 커밋)
          · trailer: Kind=merge, Parent="sA, sB", Merge=lineage
          · --no-ff 강제 (fast-forward/squash 금지 = C012 교훈 2)
        - _assert_append_only (C014) — 머지는 커밋 안 지우므로 통과
     c. gil/sealed/<cycle> 못을 머지 커밋(새 HEAD)에 박음 (불변)
```

### 왜 checkout 후 merge 인가
C014의 백트래킹으로 두 산 갈래는 서로 다른 detached 커밋에 매달려 있고, close 직전 `gil/live/<sid>` 브랜치로 못박힌다. 머지하려면 한 부모 위에 서서 다른 부모를 당겨와야 한다 — C012 build_merge가 `checkout lane-C020` 후 `merge lane-C016` 한 것과 동형. 도구는:
- `_commit_of_sid(dir, sid)`로 각 산 잎 커밋 조회 (steps.yaml에 해시 저장 안 함, C005 유지).
- 첫 sid 커밋으로 `git checkout` → HEAD가 parent[0].
- 나머지 sid 커밋(들)을 `git merge --no-ff -m <subject+trailer>`.

### git merge 호출의 append-only 안전성
`git merge --no-ff`는 새 커밋을 추가할 뿐 기존 커밋을 안 지운다. 따라서 `_assert_append_only`(C014: 이전 커밋 집합 ⊆ 이후 집합)를 통과한다. 이것이 C014 정점 교훈의 직접 응용 — "커밋 불소멸"이 계약이므로 머지(HEAD가 앞으로 감)는 자연히 허용된다. reset/rebase만 거부된다.

### trailer 계약 (C010·C012)
머지 커밋 본문:
```
gilv3 close <cyc>: lineage 머지 [sA, sB] (봉인)

Step-Id: <merge-sid>       # 봉인 머지 노드 id (예: close-merge)
Kind: merge
Parent: sA, sB            # gil parent 리스트 ≅ git 다중부모 (순서: HEAD 먼저)
Merge: lineage
```
C009/C010 rebuild가 `Parent` trailer(또는 git `%P` 다중부모)만으로 lineage DAG를 복원한다.

## 측정 설계 (build_case.sh + measure.py)

C012 build_merge.sh의 표적(두 갈래 → C036 축약)을 **gilv3 명령만으로** 재현. 절차:
1. `gilv3 open` 루트 define + 갈래 A 스텝들 → analyze/backtrack (죽은 잎, checkout 백트래킹).
   — 실제로는 산 잎 2개가 필요하므로: 갈래 A를 success로 산 잎, 백트래킹으로 형제 갈래 B도 success 산 잎.
2. 두 산 잎(multi_solution 상태) → `gilv3 close --lineage sA,sB --git`.
3. measure.py 5측정:
   - **M1 다중부모**: close 머지 커밋 `%P`가 두 산 잎 커밋 (부모 2).
   - **M2 trailer 복원**: 머지 커밋 trailer가 Kind=merge·Parent="sA, sB"·Merge=lineage. C010 rebuild가 부모 지문으로 lineage 읽음.
   - **M3 append-only**: 머지 후 두 갈래 스텝 커밋 전부 `rev-list --all`에 생존. `_assert_append_only` 통과(내부 집행).
   - **M4 squash 음성대조**: 같은 두 갈래를 `--squash`로 머지하면 부모 1개 → lineage 소실. 도구의 --no-ff가 이를 막음을 대조.
   - **M5 회귀**: `--lineage` 없는 close(단일 산 잎)가 C014와 동형 — 빈 봉인 커밋·gil/live·gil/sealed 불변.

## 정직한 경계 (설계 시점)
- 2부모 머지. 3+ 부모는 `--lineage` 콤마 리스트로 자연 확장되나 측정은 2부모만.
- multi_solution 상태(산 잎 ≥2)에서만 lineage 의미 있음 — 산 잎 1개에 --lineage는 무의미(측정 M5가 이 경로 회귀 확인).
- 머지 충돌: 독립 파일 갈래만(자동 병합). 충돌 해소 각인은 이월(C012 제안).
