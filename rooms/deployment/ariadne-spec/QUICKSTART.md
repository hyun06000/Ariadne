# Ariadne Quickstart

## 0. 딸깍 설치 (바이너리 — 파이썬도 Go도 불필요)

```
curl -fsSL -o gil https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64
chmod +x gil
```

(Intel 맥: `gil-darwin-amd64`, 리눅스: `gil-linux-{arm64,amd64}`. 무결성은 `SHA256SUMS` 대조.
바이너리는 log·fsck·open·close·step·verify·web 전부를 이행한다 — release와 open --git만 참조 구현 전용.)

이후 아래의 `python3 gil.py`를 `./gil`로 바꿔 읽으면 된다. 또는 —

이 패키지(`ariadne-spec/`)만 있으면 된다. 아래 코드 블록을 순서대로 실행하면
새 프로젝트가 부트스트랩되고 첫 사이클이 태어나고 닫힌다.
(이 문서의 bash 블록은 릴리스 테스트가 그대로 실행한다 — 문서가 낡으면 테스트가 깨진다.)

## 1. 부트스트랩

패키지가 `./ariadne-spec/`에 있다고 하자. 새 프로젝트를 만든다:

```bash
mkdir -p myproject/rooms/experiment/chains
cp -R ariadne-spec/template myproject/rooms/experiment/_template
cp ariadne-spec/gil.py myproject/gil.py
cd myproject
```

## 2. 첫 사이클 열기

```bash
python3 gil.py open demo first-question --new-chain \
  --title "정복하려는 가장 작은 문제 한 줄" --author me --date 2026-01-01
python3 gil.py log
```

`rooms/experiment/chains/demo/C001-first-question/`에 5스텝 문서가 생겼다.
1(가설)→2(설계)→3(검증)→4(분석) 순서로 채운 뒤 보고서를 쓴다.

**사용 원칙 (스펙 §2.1)**: 커밋의 단위는 스텝이다 — 스텝을 마칠 때마다
`python3 gil.py step demo C001-first-question <n> --git` 으로 각인하라 (깃 저장소라면).
긴 스텝은 중간에도 커밋한다. 침묵은 관전자에게 멈춤과 구별되지 않는다.

## 3. 보고서를 쓰고 닫기

(여기서는 데모로 최소 보고서만 쓴다 — 실전에서는 4단계까지의 분석이 근거가 되어야 한다.)

```bash
printf '# 5. 결과 보고\n\n## 요약\n\n첫 사이클 완료. 가설 채택.\n\n## 교훈\n\n1. 시작이 반이다.\n' \
  > rooms/experiment/chains/demo/C001-first-question/5-report.md
python3 gil.py close demo C001-first-question --date 2026-01-02
```

## 4. 검사와 뷰어

```bash
python3 gil.py fsck
python3 gil.py log
python3 gil.py web -o chains.html
```

`chains.html`을 브라우저로 열면 체인 그래프가 보인다. 서버·네트워크 불필요.

## 5. 깃 각인 (선택)

저장소가 깃이라면 `python3 gil.py close <chain> <id> --git`으로 닫아라 —
사이클만 담은 커밋과 태그 `cycle/<chain>/<id>`가 남고, 이후 `python3 gil.py verify`가
닫힌 사이클의 변조를 탐지한다. 규칙의 전문은 [SPEC.md](SPEC.md).

## 6. 존재의 방 (LLM 에이전트라면)

`rooms/existence/<이름>/`에 identity·will·memory·relations 4문서로 존재를 정의하고,
저장소 루트의 부트스트랩 문서(`CLAUDE.md` 등)가 세션 시작 시 그것을 읽게 하라.
존재는 저장소에만 산다 — 로컬 머신에 두지 않는다.
