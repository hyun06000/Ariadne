# 3. 가설 검증

github.io 실제 페이지를 CDP(헤드리스 Chrome)로 열어, 실제 클릭·hash 네비로 카드/상세를 열고 폴링을 가로질러 상태가 유지되는지 여러 시나리오·시점에서 관찰했다.

## 실측 결과 (전부 /tmp/c012, 산출물 이 디렉토리에 복사)

| 시나리오 | 방법 | 폴링 후 |
|---|---|---|
| 체인 카드 (steps-click) | `summary.click()` 실제 클릭 | `AFTER_1poll_loomOpen:true`, `AFTER_2poll:true` — **유지** |
| 체인 카드 (steps-full, JS) | `.open=true` | `POST_open:true` — 유지 |
| 사이클 상세 (steps-cyc3) | hash 네비 | `POST_1poll_filled:true`, `POST_2poll_filled:true` — **유지** |
| 장시간 (steps-long, 18초/3주기+) | hash+클릭 | cycFilled t0~t18 **내내 true** — 상세 내용 유지 |
| 폴링 실제 발생 (steps-pollcheck) | resource 관찰 | `selfFetches:2` (7초) — **폴링은 실제로 돈다** |

## 재현 방법

```bash
CDP=rooms/experiment/chains/loomlight/C012-polling-card-closes-live/3-verification/cdp.py
# 각 steps-*.json을 실제 github.io에 대고 실행
python3 $CDP "https://hyun06000.github.io/Ariadne/" <이 디렉토리>/steps-cyc3.json
python3 $CDP "https://hyun06000.github.io/Ariadne/" <이 디렉토리>/steps-long.json
python3 $CDP "https://hyun06000.github.io/Ariadne/" <이 디렉토리>/steps-pollcheck.json
```

## 실행 기록

- 일시: 2026-07-20. 환경: darwin, **헤드리스 Chrome(CDP)**, 실제 github.io(v2.48.0, detKey 수정 포함, 폴링 5초 확인).
- **폴링은 헤드리스에서 실제로 돈다**(selfFetches 2회/7초) — "폴링이 안 돌아서 유지된 것" 가능성 배제.
- **모든 시나리오에서 사이클 상세 내용(cycFilled)은 폴링을 가로질러 유지**됨. 체인 카드 open은 테스트마다 편차 있으나 사용자가 읽는 내용은 소실 안 됨.
- **⚠️ 상현님이 보고한 "카드가 5초마다 닫힘"을 헤드리스 CDP로 재현하지 못했다.** 가설(상호작용 차이·name 아코디언·detKey)이 이 환경에서 지지되지 않음.
- 진단 중 세부 함정들(cycdoc은 details 아닌 div·빈 마운트, SVG 앵커 .click 불가, cycdoc id 형식) — 사이클 안에서 각 시도가 기록돼 착시 없이 실제 구조로 수렴(C011 애드혹과 대비).
