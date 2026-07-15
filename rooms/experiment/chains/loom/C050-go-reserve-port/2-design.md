# 2. 실험 설계

오직 가설 하나 — "reserve/unreserve/open-예약인식을 Go에 이식하면 65/65 → 73/73, 참조
회귀 0, 무예약 web/log 바이트 동일" — 만을 검증한다.

## 이식 대상 (참조 구현 gil.py → go/main.go, 문면 대조)

C020에서 배운 순서를 따른다: **코드를 쓰기 전에 참조의 문자면 특이점을 목록화하고 함수로
대응시킨다.** 역공학은 실행 전에 문면에서 끝내는 것이 싸다.

1. **예약 원장 헬퍼** (gil.py `_reservations_path`·`_load_reservations`·`_save_reservations`·
   `_RESERVATIONS_HEADER`): Go에 `reservation` 구조체 + `loadReservations`·`saveReservations`·
   `reservationsPath`. 형식은 `<번호> <for> <slug> <일자>` 공백 구분, 번호 오름차순, 빈
   목록이면 파일 삭제. 헤더 2줄 바이트 동일.
2. **nextNumber 예약 회피** (gil.py `_next_number(records, reserved_nums)`): Go `nextNumber`에
   예약 번호 슬라이스를 받는 인자 추가. `max(사이클 번호 ∪ 예약 번호) + 1`.
3. **cmdReserve** (gil.py `cmd_reserve`): --for(author) 필수·§3.2 P1 거부, 슬러그 검증, 체인
   존재 검증, fsck 게이트, 원장에 append + save, `_reserve_commit_push`로 커밋.
4. **cmdUnreserve** (gil.py `cmd_unreserve`): `C?0*(\d+)` 번호 파싱(44·044·C044), 없는 번호
   거부, 제거 후 save, 커밋.
5. **cmdOpen 예약 인식** (gil.py `cmd_open` 680~764): 저자 예약이 있으면 최저 번호로 승격
   (consumed), 없으면 예약 번호 회피 발급. 승격 시 post-fsck 후 원장에서 소거, git 경로에
   reservations.tsv 추가·커밋 메시지에 승격 주석, `push and not consumed`면 재번호 push /
   `elif push`면 평범 push.
6. **logCmd 예약 섹션** (gil.py `log_chain` 305~311): 결말 집계 뒤에 예약이 있을 때만
   "예약됨 …" 섹션. 무예약이면 출력 불변.
7. **web 예약 섹션** (gil.py `render_tables`·`render_web_page`): 예약 있을 때만 카드 + JSON
   `reservations` 키. 무예약이면 바이트 불변.
8. **commandTable 등록**: `reserve`·`unreserve`를 §7.2 단일 소스 테이블에 추가 → help·
   gil:commands 훅·미구현 신호·능력 탐침이 자동 파생. main() switch에 dispatch 추가.

## 핵심 검증 규율 — 예약은 사이클이 아니다

reservations.tsv는 cycle.yaml이 아니다. `loadChain`/`scanChains`는 `<entry>/cycle.yaml`만
record로 수집하므로 fsck·verify·log 그래프·web 그래프가 예약을 record로 보지 않는다. 이
비침습성을 파일 위치가 물리적으로 보증한다(RESERVE-NON-INVASIVE가 판정).

## 준비물

- Go 빌드: `cd <worktree>/rooms/deployment/ariadne-spec/go && GO111MODULE=off go build -o /tmp/gil-weft main.go`
- 판정: `cd <worktree>/rooms/deployment/ariadne-spec && python3 conformance.py --gil "/tmp/gil-weft"` (절대 경로 — C028·C043·C045의 함정).
- 환경: macOS Darwin 25.2.0, Go(GO111MODULE=off), Python 3.9.6(표준 라이브러리).

## 측정 방법

- **성공**: Go 73/73 AND 참조 73/73(회귀 0) AND 무예약 실저장소에서 Go web·log가 참조와
  `diff` 무차이. 추가로 reserve/open 승격 생성물이 참조와 바이트 동일(원장급 교차 검증, C036).
- **기각**: 위 기각 조건(1-hypothesis) 중 하나라도 참.

## 사용자 컨펌

- 생략 — 이식 대상·판정 방법이 소환 브리핑에 계약으로 고정되어 있고, 참조 구현이 정답이다.
