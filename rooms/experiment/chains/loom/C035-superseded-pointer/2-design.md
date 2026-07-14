# 2. 실험 설계

## 스키마 (선고정)

```yaml
superseded_by: bench/C013-clean   # 이 사이클을 무효화한 사이클 (로컬 id 또는 전역 <chain>/<id>). 없으면 null
```

## 규칙 R11 (fsck)

- superseded_by가 있으면 실재하는 사이클로 해소되어야 한다 (로컬이면 같은 체인, `/`면 전역). 자기 참조 금지.

## gil supersede

- `gil supersede <old-ref> <new-ref>`: old cycle.yaml에 `superseded_by: <new>` 주입 → `[migrate]` 커밋 → 태그가 있으면 이주 커밋으로 이동(`git tag -f`, C004 태그 이동 규약). new 실재 검증. old가 닫혀 있어도 안전(불변의 정신: 5스텝·산출물 무변, 메타 한 줄만).

## 절차 (참조·Go)

1. 파싱·R11·log(`↣ superseded: X`)·web(무효화 노드 흐리게/간선). superseded_by seed는 open이 `null`로.
2. `gil supersede` 구현 (참조·Go).
3. T1 R11(해소·자기참조·미해소), T2 supersede 후 verify 무변조, T3 log/web 표시, T4 Go 대조, T5 conformance 26/26.

## 사용자 컨펌

- [x] 컨펌 (2026-07-15, "이슈 싹 정리")
