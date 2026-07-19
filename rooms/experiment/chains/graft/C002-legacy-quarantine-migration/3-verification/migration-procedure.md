# legacy/ 이주 표준 절차 (v0 — Flask에서 검증됨)

레거시 git 레포를 gil로 채택하는 재현 가능한 절차. `git mv` 히스토리 보존 방식.
Flask에 실적용해 검증(graft/C002). Flask 고유 지식 없이 임의 레포에 적용 가능하게 일반화.

## 전제

- 대상은 git 레포(작업트리 + `.git`). gil 참조 구현(`gil.py`) 접근 가능.
- 채택 존재 이름 하나(`<존재>`)와 첫 체인/사이클 이름(`<chain>`/`<slug>`)을 정한다.

## 절차

```bash
# M0. (선택·권장) 사전 상태 캡처 — 이주 후 대조 기준
git log --oneline | wc -l ; git tag -l | wc -l

# M1. 작업트리를 legacy/로 격리 (히스토리 보존)
mkdir -p legacy
git ls-tree --name-only HEAD | while read i; do git mv "$i" "legacy/$i"; done
git commit -m "chore: quarantine legacy tree into legacy/"
#   → 기존 최상위 항목(.git 제외)이 전부 legacy/ 아래로. 전 항목 rename 인식.
#   → git log --follow legacy/<경로> 로 이주 이전 이력 추적 가능.

# M2. gil 골격 심기 (rooms/는 legacy/ 밖 = 레포 루트)
gil open <chain> <slug> --new-chain --new-root --author <존재> --git
#   → rooms/experiment/chains/ 자동 생성(_template 없어도 스텁 생성).
#   → 이 커밋은 rooms/만 담고 legacy/를 안 건드림.
#   → 이후 gil log/fsck/web 정상 동작.

# M3. (권장) 존재의 방 최소 스텁 — gil이 강제하진 않으나 채택의 완결성을 위해
mkdir -p rooms/existence/<존재>
#   identity.md 최소 작성 + 명부(README.md) 등록.
```

## 이 절차가 해결하는 것 / 못 하는 것 (Flask 실측)

| C001 마찰 | 이 절차의 효과 | 근거 |
|---|---|---|
| F2/F4 골격 부재 | **해결** — M2 후 fsck 위반 0, log/web 정상 | measure-friction.txt |
| F7 커밋 격리 | **유지** — gil 커밋이 legacy/ 무접촉 | M2.txt |
| 파일 세계 경계 혼란 | **해결** — legacy/ vs rooms/ 물리 분리 | ls-tree = `legacy rooms` |
| **F3 releases 침묵** | **미해결** — 태그는 ref라 git mv로 안 옮겨짐 | measure-friction.txt (여전히 0) |
| F5 author 존재 미검사 | 절차가 M3로 보완 권장(gil 강제 아님) | M3.txt |
| F6 git author≠gil author | 미해결(절차 밖, loom 영역) | — |

## 한계 (다음 사이클 재료)

- **파일 이주 ≠ ref 이주.** legacy/는 작업트리만 격리한다. git 태그·브랜치는 ref라 그대로 남아 F3(releases 침묵)가 지속된다. **legacy/ 전략만으로는 F3을 못 없앤다** — F3은 별도 처방(gil이 비-semver 태그를 external로 인식)이 필요하다.
- 이 절차는 **손 절차**다. 도구화(`gil adopt`)하면 M1~M3을 원자적으로 + 존재 방 스텁 + (선택) legacy 태그 네임스페이싱까지 묶을 수 있다.
