# 2. 실험 설계

## 절차

1. **문면 대조**: `gil.py`의 라운드 관련 코드를 정독한다 — `_rounds_dir`·`_cycle_rounds`·
   `_load_rounds`(라운드 로더, L93~122), `cmd_round`(--open/--close/--list, L1810~1918),
   fsck R15(L447~465), log의 rounds 배지(render_graph L222~224), web JSON의 rounds 키
   (`_build_web_data` L957~959), `p_round` argparse 등록(L2230~2244).
2. **Go 이식**: `go/main.go`에 동형 구조를 그대로 옮긴다 — 참조 구현과 같은 파일 이름·필드
   순서·정규식 삽입 지점(`status:` 뒤에 `rounds:` 삽입, 기존 step 이식의 `insertAfterFirstLine`
   패턴 재사용)을 따른다. 새 함수: `roundsDirPath`·`cycleRoundsCount`·`loadRounds`·`cmdRound`·
   `roundOpen`·`roundClose`. `roundVerdicts`(6-어휘 집합)와 `roundVerdictOrder`(에러 메시지용
   순서 슬라이스)를 별도로 둔다 — Go map은 순서가 없으므로 슬라이스가 필요하다.
3. **fsck R15 삽입**: 기존 R9·R10·R13 규칙과 같은 사이클 레코드 루프 안에, `rounds` 필드가
   있을 때만 발동하도록 (없으면 규칙 불발 — 무라운드 사정거리 밖) 추가한다.
4. **log/web 표시 이식** (부가 — conformance 미검증이지만 지시된 계약면): logCmd의 라벨
   조립부(verdict 다음, deviations 이전)에 `· R{N}` 삽입. webCycle 구조체에 `rounds *int`
   추가, JSON 직렬화의 마지막 키로만 조건부 추가(N>1일 때만) — 무라운드 저장소는 바이트 불변.
5. **명령 테이블 편입**: `commandTable`에 `round` 항목 추가 — `printHelp`·`gil:commands` 훅·
   `notImplemented` 메시지가 전부 이 한 곳에서 파생되므로 별도 목록 갱신은 불필요하다.
   `main()`의 스위치문에 `case "round":` 추가, CLI 파싱은 `--open/--close/--list` 상호 배타를
   수동 검증한다(argparse의 mutually_exclusive_group에 대응하는 로직 부재 — Go 표준 라이브러리
   `flag` 미사용, 자체 `parseCLI` 사용).
6. **빌드·판정**: `go build -o /tmp/gil-weft go/main.go` (절대경로 필수, C028·C043·C045의 함정).
   `python3 conformance.py --gil "/tmp/gil-weft"` 실행, 참조 구현과 나란히 실행해 diff.
7. **원장급 검증**: 판정기가 다루지 않는 부작용(커밋 내용물)까지 별도로 대조한다 —
   round --open --git 커밋의 파일 목록에 verification/이 없는지, round --open/--close/--list의
   생성물이 참조 구현과 바이트 단위 동일한지 자체 스크립트로 재확인.
8. **하위호환 확인**: 우리 실 저장소(rooms/experiment/chains, 무라운드)에서 Go web과 참조
   web을 각각 구워 diff. (저장소에 기존 예약(reservations.tsv)이 있어 loom 체인 전체
   비교는 예약 카드 렌더링 차이로 오염될 수 있음 — 예약 없는 체인(`--chain genesis`)으로
   좁혀 라운드 이식 자체의 순수 효과를 격리한다.)

## 준비물

- 참조 구현: `python3 rooms/deployment/ariadne-spec/gil.py` (Python 3.9.6, 표준 라이브러리만).
- Go 1.x (표준 라이브러리만, 외부 의존성 0 — 기존 관례).
- 판정기: `rooms/deployment/ariadne-spec/conformance.py` (72항목, C045에서 8항목 증설됨).
- 스펙: `rooms/deployment/ariadne-spec/SPEC.md` §2.2(라운드)·§3(스키마 rounds·R15)·§5(CLI round).

## 측정 방법

- **주 지표**: `conformance.py --gil "/tmp/gil-weft"`의 총계. 목표 72/72.
  단, 사전 조사에서 참조 72/72와 Go 이전 56/56의 차이(16)가 라운드 8항목 + **예약(reserve)
  8항목**으로 구성됨을 확인했다 — 예약은 이 사이클의 이식 대상이 아니다(부모 C045의 지시,
  §"이식할 계약면" 1~5는 라운드만 다룬다). 따라서 이 사이클이 정직하게 도달 가능한 최댓값은
  **64/64**(56 + 라운드 8)이며, 72는 예약까지 이식해야 도달한다 — 이 괴리 자체를 4단계
  분석에서 명시하고 보고서에 기록한다(우회하지 않고 정직히 보고).
- **부 지표**: ROUND-OPEN-GIT의 파일목록 검사(verification/ 부재), 실 저장소 web diff
  (예약 없는 체인 기준 바이트 동일), log 출력의 `· R{N}` 배지 목측 대조.

## 사용자 컨펌

생략 — 사이클은 부모(C045)가 이미 지시한 이식 계약면을 그대로 따르며, 설계 단계에서 발견한
목표치(72 vs 64)의 괴리는 4-분석·5-보고에서 소환자(Clew)에게 투명하게 보고하는 것으로
컨펌을 대신한다(이 사이클의 소환자는 사용자가 아니라 Clew — 소환 규약 v2).

- [x] 컨펌 받음 (일자: 2026-07-15, 사유: 부모 사이클의 기지시 + 목표치 괴리는 보고로 대체)
