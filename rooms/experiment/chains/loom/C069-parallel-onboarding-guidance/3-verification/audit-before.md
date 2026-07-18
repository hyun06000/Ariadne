# 감사(수정 전): 병렬 기능이 온보딩에 안내되는가

신규 에이전트가 실제로 읽는 경로의 worktree/병렬 언급 건수 (수정 전):

| 문서 (신규 에이전트가 읽음) | worktree/병렬 | 문제 |
|---|---|---|
| README.ai.md (자율 온보딩) | **0** | Step A~D 완전 순차. 병렬 섹션 없음 |
| QUICKSTART.md | **0** | 설치·첫 사이클만 |
| CLAUDE.md §3 | **0** | 순차 전용 |
| rooms/experiment/README.md | **0** | — |
| SPEC 명령 표(§5) | **`gil worktree` 행 없음** | §6 산문만 "격리 브랜치", 명령명 미언급 |
| SPEC §6 소환 규약 | 산문 4건 | 브랜치/예약 규율은 있으나 `gil worktree add/land` 명령 미지목 |

측정 명령:
```bash
for f in CLAUDE.md README.ai.md README.ko.md rooms/deployment/ariadne-spec/QUICKSTART.md \
         rooms/deployment/ariadne-spec/SPEC.md rooms/experiment/README.md; do
  echo "$(grep -ciE 'worktree|병렬|parallel' "$f")  $f"
done
grep -n 'gil worktree' rooms/deployment/ariadne-spec/SPEC.md   # → (없음)
```

결론: `gil help worktree`로 **탐침**은 되나, "언제·왜·어떻게 병렬로 일하는가"를 **가르치는 안내가 온보딩 경로에 없음** → README.ai.md만 따라간 Claude는 순차로만 일한다(관찰된 현상).

부수 발견: 소비자 `2ndRound/CLAUDE.md`가 "loom/C020 build (worktree 없음)"이라 낡음 — 실제 v2.24 바이너리를 축소 서술. (별도 저장소라 이 사이클 범위 밖, 후속 제안.)
