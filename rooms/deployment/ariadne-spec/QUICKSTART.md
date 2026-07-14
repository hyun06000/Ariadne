# Ariadne Quickstart — 당신의 저장소를 아리아드네로 세우기

이 문서는 **데모가 아니라 당신의 실제 프로젝트**를 아리아드네 방식으로 운영하는 길이다.
"demo"라는 이름 대신 당신의 진짜 문제 이름을 쓰면, 그대로 당신의 저장소가 된다.

## 0. gil 설치 (바이너리 — 파이썬도 Go도 불필요)

```
curl -fsSL -o gil https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64
chmod +x gil
```

Intel 맥: `gil-darwin-amd64`, 리눅스: `gil-linux-{arm64,amd64}`. 무결성은 `SHA256SUMS` 대조.
바이너리는 log·fsck·open·close·step·verify·web·**pages**를 이행한다 (`release`만 참조 구현 전용).
*(참조 구현으로 쓰려면 아래 `./gil`을 `python3 gil.py`로 바꿔 읽으면 된다.)*

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
./gil open demo first-question --new-chain --title "smallest problem first"
./gil step demo C001-first-question 2
./gil log && ./gil fsck && ./gil web -o chains.html
```

이 블록은 릴리스 테스트가 그대로 실행한다 — 문서가 낡으면 테스트가 깨진다.
