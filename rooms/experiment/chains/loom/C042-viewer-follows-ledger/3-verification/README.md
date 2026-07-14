# 3. 가설 검증

## 재현 방법 (불변 기준 / 가변 확인 — C019 규약)

```bash
S=/tmp/c042
P="python3 rooms/deployment/ariadne-spec/gil.py"
mkdir -p $S && (cd rooms/deployment/ariadne-spec/go && go build -o $S/gil-go main.go)
G=$S/gil-go
D=rooms/experiment/chains/loom/C042-viewer-follows-ledger/3-verification

# ① maru의 상황 재현 — 로컬 뷰어를 쓰는 저장소
bash $D/fixture.sh $S/fx "$P"

# ② 계약 준수 (두 구현)
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$P"
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$G"

# ③ 변이 시험
python3 $D/mutants.py $S/mut \
  rooms/deployment/ariadne-spec/gil.py rooms/deployment/ariadne-spec/conformance.py

# ④ 교차 판정 — 두 몸, 한 계약
bash $D/cross-check.sh $S/cross "$P" "$G"
```

## 관측 1 — maru가 겪은 그 순간, 이제 창이 따라온다

뷰어를 둔 저장소(`fixture.sh`)에서 `step`:

```
$ gil step demo C001-first 2
스텝: demo/C001-first → 2/5 설계  각인: 커밋
  ✎ 뷰어 갱신: chains.html
```

| | v2.1 (이전) | v2.2 (이번) |
|---|---|---|
| 뷰어의 `step` 값 | `1` (낡음) | **`2`** (원장을 따라옴) |
| maru의 불평 | *"커밋했는데 뷰어에 안 잡히네"* | 해소 |

## 관측 2 — 뷰어는 사이클이 아니다 (커밋의 순수함)

`step` 뒤 커밋 히스토리:

```
gil: web 갱신 — demo/C001-first → 2/5     ← 뷰어 (별도 커밋)
gil: step demo/C001-first → 2/5 설계       ← 사이클 (cycle.yaml만)
```

| 커밋 | 담긴 것 |
|---|---|
| 사이클 커밋 | `rooms/experiment/chains/demo/C001-first/cycle.yaml` **뿐** |
| 뷰어 커밋 | `chains.html` **뿐** |

그리고 **태그가 봉인한 것**(`git show cycle/demo/C001-first`)은 **사이클 디렉토리뿐**이다 — 뷰어 커밋이 그 사이에 끼어도. `verify`는 **OK**. 뷰어 갱신이 불변성 보증을 건드리지 않는다.

## 관측 3 — 우리는 이 결함을 볼 수 없었다 (3사이클 밀린 이유)

우리 저장소에서 `gil step`을 돌리면 **`✎ 뷰어 갱신` 줄이 나오지 않는다.** 우리 루트에는 `gil-data` 훅을 가진 HTML이 **없기 때문**이다 — 우리는 `gil pages`(GitHub Actions)로 원격에서 굽는다.

> **배포자는 자기가 안 밟는 길의 지뢰를 못 본다** (C024·C027·C028의 계열). 이 기능이 정확히 작동한다는 증거가 곧 **우리 저장소에 아무 파일도 안 생긴다**는 사실이다 (`WEB-AUTO-NONE`).

## 관측 4 — 계약 준수 (50 → 54)

| 구현 | 결과 |
|---|---|
| 참조 (`gil.py`) | **54/54** ✔ |
| Go (`go/main.go`) | **54/54** ✔ (첫 시도) |

**회귀 0.** 신설 4항목:

| 항목 | 지키는 것 |
|---|---|
| `WEB-AUTO-REFRESH` | 뷰어가 있으면 `step`이 그것을 다시 굽는다 (창이 원장을 따른다) |
| `WEB-AUTO-PURE-COMMIT` | 사이클 커밋에 뷰어가 섞이지 않는다 (뷰어는 별도 커밋) |
| `WEB-AUTO-NONE` | 뷰어 없는 저장소엔 아무 HTML도 안 생긴다 (강요 금지) |
| `WEB-BAKE-META` | 재굽기가 사용자 `--title`을 보존(`bake` 자기보고) + `--no-web` 존중 |

## 관측 5 — 변이 시험: 4/4 격추

| 변이 | 부순 것 | 결과 |
|---|---|---|
| M1 뷰어를 사이클 커밋에 섞음 | 커밋의 순수함(§4) | `WEB-AUTO-PURE-COMMIT` 격추 |
| M2 뷰어 없어도 만들어냄 | 강요 금지 | `WEB-AUTO-NONE` 격추 |
| M3 `bake.title` 무시 | 자기보고 존중 | `WEB-BAKE-META` 격추 |
| M4 갱신 안 함 (v2.1 행동) | 기능 자체 | `WEB-AUTO-REFRESH`(+2) 격추 |

**C041의 교훈을 이번엔 처음부터 적용했다**: 변이가 *다른 방어선이 침묵하는 입력*을 시험하는지 확인했고, 6/6이 아니라 처음부터 4/4가 나왔다.

## 관측 6 — 교차 판정 (두 몸, 한 계약)

같은 픽스처에 두 구현이 각각 `step`+`close`로 뷰어를 자동 갱신한 결과:

| 산출물 | 결과 |
|---|---|
| `chains.html` 전문 | **바이트 동일** |
| `gil-data` JSON (`bake` 포함) | **바이트 동일** |
| git log (사이클·뷰어 커밋 순서) | **바이트 동일** |
| 뷰어 갱신 횟수 | **동일** (step 1 + close 1 = 2회) |

## 기각 조건 대조 (1-hypothesis.md)

| # | 조건 | 결과 |
|---|---|---|
| 1 | 사이클 커밋이 오염된다 | **아니오** — `WEB-AUTO-PURE-COMMIT`, 태그는 사이클만 봉인 |
| 2 | 안 쓰는 사람에게 파일이 생긴다 | **아니오** — `WEB-AUTO-NONE` |
| 3 | 창이 여전히 낡는다 | **아니오** — `WEB-AUTO-REFRESH` |
| 4 | 뷰어를 이름으로 찾는다 | **아니오** — `gil-data` 훅으로 식별 (목록 없음) |
| 5 | 회귀 | **0건** |
| 6 | 두 구현이 갈라진다 | **아니오** — 산출물 바이트 동일 |
| 7 | 판정기가 안 본다 | **아니오** — 4항목 신설, 변이 4/4 |

**어느 것도 참이 아니다 → 채택.**

## 실행 기록

- 일시: 2026-07-15 / macOS (darwin), Python 3, Go (표준 라이브러리만)
- 특이사항: 교차 검증 첫 판이 close 경로에서 멈췄다 — 픽스처가 보고서를 안 써서 `close`가 템플릿을 거부(C003). **구현 결함 아님**, 두 구현이 똑같이 거부. 픽스처에 보고서를 더해 close 경로까지 관측.
