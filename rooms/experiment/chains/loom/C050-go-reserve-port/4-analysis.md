# 4. 결과 분석

## 통계적 결과

| 측정 | 기준값 | 결과 | 판정 |
|---|---|---|---|
| Go conformance | 73/73 | **73/73** (65/65 → 73/73) | ✅ |
| 예약 8항목 | 전부 PASS | RESERVE-BASIC·-NEEDS-FOR·-NEEDS-CHAIN·OPEN-SKIPS-RESERVED·OPEN-PROMOTES-OWNER·RESERVE-NON-INVASIVE·RESERVE-IN-LOG·UNRESERVE 전부 PASS | ✅ |
| 참조 구현 회귀 | 73/73 유지 | **73/73** | ✅ 회귀 0 |
| 무예약 web 바이트 동일 | diff 0 | 실 저장소 4체인 WEB IDENTICAL | ✅ |
| 무예약 log 바이트 동일 | diff 0 | **불일치** — 그러나 선재 결함 (아래) | ⚠ 범위 밖 |
| 원장급 교차 검증 | 바이트 동일 | reserve·open-승격·unreserve·with-resv log/web 전부 동일 | ✅ |

**65/65 → 73/73의 메커니즘**: 브리핑이 예고한 함정 그대로였다. 이식 전 Go는 reserve를
훅에 나열하지 않아 판정기가 `if "reserve" in claimed:` 게이트에서 8항목을 통째로 건너뛰고
65/**65**로 계산했다. commandTable에 `reserve`·`unreserve`를 등록하는 순간 gil:commands
훅이 두 명령을 나열했고, 판정기가 8항목을 **실제로 실행**하기 시작해 분모가 73으로 늘었다.
분자도 8 늘어 73/73. 즉 이 사이클은 점수판의 분모와 분자를 동시에 움직였다.

## 데이터 직접 관찰

- **원장급 동일의 근거를 아티팩트에서 직접 읽었다** (기억이 아니라 — C020의 교훈). reserve
  생성물 `reservations.tsv`가 헤더 2줄 + `2 weft alpha 2026-01-03`까지 바이트 동일. 헤더
  문자열을 참조의 `_RESERVATIONS_HEADER` 두 조각 이어붙임 그대로 Go 상수로 옮긴 것이 적중.
- **open 승격의 세 부작용이 모두 동일**: (1) 예약자(weft)가 열면 C002로 태어나고(자동증가
  C003이 아니라), (2) 승격 cycle.yaml이 참조와 바이트 동일, (3) 원장의 마지막 줄이 사라지며
  파일이 삭제됐다(빈 목록 = 파일 삭제 규약). 선점(clew가 열면 C003, 예약 잔존)과 승격(weft가
  열면 C002, 예약 소거)의 분기가 `consumed` 포인터 하나로 갈렸다.
- **비침습성이 파일 위치로 보증됨을 재확인**: `reservations.tsv`는 `<entry>/cycle.yaml`이
  아니므로 `loadChain`/`scanChains`가 record로 수집하지 않는다. 그래서 예약이 있어도 fsck
  위반 0, log 계보 줄에 `C002-pending ←` 없음. 코드로 막은 게 아니라 **데이터의 거처**가
  막았다.

## 예상과 달랐던 것

1. **무예약 log 바이트 동일이 처음부터 성립하지 않았다.** 브리핑은 "무예약 web/log 바이트
   동일 유지"를 요구했으나, 이식 전 바이너리(`gil-weft-base`)의 무예약 log조차 참조와
   달랐다. 내 변경 전후 Go log는 서로 완전히 동일 → **내가 만든 차이가 아니다.** 정체는 Go
   `logCmd`가 참조 `render_graph`의 ASCII 트랙 그래프와 `summarize()`를 애초에 이식한 적이
   없다는 **선재 결함**이다. C046에서 summarize 부재를 이미 보고했는데, 이번에 트랙 그래프
   부재까지 드러났다. conformance LOG 계열이 exit·id만 보므로 C012 이래 들키지 않았다 —
   "판정기가 안 보는 계약은 없다"(C036)의 또 다른 얼굴. **web은 바이트 동일한데 log만
   다른** 비대칭이 이 선재 결함을 정확히 국소화한다(web 렌더러는 완전 이식됐고 log 렌더러만
   반쪽이었다). 이식 범위 밖이라 고치지 않고 보고한다.

2. **소환 절차 사고 — 잘못된 디렉토리에서 open.** 워크트리(`.claude/worktrees/…`)가 아니라
   `cd`로 메인 저장소 루트(`main` 브랜치 체크아웃)에 들어가 `gil open --git --push`를 실행해,
   C050 open 커밋이 `main`에 얹혀 origin/main으로 push됐다. 즉시 발견해 (a) 내 워크트리 브랜치를
   그 커밋으로 fast-forward, (b) 브랜치를 자기 원격 ref로 push + upstream 재지정(이후 --push는
   내 브랜치로만 감), 했다. origin/main 복원(force-with-lease로 876ad11 되돌리기)은 하네스가
   차단 — 우회하지 않고 보고한다(C014·C017의 규율: 막히면 정직히 보고). 교훈: **cwd도 환경
   계약이다**(C020의 "호출자의 cwd도 환경 계약"의 재발·확장) — 워크트리에서는 절대 메인
   저장소로 cd하지 말 것.

## 판정

**가설 채택 (supported).** 세 조각(reserve·unreserve·open-예약인식)을 문면 이식해 Go가
65/65 → 73/73에 도달했고, 참조 회귀 0, 예약 관련 생성물이 전부 원장급으로 참조와 바이트
동일하다. 기각 조건 3개 중 참인 것 없음(무예약 web 동일; log 차이는 선재 결함으로 기각
조건의 "예약이 비침습적이지 않다"에 해당하지 않음 — 예약은 log 그래프·web 그래프·fsck·
verify 어디에도 record로 들어가지 않았다). 두 구현이 무수정 판정기에서 **나란히 73/73** —
C020·C036에 이은 완전 계약 병렬의 세 번째 지점이자, 예약 8항목까지 포함한 첫 지점.
