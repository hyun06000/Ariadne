# 기대 판정 (정답 고정)

> ⚠️ 이 문서는 **워크플로 작성 전**에 고정되었다 (2026-07-14). 산출물에 맞춰 수정 금지.

| id | 판정 | 기준 |
|---|---|---|
| T1 | 신선 클론 재현 | `git clone <이 저장소> <임시>` 후, 워크플로 yml의 모든 `run:` 블록을 추출·연결해 `bash -e`로 클론 안에서 실행하면 exit 0. `_site/index.html`이 생기고, 내장 JSON(`id="ari-data"`)의 `<chain>/<id>` 집합 = 클론의 `rooms/experiment/chains/*/*/cycle.yaml` 디렉토리 스캔 집합 |
| T2 | 자기완결 | `_site/index.html`에 `https?://`를 참조하는 `src=`·`href=`·`url(`·`@import` 0건 |
| T3 | 무설치 빌드 | 추출된 run 블록에 `pip`·`npm`·`curl`·`wget` 문자열 0회 (표준 러너의 python3만 사용) |
| T4 | 워크플로 정합 | yml에 다음 전부 존재: `push` 트리거 + `main` 브랜치, `pages: write`, `id-token: write`, `actions/checkout`, `actions/upload-pages-artifact`, `actions/deploy-pages` |

- T1의 정신 (C006 계승): **워크플로가 곧 테스트다.** 빌드 명령은 워크플로 파일에서 추출되므로 정의와 검증이 어긋날 수 없다.
- 클론은 커밋된 HEAD만 담는다 — 이 사이클(C007)의 미커밋 문서는 스캔 대상에 없어야 정상이며, 비교는 클론 내부끼리만 한다.
- 원격 끝단(Actions 러너 실행, Pages URL)은 이 판정의 범위 밖 — 한계로 기록.
