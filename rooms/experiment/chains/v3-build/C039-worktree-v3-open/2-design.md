# 2. 실험 설계

## 설계 결정 — `worktree add --v3` 옵트인 (전환기 패턴 계승)

C031·C032가 확립한 전환기 패턴(v3를 옵트인으로 안전하게 얹고, 안내가 마찰 흡수)을
worktree에 계승한다. `worktree add`에 **`--v3` 플래그**를 더해:

- 없으면 기존대로 `gil open`(v2) self-invoke — 하위호환 무손상.
- 있으면 `gil v3 open <dir>` self-invoke — v3 네이티브 병렬 사이클.

**번호(C0NN)는 add가 결정론적으로 계산**(`_next_number(load_chain_records(chain_dir))`).
v2 open이 내부에서 하던 번호 매김을 v3에선 add가 self-invoke 전에 하고 완전 경로를
넘긴다(v3 open은 경로가 정체성이라 번호를 안 매김 — C032). dir =
`<chain_dir>/C{N:03d}-{slug}`.

**예약 불필요 실증**: 각 존재가 자기 slug을 정하므로 slug 충돌 없음. 번호는 add 시점에
계산되고 순차 land로 봉합되므로, 예약(번호 선점) 없이 병렬 안전. gil.py의 v2 예약
메커니즘은 이 사이클에서 **건드리지 않음**(v2 경로에 존치) — v3 경로가 예약을 안 쓸 뿐.

**author·parent 계보**: v3 open --git이 워크트리에서 커밋할 때 그 워크트리의 git config
user가 커밋 author가 된다(worktree add가 브랜치명 `{author}/...`로 이미 author를 경로에
새김). parent는 v3 open이 아직 인자로 안 받으므로 이번엔 **git 커밋 trailer 또는 후속
notes로 이월**(migrate가 읽는 층) — 3-verification에서 실제 소실 여부 실측.

## 절차

1. **`gil worktree add` 서브파서에 `--v3` 플래그 추가** (기본 False).
2. **`_worktree_add`에 v3 분기**: `args.v3`면 (a) `load_chain_records(wt_chains/chain)`으로
   기존 사이클 세어 `_next_number`로 번호 N 계산, (b) dir = `wt_chains/<chain>/C{N:03d}-{slug}`,
   (c) self-invoke cmd = `[python, gil, "v3", "open", dir, "--title", slug, "--git"]`.
   실패 시 워크트리·브랜치 되돌림(기존 원자성 규율 계승).
3. **배포판 gil.py에 적용** (gil.py를 이 사이클에서 처음 수정 — C032 이후 첫 gil.py 변경).
4. **격리 검증**: (M1) v3 worktree add → 워크트리 브랜치에 steps.yaml 생성·메인 무변화 ·
   (M2) 두 존재 병렬(slug 다름) add → 충돌 없이 각자 브랜치 · (M3) v2 경로 무회귀
   (--v3 없이 기존 동작) · (M4) land로 v3 브랜치 봉합 · (M5) author/parent 계보 실측.
5. **conformance 무회귀**: 게이트 상속 121/121 유지(gil.py 변경이 v2 경로 무손상 확인).

## 준비물

- 배포판 `rooms/deployment/ariadne-spec/gil.py` (이번엔 gil.py 수정), `conformance.py`(무회귀 확인)
- Python 3.9, git. 헬퍼 `_next_number`·`load_chain_records`(gil.py 내장).
- 실행: 격리 샌드박스에서 `gil worktree add demo slug --author X --v3`.

## 측정 방법

- **M1 v3 격리 생성**: 워크트리 브랜치에 `steps.yaml`·define s1 존재 ∧ 메인 HEAD 무변화.
  기준=둘 다 참.
- **M2 병렬 무충돌**: slug 다른 두 add가 각자 브랜치에 다른 dir. 기준=충돌 0.
- **M3 v2 무회귀**: `--v3` 없는 add가 기존대로 v2 사이클. 기준=동작 불변.
- **M4 land 봉합**: v3 브랜치를 `worktree land`가 --no-ff 병합. 기준=병합 성공·steps.yaml 메인 도착.
- **M5 계보 실측**: v3 사이클의 author(커밋)·parent 소실 여부. 기준=author 보존(parent 소실이면 이월 기록).
- **M6 conformance 무회귀**: 게이트 상속 121/121. 기준=불변.

## 사용자 컨펌

- 상현님 자율 위임("멈추지 말고 달려, 계속 자율 사이클"). GUARD 후속 예약축은 매듭 순서
  2번. `--v3` 옵트인은 C031·C032 확립 패턴의 기계적 계승이라 새 결정 최소 — 자율 진행.
  다만 이 사이클이 성공하면 **gil v3로 실사이클을 열 수 있는 지점**에 닿으므로 상현님께 보고.
- [x] 컨펌 받음 (일자: 2026-07-23, 자율 위임 + 전환기 패턴 계승)
