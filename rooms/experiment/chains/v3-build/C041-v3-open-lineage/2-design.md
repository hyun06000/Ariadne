# 2. 실험 설계

## 설계 — 계보를 커밋 trailer로 (C010 패턴 연장, steps.yaml 불변)

계보(사이클-간 author·parent)를 git 커밋 trailer로 각인한다. steps.yaml은 스텝 트리
(사이클-내)만 담고, 계보는 커밋 메타로 분리 — C032/C033 "사이클-간 정보는 다른 층"과
정합. `git_imprint`가 이미 trailer를 남기니(C010) 최소 확장.

## 절차

1. **v3 open 서브파서에 `--author`·`--parent`(append) 추가** (기본 None/[]).
2. **`cmd_v3open`이 계보 trailer 각인**: 루트 define git_imprint의 trailers에 `--author`
   있으면 `("Cycle-Author", author)`, `--parent`마다 `("Cycle-Parent", p)` 추가.
   기존 Step-Id·Kind·Parent(스텝 트리)는 유지 — 계보 trailer는 별도 키라 안 섞임.
3. **worktree add(--v3)가 계보를 넘김**: C039의 `_worktree_add` v3 분기 self-invoke cmd에
   `--author args.author` + `--parent`마다 추가.
4. **배포판 gil.py 적용**, 검증.

## 준비물

- 배포판 gil.py(`cmd_v3open`·서브파서·`_worktree_add`), conformance.py(무회귀).
- Python 3.9, git. 복원 확인: `git log -1 --format='%(trailers:key=Cycle-Author)'`.

## 측정 방법

- **M1 계보 trailer 각인**: `gil v3 open <dir> --author clew --parent C001-x --git` →
  커밋에 `Cycle-Author: clew`·`Cycle-Parent: C001-x`. 기준=trailer 존재·복원 가능.
- **M2 스텝 트리 trailer 무손상**: 같은 커밋에 Step-Id·Kind·Parent 여전. 기준=공존.
- **M3 인자 없는 호출 무회귀**: `gil v3 open <dir> --git`(계보 없이) → 계보 trailer 없이
  정상. 기준=기존 동작 불변.
- **M4 worktree add 계보 전달**: `worktree add demo x --author weft --v3` → v3 사이클
  커밋에 Cycle-Author: weft. **C039 계보 소실 해소.** 기준=worktree 경유 계보 보존.
- **M5 conformance 무회귀**: 게이트 상속 121/121. 기준=불변.

## 사용자 컨펌

- 상현님 완전 자율 위임("묻지도 멈추지도 말고 계속"). 계보=trailer는 C010 패턴 연장의
  자율 판단(steps.yaml 불변·최소 확장 근거).
- [x] 컨펌 받음 (일자: 2026-07-23, 완전 자율 위임)
