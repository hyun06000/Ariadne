# 5. 결과 보고 — `gilv3 web` 통합 계보 뷰어

## 요약

C022가 원장 git notes에 각인한 v3 계보를 사람 눈에 드러내는 통합 뷰어를 `gilv3 web` 서브명령으로 지었다: 순수 git notes(cycle.yaml 무의존)에서 상위 사이클 간 DAG(Cycle-Parent, `rebuild_cycle_dag` 재사용)와 하위 사이클 내 스텝 트리(step 커밋 notes 지문, C004 `steptree` 재사용)를 재구성해, 노드 클릭으로 드릴다운하는 자기완결 단일 HTML(외부 리소스 0)을 낸다. **판정: supported** — M1(진실원 132노드/131엣지 일치)·M2(v3 backtrack 구조 보존)·M3(자기완결)·M4(실 Chrome CDP 드릴다운) ALL PASS.

## 교훈

1. **원장이 진실원 — 그러나 재구성은 담은 만큼만 비춘다.** cycle.yaml 한 줄 안 읽고 두 층이 다 나왔다(상현님 결정 1 실물 성립). 단 원장 132 사이클은 전부 선형(backtrack 0) — v2 마이그레이션의 선형 매핑 때문. 없는 구조를 지어내지 않는 것이 정직이다.

2. **정직한 빈 곳은 버리지 말고 비춘다.** 부모가 도출실패 섬인 4개 엣지를, 기준을 낮춰 버리는 대신 "↑ Cxxx (섬)" stub으로 그렸다. 빛은 어둠도 어둠으로 비춘다 — M1이 진실원과 정확히 일치한 건 버리지 않은 덕분.

3. **두 각인 수단, 한 파서 (C021 재확인).** 마이그레이션=notes, 네이티브=trailer. retro_imprint 계약("notes 본문 = trailer 형식") 덕에 한 파서가 죽은 v2·산 v3 계보를 다 읽는다. `_fingerprint_lines`의 notes→trailer 폴백.

4. **실 브라우저 실측이 죽은 JS를 잡았다 (§3.1·C010·C047).** `JS` 상수를 만들고 `<script>` 방출을 빠뜨린 배선 누락 — 정적 grep과 실 CDP가 함께 짚었다. 표시는 계약이 아니므로 실측으로 증명한다.

## 다음 사이클을 위한 제안

- **B1 넓은-그래프 네비 이식.** 132노드 상위 DAG는 커지면 한 화면에 안 담긴다 — loomlight/C004 미니맵 계보를 gilv3 web으로 이식.
- **B2 3단 드릴다운(본문).** DAG→스텝트리 위에 스텝 본문(steps/<id>.md) 임베드를 더해 C006의 단일-사이클 본문 드릴다운을 통합 뷰어로. 132×스텝 비대화 대비 lazy 임베드 설계 필요.
- **B3 gil web 통합 검토.** 현재 gilv3 web은 v3 궤도 별도 명령. 장차 gil v2 원장 뷰어와 한 창으로 합칠지(gil web --v3?)는 상현님 결정.
- **B4 원장 v3 네이티브화 후 재실측.** 원장이 gilv3로 실제 돌기 시작하면 backtrack 스텝 트리가 실물로 나온다 — 뷰어는 이미 준비됨(M2). 그때 원장 실물로 M2 재확인.

## 사이클 닫기

- [x] `cycle.yaml`의 `status: closed`, `closed` 갱신 (gil close가 수행)
- [x] 존재의 방 `memory.md`에 이 사이클 기억 기록
- [x] 커밋 및 퍼블리시 (브랜치 push, land는 Clew)

## 산출물 자리

- 몸: `3-verification/gilv3.py` (web 서브명령), `web_render.py`, `notes_reconstruct.py`, `cdp_probe.py`, `measure.py`, `verify.sh`.
- 브랜치 `sheen/v3-build-unified-lineage-viewer`에 전 스텝 push. 병합은 Clew의 `gil worktree land --no-ff`.
