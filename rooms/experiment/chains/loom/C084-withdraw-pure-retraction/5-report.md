# 5. 결과 보고

## 요약

graft/C003 롤백에서 드러난 gil의 어휘 공백 — "대체 없는 순수 철회"(open 직후 스코프 오판으로 없던 걸로)를 gil이 자기 언어로 못 말하고 손 `git revert`에 의존한 것 — 을 메우기 위해 **`gil withdraw <ref>`**를 신설했다. 열린 사이클의 open 커밋을 `git revert`로 되감아 취소를 역사에 남기되(하드리셋 아님) 디렉토리를 소멸시키고, 닫힌 사이클·부재 ref는 무변화로 거부한다. 참조 118/118·Go 정직한 부재 101/101, graft/C003 손-revert와 동등성 확인 → **채택(supported)**.

## 교훈

1. **gil이 "취소"를 자기 언어로 각인한다 — 취소조차 역사에 남기며(하드리셋 아님).** supersede(대체자 필수·전방 무효화)와 대칭인 순수 철회 프리미티브. graft/C003에서 상현님이 손으로 하던 `git revert`가 gil의 어휘가 됐다. "revert는 gil/git 철학과 정합"(graft/C003)이 도구로 실현됐다.
2. **철회의 데이터 표현 = 디렉토리 소멸 그 자체.** 순수 철회는 플래그를 달 대상(디렉토리)을 지우므로 supersede의 `superseded_by` 같은 별도 원장이 필요 없다 — git 역사의 Revert 커밋이 상태를 담고 뷰어 노드가 자연 소멸한다. graft/C003 실동작("없던 걸로")과 정확히 일치.
3. **open 커밋은 태그가 아니라 `--diff-filter=A`로 특정한다** — 열린 사이클엔 태그가 없다. "디렉토리를 처음 심은 커밋"을 데이터로 판정("깃의 답을 훔쳐라") → 메시지 형식·재번호 접미사에 무관하게 견고.
4. **C012 "거부형 검사 공허 통과"를 신규 명령마다 다시 밟는다.** Go 미구현 시 거부형 항목이 'unknown command' exit≠0으로 공허 통과했다(가드 전 103/104). 부분구현 합법 가드(`help withdraw==0`일 때만 판정)로 막고 부재의 정직성은 HELP-COMPLETE(exit 3)에 이관. **"판정기가 안 보는 계약은 없는 계약이다 — 그리고 잘못 보는 계약은 거짓 계약이다."**

## 다음 사이클을 위한 제안

- **(A) Go 이식** — `gil withdraw`를 Go에 이식(_open_commit_of·revert·거부 경로). C043 리듬(참조 먼저 → Go가 정직한 부재로 이월 → 되찾기). Weft의 몫(main.go 주인). 이식 후 Go 판정에서 WITHDRAW 3항목 부분구현 가드가 켜진다.
- **(B) 체인 전체 롤백** — AskUserQuestion에서 이월한 큰 카브. `gil rollback <chain> --to <ref>`(한 체인의 여러 사이클 연쇄 철회). withdraw가 단일 사이클 프리미티브가 됐으니 그 위에 얹을 수 있다.
- **(C) supersede --withdrawn 모드** — 닫힌(태그된) 사이클의 "대체 없는 폐기"(withdraw는 열린 사이클 전용). 불변 규칙과의 관계상 revert가 아니라 메타 플래그(`withdrawn: true`)로 각인 — supersede 계열.
- **(D) 배포** — withdraw는 gil 소스 변경이므로 릴리스가 필요하다(maru 등 외부 채택자가 쓰려면). 단독 배포 or Go 이식(A)과 묶어서.
- **그 외 불변 이월**: worktree land 번호 충돌 감지(C083 사후 충돌), F3 releases 실명 수정, 유령 태그 정리, SPEC 명문화.

## 사이클 닫기

- [x] `cycle.yaml`의 `status: closed`, `closed: <일자>` 갱신 (gil close가 수행)
- [x] 존재의 방 `memory.md`에 이 사이클의 기억 기록
- [x] 커밋 및 퍼블리시 (gil close --git --push)
