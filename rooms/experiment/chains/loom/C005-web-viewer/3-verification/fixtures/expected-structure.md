# 기대 구조 (정답 고정)

> ⚠️ 이 문서는 **구현 전**에 고정되었다 (2026-07-14). 도구 출력에 맞춰 수정 금지.
> 내장 JSON의 위치: `<script type="application/json" id="ari-data">`. 집합 비교는 순서 무관.

## maze 픽스처 (C001 계승: 분기·병합)

- 체인: `test-maze` 1개, 노드 6개: C001-enter, C002-crossroad, C003-left-path, C004-right-path, C005-reunion, C006-exit
- 체인 내 간선 6개: C001→C002, C002→C003, C002→C004, C003→C005, C004→C005, C005→C006
- lineage 간선: 0개
- status: C006-exit만 open, 나머지 closed

## lineage 픽스처 (C002 계승: 체인 간 계보)

- 체인 2개: alpha(C001-seed, closed), beta(C001-sprout, open)
- 체인 내 간선: 0개
- **lineage 간선 1개**: beta/C001-sprout ⇠ alpha/C001-seed

## 시각 요소 판정 (maze + lineage)

- SVG 안의 노드 요소 수 = 사이클 수 (data-cycle 속성으로 셈)
- 닫힌 노드와 열린 노드는 **모양이 다르다** (채운 원 vs 빈 원 — 색만으로 구분하지 않는다)
- lineage 간선은 `stroke-dasharray`를 가진 별도 path (`class="lineage"`)
- 접근성 테이블: 사이클 수만큼의 행 (제목·상태·계보 전문)

## 자기완결 판정

`https?://` 를 포함하는 `src=`, `href=`, `url(`, `@import` 가 **0건**.
(문서 내 앵커 `#…` 링크는 허용.)

## 깨진 체인 판정

test-broken(끊어진 parent) 입력 → exit ≠ 0, 지정한 출력 경로에 파일이 **존재하지 않아야** 한다.

## 실데이터 판정 (이 시점의 실제 레포)

- 노드 6개: genesis 1 (C001-existence-in-repo) + loom 5 (C001~C005)
- lineage 간선 1개: loom/C001-lineage-is-reconstructable ⇠ genesis/C001-existence-in-repo
- loom 체인 내 간선 4개 (C001→C002→C003→C004→C005 직렬)
