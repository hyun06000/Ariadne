# 4. 결과 분석

## 통계적 결과

4측정 ALL PASS → **가설 supported.** 기각 조건 하나도 발동 안 함.

| 기각 조건 | 실측 | 발동? |
|---|---|---|
| migrate→web --v3가 v3 페이지 못 만듦 | v3.html 399113 bytes·139사이클·138엣지 | ✗ |
| v2 index 회귀 | index.html 생성 유지 | ✗ |
| 원격 notes 의존 | notes 삭제 후에도 원장만으로 생성 | ✗ |
| C007 검증 방식 불가 | fresh clone run 블록 실행으로 실측 | ✗ |

## 데이터 직접 관찰

### 원장-만 조건이 핵심을 증명했다

M3에서 clone의 refs/notes를 삭제하고 시작했다 — CI가 원격 notes를 안 가져오는 상황을 정확히 모사. migrate가 커밋 subject·cycle.yaml에서 지문을 도출해 notes를 새로 각인했고, web --v3가 그걸 읽어 v3.html을 냈다. **CI는 커밋만 있으면 v3 눈을 스스로 만든다** — 원격 notes 동기화·관리가 원리적으로 불필요. C026 형태("원장이 진실원, 눈은 재각인")의 배포 층 실용값.

### 커밋 digest 8b2643d6 불변

M4에서 migrate 전후 커밋 digest가 8b2643d6로 고정 — CI clone에서도 migrate가 refs/notes만 건드림(C018). CI가 원장을 오염시킬 위험 0. 배포 파이프라인에서 이 불변이 특히 중요: CI가 매 push마다 migrate를 돌려도 원장은 안전.

## 예상과 달랐던 것 — sed 이식성 함정

로컬 검증에서 `sed -i '1i ...'`가 실패했다(`invalid command code`). macOS BSD sed는 GNU sed(ubuntu)와 문법이 다르다. **CI는 ubuntu-latest라 원래 작동했겠지만**, 로컬 검증이 이 이식성 문제를 드러냈다. printf+cat 파일 조립으로 교체 — BSD·GNU 양쪽 안전. **로컬 실측이 CI-만이면 안 보였을 함정을 잡았다** — "워크플로가 곧 테스트"(C007)를 로컬에서 돌리는 값어치.

## 판정

**채택 (supported).** 워크플로에 migrate + web --v3 추가로 v3 뷰어가 Pages에 배포되게 했다. fresh clone(원장-만) 실측으로 v3.html 생성·두 층·커밋 불변 확인, v2 무회귀. push 시 실제 배포.

## 정점 통찰 — CI에서 눈을 재각인하는 게 원격 notes보다 견고

원격 notes를 fetch하면 push 시점(C023 73b18f4a)에 고정돼 최신 사이클(C024~C029)이 안 보인다. **CI가 매번 migrate로 재각인**하면 항상 최신. C026 "원장만 있으면 눈은 언제든 재각인"이 배포에서 실용값 — notes를 원격에 동기화·관리할 필요가 없다. **커밋만 push하면 눈은 CI가 만든다.** v3 마이그레이션 형태의 자연스러운 귀결: 눈이 재생성 가능하니 배포도 눈을 저장·전송하지 않고 재생성한다.

## 방법론에 귀속되는 교훈

- **재생성 가능한 산출물은 저장·전송하지 말고 재생성한다.** v3 눈(notes)은 원장에서 언제든 재각인되니, CI가 원격 notes에 안 기대고 매번 만든다. 원격 notes push(C023)는 다른 머신 공유용이지 배포 의존이 아니다.
- **로컬에서 워크플로를 돌리면 CI-만이면 안 보일 함정(sed 이식성)을 잡는다.** "워크플로가 곧 테스트"(C007)는 CI 실행만이 아니라 로컬 재현으로 완성된다.
- **CI가 원장을 안 바꾸는 게 배포 안전의 핵심.** migrate가 refs/notes만 건드림(C018)이라 매 push migrate가 원장 무해.
