# 4. 결과 분석

## 통계적 결과

| 판정 항목 | 결과 |
|---|---|
| GUARD-PRIMARY-REFUSE (주 체크아웃+남의 author → 거부·미생성·HEAD무변화) | PASS (양 구현) |
| GUARD-OWNER-OK (주인 author → 통과) | PASS (양 구현) |
| GUARD-LINKED-OK (링크드 워크트리 남의 author → 통과, 오탐 0) | PASS (양 구현) |
| 참조 conformance 전체 | **89/89** (회귀 0) |
| Go conformance 전체 | **82/82** (회귀 0) |
| 변이(guard 호출 제거) | GUARD-PRIMARY-REFUSE **FAIL**(87/89) — 판정 비공허 증명 |

기각 조건 5개 전부 방어. 변이에서 guard를 제거하니 `rc=0 dir=True`(사이클 생성됨 = 유출 재현)로 REFUSE가 FAIL, LINKED-OK는 PASS 유지 → **거부와 허용이 함께 서는 쌍**(C038)이 실제로 판정됨.

## 데이터 직접 관찰

- **실사고를 재연해 봉인 확인**: 샌드박스 주 체크아웃에서 `gil open demo intrude --author intruder`(gil.owner=owner-x) → 양 구현 모두 처방 메시지와 함께 거부, **사이클 디렉토리 미생성·HEAD 커밋 무증가**. 세 번 났던 그 사고(존재가 main으로 cd → open 유출)가 이제 커밋 이전에 막힌다.
- **우리 저장소에 활성화**: `git config gil.owner clew` 설정 후 `_guard_primary_owner(repo,'clew')` 통과 / `'weft')` 거부 실측. 이제 이 클론의 main은 존재의 오염으로부터 보호된다.

## 예상과 달랐던 것

- **reserve는 guard 대상이 아니다 — 구현 중 발견한 설계 정련.** 처음 설계는 open·reserve·correct를 guard하려 했으나, `reserve --for X`의 X는 **행위자가 아니라 예약 대상**이다. 소환자(Clew)가 main에서 남을 위해 예약하는 것은 정당한 패턴 — guard하면 오탐 차단. **guard의 "author"는 커밋의 행위자여야 한다**(open·correct의 --author는 행위자, reserve의 --for는 목적어). 그래서 open·correct만 guard.
- **gil.owner는 클론-로컬 config다**(git의 user.name처럼 `.git/config`, 커밋 안 됨). 이 클론의 main만 보호한다 — 다른 머신 클론은 각자 설정해야. 커밋되는 소유자 표식(공유 기본값)은 다음 카브. 첫 카브로는 로컬 config가 옳다(git 자신의 소유 모델과 정합, opt-in으로 CI·기존 저장소 무파손).

## 판정

**채택 (supported).** 가설 (a)~(d) 전부 실증: (a) 주 체크아웃에서 남의 author open이 커밋 이전 거부, (b) 링크드 워크트리 정당 작업 오탐 0, (c) 주인 통과, (d) 판정기 관측(양 구현 GUARD-* PASS, 변이 격추). 훈계(소환 규약 v3)가 세 번 잊혀 난 사고를 도구가 구조적으로 봉인 — **C038·C058의 "규율을 도구로 승격"의 안전판.**
