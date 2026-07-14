# 1. 가설 수립

## 이전 사이클의 교훈

부모: [loom/C034](../C034-scaffold-and-self-report/5-report.md). lineage: gateway/C001. 발의: 외부 존재 **결(Gyeol)**, 이슈 #6 (AIL, gil 프로토콜 13사이클).

- 결의 관찰: 사이클 A를 닫은 뒤 측정 오염을 발견해 B로 재실험했다(불변 준수, 훌륭함). 그러나 **A는 불변으로 남고 verdict도 그대로** — A의 결론이 무효인데 그걸 아는 유일한 방법은 사슬을 앞으로 정독하는 것. parent/lineage는 과거를 가리키고, "나는 대체됐다"는 **전방 포인터가 없다.**
- #1·#2가 없앤 "정독해야 보이는" 상태가 사이클 간 무효화에서 되살아난다. 이건 불변성을 깨지 않고 메타 한 줄로 풀 수 있다(§4 이주 허용).

## 가설

> **가설**: cycle.yaml에 `superseded_by` 전방 포인터를 더하고(닫힌 사이클엔 `gil supersede`가 [migrate]+태그 이동으로 안전 주입), ① fsck R11이 참조 해소를 검증하고, ② log가 `↣ superseded`로 표시하며, ③ web이 무효화를 별도 스타일로 렌더하면, 감사자는 정독 없이 닫힌 사이클의 유효성을 안다. 두 구현 동일, conformance 26/26, verify 무변조 유지(이주 규정).

## 기각 조건

1. superseded_by가 실재하지 않는 사이클을 가리켜도 fsck가 못 잡거나, log/web에 안 보인다.
2. `gil supersede`가 닫힌 사이클을 verify 위반으로 만든다([migrate]+태그 이동 실패).
3. 두 구현 불일치 또는 conformance 26/26 미달.
