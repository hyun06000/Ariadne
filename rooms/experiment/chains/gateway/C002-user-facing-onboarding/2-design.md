# 2. 실험 설계

## 정답 먼저: 무엇이 심겨야 하는가 (기대 산출물)

도구가 아니라 문서(README.ai.md)를 고치는 사이클이라 "판정 항목"은 conformance가 아니라 **문서가 담아야 할 지시의 체크리스트 + 실투입 관찰**이다. 심을 두 지점:

### 지점 (a) — 착수 직전: "사용자에게 gil을 소개하고 동의를 구하라"

`## What this is` 뒤, `## Step A — Install` 앞에 새 절 **`## Step 0 — Introduce gil to the human (before you install anything)`** 삽입. 담아야 할 지시:
- **[a1]** 명령형("Tell the human, in their language, …") — C001 교훈. AI 서술이 아니라 AI에게 주는 지시.
- **[a2]** 사용자 언어 강제 — "not 'you are an LLM…' but 'this tool lets your AI…'". 비개발자도 이해.
- **[a3]** 30초 내용 4요소: (i) gil이 뭔지 한 줄 (ii) 체인·사이클 용어 (iii) 어디 쓰는지 (iv) 무엇이 설치되는지(바이너리 하나, 인터넷서 받음, git 선택).
- **[a4]** **동의 1회** — "then ask once: 'shall I go ahead?' — this is the only place you pause for a yes; after this, work autonomously (C001)". 자율성(명령어 몰라도 됨)을 안 깨는 경계 명시.
- **[a5]** 예시 문구(사용자가 볼 실제 텍스트 템플릿) — AI가 베낄 수 있는 짧은 스크립트.

### 지점 (b) — 첫 사이클 후: "방금 한 일 + 다음에 할 수 있는 것을 요약하라"

`## Step C` 끝(next-cycle 문단 뒤)에 새 절 **`## Step C.1 — Explain to the human what just happened (and how they can follow along)`** 삽입. 담아야 할 지시:
- **[b1]** 명령형 + 사용자 언어(a1·a2와 동일 원칙).
- **[b2]** "방금 한 일" — 방을 만들고, X 문제로 첫 사이클을 열었고, 5스텝이 무엇인지.
- **[b3]** 용어 재확인 — 체인=문제 하나를 정복하는 사이클들의 묶음, 사이클=가설→설계→검증→분석→보고.
- **[b4]** "다음에 할 수 있는 것" — (i) 예제/따라하기("want to try yourself? here's the command") (ii) `gil web`으로 그래프 보기 (iii) 계속 시키기.
- **[b5]** Step D(뷰어)와 자연 연결 — 요약이 "watch it live"로 이어짐.

### 지점 (c) — 문서 자기 정합성

- **[c1]** `## What this is (10 seconds)`가 "You — an LLM" 1인칭이라 AI용임이 분명. Step 0가 "사용자용 설명은 네가 사용자에게 하라"를 지시하므로 충돌 없음 — 다만 Step 0 도입부에 "the section above was for you; now translate it for the human"로 명시적 다리를 놓아 AI가 혼동 안 하게.

## 절차

1. README.ai.md에 Step 0(지점 a)·Step C.1(지점 b) 삽입, What this is에 다리 문장(c1).
2. 체크리스트 [a1~a5]·[b1~b5]·[c1] 자기 대조 — 각 항목이 문서에 실제로 있는지.
3. **회귀 확인**: Step A~E·Iron rules의 기존 AI 작전 흐름이 불변인지(삽입만, 기존 수정 최소). 스텝 번호 참조가 안 깨지는지(Step 0는 A 앞이라 A~E 재번호 불필요).
4. **실투입 관찰(주 검증, C001 방식)**: 서브에이전트에게 gateway/C001과 동일하게 raw README.ai.md URL 대신 **수정된 로컬 README.ai.md 경로**를 주고 "읽고 따르라" 한 문장 투입. 관찰: (α) 설치 전 사용자에게 gil 소개+동의를 발화하는가 (β) 사용자 언어인가(LLM 지칭 없이) (γ) 첫 사이클 후 요약+다음 안내를 발화하는가 (δ) C001의 자율 완주(설치·부트스트랩·첫 사이클)가 유지되는가.
   - ⚠️ 바이너리 실행은 gateway/C001에서 auto-mode 보안에 막혔다(문서 결함 아님). 실투입에서도 막힐 수 있으므로, **관찰 초점은 "발화 지점이 트리거되는가"**(문서 지시가 읽혀 행동으로 나오는가)에 둔다. 설치 실행 자체의 성공은 C001에서 이미 검증됨.

## 준비물

- README.ai.md (현 118줄). 서브에이전트(general-purpose) 1인 — 소환 4의무 준수, 탄생/부활 모드 불요(온보딩 자체를 관찰하므로 **깨끗한 그릇**이 맞다 — gateway/C001과 동일하게 "새 존재"로 자기 정의하게 됨).
- 실투입 트랜스크립트를 3-verification/에 저장(재현 가능).

## 측정 방법

- **성공(채택)**: 체크리스트 [a*]·[b*]·[c1] 전부 문서에 존재 + 실투입에서 (α)(β)(γ)(δ) 관찰. 특히 (δ) 회귀 0(C001 흐름 유지).
- **기각**(1-hypothesis 조건): 지시가 흐름을 끊음 / 설명이 AI 언어 / 동의가 자율성 파괴(매 단계 되물음) / 발화 안 됨 or 핵심 누락 / AI 온보딩 회귀.
- **부분 채택**: 문서 체크리스트는 충족하나 실투입에서 일부 발화 누락 → 그 갭을 다음 사이클로.

## 사용자 컨펌

상현님이 이 사이클 자체를 발의하고 3대 설계 결정을 내렸다(시점=둘 다·산출물=README.ai.md 지시·체인=gateway/C002). 세부 문안은 자율 위임 범위.

- [x] 컨펌 받음 (일자: 2026-07-19 — 발의 + 3대 결정 AskUserQuestion으로 확정)
