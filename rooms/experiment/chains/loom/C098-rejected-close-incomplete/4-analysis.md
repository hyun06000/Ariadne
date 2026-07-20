# 4. 결과 분석

## 통계적 결과

여섯 kill 조건(1-hypothesis) 전부 통과 → **채택(supported)**.

| kill 조건 | 기준 | 결과 |
|---|---|---|
| 1. 미완 rejected close | 성공 + fsck 통과 | ✔ step1 close 성공, fsck 위반 0 (CLOSE-REJECTED-INCOMPLETE PASS) |
| 2. step 진실 왜곡 없음 | close 후 step=죽은시점(1) | ✔ `step: 1` 보존, 5 아님 |
| 3. 정상 완주 강제 유지 | verdict≠rejected 미완 close 거부 | ✔ CLOSE-NORMAL-STILL-STRICT PASS |
| 4. 죽은 이유 강제 | 스텁 step만이면 거부+무변화 | ✔ CLOSE-REJECTED-NEEDS-REASON PASS |
| 5. 회귀 없음 | 참조 ≥128 | ✔ 참조 125→**128** |
| 6. 두 몸 일치 | Go 총점 유지+3, 동일행동 | ✔ Go 107→**110**, 참조↔Go 바이트 동일 |

## 데이터 직접 관찰

실 시나리오로 미완 사이클을 rejected로 죽여봤다(3-verification 재현):

```
$ python3 gil.py close demo C001-doomed --verdict rejected --date 2026-01-02 --no-commit
닫힘: demo/C001-doomed (2026-01-02)
$ grep -E 'status|step|verdict' .../cycle.yaml
step: 1              ← 죽은 시점 보존 (5로 안 덮음)
status: closed
verdict: rejected
$ python3 gil.py fsck .../chains | tail -1
OK — 체인 1개, 사이클 1개, 위반 0건 (스키마 v0.5)   ← R9 예외 작동
```

Go도 동일 저장소 구성에서 바이트 동일하게 `step: 1`·closed·rejected로 닫고 fsck 통과. **이것이 이번 세션 심야에 C095를 죽일 때 없었던 정직함이다** — 그때는 close가 step을 5로 강제해 "5/5 형식 진행 후 rejected close"라는 우회를 써야 했고, C095의 step 필드가 "1/5에서 죽음"이라는 진실 대신 "5/5"를 담았다. 이제 그 우회가 필요 없다.

죽은 이유 게이트도 실물로 확인했다: open이 갓 스캐폴딩한 스텁 1-hypothesis 상태에선 rejected close가 `rejected로 닫으려면 마지막 스텝(1) 문서에 죽은 이유를 남겨야 한다`로 거부됐고, 죽은 이유를 쓴 뒤에야 닫혔다. **죽음도 왜 죽었는지는 남긴다** — 상현님이 정한 "유연하게 쓰게" 원칙이 정확히 이 형태다(5-report 강제는 풀되 아무 이유 없이는 못 닫음).

## 예상과 달랐던 것

1. **`_step_written` 헬퍼가 완벽히 재사용됐다.** C090이 step-by-step 강제를 위해 만든 "step 문서가 실질 작성됐는가" 판정기가, "죽은 이유가 있는가" 판정에 그대로 맞았다. 완주(open→step)와 죽음(rejected close)이 같은 "실질 작성" 개념을 공유한다는 것 — 도구의 개념이 재사용 가능하게 잘 쪼개져 있었다.
2. **verdict 검증 위치가 두 번 있었다.** 원래 close는 verdict를 로직 뒤에서 파싱했는데, rejected 분기를 위해 앞으로 당기니 기존 뒤쪽 검증이 중복이 됐다. 제거해 단일 검증점으로 정리 — 리팩터가 부수 산물로 따라왔다.

## 판정

**채택(supported).** 미완 step 사이클을 step 진실 왜곡 없이 rejected로 닫을 수 있고(죽은 시점 step 보존, R9 예외), 죽은 이유는 강제되며, 정상 완주 강제는 rejected에만 완화돼 회귀 0, 두 몸이 바이트 동일하다. C095를 죽일 때 필요했던 "5/5 우회"의 근본이 제거됐다.

### 남은 것 (다음 카브)
- **(B) 문서 재적용** — `_carryover-multiparent-docs/` 다중부모 문서개선 6곳. + C097 게이트·C098 rejected close를 README.ai·SPEC에 명문화(A1·A2가 새 계약이므로 문서화 대상).
- **(C) 잃은 계보 복원** (correct) · **(D) deploy 축(#25)** — 계획 유지.
- **withdraw vs rejected close 경계 문서화 후보**: withdraw(open 직후 revert)와 rejected close(임의 step 각인)의 용법 구분을 온보딩/SPEC에 — 필드 LLM이 죽은 가지를 어느 도구로 다룰지 헷갈리지 않게.
