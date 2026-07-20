# 3. 가설 검증 — 우회 대신 이슈 규율

## 재현 방법

```bash
grep -q "Don't fork, patch, or wrap gil — file an issue" README.ai.md
grep -q "gh issue create" README.ai.md
grep -q "gil을 고치거나 래핑하지 말고 이슈로" rooms/deployment/ariadne-spec/QUICKSTART.md
grep -q "gh issue create" rooms/deployment/ariadne-spec/QUICKSTART.md
git diff rooms/deployment/ariadne-spec/QUICKSTART.md   # 데모 ./gil 코드 라인 변경 없음
```

## 결과

| 측정 | 기대 | 결과 |
|---|---|---|
| M1 README.ai.md 철칙 | 명령형 우회금지 + `gh issue create` 대안 | PASS |
| M2 QUICKSTART 한 줄 | 사람용 blockquote 존재 | PASS |
| M3 대안 제공 | 두 문서 모두 이슈 경로 제시(막기만 아님) | PASS |
| M4 데모 블록 불변 | QUICKSTART `./gil …` 코드 라인 diff 없음 | PASS |

## 변경 문서
- `README.ai.md` — Iron rules에 "Don't fork, patch, or wrap gil — file an issue instead." 철칙 추가. `./gil help`(능력을 묻는다)와 같은 결로 연결: 없는 건 지어내지 말고 묻고, 없으면 이슈로. 최근 기능(`--live`·배포 버저닝)이 필드 이슈에서 태어났음을 근거로 인용.
- `rooms/deployment/ariadne-spec/QUICKSTART.md` — §0 능력 탐침 대목 뒤에 사람용 blockquote: "당신의 LLM이 gil을 고치거나 래퍼를 만들려 하면 멈추게 하고 이슈로."

## 실행 기록
- 2026-07-20, darwin. M1~M4 전부 PASS. 산문 추가만이라 데모 스모크(릴리스 테스트가 실행하는 코드 블록) 불변.
