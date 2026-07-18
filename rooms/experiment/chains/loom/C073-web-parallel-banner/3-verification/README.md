# 3. 가설 검증

코드는 `gil.py`(`_render_parallel_banner` + 두 본문 배선 + `.parbanner` CSS)·`go/main.go`(동형 이식)·`conformance.py`(`WEB-PARALLEL-BANNER`)에. 여기엔 산출물·결과·재현 절차.

## 산출물

- `demo-banner-with-reservation.html` — 예약 1건 픽스처를 `gil web`으로 구운 실제 뷰어. 상단에 병렬 배너.
- `demo-banner-snippet.txt` — 렌더된 배너 HTML 조각.
- `results.txt` — conformance(참조 98/98·Go 84/84) + parity 3경우 결과.

## 재현 방법

```bash
G=rooms/deployment/ariadne-spec/gil.py
C=rooms/deployment/ariadne-spec/conformance.py
GO=rooms/deployment/ariadne-spec/go

# 1. Go 빌드
(cd $GO && GO111MODULE=off go build -o /tmp/gil-go main.go)

# 2. 판정기 — 양 구현 (참조 98/98, Go 84/84, WEB-PARALLEL-BANNER 포함)
python3 $C --gil "python3 $(pwd)/$G"
python3 $C --gil "/tmp/gil-go"

# 3. parity — 예약 있는 픽스처 만들고 참조↔Go 바이트 대조
mkdir -p /tmp/fx/rooms/experiment/chains/demo/C001-a
printf 'id: C001-a\nchain: demo\nparent: null\nlineage: []\nauthor: fx\nstatus: closed\nopened: 2026-01-01\nclosed: 2026-01-02\ntitle: "t"\n' > /tmp/fx/rooms/experiment/chains/demo/C001-a/cycle.yaml
printf '# Chain: demo\n' > /tmp/fx/rooms/experiment/chains/demo/chain.md
printf '# hdr\n5 weft newthing 2026-07-19\n' > /tmp/fx/rooms/experiment/chains/demo/reservations.tsv
python3 $G web /tmp/fx/rooms/experiment/chains -o /tmp/r.html; /tmp/gil-go web /tmp/fx/rooms/experiment/chains -o /tmp/g.html
cmp /tmp/r.html /tmp/g.html   # 바이트 동일

# 4. 무예약이면 배너 부재 (main에서)
python3 $G web -o /tmp/m.html && grep -c 'role="status"' /tmp/m.html   # → 0
```

## 측정 결과

| 측정 | 기준 | 결과 |
|---|---|---|
| WEB-PARALLEL-BANNER (참조) | 예약0 부재·예약1 출현+표기 | PASS |
| WEB-PARALLEL-BANNER (Go) | 동일 | PASS |
| 참조 conformance | 회귀 0 | 98/98 (97+1) ✔ |
| Go conformance | 회귀 0 | 84/84 (83+1) ✔ |
| parity 무예약(main) | 바이트 동일 | ✔ |
| parity 예약 위계 | 바이트 동일 | ✔ |
| parity 예약 평면(--flat) | 바이트 동일 | ✔ |

## 실행 기록

- 일시: 2026-07-19. 환경: darwin, Python 3, Go(/opt/homebrew, `GO111MODULE=off`). gil 2.25.0 기반.
- 특이사항: web은 양 구현에 있어 WEB-PARALLEL-BANNER가 참조·Go 모두에 적용(threads와 달리 Go 부재 아님). 배너 CSS(3규칙)는 항상 존재하나 배너 div는 예약 유무로 토글 → 예약 0이면 div 부재.
