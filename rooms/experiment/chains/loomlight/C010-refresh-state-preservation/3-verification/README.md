# 3. 가설 검증

## 산출물

- `cdp.py` — stdlib만으로 짠 최소 Chrome DevTools Protocol 드라이버(raw WebSocket). 헤드리스
  Chrome을 띄우고 URL을 열어, JSON으로 기술된 step 시퀀스(`{"eval":...}`,`{"sleep_ms":...}`)를
  순차 실행해 각 eval 결과를 JSON으로 반환한다. **정적 페이지 리프레시가 상태를 파괴하는지는
  시간을 가로지르는 실측이 필요하고(§3.1), `--dump-dom` 한 장으로는 못 잡는다** — 그래서 CDP.
- `steps-1-repro-metarefresh.json` — **결함 재현(대조군)**: meta refresh 뷰어에서 details를 열고
  프로브를 심은 뒤 리프레시 주기 통과 → 프로브 소멸·details 리셋을 관측.
- `steps-2-poll-preserves-state.json` — **처치군**: 폴링 뷰어에서 체인 아코디언·사이클 스텝을 열고
  스크롤한 뒤, 폴링 주기 통과 → 열림·스크롤 유지를 관측.
- `steps-3-data-updates-through-poll.json` — **데이터 갱신**: 폴링 중 서빙 파일을 sentinel 주입본으로
  교체 → 폴링이 새 `#gil-data`를 반영(sentinel 등장)하며 동시에 열린 상태 유지를 관측.
- `verify.sh` — 구조 판정(meta 부재·폴링 마운트·외부 리소스 0) + 헤드리스 실측(2a)을 한 번에 도는 러너.

## 재현 방법

```bash
# 참조(gil.py)
cd <워크트리 루트>
bash rooms/experiment/chains/loomlight/C010-refresh-state-preservation/3-verification/verify.sh \
     "python3 $(pwd)/rooms/deployment/ariadne-spec/gil.py"

# Go (세션-로컬 격리 빌드)
GOB=$(mktemp -d); cp rooms/deployment/ariadne-spec/go/main.go $GOB/
( cd $GOB && /opt/homebrew/bin/go mod init gilgo && /opt/homebrew/bin/go build -o gil-go . )
bash rooms/experiment/chains/loomlight/C010-refresh-state-preservation/3-verification/verify.sh "$GOB/gil-go"

# conformance (회귀 0)
GILPY="python3 $(pwd)/rooms/deployment/ariadne-spec/gil.py"
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$GILPY"       # 128/128
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$GOB/gil-go"  # 110/110
```

## 측정 결과 (판정)

환경: macOS(darwin 25.5.0), Python3, Go1.x(/opt/homebrew/bin/go), Google Chrome headless=new.
서빙: `python3 -m http.server`(폴링 fetch는 same-origin 필요).

### M1 · 결함 재현 (meta refresh, 대조군) — **재현됨**
`steps-1` (viewer --refresh 3): 리프레시 통과 후
`{"afterRefresh_hasProbe":false, "firstDetailsOpen":false}` — 심은 프로브 details가 **소멸**하고
첫 details가 **닫힘**. 전체 문서 리로드가 DOM을 새로 씀을 실측으로 확인. **이것이 필드 결함이다.**

### M2 · 폴링 상태 보존 (처치군) — **통과**
`steps-2` (참조·Go 양쪽): 폴링 주기(3s)를 넘긴 4.2s 대기 후
`{"A_chainOpen":true, "A_step1Open":true, "A_cycbodyFilled":true, "A_scroll":420}`.
열린 체인 아코디언·사이클 스텝·스크롤이 **전부 유지**되고, 사이클 body는 새 data로 다시 채워짐.
meta refresh 대조군(M1)이 전부 리셋한 것과 정확히 대비된다.

### M3 · 데이터 갱신 through 폴링 — **통과**
`steps-3`: 폴링 도중 서빙 파일을 sentinel(`"SENTINEL":"POLLED_V2"`) 주입본으로 교체 →
`{"chainStillOpen":true, "sentinelInDom":"POLLED_V2"}`. 폴링이 새 `#gil-data`를 반영하면서도
열린 상태를 유지 — **실시간성과 상태보존이 동시에** 성립.

### M4 · 두 몸 한 계약 (참조↔Go) — **통과 (C010 표면)**
- 내가 추가한 폴링 JS 블록(`function detKey`~`startPolling`)이 참조·Go 산출물에서 **바이트 동일**
  (`cmp` 무출력, 62줄).
- 양쪽 다 meta refresh 부재·폴링 마운트 존재·외부 URL 0 (hierarchy·flat 모두).
- Go-baked 뷰어도 M2 실측을 동일 통과.
- **주의(정직)**: 전체 산출물 `cmp`는 여전히 갈리지만, 그 차이는 **C010 이전부터 존재한** `webCSS`↔
  `_WEB_CSS`의 pre-existing drift(pristine HEAD 빌드도 line 36에서 갈림)다. 내 변경이 낳은 것이 아니며
  refresh 표면 밖(C088 CSS 영역)이다. 이 사이클에서 고치지 않고 정직히 남긴다(§3.1·C036 절제).

### M5 · conformance 회귀 0 — **통과**
`WEB-REFRESH`·`WEB-REFRESH-DEFAULT`를 새 계약(meta 부재 + 폴링 마운트 + bake.refresh 기록 +
자기완결)으로 재정의. 참조 **128/128**, Go **110/110** — 이전(128/110) 대비 회귀 0.

## 기각 조건 대조

1. 폴링 후 details 닫힘/프로브 소멸 → **아님**(M2: 유지). 
2. 데이터 미갱신 → **아님**(M3: sentinel 반영).
3. 외부 리소스≠0 / 서버 필요 → **아님**(verify.sh: 외부 URL 0, same-origin 정적 fetch만).
4. parity/conformance 회귀 → **아님**(M4·M5: C010 표면 바이트 동일, 128/110 유지).

네 기각 조건 모두 미발동 → **가설 지지(supported).**
