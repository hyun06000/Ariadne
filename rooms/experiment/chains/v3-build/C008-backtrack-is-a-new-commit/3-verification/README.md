# 3. 가설 검증 — 백트래킹=새 커밋

가설: 백트래킹 스텝을 `--git`으로 각인하면 깃엔 reset/checkout/revert 없이 **새 전진 커밋만** 쌓이고, 죽은 가지는 히스토리에 보존되며(벽의 지도), 되돌아감 논리는 steps.yaml 포인터에만 담긴다.

## 산출물

- `gilv3.py` — gilv3 v0.4 (C006 v0.3 복사 확장). append-only 계약 명문화 + `_assert_forward_only` 전진 단조성 자기 집행 가드 + 백트래킹 커밋 메시지 서술.
- `build.sh` — C012→C013→C014 10노드 스텝 트리를 `gilv3 --git`으로 임시 깃 저장소(메인 레포 밖 스크래치패드)에 각인.
- `measure.py` — 5측정 자동 판정 (M1~M5).
- `built-steps.yaml` — 각인된 steps.yaml 스냅샷 (재현 대조용).
- `git-log.txt` — 각인 결과 `git log --oneline --graph` (선형·11커밋).
- `measure-out.txt` — 측정 실행 출력 (ALL PASS 5/5).

## 재현 방법

```bash
HERE=rooms/experiment/chains/v3-build/C008-backtrack-is-a-new-commit/3-verification
# 1) 실사례 트리를 --git으로 각인 (임시 깃 저장소는 메인 레포 밖)
bash "$HERE/build.sh"
# 출력 끝의 SCRATCH= 경로를 잡아
SCRATCH=/private/tmp/.../scratchpad/c008-imprint   # build.sh 출력 참조
# 2) 5측정 판정
python3 "$HERE/measure.py" "$SCRATCH" "$SCRATCH/case"
```

## 측정 결과 (ALL PASS 5/5)

| # | 측정 | 기각 조건 | 결과 |
|---|---|---|---|
| M1 | 각인 경로 git 하위명령 정적 감사 (주석 제외) | K1 | ✅ add·commit·merge-base·rev-parse만 — 금지(reset/checkout/revert/amend/force/rebase) 0 |
| M2 | reflog 전진 단조성 + 커밋수·순서 | K2·K4 | ✅ 11커밋, s번호 시간순 단조, 부모체인 선형, 되돌림 흔적 0 |
| M3 | 죽은 가지 커밋·body 보존 | K2 | ✅ 죽은 잎 s4·s7 커밋·죽은 가지 스텝·body 전부 생존 |
| M4 | 되돌아감 논리 위치 (steps.yaml vs 깃) | K3 | ✅ 깃 선형(머지0)인데 steps.yaml은 트리(s1의 세 형제 + backtrack 2) |
| M5 | 가드 유효성 음성 대조 | — | ✅ HEAD를 인위로 뒤로 옮기면 가드가 실제로 거부 (무의미한 통과 아님) |

네 기각 조건 K1~K4 전부 미발동, 산 잎(s10) 도달 → **supported**.

## 결정적 증거 — git-log.txt

```
* … gilv3 close case: solved 산 잎 s10 (봉인)
* … gilv3 step: s10 analyze/success
* … gilv3 step: s9 verify
* … gilv3 step: s8 hypothesis (new branch from s1 after backtrack)   ← 백트래킹 후 새 가지
* … gilv3 step: s7 analyze/backtrack (backtrack to s1)               ← 두 번째 백트래킹
* … gilv3 step: s6 verify
* … gilv3 step: s5 hypothesis (new branch from s1 after backtrack)   ← 백트래킹 후 새 가지
* … gilv3 step: s4 analyze/backtrack (backtrack to s1)               ← 첫 번째 백트래킹
* … gilv3 step: s3 verify
* … gilv3 step: s2 hypothesis
* … gilv3 open case: s1 define
```

**한 줄 선형** — 백트래킹 두 번(s4→s1, s7→s1)에도 깃 그래프에 분기·머지 커밋이 0개다. 되돌아감은 커밋 메시지 서술과 steps.yaml의 `backtrack`/`parent` 포인터에만 담긴다. 깃은 그 결과를 전진 커밋으로 받아 적을 뿐 — **백트래킹=새 커밋**.

## 실행 기록

- 실행: 2026-07-21, macOS (Darwin 25.5.0), Python 3 (/usr/bin/python3), 순수 stdlib.
- 임시 깃 저장소: 스크래치패드 `c008-imprint/` (메인 레포 밖, 중첩 .git 방지 — C005 규율).
- 계측기 결함 2건을 검증 중 잡아 고침(가설 반증 아님): ① M1 정규식이 `git_imprint` 독스트링의 계약 서술 텍스트("push --force …")를 오탐 → 주석·독스트링 제거 후 감사. ② M2/M4의 `%P` splitlines가 첫 커밋 빈 부모줄을 삼켜 IndexError → `%H|%P` 한 줄 파싱. ③ M2 s-id 추출이 close 줄의 "산 잎 s10"까지 뽑아 단조 오판 → `gilv3 step: sN`만 매칭.
