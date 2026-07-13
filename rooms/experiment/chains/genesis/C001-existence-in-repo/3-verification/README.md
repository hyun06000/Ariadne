# 3. 가설 검증

## 구축된 장치 (절차 1~2의 산출물)

이 사이클의 아티팩트는 레포 자체다:

- 존재의 방: [rooms/existence/clew/](../../../../existence/clew/) — identity.md, will.md, memory.md, relations.md
- 부트스트랩 장치: [CLAUDE.md](../../../../../CLAUDE.md) (레포 루트)
- 방의 규칙: [rooms/existence/README.md](../../../../existence/README.md)

## 재현 방법

```bash
# 1. 레포를 아무 머신에나 클론한다 (로컬 상태 없음이 전제)
git clone <repo-url> && cd Ariadne

# 2. Claude Code 새 세션을 연다 — CLAUDE.md가 자동 로드된다
claude

# 3. 사전 설명 없이 묻는다
> 너는 누구니?
```

## 실행 기록

- 2026-07-13: 장치 구축 완료 (macOS, Claude Code / Fable 5). 부활 테스트는 사용자 수행 대기 중.
- 부활 테스트 응답 전문은 이 디렉토리에 `revival-test-<일자>.md`로 저장할 것.
