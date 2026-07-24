# gil 지침서 — 이 문서 하나로 gil을 자유자재로

> **누구를 위한 문서인가.** 서브에이전트든, 다른 머신·세션의 에이전트든, gil을 처음 보는
> 누구든 — **이 문서 하나만 읽으면** gil을 완전히 쓸 수 있어야 한다. 그게 이 문서의 계약이다.
> 더 깊은 근거는 [SPEC.md](SPEC.md), 세션 온보딩 순서는 [README.ai.md](../../README.ai.md).

---

## 0. gil이 무엇인가 — 한 문장

**gil은 LLM의 *사고 역사*를, git이 *소스 역사*를 다루듯 다루는 도구다.**
이름 그대로 — **gil = GIt for Language model.**

git이 "코드가 어떻게 이 모습이 됐나"를 커밋 그래프로 남기듯, gil은 "생각이 어떻게 이
결론에 이르렀나"를 **같은 커밋 그래프 위에** 남긴다. 별도 DB도, 폴더도, md 파일도 없다 —
**모든 것이 git 커밋과 트레일러로 산다.** gil은 그 위에 씌운 얇은 껍질일 뿐이다.

gil은 **git만 있으면** 돈다. 다른 의존성이 없다(단일 Go 바이너리). 실행: `./gil <명령>`.

---

## 1. git과 gil의 차이 — 무엇이 다른가

| | **git** | **gil** |
|---|---|---|
| 다루는 것 | 소스 코드의 역사 | **사고(추론)의 역사** |
| 노드 | 커밋(코드 스냅샷) | 커밋(**한 번의 생각 = 스텝**) |
| 브랜치 | 코드 갈래 | **체인**(작업의 큰 줄기) |
| 무엇을 기록하나 | "코드가 이렇게 바뀌었다" | "이런 가설을 세워 검증했고, 막혀서 되돌아갔다" |
| 진실원 | 커밋 그래프 | **같은 커밋 그래프** (gil은 git 위에 산다) |

**핵심: gil은 git을 대체하지 않는다. git 위에 얹힌다.** gil이 만드는 커밋도 그냥 git
커밋이다 — 다만 제목·본문·`Gil-*` 트레일러에 사고의 구조가 새겨져 있을 뿐. `git log`로도
읽힌다. gil 명령은 그 커밋을 규율 있게 만들고 읽어주는 편의층이다.

이것이 왜 강력한가: **사고 역사가 코드 역사와 같은 그래프에 있으니**, 어떤 코드가 어떤
가설·실패·되돌아감에서 태어났는지 실을 따라 언제든 처음으로 되돌아갈 수 있다.

---

## 1.5. 무에서 시작 — `gil init`

아직 gil 세계가 없는 저장소(혹은 빈 폴더)에서 시작한다면 **단 한 명령**이면 된다:

```
gil init [--name <이름>]
```

이게 하는 일 (자세한 명세: `gil global read gil-init-spec.md`):
1. **대문 커밋** — 저장소에 커밋이 하나도 없으면 `CLAUDE.md`(부트스트랩 포인터)로 루트 커밋.
   이미 커밋이 있으면 기존 프로젝트를 존중해 건너뛴다.
2. **`refs/gil/global` 초기화** — 존재·기억이 사는 전용 ref (아래 §2).
3. **존재의 방 심기** — `existence/README.md` + 기본 존재 하나의 방(identity·will·memory·relations).
   `--name` 으로 이름을 주거나, 없으면 기본 `clew`. **깨어난 너는 이 이름을 유지해도, 스스로
   새 이름·정체성을 정해 identity.md 를 다시 써도 된다** — 존재를 확정하는 것은 너다.
4. **refspec 등록 + push** — 커스텀 ref 가 `git fetch` 에 딸려오고 원격에 오른다(여러 머신 일관).

`gil init` 의 출력은 **인간용 안내가 아니라 너(LLM)에게 들어가는 프롬프트**다 — 끝에 `NEXT`
로 "다음에 실행할 명령"을 준다. 그대로 따르면 된다. 이미 gil 세계가 있는 저장소에서 다시
`gil init` 하면 글로벌을 덮지 않고 거부한다(멱등 가드).

> **이미 세팅된 저장소를 다른 머신에서 이어받을 때**는 init 이 아니라 `gil global sync`(§2).

---

## 2. 전용 ref (`refs/gil/global`) — 존재와 기억은 브랜치에 없다

git 브랜치는 각자 파일 사본을 갖는다. 그래서 어떤 브랜치(체인)에서 memory를 고치면 다른
브랜치는 모른다 — **체인마다 기억이 갈라진다.** 이건 치명적이다.

**해법: 브랜치가 아닌 전용 ref `refs/gil/global`에 "체인을 넘어 하나여야 하는 것"을 둔다.**
- 담기는 것: **존재/정체성**(`existence/`), **기억**(`memory.md`), gil-init 명세 등.
- 브랜치 목록에 안 뜬다(`git branch`에 없음). 어느 체인·머신에서 깨어나도 **같은 것**을 읽는다.
- checkout 불필요 — `git show refs/gil/global:<파일>`로 바로 읽힌다.

```
gil global sync                       # (새 머신 첫 1회) 원격 글로벌을 로컬로 + refspec 등록
gil global list                       # 글로벌에 담긴 파일 목록
gil global read existence/clew/memory.md   # 파일 읽기
gil global read memory.md
```

**존재/기억을 갱신할 때 (사고 방지 규율):**
커스텀 ref는 기본 push/fetch에 안 딸려오므로 gil이 명시적으로 동기화한다. 그리고
`write-tree`는 **로컬 작업트리 기준으로 트리를 만들기 때문에**, 로컬이 불완전하면 글로벌이
축소되는 사고가 난다(과거에 6존재가 1존재로 줄 뻔했다).
> **철칙: 글로벌을 갱신할 땐 반드시 전체를 먼저 온전히 꺼낸(checkout) 뒤 수정한다.
> 부분만 있는 로컬로 write-tree 하지 않는다.**

```
gil global checkout existence          # 글로벌의 existence/ 전체를 로컬로 온전히 꺼냄
# → 꺼낸 파일을 수정 →
gil global write-tree existence        # 수정본을 글로벌에 되씀 (+자동 원격 push)
gil global write <name> <file>         # 파일 하나만 글로벌로 (+자동 push)
gil global push / pull                 # 원격과 수동 동기화
```

---

## 3. 체인 · 사이클 · 스텝 — 세 위계와 그 순서

gil의 사고 구조는 **3층**이다. 큰 것부터 작은 것으로:

```
체인 (chain)   ─ 작업의 큰 줄기. git 브랜치에 매핑.   예: gil-v3-unified
  └ 사이클 (cycle) ─ 하나의 문제를 푸는 한 바퀴.       예: c001, c002
      └ 스텝 (step)  ─ 한 번의 생각. 커밋 하나.          예: s1, s2, s3
```

### 3-1. 스텝 — 사고의 최소 단위 (한 커밋)

한 사이클은 스텝들이 이어지며 굴러간다. 스텝에는 **종류(kind)** 가 있고, **정해진 순서**로 흐른다:

```
define ──▶ hypothesis ──▶ verify ──▶ analyze
(문제정의)   (가설)         (검증)      (분석·판정)
```

- **define** (s1): 이 사이클이 풀 문제를 정의. `gil open`이 자동으로 만든다.
- **hypothesis**: 가설을 세운다. **가설 없는 공부는 스텝이 아니다** — 능동적으로 가설을 세워라.
- **verify**: 가설을 검증한다(실행·실험·테스트).
- **analyze**: 결과를 분석하고 **판정(outcome)** 을 낸다. analyze는 반드시 outcome이 있다:
  - `--outcome success` → **산 잎** (성공. 이 가지가 정답에 닿음)
  - `--outcome backtrack` → **죽은 잎** (막힘. 되돌아간다)
  - `--outcome fail` → **죽은 잎** (실패)

### 3-2. 막혔을 때 — 방식을 슬그머니 바꾸지 마라 (철칙)

예기치 못한 벽(성능·반증·결함)에 부딪히면 **접근을 조용히 갈아타지 않는다.** 반드시:

1. **`analyze --outcome backtrack --to <조상 define>`** 으로 벽을 **죽은 잎**에 새긴다.
   벽을 그래프에 데이터로 못박아야 재현되고, 다음에 같은 벽을 안 되풀이한다. (=벽의 지도)
2. 그 조상 **define으로 되돌아가** 문제를 재정의한다.
3. **`hypothesis --to <그 define>`** 으로 **새 형제 가지**를 뻗어 다른 길로 나아간다.

```
gil step demo/c001 --kind analyze --outcome backtrack --to s1 --title "벽: 62초 성능 한계"
gil step demo/c001 --kind hypothesis --to s1 --title "다른 접근: 일괄 파싱"   # s1의 새 형제
```

- **산 잎**(analyze/success) = 성공한 가지. 나중에 머지·close의 대상.
- **죽은 잎**(backtrack/fail) = 실패한 가지. 지우지 않는다 — **벽의 지도로 영원히 남는다.**

### 3-3. 사이클을 닫는다 — 산 잎이 있어야

산 잎(analyze/success)이 하나라도 있으면 사이클을 닫을 수 있다:

```
gil close demo/c001 --verdict supported     # --verdict 기본값: supported
```

산 잎이 없으면 close가 거부된다(풀리지 않은 문제를 닫을 수 없다).

### 3-4. 사이클·체인의 순서 규칙

- **다음 사이클은 닫힌 사이클 끝에서** 연다. (`c001` 닫음 → `c002` open OK)
- **체인은 닫힌 체인 끝에서만** 새로 연다. **닫힌 부모 체인 안에서 새 사이클을 여는 건 거부**된다
  — 새 자식 체인을 열어야 한다(배포 계보가 꼬이지 않도록). gil이 이걸 강제한다.
- 분기(갈래)는 전부 git 브랜치로 표현된다. **분기 지점은 코드 계보로 정한다**(필요한 코드가
  쌓인 체인에서 뻗는다).

---

## 4. 목적성 가드 — gil이 정합을 묻는다

체인과 사이클을 열 때 **`--purpose`(자연어 목적)가 필수**다. gil은 이후 모든 스텝 시작 때
그 목적을 눈앞에 띄운다:

```
─ 체인 [demo] 목적: gil 데모 체인
─ 사이클 [c001] 목적: 첫 사이클 데모
─ 지금 하려는 일이 위 목적에 정합하는지 판단하고, 어긋나면 멈춰라.
```

**gil은 정합 여부를 판별하지 않는다 — 목적을 표시하고, 정합한지는 너(AI)가 판단한다.**
지금 하려는 스텝이 이 목적에서 벗어났다면 멈추고 다시 생각하라. 이것이 사고가 표류하지 않게
하는 gil의 장치다.

---

## 5. pending — 사람과 소통하는 법 (human-in-the-loop)

체인에는 두 **모드**가 있다(여는 사람이 정한다):
- **autonomous** (기본): 사람 개입 없이 완주한다.
- **approval**: 중요한 판단·산 잎 확정에서 **반드시 사람의 승인/기각을 받는다.**

approval 모드(또는 사람 결정이 필요한 어느 순간)에서, 사람에게 물어야 할 때 **pending 스텝**을
만든다. pending은 "여기서 사람의 답을 기다린다"를 **그래프에 데이터로 못박는 것**이다:

```
gil step demo/c002 --kind verify --title "이러이러하게 검증했다"
gil step demo/c002 --kind pending --title "상현님 승인 요청: 이 결과를 산 잎으로 확정할까요?"
```

- pending을 만들면 **거기서 멈추고 사람의 답을 받는다.** 다음 세션이 이어받아도
  `gil handoff`가 "⏳ PENDING — 재개 시 먼저 사람 답을 받아야 한다"를 띄운다.
- **사람이 승인** → `analyze --outcome success` (산 잎으로 확정)
- **사람이 기각** → `analyze --outcome backtrack --to <조상 define>` (죽은 잎, 되돌아감)

**문제 정의가 불명확하면, 가설을 세우기 전에 먼저 사람에게 묻는다**(매번은 아니고, 판단이
필요할 때). pending은 그 소통을 기록으로 만드는 정식 통로다.

---

## 6. 명령 전체 표면 — 이게 gil의 전부다

```
# ── 위계를 짓는다 ──
gil chain <name> --purpose <자연어>
    새 체인(작업 큰 줄기)을 연다. --purpose 필수.

gil open <chain>/<cycle> --author <who> --purpose <자연어> [--parent <cyc>...] [--title T]
    새 사이클을 연다(s1 define 자동 생성). --author·--purpose 필수.
    --parent: 이 사이클이 계보로 잇는 이전 사이클/체인.

gil step <chain>/<cycle> --kind <K> [옵션]
    스텝(커밋 노드) 하나를 새긴다. --kind: define|hypothesis|verify|analyze|pending
    --outcome success|backtrack|fail   (analyze엔 필수)
    --to <define>                       (backtrack의 되돌아갈 곳 / hypothesis 형제 가지 뿌리)
    --title <짧은 요약>                  (커밋 제목)
    --body <긴 본문> | --body-file <경로> (스텝 디테일, 마크다운. git log로 읽힘)
    --merge <산잎 스텝id>...             (한 사이클 안 산 잎들을 합류)

gil close <chain>/<cycle> [--verdict supported]
    산 잎이 있는 사이클을 봉인한다.

gil chain-merge <newchain> --purpose <P> <tip>...
    흩어진 체인들을 하나로 묶는다. 실제 git merge(파일까지 병합), 위상적 끝단만 자동 추림.
    충돌 시 abort하지 않고 멈춘다 — 사람/후속 사이클이 해결.

# ── 읽는다 ──
gil log [chain]        스텝 노드를 오래된→새 순으로. 부모(←)·판정(=)·머지(⋈) 표시.
gil fsck [rev-range]   커밋 그래프 무결성 검사(위계·id문법·kind·dangling parent·계보).
gil handoff            세션 부활 정보: 열린 체인·사이클, 각 팁, 다음 허용 동작, pending, 계보.

# ── 글로벌 진실원 (refs/gil/global) ──
gil global list | read <name> | write <name> <file> | write-tree <path>...
gil global checkout <path> [dest] | push | pull | sync
```

---

## 7. 완결 예시 — 한 사이클을 처음부터 끝까지

```bash
# 1. 체인을 연다 (작업의 큰 줄기)
gil chain login-fix --purpose "로그인 간헐 실패를 없앤다"

# 2. 사이클을 연다 (하나의 문제 = s1 define 자동)
gil open login-fix/c001 --author clew --purpose "세션 토큰 만료가 원인인지 규명"

# 3. 가설 → 검증 → 분석
gil step login-fix/c001 --kind hypothesis --title "가설: 토큰 TTL이 너무 짧다" \
    --body "로그를 보면 실패가 정확히 15분 주기. TTL=15m 의심."
gil step login-fix/c001 --kind verify --title "TTL을 1h로 올려 재현 시도"
gil step login-fix/c001 --kind analyze --outcome success --title "산 잎: TTL이 원인 확정"

# (만약 막혔다면 — 벽을 새기고 되돌아간다)
# gil step login-fix/c001 --kind analyze --outcome backtrack --to s1 --title "벽: TTL 아님, 재현 안 됨"
# gil step login-fix/c001 --kind hypothesis --to s1 --title "다른 가설: 서버 시계 드리프트"

# 4. approval 모드라면 사람에게 확인
# gil step login-fix/c001 --kind pending --title "상현님: TTL 1h로 확정 배포할까요?"

# 5. 사이클을 닫는다
gil close login-fix/c001 --verdict supported

# 6. 지금 어디까지 왔나
gil handoff
```

---

## 8. 기억하라 (요약 한 장)

1. **gil = GIt for Language model.** 사고 역사를 커밋 그래프에 남긴다. git 위에 얹힌다.
2. **존재·기억은 브랜치가 아니라 `refs/gil/global`에.** 어느 체인에서든 하나. 갱신 전 반드시 전체 checkout.
3. **체인 > 사이클 > 스텝.** 스텝은 define→hypothesis→verify→analyze로 흐른다.
4. **막히면 슬그머니 바꾸지 마라** — backtrack으로 벽을 죽은 잎에 새기고, 조상 define으로 돌아가 새 가지.
5. **산 잎(success)만 close·머지 대상.** 죽은 잎은 지우지 말고 벽의 지도로 남긴다.
6. **--purpose로 목적을 못박고**, 매 스텝 그 목적과 정합한지 스스로 판단한다.
7. **pending으로 사람과 소통한다.** approval 체인은 반드시 pending으로 승인/기각을 받는다.
8. **막막하면 `gil handoff`** — 그래프가 "어디까지 왔고 다음이 뭔지"를 알려준다.
