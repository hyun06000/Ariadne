# 3. 가설 검증

## 재현 방법 (불변 기준 / 가변 확인 — C019 규약)

**불변 기준 (픽스처)**: 언제 돌려도 같은 결과여야 한다.

```bash
S=/tmp/c041                                   # 임의의 스크래치
P="python3 rooms/deployment/ariadne-spec/gil.py"
mkdir -p $S && (cd rooms/deployment/ariadne-spec/go && go build -o $S/gil-go main.go)
G=$S/gil-go
D=rooms/experiment/chains/loom/C041-correction-protocol/3-verification

# ① 회색지대 재현 — 봉인된 거짓 출처
bash $D/fixture.sh $S/fx "$P"

# ② 계약 준수 (두 구현)
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$P"
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$G"

# ③ 변이 시험 — 판정기가 행동을 판정하는가
python3 $D/mutants.py $S/mut \
  rooms/deployment/ariadne-spec/gil.py rooms/deployment/ariadne-spec/conformance.py

# ④ 교차 판정 — 두 몸, 한 계약
bash $D/cross-check.sh $S/cross "$P" "$G"
```

**가변 확인 (실데이터)**: 저장소 자신의 `loom/C029-time-machine` 정정. 이미 수행됐으므로 재실행하면 **C8(현재 값과 동일)로 거부된다** — 그것이 정상이다.

## 관측 1 — 회색지대의 기계적 형태 (수정 전)

`loom/C029-time-machine`: `cycle.yaml`은 `parent: null`, 그 **불변 문서**는 *"부모: loom/C028"*.

| 선택 | `gil fsck` | `gil verify` (CI 게이트가 매 push마다 실행) |
|---|---|---|
| 거짓을 그대로 둔다 | `경고 [다중루트] loom: 루트가 2개` | ✅ `OK — 변조 0건` |
| 손으로 고친다 | 경고 사라짐 | ❌ `변조 감지 [cycle/loom/C029-time-machine]` **exit 1** |

> **진실을 말한 대가로 위조자가 된다.**
>
> `verify`의 `변조 0건`은 *"거짓이 없다"* 가 아니라 *"각인 이후 아무도 손대지 않았다"* 는 뜻이었다 — **원본성은 진실성이 아니다.**

## 관측 2 — 계약 준수 (40 → 50 항목)

| 구현 | 결과 |
|---|---|
| 참조 (`gil.py`) | **50/50** ✔ |
| Go (`go/main.go`) | **50/50** ✔ (첫 시도) |

**회귀 0** — 기존 40항목 전부 통과. 신설 10항목:

| 항목 | 지키는 것 |
|---|---|
| `CORRECT-UNSEALED-REJECT` | C1 — 봉인이 없으면 정정도 없다 |
| `CORRECT-NO-AUTHOR` | C2 — 도구는 **정정의 출처도** 지어내지 않는다 |
| `CORRECT-FIELD-LIMIT` | C3 / **L1** — 증거가 있어도 저자의 주장은 불변 |
| `CORRECT-EVIDENCE-REQUIRED` | C4·C5 / **L2** — 스키마상 합법인 거짓도 증거 없이는 못 쓴다 |
| `CORRECT-RECORD` | **L3** — 정정 2회 후 **모든** `from`이 남아 있다 |
| `CORRECT-TAG-MOVE` | 정정한 자가 위조자가 되지 않는다 |
| `CORRECT-VERIFY-STILL-CATCHES` | **기각 조건 1** — 정정 후에도 진짜 변조는 잡힌다 |
| `CORRECT-TAMPER-GUARD` | C6 — 변조 세탁의 뒷문 차단 |
| `FSCK-R13` | 기록 없는 정정 = 지우개 |
| `SUPERSEDE-TAG-MOVE` | §4 태그 이동 규약(C035) — **변이 시험이 우연히 찾아낸 사각지대** |

## 관측 3 — 변이 시험: 최종 6/6 격추 (첫 실행은 2/6이었다)

| 변이 | 부순 조항 | 첫 실행 | 최종 |
|---|---|---|---|
| M1 증거 검사 제거 | L2 | **생존** | 격추 |
| M2 필드 제한 해제 | L1 | **생존** | 격추 |
| M3a 기록 덮어쓰기 | L3 (과거 정정 유실) | **생존** | 격추 |
| M3b `from` 생략 | L3 (거짓값 유실) | **생존** | 격추 |
| M4 태그 이동 생략 | §4 | **생존** | 격추 |
| M5 C6 선검사 제거 | 뒷문 | 격추 | 격추 |

**살아남은 넷이 전부 나를 가르쳤다.**

### M1·M2 — 심층 방어가 변이를 가린다 (판정기의 진짜 사각지대)

증거 검사를 제거했는데도 항목이 **통과**했다. 거부는 됐지만 **다른 문지기**가 막은 것이다:

```
$ gil correct demo/C002 --field parent --to C999-ghost --evidence 1-hypothesis.md --author x
오류: fsck 위반 — R6 …: parent 'C999-ghost'가 존재하지 않는다 (끊어진 참조)
```

내 테스트의 거짓값이 **너무 뻔했다.** 없는 사이클이라 스키마 검사(C7/R6)가 대신 잡았고 — **증거 계약은 한 번도 시험되지 않았다.** M2도 같은 병이었다: `verdict → rejected`는 증거 검사가 대신 막아, 필드 제한(L1)이 없어도 통과했다.

> **이 사이클은 "그럴듯한 거짓이 가장 오래 산다"를 다루는데, 내 테스트는 그럴듯하지 않은 거짓을 썼다.**

고친 방법: 거짓값을 **스키마상 완벽히 합법인 것**(실재하지만 문서가 증언하지 않는 `C003-other`)으로 바꾸고, 필드 제한 시험에서는 증거가 실제로 그 값을 증언하게 만들었다. **한 조항을 시험하려면 다른 방어선이 침묵하는 입력을 골라야 한다.**

### M3a — 한 번의 정정으로는 각주와 지우개를 구별할 수 없다

정정을 1회만 하면 **덧붙이는 구현과 덮어쓰는 구현이 같은 파일을 만든다.** L3("과거의 정정도 지워지지 않는다")를 시험하려면 **정정이 두 번** 있어야 한다. 항목을 2회 정정으로 바꾸자 격추됐다.

### M3b·M4 — 하네스 결함, 그리고 그중 하나가 진짜 구멍을 팠다

- **M3b**: 치환의 첫 일치가 `_CORRECTION_KEYS`(**검사기**)여서 **쓰는 쪽이 아니라 보는 쪽**을 변이시켰다. 행동이 안 변하니 통과가 맞다 (C011의 *동등 변이*).
- **M4**: 첫 일치가 **`cmd_supersede`의 태그 이동**이었다. 그 변이가 **아무 항목도 실패시키지 않았다** — 즉 **`supersede`의 태그 이동은 v1.9 이래 아무도 판정하지 않고 있었다.** 그 자리에 `SUPERSEDE-TAG-MOVE`를 심었다.

> *판정기가 안 보는 계약은 없는 계약이다* (Weft). 이번엔 **내 변이가 실수로 그 사각지대를 밟아서** 드러났다.

## 관측 4 — 교차 판정 (두 몸, 한 계약)

같은 픽스처에 두 구현이 각각 정정을 가한 결과:

| 산출물 | 결과 |
|---|---|
| `cycle.yaml` · `corrections.yaml` | **바이트 동일** |
| `fsck` · `verify` 출력 | **바이트 동일** |
| `[correct]` 커밋 메시지 · 태그 메시지 | **바이트 동일** |
| `web` HTML 전문 | **바이트 동일** |
| `correct` 출력 (커밋 해시 마스킹) | **바이트 동일** |
| `log` | **요약 섹션 1줄 차이** — 참조만 `root: …`를 출력 |

`log`의 차이는 **계약 위반이 아니다**: §3.1이 *"log의 렌더 형식은 계약이 아니다"* 라고 못 박았다 (C021이 같은 자리에서 확립한 조항 — 두 번째 적용).

## 관측 5 — 실데이터: 저장소 자신의 수술

```
$ gil correct loom/C029-time-machine --field parent --to C028-pages-command \
    --evidence 1-hypothesis.md:5 --author clew --reason "…"
정정: loom/C029-time-machine
  ✎ parent: null → C028-pages-command
  증거: 1-hypothesis.md:5 (봉인본 cycle/loom/C029-time-machine)
  기록: …/corrections.yaml — 거짓은 지워지지 않았다
  태그 이동: f35408e5 → 3680ed0d
```

| 검사 | 수정 전 | 수정 후 |
|---|---|---|
| `fsck` 다중루트 | `루트가 2개 — C001-…, C029-time-machine` | **소멸** (`경고 [정정] 1건`으로 대체) |
| `verify` | OK — **거짓을 봉인하고 있었다** | **OK** — 정정을 봉인한다 |
| `log` | `C029-time-machine [closed]` | `… [closed] … ✎ corrected(1)` |
| 태그 메시지 | `close` | `[correct] parent: null → C028-pages-command — 증거 1-hypothesis.md:5 (이전 커밋 f35408e5에서 이동)` |
| 거짓값 | 색인에 살아 있었다 | `corrections.yaml`의 `from: null`에 **영구 보존** |

## 기각 조건 대조 (1-hypothesis.md)

| # | 조건 | 결과 |
|---|---|---|
| 1 | 정정 후 진짜 변조를 verify가 놓친다 | **아니오** — `CORRECT-VERIFY-STILL-CATCHES` 통과 |
| 2 | `verdict` 등 저자의 주장이 정정된다 | **아니오** — `CORRECT-FIELD-LIMIT` (증거가 있어도 거부) |
| 3 | 증거 없이 통과한다 | **아니오** — `CORRECT-EVIDENCE-REQUIRED` (스키마상 합법인 거짓도 거부) |
| 4 | 거짓이 지워진다 | **아니오** — `CORRECT-RECORD` (2회 정정, 모든 `from` 보존) |
| 5 | 회귀 | **0건** |
| 6 | 두 구현이 갈라진다 | **아니오** — 산출물 바이트 동일 (log 렌더 제외, §3.1) |
| 7 | 판정기가 안 본다 | **아니오** — 10항목 신설, 변이 6/6 격추 |

**어느 것도 참이 아니다 → 채택.**

## 실행 기록

- 일시: 2026-07-15 / macOS (darwin), Python 3, Go (표준 라이브러리만)
- 특이사항 1: 변이 하네스의 첫 판(`mutants.sh`)이 zsh 인용 문제로 깨졌다 — **하네스 결함, 구현 결함 0** (C037의 계열). `mutants.py`로 재작성.
- 특이사항 2: 첫 변이 실행 2/6은 **판정기의 결함**이었다 (구현은 처음부터 옳았다). 위 관측 3 참조.
