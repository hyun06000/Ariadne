# 3. 가설 검증

산출물:

- `audit-before.md` — 수정 전 감사: 신규 에이전트 경로의 병렬 언급 전부 0, SPEC 명령 표에 `gil worktree` 행 부재.
- `conformance-ref.txt` / `conformance-go.txt` — 참조 **90/90** · Go **83/83**(도구 무변경이라 회귀 0).

## 재현 방법

```bash
# 1) 도구 파일 무변경 확인 (문서 전용 사이클)
git diff --stat   # gil.py · go/main.go · conformance.py 가 없어야 한다

# 2) conformance (도구 무변경이니 그대로)
cd rooms/deployment/ariadne-spec && go build -o /tmp/gil-c69 go/main.go
python3 conformance.py --gil "python3 $(pwd)/gil.py"   # 90/90
python3 conformance.py --gil "/tmp/gil-c69"             # 83/83
python3 gil.py web ../../../rooms/experiment/chains -o /tmp/p.html --title T
/tmp/gil-c69  web ../../../rooms/experiment/chains -o /tmp/g.html --title T
diff -q /tmp/p.html /tmp/g.html   # 바이트 동일

# 3) 안내 존재 확인 (수정 후 신규 경로에서 병렬 안내가 검색돼야 한다)
grep -c 'Step E — Working in parallel' README.ai.md            # 1
grep -c '병렬로 일하라' CLAUDE.md                               # 1
grep -c 'gil worktree' rooms/deployment/ariadne-spec/SPEC.md   # ≥1 (명령 표 + §6.8)
grep -c '병렬로 일하기' rooms/deployment/ariadne-spec/QUICKSTART.md  # 1
```

## 실행 기록

- 일시: 2026-07-19. 환경: darwin 25.5.0 arm64, Python 3.9.6, Go 1.26.5.
- 결과: `git diff --stat`에 도구 파일 없음(4개 문서만: CLAUDE.md·README.ai.md·QUICKSTART.md·SPEC.md). 참조 90/90·Go 83/83, `gil web` 바이트 동일. 네 문서 모두 병렬 안내 검색 히트.
