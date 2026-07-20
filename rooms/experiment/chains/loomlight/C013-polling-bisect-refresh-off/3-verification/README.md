# 3. 가설 검증

폴링 이분 격리. 층 (a) 내가 실행(폴링 끄기 유효성), 층 (b) 상현님 실브라우저 판정 대기.

## 층 (a) 결과 — `--refresh 0`은 폴링을 실제로 끈다 (내가 확정)

- **M2**: `gil web --refresh 0` 뷰어의 gil-data `bake.refresh=0`. startPolling은 `sec>0`일 때만 `setInterval(poll)`을 걸므로, refresh 0이면 폴링 미장착.
- **M1**: 헤드리스에서 8초 관찰 → `newFetches: 0`. 폴링(같은 URL 재fetch)이 실제로 안 돈다. (대조: C012에서 refresh 5는 7초에 fetch 2회.)
- → **격리 유효**: `--refresh 0`은 폴링을 확실히 끈다. 기각조건 2(refresh 0인데 폴링 돌면 무효) 방어됨.

## 층 (b) 재현 방법 — 상현님 실브라우저 (이분의 실제 판정)

헤드리스는 C012에서 원래 닫힘을 재현 못 하므로, 실판정은 실브라우저에서만 가능하다. 상현님이 실행:

```bash
# 저장소 루트에서 — github.io와 동일 코드(v2.48.0)에 폴링만 끈 뷰어
python3 rooms/deployment/ariadne-spec/gil.py web rooms/experiment/chains -o /tmp/noref.html --refresh 0
open /tmp/noref.html   # 실브라우저로 열림
# → 카드(체인/사이클 상세)를 열고 30초~1분 가만히 둔다. 닫히는가?
```

- **닫힘이 멈추면** → 폴링이 유일 범인(억셉트). 다음 사이클: 헤드리스가 못 잡는 폴링 부작용.
- **여전히 닫히면** → 폴링 무관(기각). 다음 사이클: CSS·브라우저 축.

## 실행 기록

- 일시: 2026-07-20. 환경: darwin, 헤드리스 Chrome(층 a). gil v2.48.0.
- **층 (a) 완료**: `--refresh 0` = 폴링 0회, 격리 유효 확정.
- **층 (b) 대기**: 상현님 실브라우저 판정이 이분의 답. 이 데이터만이 "폴링이 범인이냐"를 가른다 — 내 헤드리스로는 원래 재현 불가라 판정 불가.
