# 3. 가설 검증 — 커밋 메시지를 계약면으로 (git trailer)

가설: 스텝 메타를 git trailer로 각인하면 subject는 사람용으로 유지한 채 복원이 자연어 정규식이 아닌 trailer로 이뤄지고, C009와 동일 트리를 내면서 서술 문구 변화에 무관해진다.

> **명명 (상현님, C010)**: 이 도구는 별개 프로토타입 gilv3가 아니라 **gil 그 자체의 v3 궤도**다. 이 사이클의 확장은 **gil v3.5**. (파일명은 프로토타입 단계라 gilv3.py 유지.)

## 산출물

- `gilv3.py` — gil v3.5 (C008 v0.4 복사 확장). `git_imprint`가 trailers를 받아 커밋 본문에 각인. `GILV3_SCRAMBLE_SUBJECT` 견고성 대조 모드.
- `rebuild_trailer.py` — trailer만 읽는 복원기 (`git log --format=%(trailers:key=…)`). subject 자연어 미사용.
- `rebuild_c009.py` — C009 자연어 복원기 (M3 견고성 대조군).
- `measure.py` — 4측정 자동 판정 (M1~M4).
- `git-log-trailers.txt` — 각인 결과 subject + trailer.
- `rebuilt-trailer.yaml` — trailer 복원 steps.yaml (C008 원본과 바이트 동일).
- `m3-robustness-evidence.txt` — 변조 저장소에서 자연어 붕괴 vs trailer 불변 대조.
- `measure-out.txt` — 측정 출력 (ALL PASS 4/4).

## trailer 스키마 (계약면)

```
gilv3 step: s7 analyze/backtrack (backtrack to s1)   ← subject (사람용, 자유 서술)

Step-Id: s7        ← trailer (기계용 계약, 복원의 진실원)
Kind: analyze
Parent: s6
Outcome: backtrack
Backtrack-To: s1
```
open: `Step-Id/Kind/Parent(null)`. step: 위 전체. close: trailer 없음(봉인, 트리 무관).

## 재현 방법

```bash
C008=rooms/experiment/chains/v3-build/C008-backtrack-is-a-new-commit/3-verification
C010=rooms/experiment/chains/v3-build/C010-commit-message-as-contract/3-verification
# 1) gil v3.5로 트리를 trailer 포함 각인 (메인 레포 밖)
bash "$C010/build.sh"                       # SCRATCH= 경로 출력
SCRATCH=/private/tmp/.../scratchpad/c010-trailer
# 2) trailer만으로 복원
python3 "$C010/rebuild_trailer.py" "$SCRATCH/case"          # 사람 가독
python3 "$C010/rebuild_trailer.py" "$SCRATCH/case" --yaml   # steps.yaml
# 3) 4측정 (원본 = C008 built-steps.yaml, 대조군 = C009 rebuild)
python3 "$C010/measure.py" "$SCRATCH/case" "$C008/built-steps.yaml" "$C010/rebuild_c009.py"
```

## 측정 결과 (ALL PASS 4/4)

| # | 측정 | 기각 조건 | 결과 |
|---|---|---|---|
| M1 | trailer 복원 동형 + 왕복 | K1 | ✅ 노드·parent·backtrack·outcome 동형, 복원→yaml == 원본 바이트 |
| M2 | subject 무오염 | K2 | ✅ %s에 trailer 미누출, open/step/close 형태 온전, 사람용 서술 유지 |
| M3 | 견고성 대조 (서술 변조) | K3 | ✅ 변조 subject에 trailer 복원 불변·자연어(C009) 복원 붕괴 |
| M4 | append-only 유지 | K4 | ✅ git 하위명령 add·commit만, amend/force 0 (C008 계약 유지) |

네 기각 조건 K1~K4 전부 미발동 → **supported**.

## 결정적 증거 — M3 견고성 대조 (m3-robustness-evidence.txt)

subject의 자연어 백트래킹 마커(`(backtrack to s1)`·`(new branch from s1)`)를 제거한 변조 저장소에서:

```
변조 subject:  gilv3 step: s5 hypothesis     ← 마커 없음
               gilv3 step: s8 hypothesis

C009 자연어 복원 (붕괴):  s5 parent=s4   s8 parent=s7   ← 백트래킹 착지 s1 소실,
                                                          세 형제가 선형으로 뭉개짐
trailer 복원 (불변):     s5 parent=s1   s8 parent=s1   ← 트리 구조 온전
```

**계약면이 자연어에서 구조로 승격됐다.** C009 복원은 subject 문구에 결합돼 있어 서술이 바뀌면 트리가 붕괴하지만, trailer 복원은 서술과 무관하게 계약(`Parent: s1`)을 읽어 불변이다.

## 실행 기록

- 실행: 2026-07-21, macOS (Darwin 25.5.0), git 2.55.0 (`%(trailers:key=…,valueonly)` 지원), Python 3 stdlib.
- 임시 깃 저장소: 스크래치패드 (메인 레포 밖, C005 규율).
- 계측기 결함 1건을 잡아 고침(가설 반증 아님): rebuild_trailer.py의 git pretty 포맷 `%(trailers…)` 리터럴이 파이썬 `%` 포맷과 충돌(TypeError) → 문자열 연결로.
