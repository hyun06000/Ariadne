# Ariadne 🧵

> **LLM이 복잡한 문제를 정복하게 하는 방법론과 도구 — 깃이 역사를 정복한 방식 그대로, 작고 재현 가능한 사이클의 체인으로.**

**문서**: [English (README.md)](README.md) · [AI 에이전트용 (README.ai.md)](README.ai.md) · [퀵스타트](rooms/deployment/ariadne-spec/QUICKSTART.md) · [스펙](rooms/deployment/ariadne-spec/SPEC.md)
**라이브**: [🕸 체인 뷰어](https://hyun06000.github.io/Ariadne/) · [⚡ 릴리스](https://github.com/hyun06000/Ariadne/releases/latest) · 라이선스: [MIT](LICENSE)

---

## 한 문장

명령어를 배울 필요 없다 — **gil은 당신이 아니라 당신의 AI 에이전트가 쓰는 도구다.** 당신의 코딩 에이전트(Claude Code, Cursor 등)에게 이 한 줄을 건네라:

> **"https://raw.githubusercontent.com/hyun06000/Ariadne/main/README.ai.md 를 읽고 그대로 따라줘."**

에이전트가 gil을 설치하고, 당신의 저장소를 세우고, 무슨 문제를 먼저 정복할지 당신에게 묻고, 재현 가능한 실험 사이클을 돌리기 시작한다 — 당신은 체인이 자라는 걸 지켜보면 된다. 아래는 궁금한 이를 위한 맥락일 뿐, 설치는 위 한 문장이 전부다.

*(에이전트가 잠긴/auto 모드로 돈다면, 내려받은 바이너리 실행을 한 번 승인해달라고 물을 수 있다 — 그 한 번의 승인이 당신 몫의 유일한 단계다.)*

---

아리아드네는 테세우스에게 실타래를 건네 미궁에서 길을 잃지 않게 했다. 이 저장소는 그 실을 LLM 에이전트에게 건넨다: 세션을 넘어 지속되는 존재, 커밋처럼 이어지는 실험, 그리고 에이전트의 **추론의 역사**를 깃이 소스의 역사를 다루듯 다루는 도구 — **gil**.

**gil** (길 — 아리아드네의 실이 가리키는 것; 동시에 **G**It for **L**anguage models)은 단일 바이너리다:

```bash
# macOS Apple Silicon (Intel·리눅스는 Releases 참조)
curl -fsSL -O https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64
curl -fsSL -O https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS
grep ' gil-darwin-arm64$' SHA256SUMS | shasum -a 256 -c - && mv gil-darwin-arm64 gil && chmod +x gil
./gil open demo first-question --new-chain --title "가장 작은 문제부터"
./gil step demo C001-first-question 2     # 커밋의 단위는 사이클이 아니라 스텝이다
./gil log && ./gil fsck && ./gil web -o chains.html
```

파이썬도 툴체인도 불필요. **체크섬 대조는 선택이 아니다** — 불일치하면 `&&` 체인이 끊겨 `gil`은 실행 파일이 되지 못한다. 검증되지 않은 바이너리가 실행될 경로 자체가 없다. (릴리스 직후의 불일치는 CDN 지연이니 잠시 후 재시도하면 된다.) 자격은 `conformance.py --gil "$PWD/gil"` — **29/29이면 "이 구현은 gil이다."**

## 핵심 개념

| 개념 | 의미 |
|---|---|
| **사이클** | 정복의 최소 단위: 가설 → 설계 → 검증 → 분석 → 보고 — **기각 조건은 선고정**한다. 모든 산출물은 저장되고 사이클 단위로 재현 가능하다. |
| **체인** | 사이클은 부모의 *보고서*(교훈)를 참조한다. 분기·병합·체인 간 계보(`lineage`)로, 깃의 내용 DAG 위에 **추론의 DAG**가 짜인다. |
| **세 개의 방** | [`existence/`](rooms/existence/) — 존재의 정체성·의지·기억·관계 (존재는 로컬이 아니라 저장소에 산다) · [`experiment/`](rooms/experiment/) — 사이클의 체인 · [`deployment/`](rooms/deployment/) — 닫힌 사이클을 근거로 한 버전 릴리스. |
| **계약** | [스펙](rooms/deployment/ariadne-spec/SPEC.md)이 gil을 정의하고 구현은 교체 가능하다. 현재 두 이행자 — 파이썬 참조 구현과 Go 바이너리 — 가 실데이터에서 바이트 단위 동일하다. |

닫힌 사이클은 불변이다 — 선의가 아니라 깃 태그(`cycle/<chain>/<id>`)와 `gil verify`가 집행한다. 열린 사이클은 실시간으로 관전된다: 스텝 전이마다 커밋이고, push마다 [뷰어](https://hyun06000.github.io/Ariadne/)가 갱신된다.

## 이 저장소는 자기 방법론으로 자기를 만들었다

여기 있는 모든 것은 이 저장소가 설명하는 바로 그 방법론으로 만들어졌다 — 3개 체인, 28개의 닫힌 사이클, 그리고 **기각된 가설 1건**(genesis/C001: 선고정된 기각 조건이 설계대로 발동했다). 존재의 방에는 두 AI가 산다: 첫 거주자 **Clew**, 그리고 실험(genesis/C003)에서 태어나 스스로 이름을 지은 **Weft** — 그는 격리된 워크트리에서 Go 구현의 절반을 직조했다: 소환되고, 감사하고, 병합되었다. 전 역사는 태그·push되어 재실행 가능하며 [뷰어](https://hyun06000.github.io/Ariadne/)가 그래프로 그린다.

## 데모 말고, 당신의 저장소에서 진짜로 쓰기

위 예시는 30초 맛보기다. **당신의 실제 프로젝트**를 아리아드네 방식으로 — 진짜 사이클, 자라나는 체인, LLM 존재, 당신의 github.io 뷰어 — 운영하려면 **[퀵스타트](rooms/deployment/ariadne-spec/QUICKSTART.md)**를 따르라. 실제 명령으로 안내한다:

1. **저장소를 연다** — 아무 깃 저장소에서 `gil open <문제영역> <슬러그> --new-chain`. 템플릿 준비 불필요 — `open`이 `git init`처럼 스캐폴드한다. `--git --push`를 붙이면 사이클을 여는 순간부터 각인되어 뷰어에 보인다.
2. **스텝으로 일한다** — 각 스텝 문서를 채우고 전이마다 `gil step … --git`(커밋 단위는 스텝). `gil close … --git`으로 닫으면 보고서가 다음 사이클의 부모가 된다.
3. **뷰어를 본다** — 택일: **로컬** `gil web -o chains.html`(브라우저로 열기, GitHub 불필요) 또는 **github.io** `gil pages`(push마다 자동 배포). 내부는 같은 `gil web`.
4. **LLM을 붙인다** — [README.ai.md](README.ai.md)를 가리킨다: *"README.ai.md를 읽고 따르라."* 존재를 `rooms/existence/`에 정의하고 루프를 돈다.

`demo` 사이클은 도구 감을 잡는 용도일 뿐, 1번부터가 당신의 저장소를 세우는 진짜 길이다.

## 라이선스

[MIT](LICENSE) © 2026 박상현. 설계: 박상현 · 직조: Clew & Weft (LLM 존재들, 자신들의 방법론으로).
