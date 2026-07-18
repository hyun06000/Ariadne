# 1. 가설 수립

## 이전 사이클의 교훈

부모 loomlight/C002는 참조 구현(gil.py)에 opt-in 플래그 `--hierarchy`를 얹어
**체인 목록 → 체인 그래프 → 사이클 5스텝**의 3단 드릴다운을 JS 0줄(중첩 `<details>`)로 실현했다.
그러나 그 사이클은 Go 이식을 **"이 워크트리에 Go 툴체인이 없어 실측 불가"**라며 정직히
loomlight/C003으로 이월했다(C036·C050 절제). 그 결과 지금 참조는 `--hierarchy`를 알지만
Go는 모른다 — 두 몸이 능력 면에서 갈라진 상태다(C020 "두 몸 한 계약"의 부분 균열).

C002의 핵심 설계 원리: **opt-in 하위호환 = 관측 불가능한 변화.** `--hierarchy` 없는 기본
경로는 개선 전과 한 바이트도 다르지 않게 두었다(참조·Go 기본 출력이 이미 바이트 동일).

## 문제 분할

1. Go의 web 렌더 경로(`renderWebPage`·`webJSONPayload`·`buildWebData`)에 참조의
   위계 렌더 함수(`_render_hierarchy_body`·`_render_cycle_detail`·`_read_step`·`_WEB_HIER_CSS`)를
   **동형 이식**한다.
2. `--hierarchy` 플래그를 Go CLI·`webArgs`·`cmdWeb`·`bakeViewer`에 배선하고, `bakeMeta`가
   `bake.hierarchy`를 읽어 자동 재굽기(`refreshViewers`)가 위계를 잃지 않게 한다(C042 확장).
3. 스텝 파일을 찾기 위해 `buildWebData`가 cid→디렉토리명 매핑(참조의 `_dirs`)을 보존한다.

지금 정복할 첫 번째 문제: **위 셋 전부** — 위계는 opt-in이라 기본 경로를 건드리지 않으므로
한 사이클에 안전히 담긴다. 정복의 판정선은 "참조·Go의 `--hierarchy` 출력 바이트 동일".

## 가설

> **가설**: 참조의 위계 렌더 경로를 Go에 동형 이식하면, `gil web --hierarchy`의 산출물이
> **참조와 Go에서 바이트 동일**해지고(C020 복원), `--hierarchy` 없는 기본 출력·conformance는
> **회귀 0**으로 남는다(opt-in 계약).

## 기각 조건

- **기각 1**: 두 구현의 `--hierarchy` 출력이 `cmp`에서 한 바이트라도 다르다.
- **기각 2**: `--hierarchy` 없는 기본 출력이 개선 전 Go baseline과 바이트가 갈라진다(회귀).
- **기각 3**: Go conformance가 개선 전(78/78)보다 줄어든다.
- **기각 4**: 이 워크트리에서 Go 빌드가 실제로 되지 않는다(그러면 흉내내지 않고 정직히 이월, C053).
