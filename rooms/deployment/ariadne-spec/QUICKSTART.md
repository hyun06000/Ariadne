# Ariadne Quickstart — 당신의 저장소를 아리아드네로 세우기

이 문서는 **데모가 아니라 당신의 실제 프로젝트**를 아리아드네 방식으로 운영하는 길이다.
"demo"라는 이름 대신 당신의 진짜 문제 이름을 쓰면, 그대로 당신의 저장소가 된다.

## 0. gil 설치 (바이너리 — 파이썬도 Go도 불필요)

```
curl -fsSL -O https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64
curl -fsSL -O https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS
grep ' gil-darwin-arm64$' SHA256SUMS | shasum -a 256 -c - && mv gil-darwin-arm64 gil && chmod +x gil
```

Intel 맥: `gil-darwin-amd64`, 리눅스: `gil-linux-{arm64,amd64}` (리눅스는 `shasum -a 256` 대신 `sha256sum`).

**체크섬 대조는 선택이 아니다.** 불일치하면 `&&` 체인이 끊겨 `gil`은 실행 파일이 되지 못한다 — 검증되지 않은 바이너리가 실행될 경로가 없다. 릴리스 직후의 불일치는 CDN 지연이므로 **1분쯤 뒤 블록을 재시도**하면 된다 (실측: 배포 1분 이내에 실제로 불일치가 관측됐다 — 이슈 #8).
gil이 닫힌 사이클에 대해 하는 일(선언된 해시와 실물의 대조)을 자기 자신의 설치에도 그대로 적용한 것이다.
**이 빌드가 무엇을 할 수 있는지는 문서에 묻지 말고 도구에 물어라** — 문서의 목록은 낡지만 도구의 자기보고는 계약이다 (§7.2):

```bash
./gil help              # 이 빌드가 구현한 명령 목록 (+ 기계 훅 gil:commands …)
./gil help goto         # 한 명령의 사용법 — 없는 명령이면 exit 3. 부작용 없는 능력 탐침
```

능력을 확인하겠다고 **명령을 실행해 보지 마라**. `./gil pages`는 두드리는 순간 워크플로 파일을 만든다 — 탐침은 `./gil pages --dry-run`이다.
*(참조 구현으로 쓰려면 아래 `./gil`을 `python3 gil.py`로 바꿔 읽으면 된다. `release`는 참조 구현 전용이며, 바이너리는 그 사실을 `./gil help release`로 정직하게 답한다.)*

## 1. 저장소를 연다

당신의 프로젝트 디렉토리(깃 저장소)에서 `gil`을 두고 시작한다. **템플릿을 미리 만들 필요 없다** —
`open`이 없으면 스스로 만든다 (`git init`처럼):

```bash
git init                      # 이미 깃 저장소면 생략
./gil open <문제영역> <첫-사이클-슬러그> --new-chain \
  --title "지금 풀 가장 작은 문제 한 줄" --author <당신-또는-LLM의-이름>
```

예: `./gil open parser tokenizer-spike --new-chain --title "토크나이저가 중첩 괄호를 처리하는가" --author me`.
`rooms/experiment/chains/<문제영역>/C001-<슬러그>/`에 5스텝 문서가 생긴다.

> **`--author`는 필수이고 기본값이 없다** (SPEC §3.2). 도구는 `opened`·번호처럼 *계산으로 아는 것*은 채우지만,
> **출처**(`author`·`parent`)는 오직 저자만 안다 — 모르는 것을 지어내면 원장이 거짓이 된다. 깃이 `user.name` 없이
> 커밋을 거부하는 것과 같은 이유다. 마찬가지로 **비어있지 않은 체인**에 사이클을 열면 `--parent <부모-id>`가
> 필수다 (정말 새 루트를 세우는 것이라면 `--new-root`). 빈 체인의 첫 사이클만 예외 — 루트라는 게 계산되니까.
**열 때부터 보이게**: `--git`(원격이 있으면 `--git --push`)을 붙이면 사이클을 여는 순간이
바로 각인된다 — 관전자에게 침묵과 멈춤은 구별되지 않는다 (SPEC §2.1-3).
`--push`는 번호 원장 규율을 따른다: 다른 존재가 같은 번호를 먼저 올렸으면 fetch·rebase 후
**자동으로 재번호**하고 다시 push한다 (§6-6). 양 구현 모두 지원한다 (loom/C036).

## 2. 사이클을 스텝으로 진행한다 (핵심 규율)

각 스텝 문서를 채우고, **스텝을 마칠 때마다 커밋한다** — 커밋의 단위는 사이클이 아니라 스텝이다(스펙 §2.1):

```bash
# 1-hypothesis.md 를 채운 뒤:
./gil step <문제영역> C001-<슬러그> 2 --git    # → 2/5 설계
# 2-design.md ... 3-verification/ ... 4-analysis.md 를 차례로:
./gil step <문제영역> C001-<슬러그> 3 --git
./gil step <문제영역> C001-<슬러그> 4 --git
./gil step <문제영역> C001-<슬러그> 5 --git    # → 5/5 보고
```

긴 스텝(특히 3단계 검증)은 중간에도 커밋하라. 침묵은 관전자에게 멈춤과 구별되지 않는다.

## 3. 사이클을 닫는다 (각인)

`5-report.md`에 교훈과 다음 사이클 제안을 쓴 뒤 (템플릿 그대로면 닫기가 거부된다):

```bash
./gil close <문제영역> C001-<슬러그> --git
```

깃 저장소면 사이클 디렉토리만 담은 커밋과 태그 `cycle/<문제영역>/C001-<슬러그>`가 남는다.
이후 `./gil verify`가 닫힌 사이클의 변조를 탐지한다 — 불변은 규범이 아니라 기계적 사실이다.

## 4. 다음 사이클은 이 보고서에서 태어난다

```bash
./gil open <문제영역> <다음-슬러그> --parent C001-<슬러그> \
  --title "C001의 교훈에서 나온 다음 문제" --author me --git
```

다른 문제 영역의 교훈을 이어받으면 `--lineage <다른체인>/<사이클id>`. 이렇게 체인이 자란다.
`./gil log`로 계보를, `./gil fsck`로 규칙 위반을 언제든 확인한다.

### 4.1 닫은 뒤에 출처가 틀렸다면 (`gil correct`)

`open`에서 `--parent`를 빠뜨린 채 닫았다면 `fsck`가 `경고 [다중루트]`로 알려준다. 닫힌 사이클은 불변이지만 — **도구가 대필한 거짓**은 정정할 수 있다. 단, **불변 문서가 그 값을 증언해야** 한다:

```bash
./gil correct <문제영역>/C002-<슬러그> \
  --field parent --to C001-<슬러그> \
  --evidence 1-hypothesis.md:5 \
  --author me --reason "open 시 --parent 누락"
```

정정 가능한 것은 **출처 필드**(`author`·`parent`·`lineage`)뿐이다. `verdict`나 보고서 내용은 **저자의 주장**이므로 바꿀 수 없다 — 결론이 무효가 됐다면 `gil supersede`다. 거짓값은 `corrections.yaml`에 영구히 남는다: **정정은 지우개가 아니라 각주다.**

## 4.5 병렬로 일하기 (선택 — 독립 갈래가 여럿일 때)

지금까지는 사이클 하나씩 순차다. 서로 **독립인 사이클이 여럿이면 동시에** 돌릴 수 있다 — 각 존재가 **격리 워크트리**에서 일해 공유 main에서 충돌하지 않는다. 능력은 `./gil help worktree`에 묻는다.

```bash
./gil worktree add <문제영역> <슬러그> --author <존재이름> --new-chain   # 새 워크트리+브랜치, 여기서만 일한다
# 그 존재가 워크트리 안에서 5스텝을 밟고 스텝마다 자기 브랜치를 push (main push 금지)
./gil worktree land <문제영역> <슬러그> --push                          # --no-ff 병합(부모2 보존) + 정리; 충돌은 거부·보존·abort
```

**철칙: 네 워크트리에서 일하라 — 공유 main으로 cd해 `gil open`을 실행하지 마라.** 그 유출이 다른 존재의 미커밋 작업을 지운 사고가 세 번 났다. `git config gil.owner <주-존재>`를 두면 주 체크아웃에서 주인 아닌 author의 `open`·`correct`를 도구가 거부한다(opt-in guard). 아직 push 안 된 병렬 작업의 번호는 `./gil reserve <문제영역> <슬러그> --for <이름>`으로 선점한다. 혼자 순차로 일한다면 이 절은 건너뛴다. 전문은 스펙 §6.8.

## 5. 체인 그래프 뷰어 — 두 가지 중 택일

뷰어를 보는 길은 둘이다. **GitHub을 안 써도 된다** — 로컬만으로 충분하다.

**A. 로컬 HTML (GitHub 불필요, 로컬 깃만 써도 됨):**

```bash
./gil web -o chains.html      # 자기완결 HTML 한 장 — 브라우저로 그냥 연다
```

서버도 네트워크도 필요 없다. 갱신하려면 다시 실행하면 된다. 팀과 나누려면 이 파일만 보내면 된다.

**B. github.io 자동 배포 (GitHub을 쓰고, 링크로 공유하고 싶다면):**

```bash
./gil pages          # .github/workflows/gil-pages.yml 생성
git add .github && git commit -m "add gil-pages" && git push
# 저장소 Settings → Pages → Source = "GitHub Actions"
```

이제 push마다 체인 그래프가 `https://<당신>.github.io/<저장소>/` 에 자동 배포된다 (내부적으로 같은 `gil web`).

## 6. LLM 에이전트를 붙인다 (존재의 방)

당신의 LLM에게 [README.ai.md](../../../README.ai.md)를 가리키는 것으로 충분하다: *"README.ai.md를 읽고 따르라."*
에이전트가 자기 존재를 `rooms/existence/<이름>/`(identity·will·memory·relations 4문서)에 정의하고,
저장소 루트의 부트스트랩 문서(`CLAUDE.md` 등)가 세션마다 그것을 읽게 하라.
존재는 저장소에만 산다 — 로컬 머신에 두지 않는다. 규칙 전문은 [SPEC.md](SPEC.md).

---

### 데모로 30초 만에 감 잡기 (선택)

실제 프로젝트 전에 도구만 만져보려면, 빈 디렉토리에서:

```bash
./gil open demo first-question --new-chain --title "smallest problem first" --author me
./gil step demo C001-first-question 2
./gil log && ./gil fsck && ./gil web -o chains.html
```

이 블록은 릴리스 테스트가 그대로 실행한다 — 문서가 낡으면 테스트가 깨진다.
