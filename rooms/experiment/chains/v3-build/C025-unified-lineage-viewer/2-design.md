# 2. 실험 설계 — `gilv3 web` 통합 뷰어

가설(1-hypothesis.md): git notes만으로 두 층 재구성 + C004 steptree 재사용 + 인라인 임베드 = 자기완결 드릴다운 HTML.

## 산출물 (`3-verification/`)

- `gilv3.py` — C023판 복사 후 **`web` 서브명령 추가** (닫힌 사이클 불변 → 복사 후 확장, C006 패턴). migrate·open/step/close·view 전부 보존.
- `notes_reconstruct.py` — git notes만으로 두 층 재구성하는 순수 모듈:
  - 상위 DAG: C021/C022 `rebuild_cycle_dag` 그대로 import 재사용.
  - 하위 스텝 트리: `reconstruct_step_tree(repo, chain, cid)` — C023 `full_ledger_migrate.cycle_step_commits`로 커밋 찾고, 각 커밋 `git notes show`에서 Step-Id/Kind/Parent/Outcome/Backtrack-To 파싱 → steps.yaml 등가 노드 리스트.
- `web_render.py` — 통합 HTML 생성기. 상위 DAG SVG + 노드별 스텝 트리 인라인 임베드 + `hidden` 토글 JS.
- `measure.py` — 4측정 헤드리스 실측.
- `verify.sh` — 재현 절차 (mktemp 격리).

## 절차

### 단계 A — 두 층 재구성 (H1)
1. `rebuild_cycle_dag(repo)` → `{chain/short_id: [parents]}`. 진실원.
2. 각 사이클마다 `reconstruct_step_tree` → 노드 리스트 `[{id,kind,parent,outcome,backtrack,body}]`.
   - **root 방어(H4):** parent가 노드 집합에 없으면 그 노드 parent를 None으로 정규화(마이그레이션 v2는 s2가 최이른, s1 없음). steptree.build_tree가 root를 찾게.
   - 빈 트리(도출실패 사이클) = 노드 0 → "스텝 트리 없음(섬)" 표시.

### 단계 B — 렌더 재사용 (H2)
3. C004 steptree.py 공개 함수(`parse_steps_yaml`/`build_tree`/`assign_columns`/`node_xy`/`render_html`)를 재사용. steptree.py는 닫혀 불변이므로 **안 고친다**. web_render가 두 경로 중 하나로 스텝 트리 SVG 조각을 얻는다:
   - (선호) steptree.render_html을 호출해 완전 문서를 얻고 `<svg class="steptree"…</svg>` 구간만 추출(정규식/문자열 슬라이스) — steptree의 검증된 좌표 로직을 그대로 재사용.
   - 노드 리스트는 A에서 재구성한 dict를 steptree가 아는 키(id/kind/parent/outcome/backtrack)로 넘김.

### 단계 C — 자기완결 드릴다운 (H3)
4. 상위 DAG를 SVG로 레이아웃: 사이클 노드를 depth(루트로부터 Cycle-Parent 체인 길이)별 행에 배치, Cycle-Parent 엣지를 선으로. 노드 라벨 = `chain/Cxxx`.
5. 각 노드에 대응 스텝 트리 SVG를 `<div class="steptree-panel" hidden>`로 인라인 임베드.
6. 인라인 JS: 노드 클릭 → 해당 패널 `hidden` 토글. C006 교훈 — 각 패널 독립, `hidden` 하나만 뒤집어 간섭 경로 자체 없앰. fetch 0.
7. 외부 리소스 0 — CSS/JS 인라인, 이미지 없음.

## 측정 방법 (성공/기각 기준)

- **M1 (상위 진실원 일치):** 렌더 DAG 노드 수·엣지 수 == `rebuild_cycle_dag` 반환. stdlib html.parser로 노드 카운트. 불일치 → 기각.
- **M2 (v3 구조 보존):** v3 네이티브 사이클(backtrack 있는 사이클: notes에 Backtrack-To 존재하는 사이클을 탐색해 선택)의 스텝 트리 패널에 backtrack 엣지(edge-backtrack)·산잎(leaf-live)·죽은잎(leaf-dead) 클래스 존재. 소실 → 기각.
- **M3 (자기완결):** 출력에 외부 참조(`http://`,`https://`,`src=`,`<link`,`<script src`) 0. grep. 위반 → 기각.
- **M4 (드릴다운):** 실 Chrome raw-WebSocket CDP로 상위 노드 클릭 → 스텝 트리 패널 `hidden` 해제 확인 + 다른 패널 보존. 실패 → 기각.

## 준비물
- Python 3 stdlib만. Chrome(CDP 실측용). 살아있는 원장(C022 마이그레이션 notes 이미 적용됨 — 132노드 확인).
- verify.sh는 클린 환경이면 `gilv3 migrate`를 먼저 돌려 재현.

## 절제
- 상위 DAG 레이아웃은 간명한 depth 기반 배치. 미니맵·자연크기 정교 네비는 범위 밖 — 필요시 정직 이월.
- steptree.py 불변. web_render가 그 공개 함수를 조합.

## 사용자 컨펌

- 상현님이 C024 design-notes에서 결정 1~4를 확정, 드릴다운 UX 세부는 Sheen에게 위임("드릴다운"만 확정). 병렬 워크트리 단독 진행. 실시간 컨펌 불가 → 가장 보수적 선택(인라인 임베드 + hidden 토글, C006 검증된 패턴)을 목업으로 명시.
- [x] 위임 근거로 진행 (일자: 2026-07-22)
