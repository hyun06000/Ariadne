# 2. 실험 설계

1. **참조 cmd_step/cmd_close** — 커밋 조건을 `args.git` → `깃 저장소이고 not args.no_commit`으로. `--git`은 하위호환(있어도 무해). `--no-commit` 신설. close의 태그·verdict·push는 그대로.
2. **Go 대응** — 동일. `--no-commit` 플래그.
3. **README.ai.md·§2.1** — "step/close는 깃 저장소에서 자동 커밋한다. 안 붙여도 각인된다"로 갱신.
4. **T1**: 깃 저장소에서 `step`(--git 없이) → 커밋 생김. `close`(--git 없이) → 커밋+태그.
5. **T2**: `--no-commit` → 커밋 안 함. 깃 아닌 저장소 → 조용히 스킵(상태 전이만).
6. **T3**: 기존 --git·--push·--verdict 동작 유지.
7. **T4 Go 대조** + **T5 conformance 26/26**.

## 사용자 컨펌

- [x] 컨펌 받음 (2026-07-15, 박상현: 기본 커밋 선택)
