# 2. 실험 설계

## 스키마 v0.3 (선고정)

```yaml
verdict: rejected        # supported | partial | rejected | inconclusive (선택; closed면 권장)
deviations:              # 선고정으로부터의 이탈 (있으면 반드시; 위반 아니라 표시)
  - kill_condition: KC2
    registered: "5% 미만 개선 시 관수 프로파일 폐기"
    taken: "특징을 채택함"
    reason: "8개 비교 중 7개 일관되게 양"
```

- deviations는 cycle.yaml에 직접 쓰거나 `--deviations-file`로. **파싱은 평탄 YAML의 한계를 넘으므로**, deviations는 별도 파일 `deviations.yaml`(사이클 디렉토리)에 두고 cycle.yaml엔 `deviations: N`(개수)만 — 평탄 파서 유지 + 기계 가시성 확보. *(설계 판단: 스키마 v0.2의 평탄 key-value 계약을 깨지 않기 위해.)*

## 규칙 R10 (fsck)

- `verdict`가 있으면 값이 4집합 중 하나여야 한다 (아니면 위반).
- `deviations` 필드가 있으면 정수여야 하고, N>0이면 `deviations.yaml`이 존재하고 N개 항목이어야 한다.
- `status: closed`인데 `verdict` 없으면 **경고**(stderr, exit 0 유지 — 기존 사슬 유예). 강제 아님.

## 절차 (참조·Go 양 구현)

1. 스키마/규칙 구현: 파서에 verdict·deviations 인식, fsck R10, `gil close --verdict <v>`.
2. `gil log`: `[closed · rejected]` 표시 + 이탈 `⚠N` 마커 + 하단 집계(`supported N · rejected M · 이탈 K건`).
3. `gil web`: verdict별 노드 색(기각=경고색), JSON에 verdict·deviations 포함.
4. **T1 표시·집계**: verdict 섞인 픽스처 → log 표시·집계, web JSON·색.
5. **T2 R10**: 잘못된 verdict 값→위반, deviations 형식 오류→위반, closed+verdict없음→경고(exit 0).
6. **T3 유예**: 기존 34사이클(verdict 없음)에 fsck → 경고만, exit 0, 위반 0.
7. **T4 양 구현 대조** + **T5 conformance 26/26**.
8. **도그푸딩**: 이 사이클을 `--verdict supported`로 닫는다. maru의 online1/C003 사례를 deviations 예시로 문서화.
9. 릴리스 v1.4.0, SPEC 갱신, 이슈 #1에 답글.

## 사용자 컨펌

- [x] 컨펌 받음 (2026-07-15, 박상현: "구현가자")
