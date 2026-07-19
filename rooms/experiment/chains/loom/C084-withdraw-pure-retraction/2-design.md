# 2. 실험 설계

## 설계 결정

### D1. open 커밋을 어떻게 특정하는가 (핵심)

열린 사이클은 태그가 없다(태그는 close --git이 붙임). 따라서 supersede처럼 태그를 못 쓴다.
**가장 견고한 특정법 = 사이클 디렉토리를 처음 추가한 커밋.**
- `git log --diff-filter=A --format=%H -- <cycle_rel>` 의 마지막(=가장 오래된) 커밋이 디렉토리를 생성한 open 커밋.
- 커밋 메시지 grep보다 견고(메시지 형식 변경·재번호 접미사에 무관, 데이터로 판정).
- graft/C003의 `2cb2e56`가 정확히 이 커밋(6파일 A).

### D2. withdraw의 행동 (원자적)

1. `<ref>` 사이클이 **열린 상태**인지 확인 (cycle.yaml status == "open"). 닫힌(태그된) 사이클 철회는 범위 밖 → 거부.
2. 이미 `withdrawn`이면 거부(멱등 아닌 명시 거부 — 상태 오염 방지).
3. open 커밋(D1) 특정. 못 찾으면 거부(무변화).
4. `git revert --no-edit <open_commit>` — 취소를 역사에 각인(하드리셋 아님).
   - revert가 충돌하면(그 사이후 같은 파일 수정) `git revert --abort`로 무변화 복원 후 거부.
5. revert는 디렉토리를 지우므로 cycle.yaml에 `withdrawn: true`를 남길 대상 파일이 사라진다.
   → **철회 상태는 revert 커밋 자체 + 별도 원장이 아니라, 디렉토리 소멸로 표현**한다. graft/C003이 그랬듯 "열었다 철회"가 git 역사(open + Revert 두 커밋)에 남는다.
   - 단, 뷰어/log가 "철회"를 능동적으로 비추려면 데이터가 필요 → **D3 참조.**
6. `--push`면 push(원격 없으면 우아한 강등, _push).

### D3. 철회를 뷰어가 비추는 법

revert는 디렉토리를 없애므로 gil-data에서 그 사이클 노드가 사라진다(자연 소멸). 이는 graft/C003 실동작과 정확히 일치 — "없던 걸로". **별도 withdrawn 플래그 원장은 이 카브 범위 밖**(디렉토리가 살아있어야 플래그를 달 곳이 있는데, 순수 철회는 디렉토리를 지운다). 즉 이 카브의 "철회 상태 데이터"는 **git 역사의 Revert 커밋**이 담당한다. 뷰어에 "철회된 사이클 목록"을 띄우는 건 후속 카브(withdrawn 원장 or supersede --withdrawn)로 이월.
→ 가설의 ②를 "revert 커밋이 역사에 철회를 남긴다"로 좁혀 검증한다(디렉토리 소멸 = 철회의 데이터적 표현).

### D4. conformance 계약

`WITHDRAW-*` 판정 항목 신설(참조·Go 양쪽 목표, 단 Go 이식은 이월 가능):
- WITHDRAW-RETRACTS: 열린 사이클 withdraw → 디렉토리 소멸 + Revert 커밋 존재 + exit 0.
- WITHDRAW-REJECTS-CLOSED: 닫힌(태그된) 사이클 withdraw → exit≠0, 무변화.
- WITHDRAW-ATOMIC: 존재하지 않는 ref withdraw → exit≠0, 무변화(HEAD 불변).

## 절차

1. `cmd_withdraw` + 서브파서 `withdraw <ref>` 구현 (참조 gil.py).
2. graft/C003 시나리오 재현: 신선한 테스트 저장소(또는 스크래치)에서 사이클 open → withdraw → 디렉토리 소멸·Revert 커밋·fsck 0 확인.
3. 거부 경로 3종(닫힌·부재·이미철회 아님→부재로 대체) exit·무변화 검증.
4. conformance에 WITHDRAW-* 추가, 참조 구현 통과 확인.
5. graft/C003의 실제 손-revert(97ccb4f)와 gil withdraw 결과가 동등함을 대조.

## 준비물

- gil.py (참조 구현, rooms/deployment/ariadne-spec/gil.py), python3.
- 테스트: 스크래치패드에 신선 git 저장소로 사이클 open→withdraw 재현(실 저장소 무오염).
- conformance.py (판정기).

## 측정 방법

- withdraw 후: 사이클 디렉토리 부재(측정 1) + `git log --grep=Revert` 존재(측정 2) + fsck 위반 0(측정 3) + exit 0(측정 4).
- 거부 3종: exit≠0 + `git rev-parse HEAD` 불변(측정 5).
- conformance: WITHDRAW-* 참조 통과(측정 6).
- **기각 기준**: 위 중 하나라도 실패, 또는 반쪽 상태(revert만 되고 디렉토리 잔존 등) 발생.

## 사용자 컨펌

- 첫 카브 = `gil withdraw <ref>` 신규 명령: AskUserQuestion으로 확정(2026-07-19).
- 세부 설계(D1~D4)는 상현님 전권 위임(자율 진행) 하에 진행. 분기점 없음(단일 명령·단일 가설).

- [x] 컨펌 받음 (일자: 2026-07-19 — 첫 카브 선택)
