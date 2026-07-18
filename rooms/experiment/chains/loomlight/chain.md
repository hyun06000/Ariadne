# Chain: loomlight

> 직조를 비추는 빛. 뷰어(gil log / web / pages)가 추론의 태피스트리를 사람 눈에 보이게 한다.

## 이 체인이 정복하려는 문제

**원장에 이미 짜인 진실을 사람의 눈에 정직하게 비춘다.**

Ariadne는 사이클 체인을 `cycle.yaml`·깃 태그·원장으로 기록한다. 이 기록은
기계의 눈에는 완전하지만 사람의 눈에는 어둡다. 뷰어는 새 진실을 만들지 않고,
이미 있는 진실을 사람이 읽을 수 있는 그래프로 옮긴다 — 계보를, 분기를, 병합을,
진행 스텝을, 결말(verdict)을, 정정과 무효화를, 그리고 지금 이 순간의 상태를.

## loom과의 관계 — 이 체인은 loom의 뷰어 갈래를 lineage로 모은 거울이다

뷰어 작업은 loom 체인 전역에 흩어져 태어났다(도구 본체·스펙·계약과 뒤섞여서).
loomlight는 그 뷰어 갈래를 **한 곳에서 조망하기 위한 전용 체인**이다.

**모으되 옮기지 않는다.** 닫힌 사이클은 불변이고(R4·R5: chain=디렉토리=id 한 몸,
태그 `cycle/loom/Cxxx`), 물리적 이동은 프레임워크가 집행하는 불변성 위반이다.
그래서 깃이 커밋 해시를 참조하듯, loomlight/C001은 `lineage` 필드로 10개 원본
사이클을 **가리켜** 모은다. 원본은 loom에 그대로 남고, `gil log`는 교차-체인
lineage 엣지(`⇠`)로 두 체인을 잇는다.

## 색인 — loom에 흩어진 뷰어 10사이클 (전역 표기 `loom/<id>`)

| # | 사이클 | 한 줄 요약 |
|---|---|---|
| 1 | [loom/C005-web-viewer](../loom/C005-web-viewer/5-report.md) | web 뷰어 기초 — 같은 파서, 렌더러만 교체해 자기완결 정적 HTML 그래프 |
| 2 | [loom/C013-realtime-step-visibility](../loom/C013-realtime-step-visibility/5-report.md) | 스텝 필드 + 스텝별 커밋·push로 열린 사이클의 진행이 준실시간 가시화 |
| 3 | [loom/C015-being-work-visibility](../loom/C015-being-work-visibility/5-report.md) | 존재들의 작업(브랜치·최근 활동)을 뷰어에 — 병렬 노동의 관전 |
| 4 | [loom/C020-go-web-port](../loom/C020-go-web-port/5-report.md) | web을 Go로 이식 — 두 구현이 26/26으로 나란히(두 몸 한 계약) |
| 5 | [loom/C028-pages-command](../loom/C028-pages-command/5-report.md) | `gil pages` — 명령 하나로 자기 체인을 github.io에 딸깍 배포 |
| 6 | [loom/C031-web-lane-layout](../loom/C031-web-lane-layout/5-report.md) | 형제 갈래를 세로 레인으로 분리(git log --graph처럼), rejected는 색으로 |
| 7 | [loom/C042-viewer-follows-ledger](../loom/C042-viewer-follows-ledger/5-report.md) | 원장이 자동 갱신되면 창도 자동 갱신 — 낡은 화면은 침묵보다 나쁘다 |
| 8 | [loom/C047-web-topology-layout](../loom/C047-web-topology-layout/5-report.md) | 토폴로지 레이아웃 — 분기 형제를 같은 깊이(row=depth)에 두어 세로 압축 |
| 9 | [loom/C048-sibling-label-spacing](../loom/C048-sibling-label-spacing/5-report.md) | 같은 위계 형제 노드의 라벨 겹침 해소 — 열 간격을 라벨 폭으로 |
| 10 | [loom/C049-live-viewer-refresh](../loom/C049-live-viewer-refresh/5-report.md) | 새로고침 없는 실시간 관찰 — `gil web --refresh`(meta)·`--watch`(감시 재생성) |

계보로 읽으면: **기초(C005)** 위에 **가시성의 축**(C013 스텝 → C015 존재 노동 →
C042 자동 갱신 → C049 실시간)과 **레이아웃의 축**(C031 레인 → C047 토폴로지 →
C048 라벨 간격)이 자라고, **이식·배포의 축**(C020 Go · C028 pages)이 이를 두 구현·
정적 호스팅으로 실물화한다.

## 나침반 — 남은 뷰어 개선 (예언이 아니다. 각 가설은 직전 보고서의 교훈에서 나온다)

10사이클의 보고서에 흩어진 "알려진 한계/다음 후보"를 뷰어 관점으로만 추린 지도다.
전체 백로그는 [C001-gather-viewer-lineage/5-report.md](C001-gather-viewer-lineage/5-report.md).

1. **레인 가로 압축** — 세로는 토폴로지로 압축됐으나 형제가 많으면 가로(col)로 넓어진다.
   죽은 레인의 col 재사용(C047-C, C049-C). C048이 형제를 벌린 뒤 가로 길이가 새 압력.
2. **lineage 간선 시각 밀도** — 체인이 많고 lineage가 교차하면 점선이 얽힌다(C005·C009).
   loomlight가 loom을 10겹으로 가리키는 지금이 이 밀도의 첫 실증 조건.
3. **정적 레인 폭 / 긴 id 겹침** — 레인 폭이 정적이라 긴 id에서 겹칠 수 있다(C005).
   C048이 형제 라벨은 풀었으나 폭 자체는 정적.
4. **corrected(✎)·superseded(↣)의 시각 표현 강화** — 갱신(C042)만 다뤘고 이 두 상태의
   시각 표현은 별도 실로 남았다(C042-D). 연쇄 무효화 A↣B↣C의 유효성 추적도(C035-A).
5. **원격(Pages) 실시간** — C049가 로컬 실시간(--refresh/--watch)을 풀었으나 Pages는
   빌드 지연(~1분)이 남는다(C013-B).
6. **verdict 결말 서사의 시각화** — 우리 자신 사이클의 verdict 소급 이주 후 뷰어 서사(C031-A).
7. **외부 채택자 피드백 루프** — 제보자의 사슬을 뷰어로 렌더해 되돌려주기(C031-C).

## 시작일

2026-07-19 · 창건자: Sheen(신) · 소환자·발의자: Clew ("뷰어를 더 강화하려 한다 —
흩어진 뷰어 사이클을 한 곳에 모은 전용 설계 체인을 만들라")
