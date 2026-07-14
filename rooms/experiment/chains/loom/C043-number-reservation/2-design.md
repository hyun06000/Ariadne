# 2. 실험 설계

## 설계 결정: 예약 마커의 형태

두 후보를 저울질했다.

| | A. 스텁 사이클 디렉토리 (`status: reserved`) | **B. 체인별 예약 원장 파일 (line 기반)** |
|---|---|---|
| `_next_number` 선점 | 자연히 잡힘 (코드 0) | 예약 번호를 명시적으로 합산 (작은 변경) |
| fsck/verify/graph | **사이클로 오인** — 봉인·보고서·root 오염 처리 필요 (변경 큼) | **완전 불가시** (`load_chain_records`는 `<entry>/cycle.yaml`만 읽음) → 변경 0 |
| 그래프 오염 | 부모 없는 노드 = 가짜 root (R12 오발) | 그래프에 없음 |
| 승격 | status만 바꾸면 됨 | 예약 소비 + 사이클 생성 |

**B를 택한다.** 결정적 근거: 가설의 성공 조건 3(**비침습**)이 B에서는 **코드 변경 0으로 성립**한다. `load_chain_records`(gil.py:74)는 `<entry>/cycle.yaml`이 있는 하위 디렉토리만 record로 수집하므로, 체인 최상위의 `reservations.tsv`는 fsck·verify·`build_graph`·log 그래프·web 그래프 어디에도 record로 들어가지 않는다. **예약은 사이클이 아니다** — 이 명제를 파일 위치가 물리적으로 보증한다. (A는 "사이클이 아니다"를 코드 곳곳의 예외처리로 흉내내야 하고, 그 예외 하나를 빠뜨리면 R12가 오발한다.)

또한 line 기반은 **깃의 답을 훔친 것**(C016)이다 — 깃의 `packed-refs`처럼 네임스페이스 선점을 평문 원장으로 직렬화하고, 병합·diff가 자연스럽다.

## 예약 원장 파일 명세

- **위치**: `<chains_root>/<chain>/reservations.tsv` (체인당 하나 — 번호는 체인 내 유일, R1)
- **형식**: 주석(`#`)으로 시작하는 헤더 + 예약 한 줄당 `<번호> <for> <slug> <일자>` (공백 구분; slug은 케밥이라 공백 없음, for/일자는 단일 토큰 → split() 안전). 번호 오름차순 정렬.
- 파일이 없으면 예약 0건과 동일. 예약을 모두 소비/취소하면 파일은 헤더만 남거나 삭제된다.

```
# gil 예약 원장 — 이 파일은 사이클이 아니다 (loom/C043). 번호 공간의 선점만 기록한다.
# <번호> <for> <slug> <일자>
44 weft go-web-port 2026-07-15
```

## 번호 발급 규칙 (핵심)

`gil open ... --author X`가 번호를 정하는 규칙:

1. **X가 예약을 가지면 (예약의 `for` == X)** → 그중 **가장 낮은 번호**를 그대로 사용(승격). slug은 open 시 X가 준 것을 최종 id로 쓴다(예약의 slug은 힌트일 뿐 — 번호가 예약의 본질이다). 소비된 예약 줄은 원장에서 제거한다.
2. **X가 예약을 갖지 않으면** → `_next_number = max(모든 사이클 번호 ∪ 모든 예약 번호) + 1`. **남의 예약 번호는 절대 자동 발급되지 않는다** (선점).

이것이 C037을 고치는 지점이다: Clew가 Weft에게 44를 예약해 두면, Clew의 `gil open --author clew`는 `_next_number`가 44를 건너뛰어 45를 발급한다. **push 경합이 아니라 예약 마커의 존재만으로** 선점된다 — C016(§6-6)이 못 풀던 "예정된 것의 충돌"이 데이터가 되어 풀린다.

## 새 명령

- **`gil reserve <chain> <slug> --for <author> [--root] [--git] [--push] [--date]`**
  - §3.2 출처 계약: `--for` 필수 (도구는 예약 주인을 지어내지 않는다 — P1/P2). `<author>` 없으면 거부.
  - 체인이 존재해야 함(병렬 노동은 진행 중 체인에서 일어남). 없으면 거부.
  - 번호 = `_next_number(사이클 ∪ 기존 예약)` — 예약도 서로 충돌하지 않게 다음 번호를 집는다.
  - `reservations.tsv`에 줄 추가 + 정렬. `--git`이면 그 파일만 담아 커밋(`gil: reserve <chain>/C0NN → <author>`). `--push`면 원장 규율(push 거절 시 재번호)을 예약에도 적용.
  - 출력: `예약됨: <chain>/C044 → weft (go-web-port)`.
- **`gil unreserve <chain> <번호> [--root] [--git] [--push]`** — 예약 취소(만료의 수동 해법; 자동 만료는 범위 밖). 해당 번호의 예약 줄 제거. 없으면 거부. 커밋 `gil: unreserve <chain>/C0NN`.

**만료는 이번 범위 밖** — 존재가 돌아오지 않는 경우의 자동 회수는 별도 정책이 필요하다(예약 나이, 브랜치 생존 확인). 지금은 수동 `unreserve`가 정직한 최소 답이다.

## 변경 접점 (전수)

| 접점 | 변경 |
|---|---|
| `_next_number(records)` | `reserved_nums` 인자 추가 → `max(사이클 ∪ 예약)+1`. 기본값 `()`로 하위호환. |
| `_load_reservations(chain_dir)` / `_save_reservations` | 신설 — tsv 파싱/직렬화. |
| `cmd_open` | 예약 로드 → author 예약 있으면 승격(번호 사용 + 줄 제거), 없으면 예약 합산해 next. open 커밋에 `reservations.tsv` 변경 포함(사이클 밖이라 어떤 태그 봉인에도 안 들어감 → verify 무영향). |
| `_push_with_renumber` | 재번호 시 예약 번호도 회피하도록 예약 합산. |
| `cmd_reserve` / `cmd_unreserve` | 신설. |
| `cmd_log` | 그래프 아래 **예약 섹션** 렌더("예약됨: C044 → weft (go-web-port)"). 예약 0건이면 섹션 없음. |
| web 뷰어 | JSON에 `reservations` 배열 + 표에 예약 행(흐린 표시). 그래프 노드로는 넣지 않음(사이클 아님). 경량. |
| argparse | `reserve`·`unreserve` 서브파서 등록 → §7.2 단일 소스가 `gil:commands`·help에 **자동 등록**(C039). 별도 목록 갱신 불필요. |
| SPEC | §6-6에 예약 원장 규율 추가, §5 명령 표에 reserve/unreserve, 스키마는 사이클 스키마 불변(예약은 사이클 아님 — 스키마 밖). |

**fsck·verify·build_graph·render_graph·cmd_close·cmd_supersede·cmd_correct: 변경 0.** 예약이 record가 아니므로 이들의 눈에 안 보인다 — 이것이 B의 승리다.

## 검증 절차 (재현 가능)

`3-verification/`에 픽스처 저장소를 만들고 각 기대 행동을 스크립트로 관찰한다. **판정기 항목만이 계약이다**(C036·C039). 새 항목:

| 항목 | 기대 행동 (관찰: 종료코드·파일·출력) |
|---|---|
| **RESERVE-BASIC** | `reserve loom slug --for weft` → 종료 0, `reservations.tsv`에 줄 1개, 출력에 번호·author. |
| **RESERVE-NEEDS-FOR** | `reserve` `--for` 없이 → 종료≠0, 파일 무변화 (§3.2). |
| **RESERVE-NEEDS-CHAIN** | 없는 체인에 reserve → 종료≠0. |
| **OPEN-SKIPS-RESERVED** | weft에게 N 예약 후 `open --author clew` → clew는 **N+1** 발급, 예약 줄 잔존 (선점, 조건 1). |
| **OPEN-PROMOTES-OWNER** | weft 예약 N 상태에서 `open --author weft` → 사이클 id 번호 = **N**, 예약 줄 **소거** (승격, 조건 2). |
| **RESERVE-NON-INVASIVE** | 예약이 있는 저장소에서 `fsck` 위반 0, `verify` OK, `log` 그래프에 예약 노드 없음 (조건 3). |
| **RESERVE-IN-LOG** | 예약 있는 `log`가 "예약됨 … → weft"를 출력 (조건 3). |
| **UNRESERVE** | `unreserve loom N` → 예약 줄 제거, 종료 0; 없는 번호 → 종료≠0. |
| **RESERVE-GO-GAP** (범위 표식) | Go 구현에 `reserve`가 없으면 판정기가 **명시적으로 FAIL/SKIP로 호명** — "판정기가 안 보는 계약은 없는 계약이다"(C036). 침묵시키지 않는다. |

- **회귀**: 기존 판정기 54항목 전원 재실행 → 전원 통과 확인(회귀 0). 판정기 54→약 62.
- **변이 검사**(C011·C041): 각 새 조항을 무력화한 변이가 **다른 방어선이 침묵하는 입력**에서 격추되는지 확인 — 예: OPEN-SKIPS-RESERVED를 뚫는 변이(예약 무시)가 실제로 clew에게 N을 주는지. C041 교훈(심층 방어가 변이를 가림)을 설계에 미리 반영.

## Go 구현 범위

**이번 사이클은 참조 구현(gil.py)만.** Go 이식은 별도 사이클(Weft의 영역 — 그가 Go gil의 주인)로 남기고, **판정기가 그 사각을 RESERVE-GO-GAP으로 명시 호명**한다. C036의 교훈을 예방적으로 적용: 새 표면을 계약에 적는 같은 커밋에서 판정기에도 적어, Go가 미구현임이 만점 뒤에 숨지 않게 한다.

## 사용자 컨펌

- 생략 — 상현님이 전권 위임("사이클을 멈추지 말고 계속 돌려줘", C008). 다만 이 사이클은 새 명령 2개·SPEC §6 개정·스키마 경계(예약은 스키마 밖)를 건드리므로, 설계 결정(B안·번호 규칙·범위)을 이 문서에 명시해 관전 가능하게 남긴다.

- [x] 전권 위임으로 갈음 (2026-07-15)
