# 2. 실험 설계 — 라운드를 데이터로

가설(H1·H2·H3)을 검증하기 위한 설계. **정답(기대 행동)을 구현보다 먼저 고정한다.**

## 설계 결정 (답의 고정)

### D1 — 라운드 레이아웃: R1은 기존 문서, R2+는 `rounds/`

- **R1 = 기존 5스텝 문서** (`1-hypothesis.md` + `3-verification/`). `rounds` 필드가 없거나 `1`이면 사이클은 정확히 R1 하나 = **지금과 동일**(H3).
- **R2, R3, … = `rounds/R{k}/`** 각각 `{hypothesis.md, round.yaml, verification/}`.
- `cycle.yaml`의 `rounds: N` = **총 라운드 수**(R1 포함). `rounds: 2` = R1(기존) + R2(`rounds/R2/`).

> 이 비대칭(R1은 기존, R2+는 새 디렉토리)이 하위호환을 **공짜로** 만든다. 기존 사이클은 손대지 않는다.

### D2 — 라운드 메타는 `rounds/R{k}/round.yaml` (평탄, 중첩 없음)

`cycle.yaml`은 `rounds: N` **개수만** 담는다. 라운드별 상세는 각 라운드 디렉토리의 `round.yaml`에 산다 — 평탄 파서 계약 §3.1 **무손상**. (C043의 구조: "낡을 수 있는 것은 사이클 밖에 두어 `load_chain_records`가 안 보게".)

```yaml
# rounds/R2/round.yaml
round: 2
title: "트리거는 집중도로 판정한다"
opened: 2026-07-15
closed: null
verdict: null   # 아래 6-어휘 중 하나 (닫을 때)
```

### D3 — 라운드 verdict 어휘 (6) vs 사이클 verdict 어휘 (4)

| 층 | 어휘 | 규칙 |
|---|---|---|
| **사이클** (`cycle.yaml.verdict`) | supported · partial · rejected · inconclusive | R10 **불변** |
| **라운드** (`round.yaml.verdict`) | supported · partial · rejected · inconclusive · **invalid-method** · **confounded** | R15 (신설) |

- **`invalid-method`**: 검증 *방법 자체가 무효*라 가설의 참/거짓을 판정 못함 (maru의 CV 함정 — 척도 다른 변수 간 비교 불가).
- **`confounded`**: 교란 변수로 결론 불가 (maru의 일주기 공선성 — 시각 미통제).
- 이 둘이 라운드 전용인 이유(H2): **"방법이 틀려서 결과가 무효"를 "가설이 틀림(rejected)"과 구별**한다. rejected는 가설에 대한 정직한 판정이지만, invalid-method는 판정 자체가 성립 안 했다는 뜻 — 다음 라운드가 *방법을 고쳐* 자란다.

### D4 — `gil round` 명령

```
gil round <chain> <id> --open  --title "..." [--git --push]   # 새 라운드 R{N+1} 사전등록
gil round <chain> <id> --close --verdict <v> [--git --push]   # 열린 라운드 닫기
gil round <chain> <id> --list                                 # 라운드 조회 (부작용 0, 능력 탐침 안전)
```

- **`--open`**: `status: open` 사이클에서만. `cycle.yaml.rounds`를 `N+1`로 증가, `rounds/R{N+1}/{hypothesis.md(템플릿), round.yaml(opened·title·verdict:null)}` 생성. **`verification/`은 만들지 않는다.** `--git`이면 이 세 파일(+cycle.yaml)만 커밋 → **hypothesis가 verification보다 먼저 각인(H1)**. 사이클의 첫 `round --open`은 R2를 만든다(R1은 기존 문서).
- **`--close`**: 가장 높은 번호의 **열린**(verdict:null) 라운드에 `verdict`·`closed` 기록. verdict는 6-어휘. `--git`이면 그 라운드 디렉토리(verification 포함)를 커밋.
- **거부(계약면 = exit≠0 + 저장소 무변화)**: 닫힌 사이클(C1 유사), verdict 어휘 밖, `--open`에 `--title` 없음, 닫을 열린 라운드 없음, `--open`과 `--close` 동시.

### D5 — fsck **R15** (라운드 사전등록 · 위반)

`rounds` 필드가 있으면:
- `rounds`는 정수 ≥ 1.
- `N = rounds > 1`이면 각 `k ∈ [2..N]`에 대해 `rounds/R{k}/hypothesis.md`가 **존재**해야 한다 — 없으면 **위반**(사전등록 파일 없음 = 사전등록 안 됨).
- `rounds/R{k}/round.yaml`이 있고 `verdict`가 있으면 **6-어휘 중 하나** — 아니면 위반.

R14의 선례를 따라 **위반**(경고 아님): v2.5에서 태어나 유예할 과거가 없고, 정당한 탈출구가 없다(`round --open`이 항상 hypothesis.md를 만든다). `rounds` 필드가 없으면 규칙 자체가 불발 → **무라운드 사이클은 R15의 사정거리 밖**(하위호환).

### D6 — log 표시

라운드가 2 이상인 사이클만 `[… · R{N}]` 꼬리를 붙인다. 예: `● C045-round-first-class [closed · supported · R2]`. **무라운드 사이클의 log 출력은 한 글자도 변하지 않는다**(H3).

### D7 — web/JSON

`gil-data` JSON의 각 노드에 `rounds` 값을 **`rounds > 1`일 때만** 넣는다(C043: "낡을 수 있는 것은 있을 때만 내보내라"). 시각적으로 라운드 배지. **무라운드 저장소의 HTML은 바이트 동일**(H3) — Go 미구현과도 동일. bake 계약(§5.2) 무손상.

## 기대 행동 표 (판정기 항목 = 답의 고정)

C043 규율: **새 표면을 계약에 적는 같은 커밋에서 판정기에도 적는다.**

| # | 항목 | 입력 | 기대 (계약면: exit·파일·산출물) |
|---|---|---|---|
| T1 | `ROUND-OPEN` | 열린 사이클에 `round --open --title T` | exit 0; `rounds/R2/hypothesis.md`·`round.yaml` 생성; `cycle.yaml.rounds == 2` |
| T2 | `ROUND-PREREG` | T1 직후 | `rounds/R2/verification/`이 **부재** — hypothesis만 사전등록됨(H1) |
| T3 | `ROUND-OPEN-GIT` | `round --open --git` | 커밋에 `hypothesis.md`·`round.yaml`·`cycle.yaml` 포함, `verification/` **미포함**(사전등록 순서, H1) |
| T4 | `ROUND-CLOSE-VERDICT` | `round --close --verdict invalid-method` | exit 0; `round.yaml.verdict == invalid-method`(6-어휘 허용, H2) |
| T5 | `ROUND-CLOSE-REJECT-VOCAB` | `round --close --verdict bogus` | **exit≠0 + 저장소 무변화** (어휘 밖 거부) |
| T6 | `ROUND-CLOSED-CYCLE` | 닫힌 사이클에 `round --open` | **exit≠0 + 저장소 무변화** (불변 보호) |
| T7 | `FSCK-R15` | `rounds:2`인데 `rounds/R2/hypothesis.md` 없는 픽스처 | fsck exit≠0, 기계 훅 토큰 `R15` |
| T8 | `FSCK-R15-OK` | 정상 2-라운드 픽스처 | fsck가 R15로 걸지 않음 |
| T9 | `ROUND-LIST-SAFE` | `round --list` | exit 0, **작업 트리 무변화**(능력 탐침 무해, §7.2-6) |
| T10 | `HELP-COMPLETE`(기존) | CONTRACT_COMMANDS에 `round` 추가 | 참조는 round 구현→통과; **Go는 미구현→exit 3 정직 보고** 시 통과 |
| T11 | `BACKCOMPAT` | 무라운드 저장소 fsck·web | 변경 전후·두 구현 간 **바이트 동일**(H3) — 기존 판정 항목이 커버 |

**변이 격추 계획** (C011·C041: 각 조항을 *다른 방어선이 침묵하는 입력*으로 시험):
- M1: `round --open`이 verification/도 만들게 → T2·T3가 잡아야.
- M2: verdict 어휘 검사 제거(6→무제한) → T5가 잡아야.
- M3: R15에서 hypothesis.md 존재 검사 제거 → T7이 잡아야.
- M4: 무라운드에도 web JSON에 `rounds:1` 무조건 삽입 → T11(바이트 동일)이 잡아야.

## 준비물

- 참조 구현 `gil.py` (Python 3 표준 라이브러리), 현행 v2.4.0 기반.
- 판정기 `conformance.py` (현행 64/56 항목, Go 56).
- 픽스처: 정상 2-라운드 사이클, R15 위반 사이클(hypothesis 누락) — `3-verification/`에 재현 스크립트로 저장.

## 측정 방법

- **성공**: 참조 구현이 신설 항목 T1~T11 전부 통과, **기존 항목 회귀 0**, 변이 M1~M4 전부 격추, 무라운드 저장소 web/fsck **바이트 동일**(두 구현·변경 전후).
- **부분 기각**: 평탄 파서 계약이나 fsck 깃 무의존을 지키려다 H1/H2 중 하나를 포기해야 하면.
- **기각**: 하위호환(H3)이 깨지면(회귀 ≠ 0).

## 부수 산출 — SPEC에 "버그 수정 vs 새 가설" 경계 명문화 (#10)

도구는 "이건 버그냐 새 가설이냐"를 판정할 수 없다 — **저자만 안다**(§3.2 정신). 그래서 이것은 기계 강제가 아니라 **규율**이고, `gil round`가 새 가설을 위한 *자리*를 제공한다:

- **버그 수정**: 코드가 가설이 말한 것을 검증하지 *못했다*. 고치고 재실행해도 **같은 가설**. → 라운드 불필요, 중간 커밋으로 충분.
- **새 가설(= 새 라운드)**: 가설의 **조작적 정의**가 바뀌었고 그 선택이 **데이터를 본 뒤**에 이뤄졌다. → **반드시 새 라운드**, 기대값을 다시 못박는다.

## 사용자 컨펌

- 방향(#9·#10 라운드 1급화)은 상현님이 이미 선택(AskUserQuestion). 설계 세부는 전권 위임(C008)으로 자율 진행하되, 위 설계 결정 D1~D7을 보고서에 명시해 감사 가능하게 남긴다.
- [x] 컨펌 받음 (일자: 2026-07-15, 방향 선택 = 착수 승인)
