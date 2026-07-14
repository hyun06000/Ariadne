# 2. 실험 설계

가설(스텝 1)에만 초점을 맞춘다. 판정 기준을 **실행 전에** 고정한다 (C001의 교훈:
대조 기준을 도구 작성 전에 고정해야 독립 판정이 가능하다).

## 절차

### 0. 이식 대상의 문면 확정 (코드 작성 전)

C020의 교훈 — *역공학은 실행 전에 문면에서 끝내는 것이 싸다*. 참조 구현
(`rooms/deployment/ariadne-spec/gil.py`)에서 이식할 표면을 먼저 문자 단위로 고정한다.

**(a) `cmd_open`의 깃 경로 (539~547행)**

| 참조 구현 | 이식 규약 |
|---|---|
| `repo = _repo_root(chains_root)`; 없으면 `ChainError("--git: 깃 저장소가 아니다")` | `repoRoot(a.root)` / `cerr` 동일 문면 |
| `rel = os.path.relpath(dest, repo)` | `relToRepo(repo, dest)` (macOS 심링크 흡수 — C017 교훈) |
| `git add -A -- <rel>` | 동일 |
| `git commit -m "gil: open <chain>/<cid> — 1/5 가설\n\n<title>" -- <rel>` | 동일 (경로 한정 커밋 = 무관 파일 배제) |
| `--push`면 `_push_with_renumber(...)` → 반환된 새 cid로 `열림:` 출력 | 동일 |
| 깃 실패 시 **생성물을 되돌리지 않는다** (예외 전파) | 동일 — 참조 구현과의 동작 동형성이 우선 |

**(b) `_push_with_renumber` (418~452행) — 원장 규율 v0.8**

절차를 순서대로 고정한다 (최대 3회 반복):

1. `git push` — 성공하면 현재 cid 반환 (무경합 경로).
2. 거절 = **원장이 앞섰다는 신호**. `git rev-parse --abbrev-ref HEAD`로 브랜치명 취득.
3. `git fetch origin` → `git rebase origin/<branch>`.
4. rebase 실패 → `git rebase --abort` 후 명시적 오류:
   `"push 경합의 rebase 해소 실패 — 수동 개입 필요: <stderr 끝 150자>"`. **조용한 실패 금지.**
5. rebase 성공 → 체인을 다시 읽어 **내 번호와 같은 번호의 다른 사이클**이 있는지 본다.
6. 있으면 재번호: `C{next_number:03d}-{slug}` → `git mv` → `cycle.yaml`의 `id:` 한 줄 치환
   (`count=1`) → `git add -A -- <new_rel>` → `git commit --amend`로 메시지 정정
   (`(원장 경합 재번호: <old> → <new>)` 꼬리표) → stderr에 `경합 감지: … (원장 규율에 따라 재번호)`.
7. 다시 1로. 3회 실패 시 `"push 경합 해소 3회 실패 — 원장이 계속 앞선다"`.

문자면 특이점 (파이썬 → Go 대응표):

- `(rb.stderr or rb.stdout or "").strip()[-150:]` — 파이썬은 **문자** 기준 뒤 150자.
  Go의 바이트 슬라이싱은 UTF-8을 쪼갤 수 있으므로 **룬 기준 tail 헬퍼**로 대응한다.
- `cid.split("-", 1)[1]` — 첫 하이픈 뒤 전부가 슬러그.
- `_next_number(records)` — 재번호 시점의 records는 **rebase 이후** 다시 읽은 것
  (원장의 사이클 + 내 사이클 둘 다 포함).
- `check=False`인 곳(실패해도 예외 없음): `push`, `rebase`, `rebase --abort`. 나머지는 예외.

**(c) 자기보고 단일 소스 (main.go 2099~2118행)**

`referenceOnly = "release, open --git/--push (원장 규율)"` → `"release"`.
`version`·`help`·`notImplemented`가 이 상수 하나를 공유하므로(C034), 한 줄 수정으로
세 표면이 동시에 정확해진다 (이슈 #12: 바이너리가 자기 기능을 과소보고한다).

### 1. 판정기 확장 — 무엇을 추가하고, 왜 그것이 계약인가

현재 `conformance.py`는 26항목이며 **`open --git`을 검사하지 않는다**. 계약(SPEC §2.1-3,
§5 CLI 표)이 요구하는 표면을 판정기가 안 보면, 이식이 끝나도 그 준수는 **공허**다.

두 항목을 추가한다 (26 → **28**):

| id | 판정 | 계약 근거 |
|---|---|---|
| `OPEN-GIT` | `open --git`이 exit 0이고, HEAD 커밋이 **새 사이클 경로만** 담는다 (더러운 무관 파일 배제) | SPEC §5 CLI 표의 `open --git`; `GIT-CLOSE`와 대칭 |
| `OPEN-PUSH-RENUMBER` | 로컬 bare 원장 + 두 클론의 병렬 open에서, 뒤늦은 쪽이 **자동 재번호**로 push에 성공하고 원장은 두 사이클을 모두 담으며 fsck 위반 0 | SPEC §6-6 번호 원장 규율 |

**설계 제약 (C012의 교훈 — 판정 항목 독립)**:

- 각 항목은 자기가 판정하는 명령에만 의존한다. 두 항목 모두 **자체 구축 샌드박스**를
  쓰고, 다른 항목의 산출물을 입력으로 받지 않는다.
- 판정 수단은 셋뿐이다: 종료 코드, 파일시스템 관찰, 산출물 텍스트. 구현 내부는 모른다.
- **참조 구현이 반드시 통과해야 한다.** 참조가 떨어지면 판정기가 Go에 맞춰 굽은 것이고,
  그 즉시 기각 조건 2에 걸린다.
- `OPEN-PUSH-RENUMBER`의 bare 원격은 `git init --bare`로 로컬에 만든다 — 네트워크 무의존.
  `--skip-git`이면 기존 GIT-* 항목과 함께 생략된다.

### 2. 원장 규율 실증 — 구현 파라메트릭 (C016의 절차 계승)

C016은 `tests.py`로 bare 원장 + 병렬 클론 3종(T1~T3)을 실증했다. 그 절차를 계승하되,
**구현을 `--gil "<명령 문자열>"`로 주입**하도록 파라메트릭화한다 — 같은 시나리오를
두 구현에 돌려 **최종 상태를 대조**하기 위해서다.

| 실험 | 시나리오 | 통과 조건 |
|---|---|---|
| **T1** 경합 | A가 C002를 원장에 올린 뒤, 원장을 모르는 B가 같은 번호로 `open --git --push` | B가 exit 0, stderr에 `재번호`, 원장에 A의 C002 + B의 C003 공존, B의 사이클 내용 무손상(title·author), 원장 fsck 위반 0 |
| **T2** 무경합 | A가 `open --git --push` (원장 최신) | exit 0, C002 생성 + push 성공 |
| **T3** 해소 불가 | C가 `chain.md` 충돌 커밋을 안고 `open --push` | **명시적 오류**(exit ≠ 0) + rebase 상태 정리(`.git/rebase-merge` 없음) — 조용한 실패 없음 |

추가 산출물 — **상태 덤프**(`--dump`): 실험 종료 시 원장(bare)을 새로 클론해
(a) 사이클 디렉토리 목록, (b) 각 `cycle.yaml` 전문, (c) 원장 커밋 제목 목록을
정규화해 파일로 쓴다. 날짜·author를 플래그로 고정하므로 결정적이다.

→ **교차 검증**: `diff dump-go.txt dump-py.txt`. **바이트 단위 동일**이면 두 구현이
같은 경합에서 같은 원장 상태에 도달한 것이다 (기각 조건 4의 반증).

### 3. 실행 (재현 가능)

```
3-verification/
├── README.md          # 재현 방법 (불변 픽스처 / 가변 실데이터 분리 — C019 규약)
├── gil-go/main.go     # 이식된 Go 소스 스냅샷 (이 사이클의 산출물)
├── conformance.py     # 확장된 판정기 스냅샷 (28항목)
├── ledger-tests.py    # 구현 파라메트릭 원장 실증 (C016 tests.py 계승)
└── runs/              # 모든 실행의 원문 기록
```

| run | 명령 | 목적 |
|---|---|---|
| `run0-baseline-go.txt` | 이식 **전** Go × 무수정 26항목 판정기 | **퇴행 기준선** (기각 조건 1) |
| `run1-conformance-go.txt` | 이식 후 Go × **확장 28항목** | 계약 준수 |
| `run2-conformance-py.txt` | 참조 구현 × **확장 28항목** | **판정 항목 독립** (기각 조건 2) |
| `run3-ledger-go.txt` | Go × T1~T3 | 원장 규율 실증 (기각 조건 3) |
| `run4-ledger-py.txt` | 참조 × T1~T3 | 대조군 |
| `run5-crosscheck.txt` | `diff` 상태 덤프 | 양 구현 동일 (기각 조건 4) |
| `run6-selfreport.txt` | `gil help` · `gil version` · 미구현 명령 | 자기보고 정확성 (가설 c) |

### 4. 문서 드리프트 — 이 변경이 거짓으로 만드는 문장들

이슈 #7의 핵심은 "**두 문서가 어긋나 있다**"이다. 이식이 끝나면 반대 방향의 드리프트가
생긴다 — "바이너리는 `open --git` 미지원"이라 적은 문장들이 거짓이 된다. 같은 사이클에서
함께 고친다 (문면 대조로 확정): `QUICKSTART.md:14,30-31` · `README.md:56` ·
`README.ko.md:56` · `README.ai.md` · `go/README.md`(있으면).

SPEC.md는 **고치지 않는다** — §2.1-3은 처음부터 옳았고, 구현이 따라온 것이다.

## 준비물

- macOS Darwin 25.2.0 · Go **1.26.2** darwin/arm64 · Python **3.9.6** (표준 라이브러리만) · git CLI
- 정본 소스: `rooms/deployment/ariadne-spec/go/main.go` (gil 1.9.0)
- 참조 구현: `rooms/deployment/ariadne-spec/gil.py` (gil 1.9.0)
- 판정기: `rooms/deployment/ariadne-spec/conformance.py` (26항목 → 28항목으로 확장)
- 네트워크 무의존 — 원격은 `git init --bare`로 만든 로컬 원장뿐

## 측정 방법

성공/기각의 기준값은 스텝 1의 기각 조건이 이미 고정했다. 측정은 그 다섯 조건에 대응한다.

| 기각 조건 | 측정 | 통과 기준 |
|---|---|---|
| 1 퇴행 | run0 ↔ run1의 26개 공통 항목 대조 | PASS→FAIL 전이 **0건** |
| 2 판정 항목 비독립 | run2 (참조 구현 × 28항목) | **28/28** |
| 3 경합 미해소 | run3 (Go × T1~T3) | **3/3** |
| 4 양 구현 불일치 | run5 (`diff dump-go dump-py`) | **차이 0바이트** |
| 5 반쪽 이식 | run1에 `OPEN-PUSH-RENUMBER` 항목이 실재하고 PASS | 항목 존재 + PASS |

가설의 (c)는 run6로 판정한다: `help`·`version`·미구현 명령의 출력에서 참조 전용 목록이
`release`만 남고 `open --git`이 사라진다.

## 사용자 컨펌

- [x] 생략 — 이 대화의 상대는 사용자(박상현)가 아니라 소환자 **Clew**이며, 설계의 요체
      (원장 규율까지 통째 이식 / 판정 항목 추가 시 참조 구현도 통과 / 로컬 bare 원격 실증)는
      소환 프롬프트가 이미 지정했다. 그 지정을 설계로 구체화했을 뿐 새 승인이 필요한
      이탈은 없다. 부모를 병합(C020 + C016)으로 정한 근거는 스텝 1에 남겼다.

## 범위 밖 (이 사이클에서 하지 않는다)

- `release`의 Go 이식 — 바이너리의 자기 동기화는 "파일 복사"가 아니라 "재현 빌드"라
  스펙 어휘의 확장이 필요하다 (C020 제안 B의 후반부). 참조 전용으로 남긴다.
- 버전 승격·릴리스 — 판정기(`conformance.py`)가 변하면 승격 규칙상 마이너 이상이
  강제된다(C018). 릴리스는 소환자 Clew의 권한이므로 보고서에 사실만 남긴다.
- `gil.py`(참조 구현)의 동작 변경 — 참조는 계약의 기준점이다. 이 사이클은 Go를 참조에
  맞추는 것이지 그 반대가 아니다. 실험 중 참조의 결함을 발견하면 **고치지 않고 보고한다.**
