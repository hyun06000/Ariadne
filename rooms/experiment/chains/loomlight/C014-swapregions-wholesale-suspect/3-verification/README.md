# 3. 가설 검증

폴링 swapRegions 통스왑이 상태 파괴 근원임을 확정하고, 최소변경(열린 노드 보존)으로 고쳐 참조·Go에 이식.

## 수정 (참조 gil.py + Go main.go, swapRegions 바이트 동일)

`swapRegions`에 `hasOpenDetails(el)` 가드 추가: POLL_SEL 영역이 열린 `<details>`를 담고 있으면 `replaceChild`를 **건너뛴다**(`continue`). 열린 카드 노드의 정체성이 보존돼 DOM 런타임 상태(네이티브 토글·포커스·리스너)가 소실되지 않는다. 닫힌 영역은 여전히 갱신 → 실시간성 유지.

## 실측 결과 (헤드리스 CDP, 산출물 이 디렉토리)

| 측정 | 결과 |
|---|---|
| **원인 확정(probe.json)** | 수정 前: 폴링 후 chain-loom 노드 마커 소실 = `chainNodeReplaced:true` (통스왑이 노드 교체) |
| **M1 노드 보존(verify.json)** | 수정 後: `M1_nodePreserved:true` — 열린 카드 노드 살아남음 (참조·Go 동일) |
| **M2 데이터 갱신** | gil-data 갱신됨(1.34MB), 카드 열면 최신 |
| **M3 열림 유지** | `M3_stillOpen:true` |
| **데이터 변경(databreak.json)** | v1→v2 스왑: `openCardPreserved:true` + header `체인1개·101개`→`체인6개·124개` **갱신**. 열린 카드 보존 + 닫힌 영역 갱신 동시 성립 |
| **M4 conformance** | 참조 133/133·Go 110/110 회귀 0 |
| **M5 참조↔Go** | hasOpenDetails+swapRegions 바이트 동일 |
| **C011 회귀(c011reg.json)** | 데이터 변경 폴링 `loomOpen:true` 유지 |

## 재현 방법

```bash
GIL=rooms/deployment/ariadne-spec/gil.py
CDP=rooms/experiment/chains/loomlight/C014-swapregions-wholesale-suspect/3-verification
W=/tmp/c014; mkdir -p $W
# 노드 보존 확인
python3 $GIL web rooms/experiment/chains -o $W/viewer.html --refresh 3
( cd $W && python3 -m http.server 9002 >/dev/null 2>&1 ) &
python3 $CDP/cdp.py "http://127.0.0.1:9002/viewer.html" $CDP/verify.json
#   기대: {"M1_nodePreserved":true,"M3_stillOpen":true,...}
# 데이터 변경 시 열린 보존 + 닫힌 갱신
python3 $GIL web rooms/experiment/chains -o $W/v1.html --chain loom --refresh 3
python3 $GIL web rooms/experiment/chains -o $W/v2.html --refresh 3
cp $W/v1.html $W/viewer.html
( sleep 3.5 && cp $W/v2.html $W/viewer.html ) &
python3 $CDP/cdp.py "http://127.0.0.1:9002/viewer.html" $CDP/databreak.json
```

## 실행 기록

- 일시: 2026-07-20. 환경: darwin, 헤드리스 Chrome(CDP), Go /opt/homebrew/bin/go. gil v2.48.0 기반.
- **가설 억셉트**: 통스왑이 근원 확정(probe), 최소변경이 노드 보존(M1 참조·Go), 데이터 갱신 유지(M2·databreak), 회귀 0(M4·C011reg), 두 몸 바이트 동일(M5).
- **⭐ 리젝트 체인의 꽃**: C012(상호작용 배제)·C013(폴링 이분 막힘) 두 rejected 끝에서 얻은 가설(통스왑 의심)이, 내 손 안 계측기(JS 마커로 노드 정체성 관찰)로 검증돼 억셉트됐다. C012·C013이 못 잡던 "실브라우저에서만 보이던 것"의 아키텍처 근원(노드 교체=런타임 상태 소실)을 헤드리스로 특정·해결.
- **실브라우저 최종 확인은 다음(상현님 손)**: 헤드리스로 아키텍처 근원은 해결. 실브라우저 카드 닫힘이 이 축이면 함께 해결됐을 개연 크나, 그 최종 판정은 배포 후 상현님 확인.
