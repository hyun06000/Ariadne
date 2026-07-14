# 3. 가설 검증

산출물: 룰셋 2종(main·all-tags, GitHub API), .github/workflows/gil-gate.yml, runs/ 4건.

재현: `gh api repos/hyun06000/Ariadne/rulesets` (활성 2종 확인), 게이트는 run4 스크립트(신선 클론 추출).

## 실행 기록 (2026-07-15)

- **T1 (파괴 프로브)**: 세 차례 반복하며 결함을 잡아냈다 — 룰셋 패턴 `refs/tags/cycle/**`·`refs/tags/**`의 `**`가 GitHub에서 세그먼트를 넘지 못해 2레벨 태그(cycle/loom/C001)가 무방비였다. 프로브가 이를 드러냈고(선고정 복구 계획대로 매번 재push 복구), **`~ALL`로 교정** 후 재검증: cycle 2레벨·genesis 2레벨·v1.0.0 전부 삭제 거부 + 생존. main force-push도 거부.
- **T2 (문지기)**: 정상 클론 게이트 통과(rc 0), 유령 parent 주입 클론 게이트 차단(rc 1) — 문지기가 장님이 아님.
- **T3 (정상 경로)**: 이 사이클의 스텝 push·close 태그 생성이 룰셋 아래에서 성공.
