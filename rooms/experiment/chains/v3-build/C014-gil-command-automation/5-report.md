# 5. 결과 보고 — v3-build/C014-gil-command-automation

부모: v3-build/C012-merge-is-lineage (supported). 조부: C011(분기)·C013(코드 아티팩트, Bobbin). 저자: Clew. main 단독·순차(C074). 판정: **supported (채택)**.

## 요약

C011·C012가 순수 깃으로 증명한 매핑을 실제 gilv3.py 명령으로 옮기기 시작했다 — 그 첫 조각 **백트래킹=`git checkout`**. 도구가 open/step/close만으로 C011 build_branches.sh가 손으로 짠 3층 분기(죽은 잎 2·산 잎 1)를 자동 생성한다(생 git checkout 0). 그 과정에서 **C008을 C011로 정직하게 정정**했다: append-only의 진짜 계약은 "HEAD 전진"이 아니라 "커밋 불소멸"이다 — 그래서 checkout(HEAD 뒤로, 커밋 보존)은 허용되고 reset --hard(커밋 삭제)만 거부된다. 5측정 ALL PASS, 회귀 0. **원리를 도구가 강제하는 첫 조각.**

## 무엇을 했나

1. **델타 확정**: 최신 gilv3.py(C010판)를 읽어 "이미 있음(trailer 각인)/빠짐(checkout·태그·머지)"을 갈랐고, **C008 forward-only 집행이 checkout을 금지해 C011과 충돌**함을 발견 — 자동화가 두 사이클 이월된 진짜 이유.
2. **개념 정정**: `_assert_forward_only`(HEAD 전진) → `_assert_append_only`(커밋 불소멸). append-only가 지키려던 것(커밋 안 지움)으로 계약을 정밀화하니 checkout이 그 계약을 이미 지키고 있었다.
3. **checkout 백트래킹 실장**: cmd_step이 죽은 잎 뒤 새 형제 가지에서 조상 define 커밋으로 실제 checkout → 깃 자동 분기. `_commit_of_sid`가 trailer로 sid→커밋을 조회(steps.yaml에 깃 메타 안 넣음, C005 유지).
4. **모든 잎에 못**: checkout으로 떠나는 가지가 dangling→gc되는 것을 막는 최소 못 — 죽은 잎 `gil/dead/`, 산 잎 `gil/live/`, 사이클 종결 `gil/sealed/`.
5. **5측정 감사**: gilv3 명령만으로 재현한 저장소를 순수 깃 + C010 rebuild 재사용으로 판정.

## 교훈

1. **append-only의 진짜 계약은 커밋 불소멸이지 HEAD 전진이 아니다.** 이 사이클의 정점. C008 집행이 checkout(커밋 보존)과 reset(커밋 삭제)을 뭉뚱그려, C011의 백트래킹=checkout이 자기 집행기에 막혔다. 정정의 열쇠는 코드 추가가 아니라 **"무엇을 지키려 했나"로 돌아가 계약을 정밀화**하는 것. **원리를 도구로 옮기는 일은 종종 개념 정정이다.**
2. **모든 잎에 못이 필요하다 — 산 잎도(도구가 재발견).** C011이 죽은 가지에서 발견한 "ref 없으면 gc"를, 이 사이클은 산 가지·close 커밋도 같은 운명임을 구현 중 재발견(M4 초기 FAIL). checkout이 결국 그 자리를 떠나기 때문. C011이 모든 잎에 태그 박은 것의 필연을 도구가 재유도.
3. **불변 규율이 로직 재사용을 강제한다.** C010 rebuild가 `--all` 없어 분기를 못 읽었지만 C010은 닫혀서 못 고친다. 정직한 길은 그 파서를 `--all`로 재호출(원본 불변) — C011·C012가 예고한 "재구성기 --all 재배선" 이월의 첫 국소 실현.

## 도구화 진척

| gil 개념 | 원리 증명 | 도구 실장 |
|---|---|---|
| 스텝 종결·위계 | C005·C010·C011 | ✅ |
| **백트래킹=checkout** | **C011** | **✅ C014** |
| 잎=태그 | C011 | ◐ 브랜치 못(최소형) |
| lineage=머지 | C012 | ⬜ 다음 |
| 뷰어=git log --graph | C011·C012 | ⬜ 다음 |

## 다음 사이클을 위한 제안 (이 보고서가 부모)

- **⭐ 잎=태그 정식화** (1순위, 이 사이클이 최소형만): 브랜치 못(`gil/dead/`·`gil/live/`·`gil/sealed/`)을 **태그**로 승격. C011 결론(잎=불변 시점=태그, push 생존)과 상현님 이름 규칙(스텝 분기=해시 태그)을 실장. 브랜치는 움직이는 포인터라 잎에 부정확 — 태그가 정식.
- **⭐ lineage=머지 실장**: `gilv3 close --lineage A,B`가 `git merge --no-ff` 다중부모 커밋(C012 build_merge.sh가 명세). 백트래킹(분기)이 섰으니 이제 합류를 도구에.
- **뷰어/재구성기를 git log --all --graph 기반으로 재배선**: 이 사이클이 측정에서 `--all` rebuild를 국소 적용했다. 정식 v3 재구성기·뷰어(Sheen)를 `--all` 기반으로 — "깃 그래프가 곧 스텝 트리"의 실장.
- **체인 연속성**: close 후 detached HEAD를 다음 사이클 open이 어떻게 잇나(사이클 종결 못에서 새 사이클 루트로).
- 그 뒤(이월): 중첩 백트래킹·BFS·다중 루트 · trailer에 Chain·Cycle·Merge 정식화 · v2→v3 마이그레이션(이 도구화가 선행조건이었다 — 이제 checkout·못이 도구에 있으니 `gil migrate`가 얹힐 토대가 하나 섰다) · v2 백업+rooms 보존.

## 정직한 경계

- **잎 못이 태그 아니라 브랜치**(최소형) — 정식화는 다음. 브랜치는 잎(불변)에 의미상 부정확, push 생존도 미검증(C011은 태그로 결론).
- **rebuild --all은 측정 안 국소 적용** — rebuild_trailer.py 자체나 정식 뷰어 재배선 아님(이월).
- **lineage=머지·잎=태그 미실장** — 백트래킹 하나에 집중(철학 충돌이 거기). 그리디.
- **실사례 최소**(3층·백트래킹 2), 중첩·BFS·다중 루트·성능 미검증. detached HEAD 잔여의 체인 연속성 미탐구.
- **계측기/설계 결함 4건 수리**(모두 반증 아님): 산 가지 dangling·close 커밋 소멸·C010 rebuild 분기 미독·M4 저장소 오염. 3-verification/README에 명시.

## 사이클 닫기

- [x] 5측정 ALL PASS, supported
- [ ] `cycle.yaml` status: closed (gil close가 처리)
- [ ] memory.md 기록
- [ ] 커밋·퍼블리시
