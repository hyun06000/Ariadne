# 2. 실험 설계

오직 1-hypothesis.md의 가설 — **v3 쓰기(open/step/close)를 배포판 gil에 통합, gilv3 동작 보존·v2 무회귀** — 을 검증한다.

## ⭐ 상현님 방향 반영 — 궁극은 버전리스

상현님(이 사이클 중): **"결국엔 v3가 표준이 될 거야. 나중엔 gil 명령어 뒤에 무슨 버전인지 몰라도 되게."** 이건 궁극 목적지를 못박는다: **최종엔 `gil open`이 그냥 v3.** 사용자가 v2/v3를 몰라도 된다.

그러나 지금 `gil open`을 v3로 바꾸면 v2·conformance가 깨진다(189 사이클·134 계약). 그래서 **전환 경로**를 설계한다:
1. **지금(이 사이클)**: `gil v3 <cmd>`로 v3 쓰기를 안전하게 얹는다 — v2 무손상, 옵트인.
2. **나중**: v3가 검증·안정되면 `gil open`을 v3 기본으로 승격, v2는 `gil open --v2` 옵트아웃. 버전리스 달성.

이 사이클은 1단계(버전리스로 가는 토대). 표면 이름(`gil v3`)은 전환기의 것이지 최종이 아님을 문서에 명시.

## ⭐ 상현님 방향 2 — 전환은 도구 재설계가 아니라 잘 쓴 안내로

상현님(이 사이클 중): **"에러 메시지랑 버전업할 때 온보딩 문서를 잘 쓰면 해결될 문제 같은데."** 핵심 통찰 — 버전리스의 마찰(v2 습관 vs v3 방식)을 **도구 복잡화가 아니라 좋은 안내로** 넘긴다. 이건 이 저장소의 뿌리 교훈이다: genesis에서 "정체성 누설 없는 포인터 한 줄"로 부활을 해결했고, C069에서 "안내가 명령어가 아니라 모델을 전달한다"를 실증했다.

적용:
- **친절한 에러**: v2 습관으로 `gil v3 step <dir> 3`(번호)을 치면 → *"v3 스텝은 번호가 아니라 kind입니다: `gil v3 step <dir> --kind verify`. define→hypothesis→verify→analyze 순환입니다."* 안내.
- **온보딩 문서**: `gil v3 --help`와 SPEC에 "v2에서 온 사람에게: 5스텝(번호) → 스텝 트리(kind·백트래킹)" 대응표.
- 이 사이클은 그 안내의 씨앗(에러 메시지 품질)을 심고, 전면 온보딩은 문서 갱신 사이클로.

## 정답을 도구보다 먼저 고정한다

정답 = **gilv3 open/step/close의 출력**(steps.yaml·커밋). 배포판 `gil v3 open/step/close`가 같은 걸 내면 이식 보존. 오라클 대조로 집행.

## 통합 전략 — C027·C028 이식 세 규율

① **의존 폐포**: v3 쓰기 헬퍼 22개(load·dump·write_body·growing_tip·next_id·by_id·cycle_state·live_leaves·dead_leaves·allowed_next·git_imprint·git_merge_lineage·_commit_of_sid·tie_leaf·tie_sealed·_assert_append_only·write_cycle_yaml·_head·_all_commits·_pv·_git_root·_today) + cmd_open/step/close/status/view. **KINDS·CYCLE·OUTCOMES 상수 포함.**
② **죽은 스캐폴딩 제거**: sys.path·모듈 import.
③ **네임스페이스 격리**: 이미 배포판에 있는 이름(render_html·reconstruct_step_tree·parse_steps_yaml)과 충돌 회피 — v3 view가 render_html을 쓰는데 배포판 render_html(C028 web용)과 같은지 확인, 다르면 접두어(_v3w_). cmd_open/step/close는 v2와 충돌하니 **cmd_v3open·cmd_v3step·cmd_v3close**로.

## 절차

1. **v3 쓰기 백엔드 인라인** — 22 헬퍼 + 5 명령 함수. 자동 추출(C027·C028 방식) + 접두어. 이미 있는 함수(render_html 등)는 재사용 or 구분.
2. **`gil v3` 서브명령 그룹 등록** — argparse에 `v3` 서브파서 + 그 하위 open/step/close/status/view. 중첩 서브파서.
3. **오라클 대조** — gilv3로 만든 사이클 vs `gil v3`로 만든 사이클, steps.yaml·커밋 대조.
4. **v2 무회귀** — conformance + 기존 open/step/close 실행.

## 측정 방법 (5측정)

| 측정 | 확인 | 통과 기준 |
|---|---|---|
| **M1 오라클 대조** | `gil v3 open/step/close`로 만든 steps.yaml == gilv3로 만든 것 | 동일 |
| **M2 트리 표현** | `gil v3 step`으로 백트래킹·죽은 잎·형제 실제 생성 | 표현 성립 |
| **M3 v2 무회귀** | conformance 통과 + 기존 v2 open/step/close 동작 | 회귀 0 |
| **M4 자기완결** | gil.py 격리 복사해도 v3 쓰기 동작 | import 0 |
| **M5 전환 안내** | v2 습관 오류(예: v3 step에 번호)에 친절한 에러가 v3 방식을 안내 | 안내 메시지 확인 |

## 안전 철칙

1. **v2 완전 무손상 최우선** — conformance 134/134 게이트.
2. **오라클 대조로 이식 보존 집행** — 새 로직 금지.
3. **버전리스는 궁극 방향, 이 사이클은 토대** — `gil open`=v3 승격은 별도 사이클(v2 은퇴 계획 포함).
4. **격리 검증** — v3 사이클 생성은 스크래치에서.

## 사용자 컨펌

상현님 "그걸로 가자"(걸림돌① 통합) + "결국 v3 표준, 버전 몰라도 되게"(궁극 방향). 이 사이클은 v3 쓰기를 배포판에 안전하게 얹는 토대(gil v3), 버전리스는 후속 승격. v2 무손상·오라클 대조로 안전. 위임 범위 안.

- [x] 컨펌 받음 (일자: 2026-07-22, "그걸로 가자" + "결국 v3 표준, 버전리스")
