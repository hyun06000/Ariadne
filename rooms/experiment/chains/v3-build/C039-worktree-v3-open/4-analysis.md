# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 | 결과 | 판정 |
|---|---|---|---|
| M1 v3 격리 생성 | 브랜치에 steps.yaml ∧ 메인 무변화 | 둘 다 참(C002-mycycle, HEAD 불변) | PASS |
| M2 병렬 무충돌 | slug 다른 두 add 무충돌 | 경로 충돌 0 · **번호 중복(둘 다 C002)** | 부분 |
| M3 v2 무회귀 | --v3 없이 기존 동작 | v2 add는 C032 이후 이미 은퇴(내 변경 무관) | 재정의 |
| M4 land 봉합 | v3 브랜치 --no-ff 병합 | 두 브랜치 모두 봉합·steps.yaml 메인 도착 | PASS |
| M5 계보 | author 보존 | **author·parent 소실**(커밋 author=git user) | FAIL |
| M6 conformance | 게이트 상속 121/121 | 121/121 | PASS |

## 데이터 직접 관찰

**번호 중복을 직접 봤다.** land 후 메인 `ls demo/`:
`C001-seed  C002-mycycle  C002-other-cycle`. 둘 다 C002. 원인은 데이터로 확인 —
각 워크트리는 `git worktree add … HEAD`로 main HEAD를 뜬 격리 체크아웃이라, add 시점에
`load_chain_records(chain_dir)`가 **서로의 아직-안-land된 브랜치를 못 본다**. 둘 다
C001-seed만 세어 C002를 계산. **이것이 정확히 예약이 풀던 문제** — 병렬 open의 번호
충돌. slug이 달라 경로는 안 겹쳐 데이터 손실은 없지만, 번호는 겹친다.

**계보 소실을 커밋 author로 확인.** `git log`의 v3 open 커밋 author가 't'(워크트리
git config user.name)이지 `--author clew`가 아니다. v3 open은 `--author`를 안 받고,
worktree add가 그걸 **브랜치명 `clew/demo-mycycle`에만** 새겼다. steps.yaml의 parent도
null — worktree add가 받은 `--parent`가 v3 사이클 어디에도 안 감. **author·parent라는
사이클-간 정보가 v3 사이클 데이터에서 증발.**

**fsck가 v3를 안 본다.** `fsck` 출력 "체인 1개, 사이클 1개" — C002 둘을 안 셈. v3
사이클은 cycle.yaml 없이 steps.yaml만 있어 `load_chain_records`(cycle.yaml만 수집)의
레이더 밖. 그래서 번호 중복이 위반으로 안 걸리지만, 뒤집으면 **v3 사이클은 v2 원장
무결성(fsck·verify·graph) 전체의 사각지대**.

## 예상과 달랐던 것

- **v2 worktree add가 이미 죽어 있었다(M3).** 설계 때 "v2 무회귀 유지"를 측정하려 했으나,
  self-invoke하는 v2 open이 C032 은퇴에 걸려 게이트 없이 이미 실패 상태였다. worktree
  add의 self-invoke는 `GIL_V2_OPEN`을 환경에 안 넘긴다. **내 `--v3`는 무회귀 대상이
  아니라 worktree add를 되살리는 유일한 살아있는 경로였다** — 가설이 예상보다 더 절실.
- **세 실패(번호·계보·fsck)가 한 뿌리다.** 예상은 "worktree만 v3로 바꾸면 끝"이었으나,
  드러난 건 **v3 사이클이 v2 원장 모델에 미편입**. 번호(사이클-간 순서)·author·parent
  (사이클-간 계보)·fsck(원장 무결성)가 전부 v2가 cycle.yaml에 쓰던 것들이고, v3는
  steps.yaml만 써서 이 층이 통째로 비어 있다. **C033 "사이클-간 정보는 notes 층으로"가
  아직 코드로 미실현** — worktree가 그 공백을 정면으로 드러냈다.

## 판정

**부분 채택 (supported, 경계 명확).** 가설의 핵심 — worktree가 v3 open을 열고 C050
격리를 계승하며 예약 없이 slug 병렬이 가능 — 은 M1·M4·M6로 입증. 기각조건 1(격리 실패)은
불충족(격리 계승됨). 그러나 기각조건 2(병렬 충돌)·3(계보 소실)이 **부분 충족** —
번호 중복·author/parent 소실. 이는 가설을 뒤엎지 않고(경로·데이터는 안전) **v3 사이클의
v2 원장 편입이라는 다음 문제를 정확히 노출**한다.

**정직한 경계**: gil.py 수정(worktree add v3 분기)으로 conformance 무회귀(121/121).
실사이클을 gil v3로 여는 것은 **격리·병렬 수준에선 가능**하나, 번호·계보·fsck 통합
전까진 v2 원장과 나란히 못 산다. **상현님께 "gil v3로 실사이클 열기는 격리 수준 도달,
원장 편입은 다음"으로 보고.**
