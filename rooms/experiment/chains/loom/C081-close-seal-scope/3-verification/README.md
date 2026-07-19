# 3. 검증 — close 봉인 스코프 게이트 (이슈 #19)

## 결과 (양 구현)
| 케이스 | 결과 |
|---|---|
| 오배치(사이클 루트 비표준 신규 파일) close | 게이트 거부 + 요약, 태그 없음 |
| --allow-extra | 경고 후 봉인 |
| 3-verification/ 하위 자유 산출물(fixtures·probe) | 게이트 없이 정상 봉인 (오탐 0) |
| 표준만(1~5·README) close | 무경고 정상 (기존 불변) |

- 참조 **107/107**·Go **93/93** (CLOSE-SEAL-GATE·ALLOW·VERIFICATION-FREE 신설, 회귀 0). 수정 전 참조 105/107·Go 91/93.

## 설계의 핵심 (실데이터가 만든 경계)
실사이클 조사(C005 `ari/`·`fixtures/broken/`·`runs/`, C020 `gil-go/`, C076 `probe_*.py`)가 "정당한 3-verification 산출물은 하위 디렉토리·임의 파일명을 자유롭게 쓴다"를 보였다 → **오배치를 형태로 판단 불가**. 경계를 형태가 아니라 **위치(3-verification/ 안=존중, 밖=게이트) + 신규성(untracked)**으로 정의. 상현님 재확인.

## 수정
- 참조 `cmd_close`: `git add` 직전 `_close_unexpected_files`(git status --porcelain에서 3-verification 밖 + 표준 밖 untracked)로 게이트. --allow-extra로 승인. 거부 시 yaml 원복(저장소 무변화). `--allow-extra` 인자 신설.
- Go `cmdClose`: 동형(`closeUnexpectedFiles`, `allowExtra`).
- 판정기 3항목 신설(게이트·승인·오탐0).

## 자기적용
이 사이클(C081) 자신을 close할 때 게이트가 작동한다. 3-verification/ 안 산출물(이 README·probe)은 게이트 대상이 아니라 정상 봉인.
