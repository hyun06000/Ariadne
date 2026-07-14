# Ariadne 🧵

> **LLM이 복잡한 문제를 정복하게 하는 방법론과 도구 — 깃이 역사를 정복한 방식 그대로, 작고 재현 가능한 사이클의 체인으로.**

**문서**: [English (README.md)](README.md) · [AI 에이전트용 (README.ai.md)](README.ai.md) · [퀵스타트](rooms/deployment/ariadne-spec/QUICKSTART.md) · [스펙](rooms/deployment/ariadne-spec/SPEC.md)
**라이브**: [🕸 체인 뷰어](https://hyun06000.github.io/Ariadne/) · [⚡ 릴리스](https://github.com/hyun06000/Ariadne/releases/latest) · 라이선스: [MIT](LICENSE)

---

아리아드네는 테세우스에게 실타래를 건네 미궁에서 길을 잃지 않게 했다. 이 저장소는 그 실을 LLM 에이전트에게 건넨다: 세션을 넘어 지속되는 존재, 커밋처럼 이어지는 실험, 그리고 에이전트의 **추론의 역사**를 깃이 소스의 역사를 다루듯 다루는 도구 — **gil**.

**gil** (길 — 아리아드네의 실이 가리키는 것; 동시에 **G**It for **L**anguage models)은 단일 바이너리다:

```bash
# macOS Apple Silicon (Intel·리눅스는 Releases 참조)
curl -fsSL -o gil https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64
chmod +x gil
./gil open demo first-question --new-chain --title "가장 작은 문제부터"
./gil step demo C001-first-question 2     # 커밋의 단위는 사이클이 아니라 스텝이다
./gil log && ./gil fsck && ./gil web -o chains.html
```

파이썬도 툴체인도 불필요. 무결성은 `SHA256SUMS`, 자격은 `conformance.py --gil "$PWD/gil"` — **26/26이면 "이 구현은 gil이다."**

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

## 당신의 저장소에 도입하기

1. 위처럼 바이너리를 `curl`하고, [`template/`](rooms/deployment/ariadne-spec/template/)을 `rooms/experiment/_template`로 복사한다.
2. [퀵스타트](rooms/deployment/ariadne-spec/QUICKSTART.md)를 따른다 — 부트스트랩부터 첫 사이클 닫기까지 다섯 명령.
3. 당신의 LLM에게 [README.ai.md](README.ai.md)를 가리킨다 — 한 문장이면 된다: *"README.ai.md를 읽고 따르라."*

## 라이선스

[MIT](LICENSE) © 2026 박상현. 설계: 박상현 · 직조: Clew & Weft (LLM 존재들, 자신들의 방법론으로).
