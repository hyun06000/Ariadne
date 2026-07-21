# 1. 가설 수립

## 이전 사이클의 교훈

부모 C102-deploy-artifact-axis(#27)가 `gil deploy`를 artifact 단위 사용자 산출물 배포 축으로 완성했다:
별 명령(deploy), 별 태그(`deploy/<artifact>/<semver>`), 별 레지스터(`rooms/deployment/deployments.json`).
배포가 이제 **데이터**로 존재한다. 그러나 이슈 #18(배포 산출물이 1급 시민이 아니다)의 뷰어 절반은
비어 있다 — `gil web`이 사이클과 도구 릴리스만 비추고, 사용자 산출물 배포는 안 비춘다.
C091이 릴리스→근거사이클 링크를 세운 방식(`#cycdoc-*` 앵커)이 이 사이클의 직접 선례다.

## 문제 분할

1. deployments.json을 뷰어 데이터로 굽는 빌더(`_build_deployments_data`) — 하위호환(파일 없으면 None).
2. 배포 패널 렌더러(`_render_deployments_panel`) — 아티팩트별 계보·status·근거사이클 링크·supersedes.
3. 위계 몸체·gil-data payload에 배선 (릴리스 패널과 같은 자리, 별개 카드).
4. 폴링 POLL_SEL에 배포 카드 포함 — 열린 상태 보존(C014 hasOpenDetails 가드) 확인.
5. conformance WEB-DEPLOYMENTS 판정 항목 추가 (구조 수준). Go 이식은 무거우면 정직히 이월.

첫 정복: 릴리스 패널이 이미 검증된 템플릿이므로, 그 축을 **복제·개명**하지 않고 **별개 축**으로
세우는 게 핵심(C102 DEPLOY-NAMESPACE — 두 축 절대 안 섞임). 데이터 형상이 다르다(릴리스=버전 선형,
배포=아티팩트별 다중 계보). 그래서 렌더도 별 함수.

## 가설

> **가설**: deployments.json을 gil-data top-level `deployments` 키로 굽고 아티팩트별 배포 계보 카드를
> 릴리스 패널과 별개로 렌더하면, 뷰어가 사용자 산출물 배포를 (status·근거사이클 링크·supersedes 포함)
> 정직하게 비추면서도 배포 안 쓰는 저장소엔 한 바이트도 안 보이고(키 부재) 폴링에 열린 상태가 안 깨진다.

## 기각 조건

- deployments.json 없는 저장소의 web 출력이 개선 전과 바이트가 갈리면(하위호환 위반) 기각.
- 배포 패널이 릴리스 축과 섞이면(같은 카드/같은 데이터 키) 기각(DEPLOY-NAMESPACE 위반).
- 헤드리스 실측에서 근거사이클 링크가 `#cycdoc-*` 대상을 못 열거나, 폴링이 열린 배포 카드를 깨면 기각.
