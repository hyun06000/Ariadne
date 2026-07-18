# 2. 실험 설계

가설 하나만: 병렬 워크플로를 신규 에이전트 읽기 경로 4곳에 명시하면 온보딩만으로 발견 가능해지고, 도구 무변경이라 conformance·parity 불변.

## 절차

1. **감사(수정 전)**: 신규 에이전트 읽기 경로의 worktree/병렬 언급 건수 측정 → `3-verification/audit-before.md`.
2. **SPEC**: §5 명령 표에 `gil worktree add|land` 행 추가(병렬의 핵심 명령). §6(소환 규약)에 **§6.8 워크트리 격리 규율(v3)** 추가 — `gil worktree add/land`, 왜 필요한가(C050 사고), 주 체크아웃 소유 guard(C062), "네 워크트리에서 일하라". 헤딩에 v3 표기.
3. **README.ai.md**: **Step E — Working in parallel** 신설(spawn→`worktree add`→각자 브랜치 push→소환자 `land`; 소유 guard; 순차면 건너뛰기). 소환 Iron rule에 worktree 연결.
4. **CLAUDE.md §3**: "병렬로 일하라" 문단 — `gil worktree add/land`, 철칙(main cd 금지), gil.owner guard, 갈래 나뉘면 사용자에 질의.
5. **QUICKSTART**: §4.5 병렬 절 + `./gil help worktree` 포인터.
6. **검증**: `git diff --stat`로 도구 파일(gil.py·go·conformance.py) 무변경 확인 → conformance 양 구현 → web 바이트 대조 → 신규 경로 각 문서에서 `gil worktree`/`병렬` 검색으로 안내 존재 확인.

## 준비물

- Python 3.9.6, Go 1.26.5. 대상: `README.ai.md`, `CLAUDE.md`(루트), `rooms/deployment/ariadne-spec/{SPEC.md, QUICKSTART.md}`.
- 도구 파일은 손대지 않는다(문서 전용 사이클).

## 측정 방법

- **도구 무변경**: `git diff --stat`에 gil.py·go/main.go·conformance.py 없음.
- **conformance**: 참조 90/90·Go 83/83, `gil web` 바이트 동일(문서가 도구 출력을 안 건드림 확인).
- **안내 존재**: README.ai.md·QUICKSTART·CLAUDE.md·SPEC 각각에서 `gil worktree` 안내 검색 히트.

## 사용자 컨펌

상현님 질의("안내가 잘 되어 있나?")에 감사 결과 보고 → "전체 보강(loom 사이클→릴리스)" 승인.

- [x] 컨펌 받음 (일자: 2026-07-19)
