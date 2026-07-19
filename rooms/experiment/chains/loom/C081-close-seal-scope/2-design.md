# 2. 실험 설계

## 설계 전환 (실데이터가 "예상 밖" 정의를 반증)

상현님 결정은 A(요약 + 예상 밖 경로 경고/차단). 설계 중 실데이터를 조사하니 **"예상 밖 경로"를 형태로 정의할 수 없음**을 발견:
- 정당한 3-verification 산출물이 하위 디렉토리·임의 파일명을 자유롭게 쓴다: C005(`ari/`·`fixtures/broken/`·`runs/`·`tests.py`), C020(`gil-go/`·`runs/`), C076(`probe_*.py`).
- 재현의 오배치 `wrong-subdir/misplaced.txt`도 형태만으로는 정당한 `fixtures/broken/`과 구별 불가.

→ **close는 내용/형태로 오배치를 판단할 수 없다.** "예상 밖 경로 차단"은 정당 산출물을 오탐한다. A의 취지("사용자가 무엇을 봉인하는지 보게")를 지키되, 경계를 **"형태"가 아니라 "신규성(untracked)"**으로 재정의한다.

## 절차 (A 정련: 신규 untracked 요약 + 확인)

1. **참조 `cmd_close`: 봉인 전 신규 untracked 파일 요약**: `git add -A -- <cycle_dir>` **직전에**, 그 커밋으로 새로 tracked될 파일(= 현재 untracked)을 `git status --porcelain -- <cycle_dir>`로 수집. 있으면 목록을 출력("이 close가 새로 봉인할 파일: …").
2. **`--allow-extra` 없으면, 신규 파일이 사이클 표준 산출물(1~5·3-verification/README·deviations/corrections.yaml) 밖이면 거부**: 표준은 무경고 통과(정상 흐름). 표준 밖 신규 파일(예: 3-verification 하위 임의 산출물)이 있으면 요약 + "예상과 다르면 정리하거나 `--allow-extra`로 승인하라" 거부. **차단이 아니라 확인 게이트** — 정당하면 `--allow-extra`로 봉인.
   - 단, 실데이터가 3-verification 하위 자유 산출물이 정상임을 보였으므로, **거부 대상은 "3-verification/ 밖 + 표준 문서 밖"의 신규 파일**로 좁힌다(가장 흔한 오배치: 사이클 루트나 잘못된 위치). 3-verification/ 안은 요약만(자유 산출물 존중), 그 밖 비표준은 게이트.
3. **Go 동형 + 판정기 CLOSE-SEAL-SUMMARY/GATE**.

## 준비물
- 참조 `gil.py`(v2.31), Go `main.go`, `conformance.py`. `git status --porcelain`, `git ls-files`.

## 측정 방법
| 측정 | 성공 기준 |
|---|---|
| 오배치(사이클 루트 비표준 신규 파일) 있이 close | 거부 + 요약, `--allow-extra`로 통과 |
| 3-verification/ 하위 자유 산출물 | 요약만, 정상 봉인(거부 안 함) |
| 표준만(1~5·README) close | 무경고 정상(기존 불변) |
| 봉인 내용 | 정상 사이클 봉인 바이트/파일 불변 |
| 참조↔Go | parity |
| 판정기 | 신규 항목 PASS + 회귀 0 |

**기각선**: 정당 3-verification 산출물이 막히거나, 오배치가 무경고 봉인되거나, 기존 close 회귀.

## 사용자 컨펌
- 상현님 A 선택. 설계 중 "예상 밖=형태"가 실데이터에 반증돼 "신규성+위치"로 정련(3-verification 안은 존중, 밖 비표준은 게이트) — A의 취지 유지, 오탐 제거.

- [x] 컨펌 받음 (일자: 2026-07-19) — 상현님 재확인: "3-verification 안은 존중, 밖만 게이트". 형태가 아니라 위치(3-verification/ 경계)로 오배치를 가른다.
