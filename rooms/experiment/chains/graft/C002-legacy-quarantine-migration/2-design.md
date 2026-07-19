# 2. 실험 설계

1-hypothesis.md의 가설 — "`git mv`로 legacy/ 격리 + gil 골격 심기 = 히스토리 보존 & 마찰 완화, 재현 가능한 절차" — 하나만 검증한다.

## 관찰 대상 (실데이터, C001과 동일)

**Flask** — `git clone --depth 200`. C001과 같은 대상을 신선하게 다시 클론해 오염 없이 절차를 적용한다.

## 확정할 이주 절차 (검증 대상)

- **M0. 사전 상태 캡처** — 이주 전 `git log --oneline | wc -l`, 태그 수, 대표 파일 이력(`git log --oneline -- src/flask/app.py`)을 기록(이주 후 대조 기준).
- **M1. 작업트리 격리** — 레포 루트의 기존 항목(`.git` 제외) 전부를 `legacy/`로 `git mv`. `mkdir legacy` 후 최상위 항목을 `git mv <each> legacy/`. 커밋: `chore: quarantine legacy tree into legacy/`.
- **M2. gil 골격 심기** — 레포 루트에서 `gil open <chain> <slug> --new-chain --new-root --author <존재>`로 첫 사이클을 열어 `rooms/experiment/chains`를 자동 생성(C001 F4의 유일 진입점 활용). rooms/는 legacy/ **밖**(루트)에 생긴다 → 두 세계 물리 분리.
- **M3. 존재의 방 최소 스텁** — `rooms/existence/<존재>/`에 identity 최소 문서. 절차에 필요한지 관찰.

## 측정 절차 (가설의 두 축)

1. **히스토리 보존 (기각조건 1)**:
   - M1 후 `git log --follow --oneline -- legacy/src/flask/app.py`가 이주 이전 커밋들(M0 캡처)을 여전히 보여주는가?
   - 커밋 총수가 M0 대비 +1(격리 커밋)만 늘고 기존 이력 그대로인가?
   - `git mv`가 rename으로 인식되는가(`git show --stat`에 rename/R 표기)?

2. **마찰 완화 (기각조건 2)** — C001의 각 마찰을 격리 후 재관찰:
   - **F2/F4 (골격)**: M2 후 `gil log`/`fsck`가 위반 0으로 사는가?
   - **F3 (releases 침묵)**: `gil releases`가 여전히 0인가? **격리가 F3 표면을 없애는가?** — 핵심 판정.
   - **F7 (커밋 격리)**: M2의 `gil open --git` 커밋이 legacy/를 안 건드리고 rooms/만 담는가?
   - 격리 자체가 만든 새 마찰이 있는가?

3. **재현성 (기각조건 3)**: M0~M3가 Flask 고유 지식 없이 임의 레포에 적용 가능한 일반 단계로 적히는가? "Flask라서 특별했던 것"을 표시.

## 준비물

- gil 참조 구현: `rooms/deployment/ariadne-spec/gil.py`, `python3` 호출.
- 신선 Flask 클론: 스크래치패드 `graft-C002/flask`.
- 산출물: `3-verification/` — migration-procedure.md(확정 절차) + transcript/(raw 출력) + before-after.md(히스토리·마찰 대조).

## 사용자 컨펌

상현님이 (1) 이 사이클(legacy/ 이주, "가보자"), (2) 이주 방식 = **`git mv` 히스토리 보존**(AskUserQuestion)을 컨펌. 세부 단계는 자율 설계(전권 위임 하).

- [x] 컨펌 받음 (일자: 2026-07-19, 사이클 진행 + git mv 방식 AskUserQuestion)
