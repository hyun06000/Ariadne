# 3. 가설 검증

`worktree add --v3` 옵트인을 배포판 gil.py에 구현하고(C032 이후 첫 gil.py 수정),
격리·병렬·land·계보·무회귀를 측정했다.

## 산출물

- `verify.sh` — M1·M2·M4·fsck 재현 스크립트(격리 샌드박스).
- 구현: gil.py `_worktree_add` v3 분기 + `--v3` 플래그.

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec
bash ../../experiment/chains/v3-build/C039-worktree-v3-open/3-verification/verify.sh
# M6 conformance 무회귀:
GIL="python3 $(pwd)/gil.py"
GIL_V2_OPEN=1 python3 conformance.py --gil "$GIL"   # → 121/121
```

## 실행 기록

- 실행: 2026-07-23, macOS(Darwin 25.5.0), Python 3.9. gil.py 수정(worktree add v3 분기).

### 측정 결과

- **M1 v3 격리 생성 — PASS.** `worktree add demo mycycle --author clew --v3` →
  워크트리 브랜치 `clew/demo-mycycle`에 `C002-mycycle/steps.yaml`·루트 define s1 생성,
  메인 HEAD **무변화**. 번호는 결정론 계산(C001-seed 다음 → C002). **C050 격리가 v3로
  계승** — v3 open --git이 워크트리 브랜치에만 커밋.
- **M2 병렬(slug 다름) — 부분.** 두 존재가 slug 다른 사이클을 각자 브랜치에 열어
  **경로 충돌·데이터 손실 0**. 그러나 **둘 다 C002를 계산**(각자 main HEAD의 C001-seed만
  보고 서로의 브랜치를 못 봄) → **번호 중복**. slug이 달라 경로는 안 겹치나 번호는 겹친다.
- **M3 v2 무회귀 — 재정의.** `--v3` 없는 add는 게이트 없이 **실패**한다(self-invoke하는
  v2 open이 C032 은퇴 안내로 거부). 이는 내 변경의 회귀가 **아니라 C032가 남긴 기존
  상태** — v2 worktree add는 C032 승격 이후 이미 죽어 있었다(self-invoke가 GIL_V2_OPEN을
  환경에 안 넘김). **`--v3`가 사실상 worktree add를 되살리는 유일한 살아있는 경로.**
- **M4 land 봉합 — PASS.** 두 v3 브랜치 모두 `worktree land`가 --no-ff로 메인에 봉합,
  steps.yaml 메인 도착, 워크트리·브랜치 정리. land는 순수 git 오케스트레이션이라 v2/v3
  무관하게 작동(설계대로).
- **M5 계보 — FAIL(소실).** v3 사이클의 커밋 author가 워크트리 git config user('t')이지
  `--author clew`가 **아니다**(브랜치명에만 존재). parent도 steps.yaml에 null. **author·
  parent가 v3 사이클 데이터에서 소실** — 기각조건 3에 걸림.
- **fsck — v3 미인식(더 근본).** land 후 메인에 C002 두 개가 있어도 fsck는 "사이클 1개"
  (C001-seed만) 보고 위반 0. **v3 사이클(steps.yaml, cycle.yaml 없음)을 fsck의 사이클
  스캔이 아예 안 센다** → 번호 중복이 위반으로 안 걸리지만, 이는 v3가 v2 원장 무결성
  검사 밖에 있다는 뜻.
- **M6 conformance 무회귀 — PASS.** 게이트 상속 **121/121**. gil.py 변경이 v2 경로 무손상.
  게이트 없이 109 유지(WORKTREE-SPAWN/LAND는 v2 open self-invoke라 C032 이후 이미 FAIL,
  내 변경 무관 — `cyc=False br=False`가 은퇴 거부를 증명).

### 종합

가설의 **핵심(worktree가 v3 open을 열고 C050 격리 계승, 예약 없이 slug 병렬)은
supported**. 그러나 세 경계가 드러남: **①번호 중복(병렬 계산이 서로 못 봄) ②계보 소실
(author·parent 미기록) ③fsck v3 미인식**. 셋 다 같은 뿌리 — **v3 사이클이 v2 원장 모델
(번호·계보·무결성)에 아직 편입 안 됨**(C033 "사이클-간 정보는 notes 층으로"의 미완).
이것이 다음 사이클 좌표를 정확히 찍는다.
