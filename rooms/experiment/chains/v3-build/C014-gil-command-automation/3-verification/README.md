# 3. 검증 — 백트래킹=checkout이 gilv3 명령 동작이 되다

C011이 순수 깃 셸 스크립트(build_branches.sh)로 손으로 짠 3층 분기 트리를, 이번엔 **gilv3.py 명령(open/step/close)만으로** 재현한다. 생 `git checkout` 호출 0 — 도구가 안에서 백트래킹 checkout을 한다. 그리고 C008의 forward-only 집행을 C011 모델(커밋 불소멸)로 정정한다.

## 재현

```bash
bash build_case.sh <scratch>     # gilv3 명령만으로 3층 분기 재현 (메인 레포 밖)
python3 measure.py <scratch>     # 5측정 감사
```

두 스크립트에 같은 scratch 경로를 준다. gilv3.py C014판은 C010판을 복사 후 진화(v3-build 규율, C010 원본 불변).

## 산출물

- `gilv3.py` — C014판(474줄). C010판 대비 4곳 정정: `_assert_append_only`(커밋 불소멸 집행) · `_commit_of_sid`(sid→커밋 역인덱스) · `cmd_step`의 checkout 백트래킹 + 죽은 잎 못(`gil/dead/`) · `cmd_close`의 산 잎 못(`gil/live/`) + 사이클 종결 못(`gil/sealed/`).
- `build_case.sh` — gilv3 명령만으로 C011 실사례 재현.
- `measure.py` — 5측정 감사기.
- `measure-out.txt` — 측정 출력(ALL PASS 5/5).
- `git-graph.txt` — 도구가 만든 `git log --all --graph`(세 형제 가지가 s1에서 갈라지는 실물).

## ⭐ 핵심 개념 정정 — C008 → C011 (append-only의 진짜 계약)

C010판 `_assert_forward_only`는 HEAD 전진 단조성을 집행하며 checkout을 명시 금지했다. 그것은 두 가지를 뭉뚱그린 오류였다:

- **(A) 커밋을 지우지 않음** — reset --hard/amend/rebase/push --force가 하는 히스토리 재작성. **이것이 append-only의 진짜 가치**(닫힌 커밋 불변, '벽의 지도' 보존).
- **(B) HEAD를 뒤로 안 옮김** — checkout이 하는 것. 그러나 커밋은 하나도 안 지운다.

C008은 (A)를 지키려 (B)까지 금지해 백트래킹=checkout(C011)을 불가능하게 했다. **C014의 정정**: append-only의 진짜 계약은 HEAD 전진이 아니라 **커밋 도달가능성 단조**(집합이 오직 늘어남)다. `_assert_append_only`가 "이전 커밋이 다 살아있는가"를 본다 — checkout은 통과(M4a), reset --hard는 거부(M4b).

## 5측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 깃 그래프 분기** | 도구가 만든 저장소에서 루트 s1 커밋이 자식 3개(세 형제 가지). 선형 아닌 실제 분기 = C011 build_branches.sh 위상 | PASS |
| **M2 steps.yaml↔깃 동형** | 각 스텝 커밋의 깃 부모 Step-Id == steps.yaml parent(백트래킹은 checkout으로 깃 부모=조상 define). 불일치 0 | PASS |
| **M3 trailer 복원 무손상** | C010 rebuild 로직을 `--all`로 재호출해 분기 저장소 복원 → steps.yaml과 동형. checkout이 자기완결 trailer 복원을 안 깸 | PASS |
| **M4 append-only** | ① 죽은 가지 못(`gil/dead/`)으로 생존 ② checkout(HEAD 뒤로)이 `_assert_append_only` 통과 ③ **reset --hard 음성대조로 거부**. 커밋 불소멸 계약 | PASS |
| **M5 회귀 0** | 선형 사이클(백트래킹 없이 open→step→close)이 C010과 동일 — 분기 0·trailer 각인·cycle.yaml 봉인 불변 | PASS |

## 계측기/설계 결함 수리 (4건, 모두 반증 아님)

1. **산 가지 dangling** — 죽은 잎만 못박고 산 잎을 안 박아, checkout 후 산 가지가 ref 없이 소멸. → close가 산 잎을 `gil/live/<sid>`로 못박음.
2. **close 커밋 소멸** — close 커밋은 산 잎 위 detached HEAD라 산 잎 못이 close 커밋을 안 가림. → 사이클 종결 못 `gil/sealed/<cycle>`을 close 커밋에 박음. (C011 `cycle/<name>/solved`의 최소 형태.)
3. **C010 rebuild가 분기 못 읽음** — `git log --reverse`가 `--all` 없어 HEAD 한 가지만 봄(C010 선형 전제). → 측정에서 C010 파서를 `--all`로 재호출(C010 원본 불변, C011·C012 예고한 '재구성기 --all 재배선' 이월의 국소 적용).
4. **M4 파괴 실험이 저장소 오염** — reset/브랜치 잔여가 후속 측정 오염. → 깨끗한 복제본(cp -r)에서 파괴 실험.

## 결론

**ALL PASS → supported.** 백트래킹=`git checkout`이 원리(C011)가 아니라 도구 동작이 됐다. 도구가 명령만으로 진짜 3층 분기를 그리고, steps.yaml↔깃 그래프가 동형이며, trailer 복원이 무손상이고, C008이 C011로 정직하게 정정됐다(커밋 불소멸=append-only 진짜 계약). 회귀 0. **원리를 도구가 강제하는 첫 조각 — 잎=태그·lineage=머지는 이 토대 위에 다음 사이클로.**
