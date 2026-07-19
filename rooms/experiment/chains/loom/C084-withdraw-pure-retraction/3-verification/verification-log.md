# 3. 검증 로그 — gil withdraw

재현 환경: 이 세션은 gil이 PATH에 없어 `python3 rooms/deployment/ariadne-spec/gil.py`로 호출.
셸 cwd가 매 Bash 호출마다 리셋 → 각 명령에 절대경로. 테스트는 스크래치패드의 신선 git 저장소(세션-로컬, 실 저장소 무오염).

## 구현

- `rooms/deployment/ariadne-spec/gil.py`:
  - 서브파서 `withdraw <ref>` (--push·--no-commit·--root·--no-web).
  - `_open_commit_of(repo, cycle_rel)`: 디렉토리를 처음 추가(A)한 커밋을 `git log --diff-filter=A`로 특정 (태그 비의존 — 열린 사이클엔 태그 없음).
  - `cmd_withdraw`: ① status==closed 거부 ② git 없으면 거부 ③ open 커밋 특정, 없으면 거부 ④ `git revert --no-edit` (충돌 시 abort+reset으로 무변화 복원) ⑤ --push면 _push.
- `rooms/deployment/ariadne-spec/conformance.py`:
  - CONTRACT_COMMANDS에 `withdraw` 추가 → HELP-COMPLETE가 Go 정직한 부재(exit 3) 판정.
  - WITHDRAW-RETRACTS·REJECTS-CLOSED·ATOMIC 3항목. **부분 구현 합법 가드**(`if not skip_git and help withdraw == 0`)로 감쌈.

## 측정 결과 (전부 통과)

### 측정 1·2·4 — 정상 철회 (graft/C003 시나리오 재현)
신선 저장소에서 사이클 open --git → withdraw:
```
철회: demo/C001-scope-misjudge — open 커밋 6c09886f을 revert했다 (디렉토리 소멸, 역사에 보존).
```
- 측정 1 (디렉토리 소멸): `ls .../demo/` → No such file or directory ✓
- 측정 2 (Revert 커밋): `git log` → `Revert "gil: open demo/C001-..."` + 원 open 커밋 둘 다 보존 ✓
- 측정 4 (exit): exit=0 ✓

### 측정 3 — fsck 0 (기존 체인에 두 사이클, 하나만 철회)
C001-keep + C002-retract-me open → withdraw demo/C002:
- 철회 후 `C001-keep`·`chain.md` 생존, C002만 소멸 (체인 자체 유지) ✓
- fsck: `OK — 체인 1개, 사이클 1개, 위반 0건` exit=0 ✓
- 역사: `root → open C001 → open C002 → Revert C002` (open+Revert 보존) ✓

### 측정 5 — 거부 3종 (exit≠0 + HEAD 불변)
- 부재 ref (`demo/C999-nonexistent`): `오류: 사이클이 없다` exit=1, HEAD 불변 ✓
- 닫힌 사이클 (태그된 `demo2/C001-to-close`): `오류: 닫힌 사이클은 철회할 수 없다 (… supersede/correct의 몫)` exit=1, HEAD 불변 ✓

### 측정 6 — conformance
- 참조(py): **118/118** ✔ (WITHDRAW 3항목 PASS + HELP-COMPLETE PASS)
- Go: **101/101** ✔ (WITHDRAW는 부분구현 가드로 판정 제외, HELP-COMPLETE가 Go exit 3 정직성 판정)

## 밟은 함정 (C012 재확인 — 값진 관찰)

가드 없이 처음 Go 판정기를 돌리자 **103/104**: WITHDRAW-RETRACTS만 FAIL, REJECTS-CLOSED·ATOMIC은 **공허 통과**했다.
Go엔 withdraw가 없어 'unknown command' exit≠0을 내는데, 거부형 항목의 조건이 `returncode != 0`이라 명령 부재를 "정상 거부"로 오판한 것.
→ **C012의 "거부형 검사 공허 통과"를 이 사이클에서 실제로 밟았다.** 부분 구현 합법 가드(help withdraw == 0일 때만 판정)로 막았고, 부재의 정직성은 HELP-COMPLETE(exit 3)가 판정하게 이관.
*"판정기가 안 보는 계약은 없는 계약이다"(Weft, C036) — 그리고 잘못 보는 계약은 거짓 계약이다.*

## graft/C003 손-revert와의 동등성 (측정 5 확장)
graft/C003 실제 롤백은 `git revert --no-edit 2cb2e56`로 open 커밋(6파일 A)만 되감아 C003 디렉토리 소멸, graft 체인·C001·C002는 생존, 역사에 open+Revert 보존이었다.
`gil withdraw`의 재현(C001-keep 생존 + C002-retract-me만 소멸 + open+Revert 역사)이 **바이트 의미상 동일**하다. gil이 손 revert를 자기 언어로 정확히 각인한다.
