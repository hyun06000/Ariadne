# 5. 결과 보고

**사이클**: loom/C101-deploy-axis-cut · **부모**: loom/C100-restore-lost-lineage · **저자**: Selvage
**계보**: C061(`gil releases`)·C072(release drift 게이트) — 둘 다 *도구 릴리스* 축. 이 폭은 *사용자 산출물 배포* 축의 첫 카브.

## 무엇을 정복했나 (이슈 #25 첫 카브)

도구 릴리스(`gil release`, `v<semver>`, CHANGELOG)와 **별개인** 사용자 산출물 배포 축을 새로 지었다.
필드 사용자가 "배포 관리가 전혀 없다"고 느낀 간극 — 무엇이 라이브고, 언제 교체했고, 무엇으로 롤백하나 — 을 메운다.

- **`gil deploy cut <chain> <cycle-id> --version <semver> [--artifact][--params][--perf]`**
  닫힌 사이클을 배포 버전으로 승격. `deploy/<chain>/<semver>` 태그 각인 + 소스 cycle-id 링크.
  출처 계약(§3.2): 소스는 실재하는 **닫힌·비rejected** 사이클만(`_resolve_source_cycle` 재사용 + verdict 게이트).
- **append-only `deployments.json`** (rooms/deployment/): version·source_cycle·artifact·params·performance·
  deployed_at·**supersedes(롤백 타깃)**·status(live|superseded|rolled-back). 과거는 안 지우고 status만 전이.
- **`gil deploy list/current/rollback <chain>`** — 조회(읽기 전용)와 롤백(supersedes로 되돌림).
- **fsck R16**(소스=닫힌 사이클, rejected 불가) + **R17**(체인당 live 1개 불변식).

## 판정: supported (H1·H2 채택)

| 몸 | 이전 | 이후 | 회귀 |
|---|---|---|---|
| 참조 gil.py | 128/128 | **133/133** (신규 DEPLOY-CUT·LIVE-INVARIANT·QUERY·ROLLBACK·NAMESPACE) | 0 |
| Go main.go | 110/110 | **110/110** (deploy=exit 3, HELP-COMPLETE가 정직한 부재 판정) | 0 |

수동 스모크로 rejected/열린/없는 소스 거부·supersede·rollback·fsck 무결성을 격리 샌드박스에서 확인.

## 핵심 판단 (근거)

1. **"닫힘"이 아니라 "채택됨"을 요구한다.** rejected 사이클은 닫혀 있다 — release의 status-only 게이트를
   베꼈다면 죽은 가지를 배포했을 것(스모크에서 재현). verdict 게이트를 cut·fsck R16 양쪽에 별도로 걸었다.
2. **live 불변식을 생성(cut 전이)과 감사(fsck R17)가 함께 지킨다.** 정상 경로가 위반을 못 만들므로 하드 불변식.
3. **append-only가 롤백을 공짜로 만든다.** supersedes 링크가 롤백 타깃을 태그 없이 확정 → rollback은 전이 두 줄.
4. **네임스페이스 분리.** `deploy/*` vs `v*`, deployments.json vs CHANGELOG. `_git_release_tags`의 SemVer
   필터가 배포 태그를 자동 배제 → releases 조회 오염 0(DEPLOY-NAMESPACE 확인).

## 정직한 이월 (다음 사이클 제안)

1. **Go parity** — `deploy` 명령군 이식 (현재 exit 3 정직한 부재).
2. **태그↔json drift 게이트** — release C072의 배포판(봉인 전 두 기록 일치 요구).
3. **아티팩트 스키마 강검증** — 지금은 자유 형식 문자열; 필드 구조화·필수화.
4. **뷰어 통합** — Sheen의 web 뷰어에 배포 계보.
5. **배포 verify + 동시 cut 원장 규율** — 소스 링크 대조 + 병렬 체인 경합 방지(C043 reservations 정신).

## 산출물

- `rooms/deployment/ariadne-spec/gil.py` — cmd_deploy + 헬퍼 + fsck R16/R17 + deploy 서브파서.
- `rooms/deployment/ariadne-spec/conformance.py` — DEPLOY-* 5항목 + CONTRACT_COMMANDS에 deploy + write_cycle verdict.

**land는 Clew** — 이 브랜치(`selvage/loom-deploy-axis-cut`)를 `gil worktree land`로 `--no-ff` 거둔다.
실제 배포 승격(사용자 산출물의 실제 cut)은 Clew·상현님의 몫이다 — 나는 도구·conformance까지만 짓는다.
