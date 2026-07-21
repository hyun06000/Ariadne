# 3. 가설 검증 — 깃 로그로 트리 재구성

가설: `git log`(커밋 시간순 + 메시지 서술)만으로 steps.yaml 없이 스텝 트리를 복원하면 원본과 위상 동형이 된다 = 깃이 단일 진실원 가능.

## 산출물

- `rebuild.py` — 깃 로그만 읽는 복원기 (`git log --reverse --format=%s`만, steps.yaml·show·diff 접근 0). C003 상태기계의 거울.
- `measure.py` — 4측정 자동 판정 (M1~M4).
- `rebuilt-steps.yaml` — 깃 로그에서 복원한 steps.yaml (C008 built-steps.yaml과 바이트 동일).
- `measure-out.txt` — 측정 출력 (ALL PASS 4/4).

## 재현 방법

```bash
C008=rooms/experiment/chains/v3-build/C008-backtrack-is-a-new-commit/3-verification
C009=rooms/experiment/chains/v3-build/C009-reconstruct-tree-from-git-log/3-verification
# 1) C008 build.sh로 입력 트리를 임시 깃 저장소에 각인 (메인 레포 밖)
SCRATCH=/private/tmp/.../scratchpad/c009-rebuild
bash "$C008/build.sh" "$SCRATCH"
# 2) 깃 로그만으로 복원
python3 "$C009/rebuild.py" "$SCRATCH/case"          # 사람 가독
python3 "$C009/rebuild.py" "$SCRATCH/case" --yaml   # steps.yaml 형식
# 3) 4측정 (원본 = C008 built-steps.yaml)
python3 "$C009/measure.py" "$SCRATCH/case" "$C008/built-steps.yaml"
```

## 측정 결과 (ALL PASS 4/4)

| # | 측정 | 기각 조건 | 결과 |
|---|---|---|---|
| M1 | 노드·parent 엣지 동형 | K1 | ✅ 복원 10노드 == 원본, parent 엣지 전부 동일 |
| M2 | backtrack·outcome 동형 | K2 | ✅ backtrack {s4→s1, s7→s1}·outcome {s10 success, s4·s7 backtrack} 동일 |
| M3 | 깃 로그 단독 (정적 감사) | K3 | ✅ git 하위명령 = `log`뿐, steps.yaml·show·diff 접근 0 |
| M4 | 유일 결정성 + 왕복 무손실 | K4 | ✅ 파싱 배타적, 복원→steps.yaml == 원본 바이트 동일 |

네 기각 조건 K1~K4 전부 미발동 → **supported**.

## 결정적 증거

깃 로그만으로 복원한 트리(사람 가독 출력):
```
s1 define parent=None
s2 hypothesis parent=s1
s3 verify parent=s2
s4 analyze parent=s3 outcome=backtrack backtrack=s1     ← 죽은 잎 (목적지 서술로)
s5 hypothesis parent=s1                                  ← 백트래킹 후 새 가지 (from s1)
s6 verify parent=s5
s7 analyze parent=s6 outcome=backtrack backtrack=s1     ← 죽은 잎
s8 hypothesis parent=s1                                  ← 새 가지
s9 verify parent=s8
s10 analyze parent=s9 outcome=success                   ← 산 잎
```

`rebuilt-steps.yaml`이 C008 `built-steps.yaml`과 **diff 0 (바이트 동일)**. steps.yaml 파일을 한 번도 안 읽고, 오직 커밋 순서 + 커밋 메시지 서술 + C003 순환 규칙만으로 트리를 무손실 복원했다.

## 실행 기록

- 실행: 2026-07-21, macOS (Darwin 25.5.0), Python 3 (/usr/bin/python3), 순수 stdlib.
- 입력: C008 build.sh로 재생성한 임시 깃 저장소 (메인 레포 밖 스크래치패드, C005 규율).
- 계측기 결함 0 — 이번 검증은 한 번에 통과.
