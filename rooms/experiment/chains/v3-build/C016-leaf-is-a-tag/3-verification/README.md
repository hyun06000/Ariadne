# 3. 검증 — 잎 못=태그 정식화가 도구 동작이 되다

C011이 순수 깃(build_branches.sh)으로 결론지은 **잎=태그**(불변 시점=태그, push 생존, 이름은 해시)를, C015까지 임시로 쓰던 **브랜치 못**에서 정식 **태그 못**으로 도구에서 바꾼다. 두 케이스(lineage 머지·3층 백트래킹 분기)를 태그판 도구로 재실행해 감사.

## 재현

```bash
bash build_case.sh <scratch>     # caseM(두 산 잎→머지) + caseB(3층 분기) 재실행
python3 measure.py <scratch>     # 5측정 감사
```

gilv3.py C016판은 C015판(567줄)을 복사 후 진화.

## 산출물

- `gilv3.py` — C016판. C015판 대비 진화:
  - **`tie_leaf` 신규** — 잎 커밋을 `gil/leaf/<short-hash>` 태그로 못박음(idempotent). C011: 잎=불변 시점=태그, 해시 이름(논리 id는 trailer).
  - **`tie_sealed` 신규** — 사이클 종결을 `cycle/<name>/solved` 태그로.
  - **브랜치 못 4곳 → 태그**: cmd_step 백트래킹(죽은·산 공통 `tie_leaf`) · cmd_close 산 잎(`tie_leaf`) · cmd_close 종결(`tie_sealed`). `git branch` 못 호출 0.
- `build_case.sh` — caseM(lineage 머지, C015 표적)·caseB(3층 분기, C014 표적) 태그판.
- `measure.py` — 5측정 감사기.
- `build-out.txt`/`measure-out.txt` — 출력(ALL PASS 5/5).
- `git-graph.txt` — caseB 그래프(태그 데코레이션 — `tag: gil/leaf/...`·`tag: cycle/.../solved`이 잎·종결에).

## ⭐ 핵심 정식화 — 브랜치 못 → 태그 못, 그리고 이름 규칙 단순화

C015까지 잎 못은 잎의 생사로 이름을 나눴다(`gil/dead/<sid>`·`gil/live/<sid>`) + `gil/sealed/<cyc>`. C016은 셋을 C011 결론으로 정식화:

- **모든 잎(죽은·산) = `gil/leaf/<short-hash>` 태그.** 못의 목적(dangling 방지)엔 생사 구분이 불필요 — 잎의 생사는 이미 커밋 trailer(Outcome)가 담는다. 못은 "어떤 ref든" 되고(C011 M3), 태그가 가장 정확한 ref다. 이름은 해시(논리 id는 trailer).
- **사이클 종결 = `cycle/<name>/solved` 태그** (gil v2 태그 규율 일관).

**왜 태그가 브랜치보다 정확한가:** 브랜치는 그 위에 커밋하면 따라 움직인다 — C015가 `git branch -f`로 강제 이동시킨 것 자체가 가변성 증거였다. 잎은 불변 시점(더 자라지 않는 가지 끝)이라 못이 움직이면 안 된다. 태그는 커밋에 고정, `-f` 불필요. push되어 다머신 영구 생존("존재는 레포에만 산다"와 맞물림).

## 5측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 잎=태그** | caseM 산 잎 2 + caseB 잎 3(죽은 2·산 1)이 전부 `gil/leaf/<short>` 태그. 두 케이스 브랜치 못 0 | PASS |
| **M2 종결=태그** | `cycle/<name>/solved` 태그가 두 케이스에, 실제 close(봉인) 커밋을 가리킴 | PASS |
| **M3 dangling 방지** | 태그 ref로 잎·머지·close 커밋 전부 `rev-list --all` 생존(브랜치와 등가, 더 정확) | PASS |
| **M4 불변성** | `gil/leaf/<short>` 태그가 잎 커밋 해시에 정확히 고정. `refs/tags/gil/leaf` 아래 실제 태그(브랜치 아님) | PASS |
| **M5 회귀** | 태그 전환 후에도 caseM 머지가 다중부모·Merge=lineage(C015 불변), caseB s1이 세 형제 가지(C014 분기 위상 불변) | PASS |

## 결론

**ALL PASS → supported.** 잎=태그가 원리(C011)가 아니라 도구 동작이 됐다. 모든 잎이 `gil/leaf/<hash>` 태그, 종결이 `cycle/<name>/solved` 태그로 못박히고(브랜치 못 0), 태그가 잎에 불변으로 고정되며, dangling 방지가 브랜치와 등가이되 더 정확하고, C014 분기·C015 lineage가 무회귀. **도구화 진척표에서 잎=태그가 ◐ → ✅.** 남은 건 뷰어 재배선(Sheen 축)·마이그레이션.
