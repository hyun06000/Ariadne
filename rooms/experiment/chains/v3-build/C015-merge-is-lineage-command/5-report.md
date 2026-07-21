# 5. 결과 보고 — v3-build/C015-merge-is-lineage-command

부모: v3-build/C014-gil-command-automation (supported). lineage: v3-build/C012-merge-is-lineage. 저자: Clew. 소환자: 없음 (main 단독·순차, C074 — 소스 수정이라 격리 불필요). 판정: **supported (채택)**.

## 요약

C012가 순수 깃(build_merge.sh)으로 증명한 **합류(lineage=머지)** 를, C014가 백트래킹=checkout을 도구화했듯 **`gilv3 close --lineage sA,sB`** 명령으로 도구화했다. 생 `git merge` 호출 0 — 도구가 안에서 checkout(백트래킹)·merge(lineage)를 한다. 5측정 ALL PASS: 도구가 만든 close 머지 커밋이 **다중부모**(M1)·trailer가 lineage 담고 **부모 지문만으로 DAG 복원**(M2)·**append-only 무위반**(M3)·**squash 음성대조로 --no-ff 강제 확인**(M4)·**--lineage 없는 close는 C014 회귀 0**(M5). **깃 ≅ gil의 도구 강제가 분기(C014)·합류(C015) 양방향으로 닫혔다.**

## 무엇을 했나

1. **`git_merge_lineage` 신규** — 지정 산 잎들을 부모로 `git merge --no-ff --no-commit` → gil이 트리 해소 → 다중부모 커밋 각인. trailer(Kind=merge·Parent·Merge=lineage). `_assert_append_only`(C014) 재사용.
2. **`cmd_close`에 `--lineage` 인자** — 있으면 빈 봉인 대신 머지 커밋. 없으면 C014 선형 봉인 동일.
3. **`cmd_step`의 live_leaf 백트래킹 허용** — 산 잎 뒤 `--to`로 새 형제 가지(multi_solution 도달 가능성 회복).
4. **5측정 감사** — gilv3 명령만으로 두 산 잎 → lineage 머지 재현(build_case.sh) + 순수 깃 감사(measure.py).

## 교훈

1. **⭐⭐ 도구가 아는 충돌은 이월이 아니라 자동 해소다.** C012는 독립 코드 파일만 고쳐 충돌을 우회했지만, gilv3의 steps.yaml은 **논리 트리 전체를 담는 단일 파일**이라 두 산 갈래가 구조적으로 충돌한다(순수 깃엔 없던 문제). 그 정답은 **gil이 이미 안다**(메모리의 완전 트리). `--no-commit`으로 당긴 뒤 gil이 자기 트리로 steps.yaml을 해소한다 — **C012 "충돌 해소 자체가 지식 통합의 판단"의 실현.** 도구가 판단을 아는 충돌(steps.yaml=자동)과 모르는 충돌(같은 코드 영역=정직히 멈춰 이월)을 가른다.

2. **⭐ 앞 사이클의 도달불가 분기를 먼저 살려야 했다.** 두 산 잎을 만들려면 첫 산 잎 뒤 백트래킹이 필요한데 C014는 live_leaf step을 전면 거부해 `cycle_state`의 multi_solution 분기가 **죽은 코드**였다. C014에서 append-only 정정이 백트래킹의 선행조건이었듯, live_leaf 백트래킹이 lineage의 선행조건. **원리를 도구로 옮기면 종종 앞이 남긴 도달불가 분기를 먼저 살린다.**

3. **⭐ 정밀화한 계약이 다음 연산을 공짜로 허용한다.** C014가 "커밋 불소멸"(HEAD 전진이 아니라 도달가능성 단조)로 정정한 계약이 배당을 냈다 — 머지는 새 커밋만 추가하니 `_assert_append_only`를 손대지 않고 통과. checkout(C014)과 merge(C015)가 같은 집행기 아래 나란히 선다. **껍질이 얇았다** — lineage를 얹은 새 헬퍼는 하나(`git_merge_lineage`).

## 깃 ≅ gil 도구화 완성표

| gil 개념 | 깃 네이티브 | 원리 증명 | **도구 강제** |
|---|---|---|---|
| 스텝 종결 | 1 커밋 | C011 | ✅ C005·C014 |
| 백트래킹 | `git checkout <조상>` + detached | C011 | ✅ **C014** |
| 위계 | 커밋 trailer 지문 | C010·C011 | ✅ C010·C014 |
| 잎 | 태그(못) | C011 | ◐ (브랜치 못) |
| **lineage** | **머지 커밋 다중부모** | C012 | ✅ **C015** |
| 뷰어 | `git log --all --graph` | C011·C012 | ⬜ |

**분기(C014)·합류(C015) 양방향 도구 강제 닫힘.**

## 다음 사이클을 위한 제안 (이 보고서가 부모)

- **⭐ 잎=태그 정식화** (1순위, 이제 lineage까지 도구 강제됨): 브랜치 못(`gil/live/`·`gil/dead/`·`gil/sealed/`)을 **태그**로(C011 결론=태그, push 생존·불변 시점). 상현님 해시 이름 규칙. 현재 ◐ → ✅.
- **⭐ 뷰어/재구성기 `git log --all --graph` 재배선** (Sheen 축, 병렬 가능): C011·C012가 "그래프가 이미 뷰"임을 증명. 이제 도구가 분기·합류를 다 그리니 뷰어가 git log를 직접 읽으면 재구현 0.
- **충돌 해소 각인 = 지식 통합의 깊은 층**: 이 사이클은 steps.yaml 충돌만 자동 해소. 같은 코드 영역의 진짜 지식 충돌(두 교훈을 어떻게 합칠지의 판단)을 gil이 어떻게 각인할지 — 충돌 해소 커밋의 지문.
- **규모 확장**: 3+ 부모(옥토퍼스), 중첩 머지, 체인 간 머지(loom↔loomlight). `--lineage` 콤마 리스트가 자연 확장하나 미검증.
- **v2→v3 마이그레이션** (도구화가 선행조건 — 이제 checkout·못·머지가 도구에 섬): 마이그레이션 노트 artifact가 설계 입력.

## 정직한 경계

- 2부모 머지만(C012 규모). 3+·중첩·체인 간 미검증.
- 충돌 해소는 steps.yaml만 자동. 같은 코드 영역은 정직히 멈춰 이월.
- 잎=태그 여전히 ◐(브랜치 못). lineage에 집중(그리디).
- multi_solution 봉인의 의미 구분(선택 vs 통합) 후속 관찰.
- 계측기 결함 0(첫 build_case 실행이 steps.yaml 충돌을 잡아 설계 정정 — 반증 아니라 도구 갭 발견).

## 사이클 닫기

- [x] 5측정 ALL PASS, supported
- [ ] `cycle.yaml` status: closed (gil close가 처리)
- [ ] memory.md 기록
- [ ] 커밋·퍼블리시
