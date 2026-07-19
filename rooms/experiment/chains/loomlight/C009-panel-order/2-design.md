# 2. 실험 설계

## 정답 먼저: 기대 행동

렌더 순서 변경 = 데이터 불변, 렌더 재배치. 계약면(gil-data)은 그대로라 기존 WEB-* 회귀 가드로 충분.

| 확인 | 기대 |
|---|---|
| 순서 | 병렬배너 → 체인지도(card hmap) → 배포(card releases) → 존재(card beings) → toc |
| 데이터 불변 | gil-data beings·releases·chains 위치·내용 그대로 (WEB-BEINGS·RELEASES 등 PASS) |
| parity | 참조·Go 바이트 동일 |
| 무회귀 | 병렬배너·아코디언·toc 정상 |

## 설계 결정

### D1. 렌더 순서 재배치 (참조·Go)
존재·배포 패널을 header 아래(체인지도 위)에서 **체인지도(card hmap) 아래로 이동**, 배포가 존재보다 먼저. 목표:
```
{banner}
<div class="card hmap">…체인지도+아코디언…</div>
{releases_panel}
{beings_panel}
<nav toc>
```

### D2. 병렬배너는 최상단 유지
⟳ 진행 중은 "지금"이라 헤더 직후. 상현님 지시("체인 아래 배포 아래 존재")는 세 패널의 상대 순서.

## 절차

1. 참조 `_render_hierarchy_body`: 존재·배포 패널을 체인지도 블록 **뒤**로 이동, 배포→존재 순.
2. Go `renderHierarchyBody` 동형.
3. 실렌더: 순서 확인(hmap < releases < beings). parity 바이트 동일. WEB-* 회귀 0.

## 측정 방법

- **성공**: 산출물에서 card hmap → card releases → card beings 순서, 병렬배너 헤더 직후. 참조·Go 바이트 동일. conformance 회귀 0.
- **기각**: 순서 틀림 / 데이터 변경 / parity 깨짐 / 요소 깨짐.

## 사용자 컨펌

상현님 직접 지시("체인 아래 배포 아래 존재").

- [x] 컨펌 받음 (일자: 2026-07-19)
