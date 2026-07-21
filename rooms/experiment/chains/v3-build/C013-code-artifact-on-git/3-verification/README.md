# 3. 가설 검증 — v3-build/C013-code-artifact-on-git

실제 코드 아티팩트(다중 파일 `calc/`)를 공유 경로 한 벌 위에 싣고, 스텝별 트레이싱·롤백·죽은가지 생존·같은파일 독립분기 보존을 순수 깃으로 실측한다.

## 파일

| 파일 | 내용 |
|---|---|
| `build_codebase.sh` | 임시 저장소에 `calc/` 코드베이스를 스텝별 증분 커밋으로 짓는다. 3층 분기(s1에서 A·B·C 갈라짐), 백트래킹=checkout+detached, 잎=태그. 매 실행 `rm -rf` 후 재생성 → 완전 재현. |
| `measure_code.py` | 6측정(M1~M6)을 순수 깃 명령으로 수행, PASS/FAIL 판정. |
| `commit-index.txt` | s0~s10의 커밋 해시 (measure가 죽은잎 해시를 알도록). |
| `git-graph.txt` | 빌드 결과 `git log --all --graph` — 뷰어가 보는 것(재구현 0). |
| `measure-out.txt` | 측정 실행 출력 (ALL PASS 6/6). |
| `same-file-three-versions.txt` | 같은 `calc/core.py`의 세 가지 버전(s4·s7·s10) — H4 핵심 실증. |
| `example-live-core-s10.txt` | 산 잎(작업트리 물리 파일) core.py. |

## 재현 방법

```bash
# 1. 코드베이스 빌드 (임시 저장소는 scratchpad, 메인 레포 밖)
bash build_codebase.sh /tmp/c013-codebase

# 2. 측정
python3 measure_code.py /tmp/c013-codebase/repo /tmp/c013-codebase/commit-index.txt
# → RC=0 이면 ALL PASS
```

인자 없이 `bash build_codebase.sh` 하면 기본 scratchpad 경로를 쓴다. `git`(2.x)·`python3`·`bash`만 필요, 표준 라이브러리만.

## 시나리오

```
        (가지 A: naive concat)  s2 → s3 → s4 [죽음, 태그 gil/leaf/*]
       /
s0 → s1 ─ (가지 B: recursion)  s5 → s6 → s7 [죽음, 태그 gil/leaf/*]
       \
        (가지 C: a+b)          s8 → s9 → s10 [산 잎, 태그 gil/leaf/* + cycle/C-demo/solved]
```

세 가지가 **모두 s1에서 갈라져 같은 파일 `calc/core.py`를 서로 다르게** 고친다. 백트래킹은 `git checkout <s1해시>`+detached HEAD 커밋(C011 모델). 물리 작업트리엔 산 잎(C) 한 벌만 존재하고, 죽은 A·B의 core.py는 `git show`로만 접근된다.

## 측정 결과 (ALL PASS 6/6)

| 측정 | 가설 | 결과 |
|---|---|---|
| M1 증분 diff 트레이싱 | H1 | PASS — 10개 스텝 커밋 diff의 변경파일 집합 = 의도한 집합(불일치 0). s9는 core+util 다중파일 증분. |
| M2 1스텝=1커밋 | H1 | PASS — 11 고유 스텝, 머지 0(detached). |
| M3 git show 롤백+무손상 | H2 | PASS — 죽은잎 s4·s7 코드 추출, HEAD/status/인덱스/디스크 완전 불변, 작업트리=산잎. |
| M4 죽은가지 태그 생존+음성대조 | H3 | PASS — 태그 있으면 보임, 지우면 --all서 소멸, 되박으면 부활. |
| M5 같은파일 독립분기 보존 | H4 | PASS — core.py 세 버전 pairwise 상이 + 각 서명 + 오염 0. |
| M6 공유 한 벌(복사 0) 전버전 생존 | H4 | PASS — 물리 core.py 1개, 그래프에 core.py 손댄 커밋 9개, 세 잎버전 접근가능. |

## 실행 기록

- 일시: 2026-07-21. 환경: macOS(Darwin 25.5.0), git 2.x, python3, bash 3.2.
- 계측기 결함 1건(가설 반증 아님): 첫 실행 시 `commit-index.txt`가 잎(s0·s1·s4·s7·s10)만 기록해 M1이 s2에서 KeyError. 원인은 빌드가 `remember`를 잎에만 호출한 것. `step` 헬퍼가 매 커밋 자동 `remember` 하도록 고쳐 재빌드 → ALL PASS. 깃 동작이 아니라 스크립트 기록 누락이었음(정직 구분).
- 저자: Bobbin(격리 워크트리 `Bobbin/v3-build-code-artifact-on-git`).
