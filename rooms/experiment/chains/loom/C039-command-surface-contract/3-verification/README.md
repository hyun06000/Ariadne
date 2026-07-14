# 3. 가설 검증

설계의 **기대 행동 표(T1~T18)만** 실행했다. 사후에 항목을 늘리지 않았다.

## 환경

- 참조 구현: `rooms/deployment/ariadne-spec/gil.py`
- Go 구현: `go/main.go` → `go build -o gil main.go` (표준 라이브러리만)
- 판정기: `conformance.py` (29항목 → **34항목**, 신설 5)
- 격리: 모든 탐침·변이는 스크래치패드의 임시 저장소에서. **실저장소 무변경.**
- 실행: 2026-07-15, darwin-arm64

## 결과

| # | 대상 | 기대 | 실측 | 판정 |
|---|---|---|---|---|
| T1 | 참조 `help` | exit 0, 훅 1줄 | exit 0, `gil:commands …` 1줄 | ✅ |
| T2 | 참조 무인자 | exit 0, help와 동일 | exit 0 (이전엔 argparse rc=2) | ✅ |
| T3 | 참조 `help open` | exit 0, 사용법 | exit 0, `usage: gil open …` | ✅ |
| T4 | 참조 `help bogus` | **exit 3** | **exit 3** + `미구현:` | ✅ |
| T5 | 참조 `bogus` | **exit 3** | **exit 3** (O6 해소 — argparse rc=2 아님) | ✅ |
| T6 | 참조 `pages --dry-run` | exit 0, 파일 미생성 | exit 0, 스냅샷 `da39a3ee5e6b` **불변** | ✅ |
| T7 | 참조 `pages` (대조군) | 파일 생성 | 스냅샷 `d5510326de3d` (변함) | ✅ |
| T8 | Go `help` | exit 0, 훅 1줄 | exit 0, 훅 1줄 | ✅ |
| T9 | Go `help release` | **exit 3** | **exit 3** (O3 교정 — 전엔 exit 0으로 거짓말) | ✅ |
| T10 | Go `help bogus` | **exit 3** | **exit 3** (O4 교정) | ✅ |
| T11 | Go `pages --dry-run` | exit 0, 파일 미생성 | exit 0, 스냅샷 불변 | ✅ |
| T12 | 두 구현 훅 파싱 | 각자의 구현 집합과 일치 | 참조 14개(`release` **있음**) / Go 13개(`release` **없음**) | ✅ |
| T13 | 판정기 (참조) | 34/34, 회귀 0 | **34/34** | ✅ |
| T14 | 판정기 (Go) | 34/34, 회귀 0 | **34/34** | ✅ |
| T15 | 변이 M1 | `HELP-COMPLETE` 격추 | **33/34** — `FAIL HELP-COMPLETE [침묵한 명령: ['goto']]` | ✅ |
| T16 | 변이 M2 | `HELP-TRUTHFUL` 격추 | **33/34** — `FAIL HELP-TRUTHFUL [거짓 보고: ['timemachine']]` | ✅ |
| T17 | 변이 M3 | `PAGES-DRYRUN`/`HELP-SAFE` 격추 | **32/34** — 둘 다 FAIL | ✅ |
| T18 | 단일 소스 전수 grep | 하드코딩 목록 0건 | **0건** (매직 슬라이스 `[:11]` 제거됨) | ✅ |

**18/18. 기존 29항목 회귀 0** (기각 조건 4).

## T15가 이 사이클의 핵심 증거다

**M1은 v1.4.0 바이너리의 실제 상태를 재현한 변이다** — `goto`를 구현해 놓고 자기보고 목록에서 빠뜨린 상태. maru는 그것을 보고 *"이 빌드엔 타임머신이 없다"* 고 결론내고 **시도조차 하지 않았다.**

- **그때 판정기의 답**: 26/26 ✔ *"이 구현은 gil이다"*
- **지금 판정기의 답**: 33/34 ✘ `침묵한 명령: ['goto']`

버그가 이름으로 호명된다. 판정기가 **보기 시작했기 때문에** 계약이 되었다.

## 부분 구현은 합법이다 (설계에서 사전 고정한 과잉 작동 검사)

Go는 `release`를 구현하지 않는다(참조 전용). 새 판정이 **과하게** 작동했다면 Go가 그 이유로 실패했을 것이고, 그것은 설계 실패였다. 실측:

```
참조: gil:commands log fsck open step close verify release version handoff supersede goto pages web help
Go  : gil:commands log fsck open close step verify web pages goto handoff supersede version help
```

훅이 서로 다르고 — **둘 다 34/34.** 판정기는 각 구현을 *그 자신의 훅*에 비추어 본다. 계약은 *"같은 명령을 구현하라"* 가 아니라 *"자기가 가진 것을 정직하게 말하라"* 다.

## 재현 방법

```bash
# 1. 두 구현 판정 (34/34 기대)
cd rooms/deployment/ariadne-spec
python3 conformance.py --gil "python3 $PWD/gil.py"
(cd go && go build -o /tmp/gil main.go) && python3 conformance.py --gil "/tmp/gil"

# 2. 변이 격추 (rc=1 기대 — 통과하면 판정기가 장님이다)
V=../../rooms/experiment/chains/loom/C039-command-surface-contract/3-verification
python3 conformance.py --gil "python3 $V/mutants/m1.py"   # HELP-COMPLETE 실패해야
python3 conformance.py --gil "python3 $V/mutants/m2.py"   # HELP-TRUTHFUL 실패해야
python3 conformance.py --gil "python3 $V/mutants/m3.py"   # PAGES-DRYRUN·HELP-SAFE 실패해야
```

## 실행 기록

- 신선 빌드로 Go 바이너리 생성 → 두 구현 나란히 34/34 (`runs/conformance-*.log`).
- 변이 3종 전부 rc 1로 격추, 각각 **예측한 항목에서만** 실패 (다른 항목 오염 없음).
- 특이사항: zsh의 `g` 별칭과 탐침 스크립트의 셸 함수명이 충돌해 한 번 죽었다 (C024의 *"셸 이식성도 환경 계약이다"* 재현). 구현 결함 아님 — 하네스 결함이며 함수명 변경으로 해소.

## 산출물

- `runs/conformance-reference.log`, `runs/conformance-go.log` — 34/34 (rc 0)
- `runs/mutant-m1.log`, `mutant-m2.log`, `mutant-m3.log` — 전부 rc 1 (격추)
- `mutants/m1.py`, `m2.py`, `m3.py` — **불변 기준** (C019의 재현 규약: 픽스처는 불변, 실데이터 확인은 가변). 각 변이는 원본 대비 **정확히 한 줄** diff.
