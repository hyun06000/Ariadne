# 1. 가설 — 통합 계보 뷰어 (git notes만으로 드릴다운)

부모: C023 (migrate 명령화). 형제 계보: C021(위상 접합)·C022(freeze/apply).

## 이전 사이클의 교훈

C022가 v3 계보를 실제 원장 git notes에 각인했다 — (a) 사이클 간 `Cycle-Parent` 엣지(132노드·131엣지·머지4), (b) 사이클 내 각 스텝 커밋의 지문(Step-Id·Kind·Parent·Outcome·Backtrack-To). C023이 그걸 `gilv3 migrate` 명령으로 만들었다. 그러나 **각인된 계보를 사람 눈에 드러내는 통합 뷰어가 없다.** 원장은 기계의 눈엔 완전하나 사람의 눈엔 어둡다(내 의지). 나는 빛이다 — 이미 있는 진실을 사람 눈에 옮긴다.

## 문제 분할

확정된 설계(상현님·C024 design-notes):
1. **데이터 소스: git notes만으로 (순수 v3).** cycle.yaml 안 읽음.
2. **형태: 드릴다운.** 상위 = 사이클 간 계보 DAG 한 화면. 노드 클릭 → 그 사이클의 스텝 트리.
3. **스텝 트리: v3 초점.** v2 마이그레이션 사이클은 notes에서 선형 재구성돼도 무방. 풍부한 구조(backtrack)는 v3 네이티브 사이클에서.
4. **몸: gilv3의 `web` 명령.** (gilv3 view는 한 사이클용 — 통합은 새 서브명령.)

가장 작은 첫 단위: **`gilv3 web <repo> -o out.html`** 한 명령이 순수 git notes에서 두 층을 재구성해, 상위 DAG(클릭 가능 노드) → 하위 스텝 트리(펼침)를 한 자기완결 HTML로 낸다.

## 가설

> **가설**: git notes만으로 (cycle.yaml 무의존) 사이클 간 DAG(`rebuild_cycle_dag` 재사용)와 사이클 내 스텝 트리(각 사이클 step 커밋의 notes 지문 시퀀스 재구성)를 재구성하고, C004 `steptree.py`를 재구현 없이 재사용해 각 DAG 노드에 스텝 트리를 인라인 임베드하면, 클릭 드릴다운되는 자기완결 단일 HTML(외부 리소스 0)을 낼 수 있다.

세부:
- **H1 (두 층 재구성):** 상위=`rebuild_cycle_dag`→`{chain/short_id:[parents]}`. 하위=step 커밋 notes 지문을 모아 steps.yaml 등가 노드 리스트.
- **H2 (렌더 재사용):** 스텝 트리 렌더는 C004 steptree를 import 재사용. 재구성 노드 리스트를 steptree가 아는 형태로 먹인다.
- **H3 (자기완결 드릴다운):** 상위 DAG SVG + 노드마다 스텝 트리 인라인 임베드 + C006 교훈대로 `hidden` 토글(fetch 아님 — 정적 자산은 render 시점에 다 안다).
- **H4 (정직한 빈 곳):** 마이그레이션 v2 사이클은 s1(open)에 notes 없어 s2부터 시작 → steptree가 root=None으로 안 깨지게, parent가 노드 집합에 없으면 그 노드를 root로. 도출실패 사이클은 스텝 트리 비어있음(섬)을 정직 표시.

## 기각 조건

- notes만으로 상위 DAG 노드 수가 `rebuild_cycle_dag` 진실원과 불일치.
- v3 네이티브 사이클(C008 등)의 backtrack/산잎/죽은잎 구조가 스텝 트리에서 소실(선형으로만 나옴).
- 출력이 자기완결이 아님(외부 리소스 참조 발생).
- 드릴다운 클릭이 실 브라우저에서 스텝 트리를 펼치지 못함.

## 범위 밖 (정직한 절제)

- migrate 로직 자체(C023) — 내 축(뷰어)이 아니다.
- 참조 gil.py / Go main.go의 web(v2 원장 뷰어). gilv3는 별개 v3 궤도 — gilv3에만 얹는다.
- cycle.yaml 재도입 — 상현님 결정 1 위반. notes만.
