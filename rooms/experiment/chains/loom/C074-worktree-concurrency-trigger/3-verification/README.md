# 3. 가설 검증

문서-only 정련(C069 패턴). 변경은 SPEC §6.8·CLAUDE §3·README.ai Step E 세 곳.

## 재현 방법

```bash
G=rooms/deployment/ariadne-spec/gil.py
C=rooms/deployment/ariadne-spec/conformance.py
# 계약 불변 — 도구 코드 무변경이라 conformance 98/98, fsck 0
python3 $C --gil "python3 $(pwd)/$G" | tail -1
python3 $G fsck | tail -1
# 트리거 문구 존재 확인
grep -c "동시성당\|사이클당이 아니라" rooms/deployment/ariadne-spec/SPEC.md   # >=1
grep -c "동시성.*일 때만\|C074" CLAUDE.md                                      # >=1
grep -c "concurrency, not" README.ai.md                                        # >=1
```

## 측정 결과

| 측정 | 기준 | 결과 |
|---|---|---|
| 참조 conformance | 98/98 불변 | 98/98 ✔ |
| fsck | 위반 0 | 위반 0(경고 37 기존) ✔ |
| SPEC §6.8 트리거 문구 | 존재 | ✔ ("사이클당이 아니라 동시성당") |
| CLAUDE §3 트리거 문구 | 존재 | ✔ |
| README.ai Step E 트리거 문구 | 존재 | ✔ ("The trigger is concurrency, not per cycle") |
| 자기모순 | 없음 | ✔ (트리거≠규율, 층위 분리) |

## 실행 기록

- 일시: 2026-07-19. darwin, Python 3. gil 2.26.0. 도구 코드 무변경 → 계약면 불변.
- 특이사항: 이 사이클 자체가 순차·단독이라 **워크트리 없이 main에서** 열었다 — 정련하는 규약("순차면 워크트리 건너뛰기")의 실천 사례. gil.owner=clew guard가 소유자(Clew)의 main open을 허용.
