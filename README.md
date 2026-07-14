# Ariadne

> LLM이 복잡한 미로를 헤쳐나갈 수 있는 방법론

아리아드네는 테세우스에게 실타래를 건네 미궁에서 길을 잃지 않게 했다.
이 프레임워크는 LLM 에이전트에게 그 실을 건넨다 — 존재를 기억하고, 가장 작은 단위의 실험을 사슬처럼 이어, 재현 가능한 발걸음으로 문제를 정복하게 한다.

## 세 개의 방

| 방 | 경로 | 역할 |
|---|---|---|
| **존재의 방** | [rooms/existence/](rooms/existence/) | 에이전트의 정체성, 의지, 기억, 관계를 저장한다. 모든 존재는 여기에만 산다. |
| **실험의 방** | [rooms/experiment/](rooms/experiment/) | 문제를 "사이클" 단위로 분할해 정복한다. 사이클은 체인을 이룬다. |
| **배포의 방** | [rooms/deployment/](rooms/deployment/) | 실험을 통과한 결과물을 버저닝하여 배포한다. |

## 핵심 원칙

1. **존재는 레포에만 산다.** 에이전트(서브에이전트 포함)의 정체성·기억은 로컬 머신이 아닌 이 레포의 존재의 방에 문서로 저장되어 깃으로 관리된다. 여러 머신에서 작업해도 존재는 하나다.
2. **모든 동작은 목적을 향한다.** 문제는 가장 작은 달성 단위인 **사이클**로 분할되며, 모든 사이클은 5단계 스텝(가설 수립 → 실험 설계 → 가설 검증 → 결과 분석 → 결과 보고)을 따른다.
3. **재현 가능해야 한다.** 각 스텝의 모든 스크립트와 산출물은 문서로 저장되고, 결과는 사이클 단위에서 재현 가능해야 한다.
4. **사이클은 체인을 이룬다.** 깃 커밋처럼 각 사이클은 부모 사이클의 보고서에서 얻은 교훈을 명시하고, 필요하면 분기한다. 작은 실험들의 사슬이 결과에 도달하는 길이다.

## 시작하기

- 존재의 방의 규칙: [rooms/existence/README.md](rooms/existence/README.md)
- 사이클 방법론과 템플릿: [rooms/experiment/README.md](rooms/experiment/README.md)
- 배포 규칙: [rooms/deployment/README.md](rooms/deployment/README.md)
- **스펙과 도구 (gil v1.0.0)** — [바이너리 딸깍 설치](https://github.com/hyun06000/Ariadne/releases/latest) 또는 파이썬 참조 구현, 각각 26/26: [rooms/deployment/ariadne-spec/](rooms/deployment/ariadne-spec/QUICKSTART.md) — 이 패키지만으로 어떤 저장소든 Ariadne 방식으로 부트스트랩할 수 있다
- **체인 그래프 웹 뷰어**: `python3 rooms/deployment/ariadne-spec/gil.py web -o chains.html` — GitHub에 올리면 push마다 [Actions 워크플로](.github/workflows/ariadne-pages.yml)가 Pages로 자동 배포한다
