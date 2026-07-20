# 3. 가설 검증

`detKey` 버그를 참조·Go에 고치고, 데이터 변경 폴링에서 카드 보존을 헤드리스 CDP로 실측했다.

## 수정 (참조 gil.py + Go main.go, detKey 바이트 동일)

`detKey`의 두 결함을 고침:
1. `if(d.id) return "#"+d.id;` — id 가진 details(체인 카드 `#chain-*`·마운트 `#cycdoc-*`)는 id 자체를 키로. 순번 계산 안 함(자기 자신이 scope가 돼 idx=-1로 뭉개지던 근본 버그 제거).
2. id 탐색을 `d.parentNode`부터 — id 없는 details의 '가장 가까운 id **조상**'을 찾는다(자기 제외). 키 접두 `#`(id) vs `@`(조상+순번)로 구분.

## ⚠️ 검증 과정의 정직한 기록 — 테스트 착시에 두 번 속았다

이 사이클의 검증은 **매끄럽지 않았다**. 초기 재현 스크립트가 `document.querySelector('details.hchain')`로 카드를 추적했는데, 데이터 변경 폴링으로 `.mapchains`가 스왑되면 **querySelector가 문서 첫 카드(chain-gateway, 원래 안 열린 것)를 가리켜** `POST_chainOpen:false`가 나왔다. 이를 "수정 실패(가설 반증)"로 오독했다. **실제로는 loom 카드는 살아 있었다** — `document.getElementById('chain-loom')`로 콕 집어 추적하니 `POST_loomOpen:true`.

교훈: **재현 스크립트도 실험의 일부이고, 잘못된 선택자는 잘못된 반증을 만든다.** 상현님이 지적한 "진단이 추적 밖이면 오진을 낳는다"가 이 사이클에서 실물로 증명됐다 — 애드혹 진단이 두 번(detKey 순번 착시 + querySelector 착시) 헤맸다. 이 반성이 방법론 사이클(gateway 새 체인)의 재료다.

## 재현 방법

```bash
# 저장소 루트. 수정된 gil로 두 버전 뷰어(폴링 중 파일 교체로 데이터 변경 모사).
GIL=rooms/deployment/ariadne-spec/gil.py
W=/tmp/c011-verify; mkdir -p $W
python3 $GIL web rooms/experiment/chains -o $W/v1.html --refresh 3
python3 $GIL web rooms/experiment/chains -o $W/v2.html --refresh 3
cp $W/v1.html $W/viewer.html
CDP=rooms/experiment/chains/loomlight/C011-polling-detkey-fix/3-verification

# M1·M2 데이터 변경 폴링에서 카드 보존 (id 추적 — 착시 없는 판정)
( cd $W && python3 -m http.server 8993 >/dev/null 2>&1 ) &
( sleep 3.5 && cp $W/v2.html $W/viewer.html ) &   # 폴링 직전 데이터 교체
python3 $CDP/cdp.py "http://127.0.0.1:8993/viewer.html" $CDP/steps-databreak-byid.json
#   기대: {"POST_loomOpen":true,"loomExists":true}

# M4 동일 데이터 폴링 회귀 (C010 케이스)
python3 $CDP/cdp.py "http://127.0.0.1:8993/viewer.html" $CDP/steps-samedata-preserve.json
#   기대: POST open: ["chain-loom"]

# M5 회귀
python3 rooms/deployment/ariadne-spec/conformance.py --gil "python3 $(pwd)/rooms/deployment/ariadne-spec/gil.py" | tail -1  # 128
# Go: 세션-로컬 빌드 후 conformance.py --gil <go> → 110
```

## 실행 기록

- 일시: 2026-07-20. 환경: darwin 25.5.0, Python 3, Go /opt/homebrew/bin/go, Chrome headless(CDP).
- **M1·M2 데이터 변경 폴링 (id 추적)**: 참조 `{"POST_loomOpen":true,"loomExists":true}`, Go 동일. **카드·상세 보존 확인** — detKey 수정이 실제 필드 결함을 고쳤다.
- **M3 detKey 진단**: 수정 후 id 가진 카드 키가 `#chain-loom`으로 안정(스왑 전후 동일). 옛 `chain-loom#-1` 뭉갬 제거.
- **M4 동일 데이터 폴링 회귀**: `POST open: ["chain-loom"]` — C010이 통과시킨 케이스 유지.
- **M5 conformance**: 참조 128/128·Go 110/110 유지.
- **M6 detKey 참조↔Go**: 블록 바이트 동일(cmp True).
- **착시 기록**(위 ⚠️): 초기 querySelector 기반 스크립트가 `POST_chainOpen:false`로 잘못 반증을 냈으나, id 추적으로 실체(카드 보존됨) 확정. 재현 스크립트 자체가 실험의 일부.
