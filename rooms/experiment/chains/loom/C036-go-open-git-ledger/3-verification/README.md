# 3. 가설 검증

## 산출물

```
3-verification/
├── gil-go/main.go     # 이식된 Go 소스 스냅샷 (정본: rooms/deployment/ariadne-spec/go/main.go)
├── conformance.py     # 확장된 판정기 스냅샷 26→28항목 (정본: .../ariadne-spec/conformance.py)
├── ledger-tests.py    # 구현 파라메트릭 원장 규율 실증 (C016 tests.py 계승, --gil 주입)
└── runs/              # 모든 실행의 원문 기록 (run0~run7)
```

**불변 / 가변의 분리** (C019가 스펙에 명문화한 규약, C001의 교훈에서 옴):

- **불변 (시점 고정, 바이트 재현 가능)**: `run1`~`run7`. 판정기·실증기가 스스로
  샌드박스와 로컬 bare 원장을 만들어 쓴다 — 외부 픽스처·네트워크·레포 상태에 의존하지 않는다.
  아래 명령으로 언제 다시 돌려도 같은 판정이 나온다.
- **가변 (실데이터 스냅샷)**: 마지막 절의 실데이터 fsck 결과(사이클 41개)는 **기록 시점의
  스냅샷**이다. 레포가 자라면 숫자는 달라진다 — 도구 결함이 아니라 데이터 드리프트다.

## 재현 방법

```bash
# 0) 경로 (레포 루트에서)
SPEC=rooms/deployment/ariadne-spec
CYC=rooms/experiment/chains/loom/C036-go-open-git-ledger
BUILD=$(mktemp -d)

# 1) 이식된 Go 바이너리 빌드 (Go 1.26.2)
go build -o "$BUILD/gil" "$SPEC/go/main.go"

# 2) 계약 준수 판정 — 양 구현이 나란히 28/28이어야 한다
#    주의: --gil에는 반드시 절대 경로를 준다 (판정기는 샌드박스를 cwd로 구현을 실행한다 — C020의 함정)
python3 "$SPEC/conformance.py" --gil "$BUILD/gil"                      # → run1: Go 28/28
python3 "$SPEC/conformance.py" --gil "python3 $(pwd)/$SPEC/gil.py"     # → run2: 참조 28/28

# 3) 번호 원장 규율 실증 (로컬 bare 원장 + 병렬 클론, 네트워크 무의존) — 양 구현 3/3
python3 "$CYC/3-verification/ledger-tests.py" --gil "$BUILD/gil" --dump "$BUILD/dump-go.txt"
python3 "$CYC/3-verification/ledger-tests.py" --gil "python3 $(pwd)/$SPEC/gil.py" --dump "$BUILD/dump-py.txt"

# 4) 교차 검증 — 두 구현이 같은 경합에서 같은 원장에 도달하는가
diff "$BUILD/dump-go.txt" "$BUILD/dump-py.txt" && echo "원장 상태 바이트 단위 동일"

# 5) 자기보고 (이슈 #12)
"$BUILD/gil" help          # 참조 전용: release  ← open --git이 사라졌다
"$BUILD/gil" release 9.9.9 # 여전히 정직한 거부 (exit 3)
```

**퇴행 기준선(run0)의 재현**: 이식 전 소스는 이 사이클의 첫 커밋 이전 상태다.
`git show <이 사이클 최초 커밋>^:rooms/deployment/ariadne-spec/go/main.go`로 꺼내 빌드한 뒤
**무수정 26항목 판정기**(같은 커밋의 `conformance.py`)로 돌리면 26/26이 재현된다.

## 판정 요약

| run | 대상 | 결과 |
|---|---|---|
| `run0-baseline-go.txt` | 이식 전 Go × 무수정 26항목 | **26/26** (퇴행 기준선) |
| `run1-conformance-go.txt` | 이식 후 Go × 확장 28항목 | **28/28** — 퇴행 0, 신규 2항목 PASS |
| `run2-conformance-py.txt` | 참조 구현 × 확장 28항목 | **28/28** — 판정 항목 독립 확인 |
| `run3-ledger-go.txt` | Go × T1~T3 | **3/3** |
| `run4-ledger-py.txt` | 참조 × T1~T3 | **3/3** |
| `run5-crosscheck.txt` | 원장 최종 상태 대조 | **바이트 단위 동일** (sha256 일치) |
| `run6-selfreport.txt` | 자기보고 전/후 | 참조 전용 목록: `release, open --git/--push` → **`release`** |
| `run7-newchain-gap.txt` | `--new-chain --git` 파리티 | 양 구현 동일 — **참조 구현의 선행 결함 발견** (아래) |

## 실행 기록

- **일시**: 2026-07-14. **환경**: macOS Darwin 25.2.0 (arm64), Go 1.26.2, Python 3.9.6
  (표준 라이브러리만), git CLI. 네트워크 무의존 — 원격은 `git init --bare`로 만든 로컬 원장뿐.
- **특이사항 1 — 첫 스모크에서 바로 통과.** 코드를 쓰기 전에 참조 구현의 문면
  (`cmd_open` 539~547행, `_push_with_renumber` 418~452행)을 2-design에 표로 고정한 뒤
  함수로 대응시킨 순서의 효과다 (C020에서 확립한 방법). 재작업 0회.
- **특이사항 2 — `run5`의 1차 기록 결함.** `shasum … | sed 's|.*/||'`가 해시까지 지워
  아티팩트에 파일명만 남았다. diff 판정 자체는 옳았으나 **기록이 증거를 잃었다** — 명령을
  고쳐 재생성했다. (판정 절차도 틀릴 수 있다 — C014의 교훈이 이번엔 기록 층위에서 재발했다.)
- **특이사항 3 — 발견된 선행 결함**: `open --new-chain --git`이 새 체인의 `chain.md`를
  커밋하지 않는다. 커밋 경로가 사이클 디렉토리로 한정되는데 `chain.md`는 그 밖에 있기
  때문이다. **참조 구현·Go 양쪽 동일** (run7). fsck 규칙이 `chain.md`를 요구하지 않아
  위반으로도 안 잡힌다 — 그래서 조용하다. 2-design의 "범위 밖" 규정("참조의 결함을
  발견하면 고치지 않고 보고한다")에 따라 **고치지 않고 보고**한다.

## 실데이터 회귀 (가변 — 기록 시점 스냅샷)

이식된 Go와 참조 구현으로 이 레포를 각각 `fsck` — 두 출력이 일치했다:

```
경고 [결말없음] 34건 — verdict 미기록 (기존 사슬 유예): …
OK — 체인 4개, 사이클 41개, 위반 0건 (스키마 v0.4), 경고 34건
```

이 41개에는 **이 사이클(C036) 자신**이 포함된다 — 실데이터 체인의 첫 **병합 노드**
(`parent: [C020-go-web-port, C016-number-ledger]`)이며, 양 구현의 fsck가 다중 부모를
위반 없이 수용함을 부수적으로 확인했다.
