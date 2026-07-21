# 3. 가설 검증 — `gilv3 web` 통합 계보 뷰어

순수 git notes에서 두 층을 재구성해 자기완결 드릴다운 HTML을 내고, 4측정으로 실측한다.

## 산출물

- `gilv3.py` — C023판 복사 후 **`web` 서브명령 추가** (닫힌 사이클 불변 → 복사 후 확장). migrate·open/step/close·view 전부 보존.
- `notes_reconstruct.py` — 순수 git notes 재구성 모듈. 상위=`rebuild_cycle_dag`(C021/C022) 재사용, 하위=`reconstruct_step_tree`(step 커밋 notes 지문 → steps.yaml 등가 노드). notes 없으면 커밋 trailer로 폴백(네이티브 v3 지원).
- `web_render.py` — 통합 HTML 생성기. 상위 DAG SVG + 노드별 스텝 트리 인라인 임베드 + `hidden` 토글 JS. 스텝 트리 SVG는 C004 `steptree.render_html`에서 추출(재구현 금지).
- `steptree.py` — C004 자산 복사(재사용). 안 고침.
- `notes_reconstruct` 의존: `full_ledger_migrate.py`·`rebuild_cycle_dag.py`·`splice_topology.py`·`derive_fingerprint.py`·`retro_imprint.py` (C021/C023 자산 복사).
- `measure.py` — M1~M4 실측. `cdp_probe.py` — M4 실 Chrome CDP(C007 계보).
- `verify.sh` — 재현 절차(mktemp 격리).

## 재현 방법

```bash
bash verify.sh                    # 이 저장소 루트(살아있는 원장) 대상
# 또는
python3 gilv3.py web <repo> -o out.html   # 뷰어만 생성
python3 measure.py <repo>                 # 4측정
```

## 측정 결과 (2026-07-22, macOS, Python 3, Chrome headless)

```
web: … (378458 bytes) — 사이클 132 · 계보 엣지 131
M1 상위 진실원: 진실 132노드/131엣지 vs DOM 132노드/131엣지(그린 127 + 섬부모 4) → PASS
M2 v3 구조 보존: 재구성 7노드 · backtrack지문 1 · edge-backtrack 1 · leaf-live 1 · leaf-dead 1 → PASS
M3 자기완결: fetch벡터 0 · 비-xmlns http 0 (xmlns 133개는 SVG 네임스페이스) → PASS
M4 드릴다운 (실 Chrome CDP): M4a/M4b/M4c 전부 PASS
판정: ALL PASS
```

## 실행 특이사항 (정직한 기록)

1. **원장에 backtrack notes가 0.** 살아있는 원장 전량이 gil v2로 돌아 마이그레이션됐고(C019: "위상 보존, kind만 근사"), 마이그레이션은 v2 5스텝을 선형 매핑하므로 Backtrack-To 지문이 없다. 즉 원장의 132 사이클 스텝 트리는 전부 선형(상현님 "v2는 선형으로 보여도 상관없어"와 정합). 풍부한 구조(backtrack)는 v3 네이티브 gilv3 사이클에서만 나오는데 원장엔 아직 없다 → M2는 샌드박스에 gilv3로 backtrack 사이클을 실제로 만들어(진짜 trailer 지문) 재구성→렌더가 구조를 보존함을 증명. notes_reconstruct의 trailer 폴백이 이 네이티브 지문을 읽는다.

2. **섬 부모 엣지 4개(dangling).** `v3-build/C005→C004`, `loom/C013·C014·C018→C012`. 부모 사이클(C004·C012)은 도출실패(step 커밋 없음)라 DAG 132노드에 없다. 엣지를 소리 없이 버리지 않고 노드 위 stub + "↑ Cxxx (섬)" 라벨로 정직히 비춘다 — "notes가 담은 만큼, 없는 건 정직히 없음"(가설 H4).

3. **버그 하나 실측이 잡음.** 첫 실측에서 M4 전부 FAIL — JS를 `JS` 상수로 정의했으나 `<script>` 태그로 방출 안 해 뷰어가 죽은 JS였다. 정적 grep(`<script>` 0개)과 실 CDP(클릭 무반응)가 함께 짚었다. 표시는 계약 아님(§3.1) — 실 브라우저 실측이 정적 검증이 못 보는 배선 누락을 잡았다(C010·C047 재확인).
