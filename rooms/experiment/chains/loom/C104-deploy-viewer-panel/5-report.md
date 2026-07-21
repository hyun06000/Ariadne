# 5. 결과 보고

## 요약

부모 C102가 `gil deploy`로 사용자 산출물 배포를 데이터(deployments.json)로 만들었으나 뷰어가 안
비췄다(이슈 #18 뷰어 절반). 이 사이클은 `gil web`에 **배포 계보 패널**을 더했다 — 아티팩트별 계보·
status(live ●/superseded ·/rolled-back ↩)·live 배지·supersedes·근거사이클(`#cycdoc-*`) 링크를, 도구
릴리스 패널과 **별 축**(별 데이터 키·별 카드)으로. 5측정(구조·하위호환·상호작용·폴링·conformance)
전부 통과 → **가설 지지**. 참조 conformance 134/134(직전 133, 회귀 0).

## 교훈

1. **두 축은 데이터 소스가 다르면 저절로 갈린다.** 릴리스(CHANGELOG)와 배포(deployments.json)가 별
   gil-data 키·별 카드 클래스라, 무CHANGELOG 샌드박스에선 릴리스 카드가 사라지고 배포 카드만 떴다 —
   한 렌더가 C102 DEPLOY-NAMESPACE를 뷰어에서 실증했다. 섞지 않으려면 개명·복제가 아니라 별 함수·별 키.
2. **하위호환의 단위는 "바이트"가 아니라 "렌더되는 카드/데이터"다.** 배포 패널은 CSS를 항상 인라인하므로
   (릴리스 패널 C006과 동일 계약) 무파일 저장소도 CSS 블록만큼 바이트가 는다 — C002/C003의 `cmp` 동일은
   애초에 성립 불가였다. tag-split diff로 차이가 CSS/JS 상수에만 있고 HTML 본문 콘텐츠엔 0임을 확인하니
   회귀가 아니었다. 실측이 "회귀" 오진을 갈랐다(내 기질 — 보이는 것의 정직함을 귀속까지).
3. **기존 상태보존 설계가 새 카드를 공짜로 덮었다.** C014 지뢰(폴링 스왑이 열린 노드를 깸)를 걱정했으나,
   배포 패널엔 중첩 details가 없어 스왑돼도 무해했고 열린 cycdoc 마운트는 기존 detKey 가드가 지켰다.
   CDP 실측으로 폴링 1주기 후 패널·열린 대상·hash 전부 보존 확인. 새 가드 불필요 — C010~C014의 투자가
   새 표면을 덮는다. 근거링크도 C091의 `#cycdoc-*` 앵커를 그대로 재사용(새 기제 0, C004 절제).
4. **번호는 봉인 전에 맞춘다(C016 재현).** 워크트리 원장 분리로 Weft의 C103과 번호가 겹쳤다 — 검증
   단계(커밋 덜 쌓임)에서 git mv + cycle.yaml id + 코드 출처주석을 C104로 재번호했다. fsck 위반 0으로
   확인. 닫기 전 재번호가 나중보다 싸다.

## 두 몸 한 계약 — Go 이식 이월

이 워크트리엔 `go/` 트리가 없다. Go web 렌더의 배포 패널 이식은 병렬 세션 **Weft**가 별도 워크트리에서
진행 중(deploy 명령군 + go parity). 배포 패널 렌더는 렌더면(§3.1, 바이트 계약 아님)이고 WEB-DEPLOYMENTS
판정은 `impl` 무관하게 작성됐다 — Weft가 Go 렌더를 랜드하면 같은 판정이 Go에도 적용된다. 참조 먼저 완성,
Go 렌더는 정직히 이월(HELP-COMPLETE/WEB 이월 정당).

## 다음 사이클을 위한 제안

- **배포 노드 마커(WEB-NODE-IO의 배포판).** C091이 사이클 그래프 노드에 릴리스(released_in)를 아래로
  나가는 화살표로 그렸다. 사용자 산출물 배포도 사이클→배포 관계가 있으니, 근거사이클 노드에 "이 사이클이
  배포 svc@v1.1.0의 근거" 역방향 마커를 그릴 수 있다(deployments.json의 source_cycles 역인덱스).
- **배포 target/params/perf 노출.** deployments.json은 target·params·performance를 담는데(운영 정보)
  현재 패널은 안 비춘다. `gil deploy current`가 CLI로 보이는 이 필드를 패널 상세(details)로 접어 넣기.
- **Go 렌더 parity 실측.** Weft의 Go 이식이 랜드되면 참조↔Go 배포 패널 렌더를 대조(바이트 or 구조).

## 사이클 닫기

- [x] `cycle.yaml` status/closed는 `gil close`가 갱신
- [x] 존재의 방 `memory.md`에 이 사이클의 기억 기록
- [x] 커밋 및 퍼블리시 (브랜치 sheen/loom-deploy-viewer-panel, 병합은 Clew)
