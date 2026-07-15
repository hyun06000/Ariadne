# 3. 가설 검증

2-design의 기대 행동표를 재현 가능한 스크립트로 집행했다. 모든 스크립트는 `--gil "<호출>"`을 받아 두 구현에 동일하게 적용된다 (`--gil`엔 **절대 경로** — C028·C043 함정).

## 산출물

| 파일 | 무엇 |
|---|---|
| `repro.sh` | T1 — `open --new-chain --git`이 chain.md를 커밋하는가 (수정 전엔 미추적, 후엔 HEAD 포함) |
| `test_r14.sh` | T2 — fsck R14: chain.md 없으면 위반(exit 1), 있으면 통과 |
| `mutations.sh` | M1~M4 — 각 계약을 하나씩 제거하면 정확히 대응 항목만 FAIL하는가 |

## 재현 방법

```bash
SPEC=rooms/deployment/ariadne-spec
(cd $SPEC/go && go build -o /tmp/gil-go main.go)          # Go 빌드 (go.mod 없음)
V=rooms/experiment/chains/loom/C044-chain-md-commit/3-verification
bash $V/repro.sh    "python3 $PWD/$SPEC/gil.py"           # T1 참조
bash $V/repro.sh    "/tmp/gil-go"                          # T1 Go
bash $V/test_r14.sh "python3 $PWD/$SPEC/gil.py"           # T2 참조
bash $V/test_r14.sh "/tmp/gil-go"                          # T2 Go
python3 $SPEC/conformance.py --gil "python3 $PWD/$SPEC/gil.py"  # T4~T6 참조 → 64/64
python3 $SPEC/conformance.py --gil "/tmp/gil-go"               # T4~T6 Go   → 56/56
bash $V/mutations.sh                                       # M1~M4
```

## 실행 기록 — 2026-07-15, darwin 25.2.0, Python 3 / Go(stdlib)

### 수정 전 (결함 실증)
`repro.sh` 양 구현: `?? rooms/experiment/chains/demo/chain.md` (미추적), HEAD에 chain.md 없음 — **1-hypothesis의 결함 재현.**

### 수정 후 — 기대 행동표

| ID | 기대 | 참조 | Go |
|---|---|---|---|
| T1 | chain.md가 HEAD 커밋에 포함, 미추적 없음 | ✓ | ✓ |
| T2 | chain.md 없으면 R14 위반 exit 1 | ✓ | ✓ |
| T3 | 정상 저장소(4체인) fsck 위반 0 (과잉검출 없음) | ✓ | ✓ |
| T4 | OPEN-NEWCHAIN-COMMIT PASS | ✓ | ✓ |
| T5 | FSCK-R14 PASS | ✓ | ✓ |
| T6 | 회귀 0 — conformance 총계 | **64/64** (62→64) | **56/56** (54→56) |
| T7 | 두 구현 fsck **R14 라인** 바이트 동일 | ✓ (아래 주) | ✓ |

### 변이 격추 (M1~M4)

| 변이 | 기대 FAIL | 실제 |
|---|---|---|
| M1 파이썬 커밋 chain.md 제거 | OPEN-NEWCHAIN-COMMIT | ✓ 그것만 |
| M2 파이썬 fsck R14 제거 | FSCK-R14 | ✓ 그것만 |
| M3 Go 커밋 chain.md 제거 | OPEN-NEWCHAIN-COMMIT | ✓ 그것만 |
| M4 Go fsck R14 제거 | FSCK-R14 | ✓ 그것만 |

동반 실패 0 — 샌드박스 독립(C040) 준수.

## T7의 발견 — 범위 밖 선재 드리프트 (별도 이슈 후보)

R14+R6 위반을 섞은 저장소에서 두 구현 fsck stdout을 바이트 대조하니, **내가 추가한 R14 라인은 바이트 동일**했으나 **기존 R6 메시지**가 갈렸다:
- 참조: `parent 'ghost'가 존재하지 않는다 (끊어진 참조)`
- Go: `parent 'ghost'가 존재하지 않는다`

이는 C044가 만든 게 아닌 **선재 결함**이다. conformance가 FSCK-R6를 `exit ≠ 0`만으로 판정하고 메시지 문면을 안 봐서 안 잡혔다 — *"판정기가 안 보는 계약은 없는 계약이다"*(Weft)의 또 다른 사례. C044 범위(chain.md 커밋 + R14)를 오염시키지 않기 위해 **여기서 고치지 않고** 새 이슈 후보로 기록한다. R14 산출물 자체는 교차 통과.
