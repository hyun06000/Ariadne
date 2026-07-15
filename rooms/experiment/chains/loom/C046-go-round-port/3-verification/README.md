# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 모든 것을 저장한다: 코드는 저장소 루트의 `go/main.go` 자체
(격리 워크트리 규율 — 검증 산출물은 이 사이클 디렉토리 안에만, 코드는 정식 위치에 커밋됨),
스크립트·실행 로그·연산 결과는 `runs/`에.

## 재현 방법

```bash
bash reproduce.sh
```

`reproduce.sh`는 (1) Go 바이너리 빌드, (2) 참조 구현 conformance, (3) Go 바이너리 conformance,
(4) 실 저장소 web 바이트 비교를 순서대로 실행한다. `--gil`에는 절대경로를 준다 — 상대경로를
주면 판정기 샌드박스의 cwd에서 구현을 못 찾아 전량 FAIL한다(C028·C043·C045가 문서화한 함정).

## 실행 기록

- 환경: macOS Darwin 25.2.0, Python 3.9.6(표준 라이브러리만), Go(표준 라이브러리만, 외부
  의존성 0).
- 실행 일시: 2026-07-15.

## 저장된 산출물 (`runs/`)

- `conformance-reference.txt` — 참조 구현(gil.py) 전체 conformance 로그. **72/72**.
- `conformance-go.txt` — 이식된 Go 바이너리 conformance 로그. **64/64**.
- `diff-reference-vs-go.txt` — 두 로그의 항목 단위 diff. 차이는 정확히 **RESERVE-\* 8항목**
  뿐이다 — ROUND-\* 8항목·FSCK-R15는 양쪽 모두 PASS(diff 없음). 예약(reserve/unreserve)은
  Go에 전혀 이식되어 있지 않으며, 이 사이클의 이식 대상(부모 C045가 지시한 5개 계약면)이
  아니다 — 라운드와 무관한, 이전부터 있던 별개 공백이다.
- `round-smoke-log.txt` — `gil round --open/--close/--list`를 참조 구현·Go 양쪽에서 같은
  입력으로 실행한 로그. 생성물(hypothesis.md·round.yaml·cycle.yaml)이 **바이트 단위 동일**함을
  `diff -r`로 확인. 부록으로 log 출력(`· R2` 배지) 비교도 포함 — Go의 `root:`/분기점/병합점
  요약 줄 부재는 **이 사이클 이전부터 있던, round와 무관한 별개 공백**임을 이식 전 바이너리
  (`gil-orig`, C045 릴리스 시점 빌드)로 교차 확인했다(같은 diff가 이식 전에도 재현됨).
- `web-byte-check.txt` — 실 저장소(rooms/experiment/chains)에서 Go web과 참조 web을 구워
  비교. `--chain genesis`(무라운드·무예약)로 좁힌 비교와 전체 저장소 비교 모두 **바이트
  동일**. 전체 비교가 동일한 이유: 이 사이클을 `gil open --parent C045-round-first-class`로
  열면서 예약 원장(`loom/reservations.tsv`)의 예약 46(`weft go-round-port`)이 실제 사이클로
  승격되어 원장 자체가 소거됐기 때문 — 예약 미이식(Go의 별개 공백)이 우연히 이 시점에는
  드러나지 않는다. (이식 전 상태에서는 예약 카드 렌더링 차이로 실 저장소 diff가 있었음을
  별도로 확인했었다 — 라운드 이식과는 무관한 gap이라는 것이 핵심.)

## 결과 요약

| 항목 | 결과 |
|---|---|
| ROUND-OPEN | PASS |
| ROUND-PREREG (H1: hypothesis가 verification보다 먼저) | PASS |
| ROUND-OPEN-GIT (커밋에 verification 없음) | PASS |
| ROUND-CLOSE-VERDICT (6-어휘, H2) | PASS |
| ROUND-REJECT-VOCAB | PASS |
| ROUND-CLOSED-CYCLE (불변 보호) | PASS |
| ROUND-LIST-SAFE (무해 조회) | PASS |
| FSCK-R15 | PASS |
| 실저장소 web 바이트 동일 (하위호환) | 확인 |
| conformance 총계 | **64/64** (참조 72/72 — 차이는 예약 8항목, 이번 이식 범위 밖) |

가설의 라운드 관련 부분(1~4의 검증)은 완전히 성립한다. 다만 1-hypothesis.md의 "72/72" 기각
조건은 문자 그대로는 미달이다 — 4-분석에서 그 원인(예약 미이식)을 규명하고 5-보고에서
투명하게 기록한다.
