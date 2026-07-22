# 4. 결과 분석

## 통계적 결과

| 측정 | 기준(성공) | 실측 | 판정 |
|---|---|---|---|
| M1 V3-OPEN-CREATE | v3 open→steps.yaml·루트 define·s1.md | PASS | **PASS** |
| M2 V3-OPEN-REJECT-EXISTING | 이미 있는 사이클에 v3 open 거부 | PASS | **PASS** |
| M3 V3-RETIRE-GUIDANCE | v2 습관 open(게이트 없이)→은퇴 안내 exit≠0 | PASS | **PASS** |
| M4 무회귀 | 기존 134 안 깨짐 (게이트 상속 총 137) | 137/137 ✔ | **PASS** |
| M5 v3 게이트-독립 | 게이트 없이 v3 3항목 초록 | **첫 v2 항목서 crash** — v3 항목 도달 못함 | **부분** |

baseline 134 → **137/137**(순증 +3, 회귀 0). 배포판 적용 후 재확인 137/137 ✔.

## 데이터 직접 관찰

**v2 OPEN-\* 계약의 v3 행방 매핑 (상현님 "v2를 버린다"의 정직한 이전표):**

| v2 계약 | v3에서 어디로 | 교체 가능? |
|---|---|---|
| OPEN-CREATE (cycle.yaml+5문서) | steps.yaml + 루트 define s1 | **교체** → V3-OPEN-CREATE (신규함) |
| OPEN-INCREMENT (번호 C001→C002) | **경로가 정체** — v3 open은 번호 개념 없음 | 대응물 없음. 사이클-간 번호는 cycle.yaml/notes 층 |
| OPEN-REJECT-SLUG (슬러그 규칙) | dir 경로엔 슬러그 규칙 없음 | 대응물 없음 |
| OPEN-AUTHOR-REQUIRED (§3.2 P1) | v3 open은 --author 안 받음 | 대응물 없음. 저자는 커밋 trailer/cycle.yaml |
| OPEN-PARENT-REQUIRED/-CLOSED-GATE (C097) | v3 사이클-간 부모는 notes/cycle.yaml 층 | 대응물 없음(사이클-내 open엔) |
| OPEN-NEW-ROOT/-ROOT-CONFLICT | v3 루트 = s1 define 자체 | 대응물 없음 |
| GUARD-\* 5항목 (C050 안전) | 버전 무관 병렬 안전 — v3 open에도 필요 | 이전(검증)이 옳으나 v3 open은 아직 guard 미부착 |

**핵심**: v2 open은 **사이클-간**(번호·저자·부모 계보) 계약을 다뤘고, v3 open은 **사이클-내**(스텝 트리 시작) 계약만 다룬다. 이 둘은 다른 층이다 — v3에서 사이클-간 정보는 cycle.yaml·notes로 이동했다(migrate가 읽는 그 층). 그래서 OPEN-* 16항목 대부분은 v3 open으로 1:1 교체할 대응물이 없다.

**M5 crash 실물:**
```
FileNotFoundError: .../open/rooms/experiment/chains/demo/C001-first-step/cycle.yaml
```
게이트 없이 첫 v2 open(OPEN-CREATE 테스트)이 사이클을 못 만들자, 바로 뒤 `_seal_closed`가 cycle.yaml을 못 읽어 예외. conformance.py는 순차·예외 미처리라 **파일 끝의 v3 3항목이 실행조차 안 된다.**

## 예상과 달랐던 것

1. **"OPEN 16항목을 v3로 교체"가 대부분 "교체할 대응 계약이 없다"였다.** 설계 전 은연중 v2 OPEN 항목마다 v3 짝이 있으리라 가정했으나, 코드 실측이 뒤집었다. v2 open과 v3 open은 **다른 층의 명령**(사이클-간 vs 사이클-내)이다. 이는 C032 "인터페이스 정체성 전환"이 conformance 층에서 재확인된 것 — 승격은 함수 교체가 아니라 모델 전환이라 계약도 1:1 대응이 안 된다.

2. **판정기의 v2 결합이 open보다 깊었다(M5).** open 항목만 v3로 옮기면 게이트 없이 초록일 줄 알았으나, 첫 v2 open crash가 **전체 순차 실행을 무너뜨려** v3 항목조차 실행 안 됐다. 완전 버전리스(게이트 없이 초록)는 v3 항목 추가만으로 안 되고, **판정기가 v2 open crash에 견디거나(예외 격리) v2 항목을 실제 제거**해야 함. 다음 카브의 정확한 좌표.

## 판정

**가설 채택 (supported, 부분).** 기각조건 대조:

- 기각조건 1 (v2 결합이 open보다 깊음)? **참 — 그러나 반증 아니라 분할 경계의 실증(M5).** 게이트 없이 첫 v2 open서 crash. "게이트 없이 초록"은 이 조각으로 불충분하나, 그것이 **다음 카브의 정확한 좌표**를 찍었다(판정기 예외 격리 or v2 항목 제거). C032와 같은 패턴: 분할이 틀린 게 아니라 경계가 실측됐다.
- 기각조건 2 (GUARD 이전이 신규 구현이 됨)? **회피** — GUARD 이전은 이 카브 밖으로 정직히 이월(v3 open guard 미부착 확인, 별도 카브).
- 기각조건 3 (게이트 환경서 안내 안 나옴)? **아님** — V3-RETIRE-GUIDANCE가 게이트를 명시적으로 끈 env로 호출해 은퇴 안내 검사, PASS.
- 기각조건 4 (총 초록 줄어듦)? **아님** — 134→137 순증, 회귀 0.

**핵심 결론**: conformance에 **v3 쓰기 계약의 첫 판정 항목 3개**가 섰다(순증, 무회귀). 판정기가 이제 v3 open·은퇴 안내를 검사한다 — 상현님 "겁내지 말고 v3 위주로"의 첫 실현. 동시에 **완전 버전리스의 다음 관문**이 실측으로 드러났다: v2 계약을 실제 제거하거나 판정기를 v2 crash에 견디게 해야 게이트가 사라진다. C033은 v3 계약을 세우고(순증) 그 관문의 좌표를 정확히 찍었다 — 삭제는 대응 검증 후(작은 확실함).
