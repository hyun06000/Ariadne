# 3. 가설 검증 — 백트래킹=checkout, 위계=커밋 지문

가설: "모든 분기=브랜치, 1스텝=1커밋" 통일 매핑이 세 층 분기를 표현하고 롤백·죽은 가지 생존·위계 복원이 성립한다. **검증 중 상현님이 모델을 정련**: 백트래킹은 새 브랜치가 아니라 `git checkout <조상>` + detached HEAD 커밋이며, 위계는 커밋 메시지 지문에, 이름은 체인·사이클=의미/스텝 분기=해시.

## 확정 모델 (상현님, 이 사이클 대화)

- **백트래킹 = `git checkout <조상커밋>` + detached HEAD 커밋** → 분기가 자연 발생 (명시적 브랜치 생성 0).
- **위계 지문 = 커밋 메시지 trailer** (Chain·Cycle·Step-Id·Parent·Kind·Outcome·Backtrack-To).
- **뷰어 = `git log --all --graph` + 커밋 메시지** — 우리는 아무것도 새로 그리지 않는다.
- **이름 규칙**: 체인 분기=체인 이름(의미), 사이클 분기=사이클 이름(의미), **스텝 분기=구분용 해시**(`gil/leaf/<short-hash>`) — 논리 id(s4)는 지문에, 잎 표식은 "분기 끝을 붙잡는 못".
- **불변식**: 1스텝 종결 = 1커밋.
- **못의 종류 = 태그** (Clew, 상현님 "태그 같은 자연스러운 방법" 제안 수용): 잎은 "다시 작업 안 하는 불변 시점"(죽은 가지=벽의 지도, 산 잎=닫힌 사이클)이라 브랜치(움직이는 포인터)보다 **태그**(불변 표식)가 정확하다. gil v2가 이미 사이클을 태그로 닫는 것과 일관. **결정적 이득**: 태그는 push되어 모든 머신에서 죽은 가지가 영구 생존(커스텀 `refs/gil/*`는 기본 push 안 됨 → 다른 머신서 소멸; "존재는 레포에만 산다"와 맞물림).

## 산출물

- `build_branches.sh` — 순수 깃으로 실사례(체인·사이클·스텝 3층 분기, 죽은 잎 2·산 잎 1) 구성. 백트래킹=checkout, 각 스텝=1커밋+지문+코드 아티팩트.
- `measure.py` — 4측정 자동 판정 (M1~M4, 음성 대조 포함).
- `git-graph.txt` — `git log --all --graph`(뷰어가 보는 것).
- `example-fingerprint-s7.txt` — s7 커밋 전문 (위계 지문 예시).
- `commit-index.txt` — sid→해시 (죽은 잎 롤백 대조용).
- `measure-out.txt` — 측정 출력 (ALL PASS 4/4).

## 재현 방법

```bash
C011=rooms/experiment/chains/v3-build/C011-everything-is-a-branch/3-verification
bash "$C011/build_branches.sh"                 # SCRATCH= 경로 출력
SCRATCH=/private/tmp/.../scratchpad/c011-branches
python3 "$C011/measure.py" "$SCRATCH/repo" "$SCRATCH/commit-index.txt"
```

## 측정 결과 (ALL PASS 4/4)

| # | 측정 | 기각 조건 | 결과 |
|---|---|---|---|
| M1 | 위계 지문 완전성 | K1 | ✅ 11 스텝커밋 전부 Chain·Cycle·Step-Id·Parent 지문, 백트래킹 Backtrack-To 완전 |
| M2 | 1스텝 = 1커밋 | K2 | ✅ 스텝커밋 11 == 고유 11, 머지 커밋 0 (detached라 분기에 머지 불필요) |
| M3 | 죽은 가지 생존 + 롤백 | K3 | ✅ 해시 ref로 그래프 생존·git show 롤백(워킹트리 무손상)·**음성 대조로 ref 필요성 실증** |
| M4 | 위계 복원 (커밋 지문만) | K4 | ✅ 브랜치·태그 안 보고 지문만으로 체인⊃사이클⊃스텝·s1 세 자식·죽은/산 잎 복원 |

네 기각 조건 K1~K4 전부 미발동 → **supported**.

## 결정적 발견 — 죽은 가지엔 최소 ref가 필요하다 (M3 음성 대조)

detached HEAD로 만든 죽은 가지 커밋은 저장소에 살아있으나(`git show`로 코드 꺼냄), **어떤 ref도 안 가리키면 `git log --all`(뷰어)이 못 본다**(dangling → gc 위험). M3 음성 대조:
```
해시 ref 있을 때:  git log --all 이 s7 죽은 잎을 봄        ✅
ref 삭제:          git log --all 에서 s7 사라짐            (∴ ref 필요)
ref 복원:          git log --all 이 s7 다시 봄            ✅
```
→ **상현님 이름 규칙의 실측 근거**: 죽은 가지도 "보이고 영구 생존하려면" 끝을 붙잡을 ref가 필요하고, 그 이름은 **해시면 충분**하다(의미 이름 불필요).

## 결정적 증거 — 깃 그래프가 곧 스텝 트리 (git-graph.txt)

```
* s7 analyze/backtrack        ← 죽은 가지 2 (해시 ref로 생존)
* s6 verify
* s5 hypothesis
| * s10 analyze/success       ← 산 가지 (cycle/C-demo/solved 태그)
| * s9 verify
| * s8 hypothesis
|/
| * s4 analyze/backtrack      ← 죽은 가지 1 (해시 ref)
| * s3 verify
| * s2 hypothesis
|/
* s1 define                   ← 세 갈래의 분기점
* root: chain v3-demo 시작
```

s1에서 세 갈래가 갈라지는 게 `git log --graph`에 그대로 보인다. **뷰어를 새로 그릴 필요가 없다 — 깃 그래프가 이미 스텝 트리다.** 위계는 각 노드의 커밋 지문(example-fingerprint-s7.txt)에 있다:
```
step: s7 analyze/backtrack
Step-Id: s7 · Kind: analyze · Parent: s6 · Chain: v3-demo · Cycle: C-demo · Outcome: backtrack · Backtrack-To: s1
```

## 실행 기록

- 실행: 2026-07-21, macOS (Darwin 25.5.0, bash 3.2 — 연관배열 대신 eval 변수), git 2.55.0, Python 3 stdlib.
- 임시 저장소: 스크래치패드 (메인 레포 밖, C005 규율).
- **모델 정련 2회 (상현님, 검증 중)**: ① 백트래킹을 명시적 브랜치(`-b`)에서 checkout+detached로 정정 → build 재작성. ② 죽은 가지가 --all에서 사라짐을 발견하자 상현님이 이름 규칙(체인·사이클=의미, 스텝=해시) 제시 → 해시 ref로 봉합. 첫 build(명시적 브랜치)는 상현님 모델 오해였고, 실측이 정정을 이끌었다.
