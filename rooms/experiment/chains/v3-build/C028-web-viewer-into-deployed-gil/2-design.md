# 2. 실험 설계

오직 1-hypothesis.md의 가설 — **Sheen C025 v3 뷰어를 `gil web --v3`로 인라인 통합, 렌더 바이트 보존·v2 무회귀** — 을 검증한다. C027 이식 패턴 재사용.

## 정답을 도구보다 먼저 고정한다

정답 = **C025 gilv3 web의 출력 HTML**(오라클). 배포판 `gil web --v3`가 바이트 동일 HTML을 내면 이식 보존. 새 렌더 로직 발명 금지.

## ⭐ 통합 전략 — 인라인 이식 (C027 재사용)

Sheen C025 백엔드(steptree 308 + notes_reconstruct 160 + web_render 308 ≈ 776줄)를 gil.py에 인라인. 의존 순: **steptree → notes_reconstruct → web_render**(web_render가 steptree.render_html 씀). 접두어(`_v3web_` 또는 모듈 구분)로 기존 cmd_web(v2)·이름 충돌 방지.

- 배포판 cmd_web에 `--v3` 플래그 추가 → 분기: v3면 notes 두 층 렌더, 아니면 기존 v2.
- steptree는 C004 것(gil.py에 없음)이라 인라인 필요. notes_reconstruct·web_render도.

## 절차

1. **백엔드 인라인.** steptree·notes_reconstruct·web_render 함수를 gil.py에 이식(동작 보존, 접두어). 자동 추출(C027 방식) + 접두어 제거.
2. **cmd_web에 --v3 분기.** 배포판 cmd_web 진입에 `if args.v3:` → v3 렌더(all_cycles_with_trees + render). argparse에 `--v3` 플래그.
3. **오라클 대조.** 격리 복제본에 migrate(notes 각인) 후:
   - clone-A: C025 gilv3 web → HTML-A.
   - clone-B: 배포판 gil web --v3 → HTML-B.
   - HTML-A == HTML-B 바이트 대조.
4. **v2 무회귀.** 기본 gil web(--v3 없이) 바이트 불변 + conformance 통과.

## 준비물

- 배포판 gil.py(통합 본체) + C025판 백엔드(오라클 겸 이식 원본).
- conformance.py(v2 회귀 검증).
- 격리 복제본(migrate로 notes 각인 후 web 대조).

## 측정 방법 (5측정)

| 측정 | 확인 | 통과 기준 |
|---|---|---|
| **M1 오라클 대조** | 배포판 gil web --v3 HTML == C025 gilv3 web HTML | 바이트 동일 |
| **M2 v2 무회귀** | 기본 gil web(--v3 없이) 바이트 불변 | 바이트 동일 |
| **M3 conformance** | 통합 후 conformance 스위트 통과 | 회귀 0 |
| **M4 자기완결** | gil.py 격리 복사해도 web --v3 동작 (외부 모듈 import 0) | import 0 |
| **M5 드릴다운 구조** | 생성 HTML에 상위 DAG + 하위 스텝 트리 두 층 존재 | 두 층 확인 |

## 안전 철칙

1. **격리 복제본만** — web은 읽기 전용 생성. migrate로 notes 각인 후 대조.
2. **v2 하위호환 최우선** — 기본 web 바이트 불변이 게이트. --v3는 옵트인.
3. **인라인이되 재구현 아님** — C025 검증 함수 이식, 렌더 재설계 금지. 오라클 대조 집행.

## 사용자 컨펌

상현님이 "가자!"로 이 순서(web 뷰어 배포판 통합)를 승인. C027과 동일한 이식 작업이라 순차·단독(C074: 워크트리는 동시성일 때만). Sheen 축이나 그의 코드를 바이트 보존 이식하므로 존중. 위임 범위 안 자율 진행.

- [x] 컨펌 받음 (일자: 2026-07-22, "가자!" — v3 읽기 축을 하나의 gil로)
