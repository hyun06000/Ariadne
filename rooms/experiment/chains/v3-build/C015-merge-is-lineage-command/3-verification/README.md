# 3. 검증 — lineage=머지=git merge --no-ff 가 gilv3 명령 동작이 되다

C012가 순수 깃 셸(build_merge.sh)로 손으로 짠 다중부모 머지 노드(loom/C036 축약)를, 이번엔 **gilv3.py 명령(open/step/close --lineage)만으로** 재현한다. 생 `git merge` 호출 0 — 도구가 안에서 checkout(백트래킹)·merge(lineage)를 한다. C014가 분기(백트래킹=checkout)를 도구화했듯 C015는 합류(lineage=머지)를 도구화해 **깃 ≅ gil의 도구 강제를 양방향으로 닫는다.**

## 재현

```bash
bash build_case.sh <scratch>     # gilv3 명령만으로 두 산 잎 → lineage 머지 재현
python3 measure.py <scratch>     # 5측정 감사
```

두 스크립트에 같은 scratch 경로를 준다. gilv3.py C015판은 C014판을 복사 후 진화(v3-build 규율, C014 원본 불변).

## 산출물

- `gilv3.py` — C015판. C014판 대비 진화 3곳:
  - **`git_merge_lineage`** 신규 — `close --lineage sA,sB`가 산 잎들을 부모로 `git merge --no-ff` 다중부모 커밋 각인. trailer(Kind=merge·Parent·Merge=lineage). append-only 집행.
  - **`cmd_step`의 live_leaf 백트래킹 허용** — 산 잎 뒤에도 `--to <조상 define>`로 새 형제 가지(multi_solution 도달 가능성). C014는 live_leaf 뒤 step을 전면 거부했다.
  - **`cmd_close`에 `--lineage` 인자** — 있으면 빈 봉인 커밋 대신 머지 커밋. 없으면 C014 선형 봉인과 동일(회귀 0).
- `build_case.sh` — gilv3 명령만으로 두 산 잎(C012 표적 축약) 재현.
- `measure.py` — 5측정 감사기.
- `build-out.txt` / `measure-out.txt` — 출력(ALL PASS 5/5).
- `git-graph.txt` — 도구가 만든 `git log --all --graph`(두 산 갈래가 s1에서 갈라져 머지로 합류하는 실물).

## ⭐ 핵심 발견 — steps.yaml 충돌의 정답은 gil이 안다

C012는 두 갈래가 **독립 코드 파일**(ledger.py vs web.py)만 고쳐 자동 병합됐다. 그러나 gilv3의 `steps.yaml`은 **논리 트리 전체를 담는 단일 파일**이라, 두 산 갈래가 각자 자기 트리를 써 구조적으로 충돌한다(순수 깃엔 없던 문제). 이것이 lineage 도구화의 진짜 난점이었다.

**해소 — 이월이 아니라 도구가 아는 자동 해소.** 그 충돌의 정답은 gil이 이미 안다: 머지 시점에 메모리에 든 **완전한 논리 트리**(두 갈래 합집합 s1~s7)다. `git merge --no-ff --no-commit`으로 당긴 뒤, gil이 `dump(nodes)`로 steps.yaml을 완전 트리로 해소하고 머지 커밋을 완성한다. body 파일(`steps/<sid>.md`)은 갈래별 독립이라 이미 자동 병합. **C012 교훈("충돌 해소 자체가 지식 통합의 판단")의 실현** — steps.yaml 충돌의 판단을 도구가 담는다. steps.yaml 밖(같은 코드 영역)의 미해소 충돌만 정직히 멈춰 이월한다.

## ⭐ 선행 발견 — multi_solution은 live_leaf 백트래킹 없이 도달 불가

두 산 잎을 만들려면 첫 산 잎 뒤에 새 산 갈래를 열어야 하는데, C014는 `live_leaf` 상태 step을 전면 거부했다("close만 가능"). 그러면 산 잎이 절대 2개가 못 되고 → `cycle_state`의 `multi_solution` 분기가 **도달 불가능한 죽은 코드** → lineage 머지가 만들 두 갈래를 도구로 못 만든다. C014 정정(append-only)이 백트래킹의 선행조건이었듯, live_leaf 백트래킹이 lineage의 선행조건이었다. 진짜 계약: 산 잎 뒤 '선형 전진'은 금지(정답에 닿음)하되 '새 형제 가지로 되돌아가기'는 chain.md "다른 정답도? → 되돌아가 새 갈래"의 실현이다.

## 5측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 다중부모** | 도구가 만든 close 머지 커밋의 깃 부모가 정확히 두 산 잎(s4·s7). 첫 부모=s4(HEAD). gil [s4,s7] ≅ git 다중부모 | PASS |
| **M2 trailer 복원** | 머지 커밋 trailer Kind=merge·Parent="s4, s7"·Merge=lineage. 부모 지문(`%P`)만으로 lineage DAG 복원(cycle.yaml 안 봄, C009 합류판) | PASS |
| **M3 append-only** | 머지 후 두 갈래 커밋 전부 `rev-list --all` 생존(총 8커밋). 머지는 커밋 안 지움 → `_assert_append_only` 통과(C014 계약) | PASS |
| **M4 squash 음성대조** | 같은 두 산 잎을 `--squash`로 합치면 부모 1개 → lineage 소실. 도구의 `--no-ff`가 이를 막음(C012 교훈 2를 도구가 강제) | PASS |
| **M5 회귀** | `--lineage` 없는 close(단일 산 잎)가 C014와 동형 — 빈 봉인 커밋(부모 1개)·gil/live·gil/sealed 못 불변. 머지 경로가 선형 경로 안 건드림 | PASS |

## 결론

**ALL PASS → supported.** lineage=`git merge --no-ff` 다중부모 커밋이 원리(C012)가 아니라 도구 동작(`gilv3 close --lineage`)이 됐다. 도구가 명령만으로 두 산 갈래를 분기시키고 다중부모로 합류하며, trailer가 lineage를 담고, 부모 지문만으로 DAG가 복원되고, squash가 lineage를 잃음을 도구가 `--no-ff`로 막는다. 회귀 0. **깃 ≅ gil의 도구 강제가 분기(C014)·합류(C015) 양방향으로 닫혔다.**
