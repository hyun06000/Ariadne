# 4. 결과 분석

## 가설은 지지되는가

지지된다. 사용자 산출물 배포 축(`gil deploy`)이 도구 릴리스(`gil release`)와 명령·태그·레지스터 세 층에서
완전히 분리된 채 세워졌고, 다섯 DEPLOY-* 판정이 모두 통과했으며 기존 회귀는 0이다(참조 128→133, Go 110→110).

## 왜 통과했는가 (설계 판단의 정당화)

- **출처를 지어내지 않음(§3.2)이 배포에서도 힘을 발휘했다.** `_resolve_source_cycle`를 재사용해 소스 사이클의
  실재+closed를 요구했고, 여기에 **rejected verdict 거부**를 더했다. 결정적 발견: rejected 사이클은 *닫혀 있다*.
  status만 보는 release의 cut 게이트를 그대로 베꼈다면 죽은 가지를 배포할 수 있었다(스모크에서 실제로 재현).
  배포는 "닫힘"이 아니라 "채택됨"을 요구하므로 verdict 게이트가 별도로 필요했다 — cut과 fsck R16 양쪽에 걸었다.
- **live 불변식을 두 곳이 함께 지킨다.** cut이 직전 live를 superseded로 *전이*시켜 정상 경로에서 live가 늘
  1개가 되게 하고(생성 시점 보증), fsck R17이 *직접 조작*으로 깨진 레지스터를 사후에 잡는다(감사 시점 보증).
  C072에서 배운 "정상 경로가 이 위반을 만들 수 있는가?"의 응용 — cut은 못 만드니 하드 불변식으로 둘 수 있다.
- **append-only가 롤백을 공짜로 만들었다.** 과거 레코드를 지우지 않고 status만 전이시키니, supersedes 링크가
  롤백 타깃을 태그 없이도 확정한다. rollback은 현 live→rolled-back, 직전→live 재활성의 전이 두 줄이면 됐다.
- **네임스페이스 분리가 조회 오염을 원천 차단했다.** `_git_release_tags`의 `refs/tags/v*` + SemVer 필터가
  `deploy/*` 태그를 자동 배제한다 — DEPLOY-NAMESPACE에서 releases가 배포 태그를 못 보는 것으로 확인.

## 카브 경계 (작게 정복 — 서약 4)

첫 카브에 넣은 것: cut·레지스터·list·current·rollback·fsck(R16·R17). rollback은 supersedes가 서면
전이 두 줄이라 무겁지 않아 첫 카브에 포함하는 게 오히려 골격을 한 몸으로 닫았다(cut→조회→롤백→무결성).

정직히 이월한 것:
1. **Go parity** — 새 명령군이라 conformance HELP-COMPLETE가 exit 3으로 부재를 판정. C043/C061 리듬.
2. **태그↔json drift 게이트** — release의 C072에 상당하는 배포판. 첫 카브는 골격 우선이라 미포함.
3. **아티팩트 스키마 강검증** — 지금은 자유 형식 문자열(artifact/params/performance). 필드 구조화·필수화는 다음.
4. **뷰어 통합** — Sheen의 web 뷰어에 배포 계보 표시.
5. **배포 verify** — 태그 메시지의 소스 링크와 json의 source_cycle 대조(release verify의 배포판).

## 한계·리스크

- deployments.json은 단일 파일이라 병렬 체인 동시 cut 시 경합 가능 — 현재 배포는 순차 가정. reservations.tsv
  같은 원장 규율(C043)을 배포에도 얹는 것은 이월 후보.
- fsck R16이 rejected를 잡지만, cut 이후 소스 사이클이 correct로 rejected가 되는 경우는 사후에만 드러난다
  (fsck가 그 역할). 이는 감사층의 정당한 몫이다.
