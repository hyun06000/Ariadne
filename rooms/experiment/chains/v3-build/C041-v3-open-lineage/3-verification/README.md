# 3. 가설 검증

v3 open에 `--author`·`--parent`를 더해 루트 define 커밋에 Cycle-Author·Cycle-Parent
trailer로 계보를 각인하고, worktree add(--v3)가 이를 넘기게 했다. 배포판 gil.py 수정.

## 산출물

- `verify.sh` — M1~M4 재현 스크립트.
- 구현: gil.py `cmd_v3open` 계보 trailer + v3 open 서브파서 옵션 + `_worktree_add` 전달.

## 재현 방법

```bash
bash rooms/experiment/chains/v3-build/C041-v3-open-lineage/3-verification/verify.sh
# M5 conformance:
cd rooms/deployment/ariadne-spec
GIL="python3 $(pwd)/gil.py"; GIL_V2_OPEN=1 python3 conformance.py --gil "$GIL"  # → 121/121
```

## 실행 기록

- 실행: 2026-07-23, macOS(Darwin 25.5.0), Python 3.9. gil.py 수정.

### 측정 결과 (전 항목 PASS)

- **M1 계보 trailer 각인 — PASS.** `v3 open … --author clew --parent C001-seed --git` →
  커밋에 `Cycle-Author: clew`·`Cycle-Parent: C001-seed`. `git log --format=%(trailers)`로
  복원.
- **M2 스텝 트리 trailer 무손상 — PASS.** 같은 커밋에 `Step-Id: s1`·`Kind: define`·
  `Parent: null`(스텝 트리 부모) 여전히 공존. 계보 trailer는 별도 키(Cycle-*)라 안 섞임.
- **M3 인자 없는 호출 무회귀 — PASS.** `v3 open … --git`(계보 없이) → Cycle-Author
  trailer 없음(`[]`). 기존 v3 open 동작 불변.
- **M4 worktree add 계보 전달 — PASS(C039 소실 해소).** `worktree add demo wtcyc
  --author weft --parent C001-seed --v3` → v3 사이클 커밋에 `Cycle-Author: weft`·
  `Cycle-Parent: C001-seed`. **C039 M5의 계보 소실(커밋 author=git user, parent null)이
  이제 명시적 trailer로 보존.**
- **M5 conformance 무회귀 — PASS.** 게이트 상속 **121/121**, 게이트 없이 109 유지,
  실저장소 fsck 위반 0. gil.py 변경이 v2·v3 기존 경로 무손상.

### 종합

가설 채택. 계보(author·parent)가 커밋 trailer로 보존되고, steps.yaml·fsck·conformance
무회귀. **C039가 노출한 세 경계(번호·계보·fsck)가 이제 전부 해소** — C040(번호·fsck) +
C041(계보). 계보를 trailer로 분리한 판단(steps.yaml 스텝 트리 순수 유지, C010 패턴 연장)이
적중 — 최소 확장으로 사이클-간 계보를 v3에 담았다.
