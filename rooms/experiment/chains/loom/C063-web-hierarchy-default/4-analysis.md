# 4. 결과 분석

## 통계적 결과

| 측정 | 기준값 | 실측 | 판정 |
|---|---|---|---|
| 참조 conformance | 전 판정기 PASS | **90/90** | ✅ |
| Go conformance | 전 판정기 PASS | **83/83** | ✅ |
| 바이트 parity(기본·위계) | byte-identical | 동일(sha 22a1be56…) | ✅ |
| 바이트 parity(`--flat`·평면) | byte-identical | 동일(sha fa63d31a…) | ✅ |
| `--hierarchy` 별칭 | == 기본 | 동일 | ✅ |
| 변이 격추(변경 전=평면) | 새 판정기 FAIL | 82/83, WEB-HIERARCHY-DEFAULT FAIL | ✅ |

기존 WEB 계약(SELFCONTAINED·JSON·REFRESH·AUTO-REFRESH·AUTO-PURE-COMMIT·AUTO-NONE·BAKE-META) 회귀 0.

## 데이터 직접 관찰

수치 뒤로 들어가 산출물을 직접 봤다:
- 무옵션 `gil web`의 `gil-data` bake에 `"hierarchy": true`가 실제로 실렸고, 몸체에 `class="hchain"`·`class="htoc"` 위계 구조가 13개 나타났다. `--flat`은 bake에 hierarchy 키가 아예 없고(무예약·무리프레시처럼 "있을 때만" 규약), hchain 0개.
- 변이 로그의 신호가 이중이다: 변경 전 바이너리는 `--flat`을 모르므로 rc=2, 동시에 기본이 평면이라 default_hier=False — **두 경로 모두** 판정기를 FAIL로 민다. 판정기는 "기본이 위계"와 "`--flat`이 존재"를 함께 요구한다.
- 푸터 자기서술이 호출과 일치: 위계본은 "gil web이 생성한", 평면본은 "gil web --flat이 생성한". 문서가 자기를 어떻게 다시 굽는지 거짓말하지 않는다(C042 정신).

## 예상과 달랐던 것

- conformance가 **무수정으로도** 새 기본값을 통과했다 — WEB 판정기가 렌더 형식이 아니라 `gil-data` JSON·자기완결성만 보기 때문(SPEC §102 "렌더는 계약이 아니다"의 실증). 그래서 판정기 추가는 계약을 **넓히려는** 게 아니라, 뒤집힌 기본값을 **명시적으로 잠그기** 위한 것이었다.
- `--flat`을 모르는 변경 전 바이너리가 rc=2를 내며, 판정기가 default_hier 뿐 아니라 이 rc로도 격추된다 — 방어가 이중이라 우연한 통과가 어렵다.

## 판정

**가설 채택.** 기각 조건 셋 모두 미발동: 바이트 불일치 없음, 기존 판정기 회귀 0, 새 판정기가 변이를 격추(비공허). 기본값 뒤집기는 양 구현 대칭·계약 잠금과 함께 완료됐다.
