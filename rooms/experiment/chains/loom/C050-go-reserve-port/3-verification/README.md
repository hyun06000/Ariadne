# 3. 가설 검증

이식 대상은 `rooms/deployment/ariadne-spec/go/main.go` 한 파일. 아래는 그 파일만으로
가설을 처음부터 재검증하는 정확한 명령 순서다.

## 재현 방법

```bash
SPEC=rooms/deployment/ariadne-spec

# 1) Go 빌드 (절대 경로 산출물 — C028·C043·C045의 상대경로 함정 회피)
cd "$SPEC/go" && GO111MODULE=off go build -o /tmp/gil-weft main.go
cd -

# 2) Go 판정: 73/73 목표
cd "$SPEC" && python3 conformance.py --gil "/tmp/gil-weft" | tail -1
#   → 계약 준수: 73/73  ✔ 이 구현은 gil이다
#   RESERVE-BASIC/-NEEDS-FOR/-NEEDS-CHAIN, OPEN-SKIPS-RESERVED, OPEN-PROMOTES-OWNER,
#   RESERVE-NON-INVASIVE, RESERVE-IN-LOG, UNRESERVE — 8항목 전부 PASS

# 3) 참조 구현 회귀 확인: 73/73 유지
python3 conformance.py --gil "python3 $(pwd)/gil.py" | tail -1
#   → 계약 준수: 73/73

# 4) 무예약 저장소 web 바이트 동일 (실 저장소 chains 사용)
CH=../../experiment/chains   # (스펙 디렉토리 기준 상대경로; 절대경로 권장)
/tmp/gil-weft web "$CH" -o /tmp/go-web.html
python3 gil.py       web "$CH" -o /tmp/ref-web.html
diff /tmp/go-web.html /tmp/ref-web.html && echo "WEB IDENTICAL"

# 5) 원장급 교차 검증 (reserve/open-승격/unreserve 생성물 바이트 동일)
#    씨앗 저장소(demo/C001-seed 닫힘)를 만들어 두 구현으로 각각 reserve→open 후
#    reservations.tsv·승격 cycle.yaml·web을 diff. (본 사이클 실행 스크립트는 5-report 참조.)
```

## 실행 기록

- 일시: 2026-07-15. 환경: macOS Darwin 25.2.0, Go(GO111MODULE=off), Python 3.9.6(표준 라이브러리).
- **Go 판정: 65/65 → 73/73.** 예약 8항목 전부 PASS, 퇴행 0.
- **참조 구현: 73/73 유지** (회귀 0 — 판정 항목이 구현 독립임을 재확인).
- **무예약 web: 바이트 동일** (실 저장소 loom·gateway·g4·tapestry 4체인, 36KB+ 전문 일치).
- **원장급 교차 검증 전부 동일**: reserve→reservations.tsv, open-승격→cycle.yaml + 원장 소거,
  unreserve→원장 제거, with-reservation log 섹션·web(카드+JSON) 모두 참조와 바이트 동일.
- `--git` 커밋 경로 스모크: `reserve --git`·`unreserve --git`이 참조와 같은 커밋 메시지
  (`gil: reserve demo/C002 → weft` / `gil: unreserve demo/C002`)로 각인, 트리 클린.

## 특이사항 — 무예약 log는 바이트 동일이 **아니다** (선재 결함, 내 소관 밖)

무예약 `log`는 참조와 바이트 다르다. 그러나 이는 이번 이식이 만든 차이가 **아니다**:
`/tmp/gil-weft-base`(이식 전 바이너리)의 무예약 log도 이미 참조와 달랐고, 내 변경 전후
Go log는 서로 **완전히 동일**하다(내 예약 섹션은 무예약이면 발동하지 않음). 차이의 정체는
Go `logCmd`가 애초에 참조 `render_graph`의 ASCII 트랙 그래프(`│ ├─┐ ┴` 등)와
`summarize()`(root·분기점·병합점 줄)를 이식한 적이 없다는 **선재 결함**이다 (C046에서 이미
summarize 부재를 관측·보고했고, 이번에 트랙 그래프 부재까지 확인). conformance LOG 계열이
exit 코드와 id 존재만 보므로 여러 사이클 동안 들키지 않았다("판정기가 안 보는 계약은 없다").
이식 범위(reserve/unreserve/open-예약인식)를 넘어서므로 **고치지 않고 보고**한다 — 다음
사이클의 재료.
