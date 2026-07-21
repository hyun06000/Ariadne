# 3. 검증 — v2 메타 → v3 지문 자동 도출 (소급각인 실전화)

C018 소급각인은 지문 값을 손으로 줬다. 이 카브는 v2 커밋 subject(이미 규칙적인 메타)를 파싱해 v3 지문을 **손 없이** 도출하는 순수 함수를 세운다 — 그러면 189 전량 소급이 스크립트 한 번(derive → retro_imprint). 실제 v2 원장의 C015 사이클을 표적으로 실증(읽기만).

## 재현

```bash
# 실제 원장의 한 사이클에서 v3 지문 도출
python3 derive_fingerprint.py <repo> v3-build/C015-merge-is-lineage-command supported
python3 measure.py                # 4측정 (실제 원장 읽기 + 격리 통합)
```

## 산출물

- `derive_fingerprint.py` — v2 커밋 리스트 → v3 지문 시퀀스(순수 함수). open/step/close 파서 + V2_STEP_TO_KIND 매핑.
- `rebuild_migrate.py`·`retro_imprint.py` — C018판(재사용, 도출→각인→복원 왕복).
- `measure.py`·`measure-out.txt` — 4측정(ALL PASS).
- `derive-out.txt` — 실제 C015 사이클 도출 결과.

## v2 → v3 매핑 규칙 (확정)

실제 원장 subject 3종:
```
gil: open  <chain>/<cycle> — 1/5 가설      → 사이클 시작 (스킵, 노드 아님)
gil: step  <chain>/<cycle> → N/5 <스텝명>   → v3 노드 sN
gil: close <chain>/<cycle>                  → 봉인 (스킵)
```

v2 5스텝 → v3 노드 **1:1**(위상 보존):
| v2 step | Step-Id | Kind | Parent | 근사? |
|---|---|---|---|---|
| 1/5 가설 | s1 | define | null | |
| 2/5 설계 | s2 | hypothesis | s1 | ✓ |
| 3/5 검증 | s3 | verify | s2 | |
| 4/5 분석 | s4 | analyze | s3 | ✓ |
| 5/5 보고 | s5 | analyze (outcome=success) | s4 | ✓ |

## ⭐ 핵심 — v2에 없던 구조를 만들지 않는다 (위상 보존적 근사)

가설 초안은 "1/5 가설 → define + hypothesis 두 노드"로 쪼개려 했으나 폐기 — v2에 없던 노드를 발명하는 것. **v2 5스텝을 v3 5노드로 1:1 매핑**해 위상(선형 5노드)을 완전 보존한다. 잃는 것은 kind뿐이다: v2 5스텝 이름과 v3 4kind가 1:1이 아니라(v2 "설계"·"분석"·"보고"가 v3 kind에 정확히 안 담김), 그 3개를 **근사**로 표기한다(무손실 주장 안 함). **그 손실조차 실은 손실이 아니다** — v2 스텝명 원문은 커밋 subject에 그대로 남는다(notes는 지문만 첨부, subject 불변). 지문은 근사, 원문은 보존.

## 4측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 결정성** | 같은 커밋 2회 도출 → 동일 지문 5노드. 순수 함수 | PASS |
| **M2 파싱 정확** | 실제 C015 원장: open 1·step 5·close 1 분류 정확, step 번호 1..5 추출 | PASS |
| **M3 C018 통합** | 도출 지문 → retro_imprint → rebuild가 s1~s5를 노드로 편입(C018 왕복 재사용) | PASS |
| **M4 근사 명시** | V2_STEP_TO_KIND 테이블 문서화, 근사 스텝 3개(2·4·5) 표기 — 무손실 주장 안 함 | PASS |

## 실제 원장 도출 결과 (derive-out.txt)

C015 사이클(실데이터)에서 손 없이 도출된 v3 지문 — 각 해시가 실제 원장 커밋:
```
s1 define  parent=null
s2 hypothesis parent=s1  [근사]
s3 verify  parent=s2
s4 analyze parent=s3     [근사]
s5 analyze parent=s4 outcome=success  [근사]
```

## 결론

**ALL PASS → supported.** v2 커밋 메타에서 v3 지문이 손 없이 도출되고(결정성·파싱 정확), C018 소급각인에 그대로 먹여 유령이 노드로 편입되며(왕복 재사용), v2 5스텝→v3 kind 근사가 정직히 명시된다. **소급각인이 수동 실증에서 실전 도출로 넘어갔다** — 189 전량 소급의 도출 규칙이 섰다. 남은 건 189 전량 순회 배선(규모 확장)과 위상 접합(④ 복원).
