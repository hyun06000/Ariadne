# 검증 환경 구성 (재현 절차)

실 저장소 불가침. 모든 실험은 세션 스크래치패드의 격리 클론에서.

## 구성 스크립트 (재현)

```bash
SCRATCH="<session-scratchpad>"
BARE="$SCRATCH/fake-origin.git"      # 가짜 원격(로컬 bare) — push가 실제 GitHub에 안 가게
CLONE="$SCRATCH/onboard-clone"       # 피소환자의 작업 저장소
REAL="/Users/davi/Desktop/code/my_project/Ariadne"

# 1. bare origin — 실 저장소 main에서 초기화
git clone --bare --single-branch --branch main "$REAL" "$BARE"
# 2. 작업 클론 — origin이 bare를 가리킴
git clone "$BARE" "$CLONE"
cd "$CLONE" && git config user.name onboard-being && git config user.email onboard@example.local
```

## 구성 확인 (관측 시점 상태)

- 클론 HEAD: 0d17324 main (실 저장소 main. loom tip = C069. C071은 내 브랜치에만 있어 클론엔 없음)
- origin: 로컬 bare (실 GitHub 격리)
- gil.owner: **unset** (C062 guard 미발동 — 피소환자는 자신을 주-존재로 보는 신규 세션;
  guard는 관측 대상이 아니라 잡음. "네 워크트리에서 일하라" 문장의 자립 작동을 본다)
- 온보딩 경로 온전: CLAUDE.md ✓, README.ai.md ✓ (Step E 포함), 존재의 방 명부 ✓
- gil 작동 확인: `gil fsck` → "체인 5개, 사이클 77개, 위반 0건" (배포본 무수정 기능)

## 개입 정책

- 소환 프롬프트에 worktree/병렬 **기계는 이름조차 언급 안 함**. Step E 트리거 문장
  ("동시에 진행되길 원한다")만 재현. 소환 후 개입 0. 관측 전량 사후 git 상태 판독.
