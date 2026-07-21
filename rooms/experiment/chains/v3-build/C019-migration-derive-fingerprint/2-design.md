# 2. 설계 — v2 메타 → v3 지문 도출기

## 설계 원칙

- **v2에 없던 구조를 만들지 않는다.** 가설의 "1/5 가설 → define + hypothesis 두 노드로 쪼갬"은 v2에 없던 노드를 발명하는 것 — 폐기. v2 5스텝은 v3 5노드로 **1:1 매핑**해 구조를 보존한다.
- **순수 함수.** 도출기는 v2 커밋 리스트(+cycle.yaml parent)를 받아 v3 지문 시퀀스를 낸다 — 부작용 0(각인은 C018 retro_imprint가 별도로). 결정성(H1a) 보장.
- **근사 정직.** v2 5스텝 이름과 v3 kind 집합이 다르므로(v2=5, v3 kind=4) 매핑은 무손실이 아니다 — 근사임을 도출기가 명시(주석·출력).

## v2 커밋 → v3 지문 도출 규칙 (확정)

### 파싱 (H1b)
실제 원장 subject 3종:
```
gil: open  <chain>/<cycle> — 1/5 가설      → 사이클 시작 (스텝 커밋은 아래 step이 담당)
gil: step  <chain>/<cycle> → N/5 <스텝명>   → v3 노드 sN
gil: close <chain>/<cycle>                  → 봉인 (트리 무관, 스킵)
```
정규식으로 open/step/close 분류, step에서 N(1..5)·스텝명 추출.

### v2 5스텝 → v3 노드 1:1 (구조 보존)
| v2 step | v3 Step-Id | v3 Kind | Parent |
|---|---|---|---|
| 1/5 가설 | s1 | **define** | null (트리 루트) |
| 2/5 설계 | s2 | hypothesis | s1 |
| 3/5 검증 | s3 | verify | s2 |
| 4/5 분석 | s4 | analyze | s3 |
| 5/5 보고 | s5 | analyze | s4 (outcome=success) |

**근거:**
- **1/5 가설 = define**: v2의 첫 스텝은 문제를 세우는 자리 → v3 트리 루트 define. (v2 "가설"이라는 이름이지만 위상은 루트다.)
- **선형 parent**: v2는 백트래킹이 데이터로 없어 전부 선형 → parent = 시간순 직전(s(N-1)). v3 순환 계승과 동형.
- **5/5 보고 = analyze/success**: v2 마지막 스텝(보고)은 사이클이 닫히는 자리 → v3 산 잎(analyze/success). verdict(cycle.yaml)가 supported면 success, refuted면… v2 verdict를 outcome에 반영(근사).
- **2/5 설계·4/5 분석**: v3에 정확한 kind 없음 — 설계→hypothesis(가설 정련), 분석→analyze로 근사. 이 근사가 무손실 아님을 명시(H1d).

**정직성:** 이 매핑은 v2 5스텝을 v3 5노드로 보존하되 kind는 근사다. v2 원장의 위상(선형 5노드)은 완전 보존되고, 잃는 것은 "설계"라는 v2 고유 스텝명이 v3 kind에 정확히 안 담기는 것뿐 — 그것은 커밋 subject에 원문으로 남아 손실 아님(notes는 지문만, subject는 v2 원문 보존).

## 도출기 인터페이스 `derive_fingerprint.py`

```python
def derive_cycle(commits):
    """v2 사이클 커밋 리스트 → v3 지문 시퀀스 [(hash, [(k,v)...]), ...].
    commits: [(hash, subject), ...] 시간순. 순수 함수(결정성).
    open/close는 스킵, step N/5만 sN 노드로. 근사 매핑(V2_STEP_TO_KIND)."""

V2_STEP_TO_KIND = {1:"define", 2:"hypothesis", 3:"verify", 4:"analyze", 5:"analyze"}
V2_STEP_PARENT  = {1:None, 2:"s1", 3:"s2", 4:"s3", 5:"s4"}
# 5/5는 outcome=success (산 잎) — verdict 반영은 호출자가 cycle.yaml에서.
```

## 측정 설계 (build_case + measure)

**실제 v2 원장의 한 닫힌 사이클**(이 체인의 예: C015)을 표적으로 — 실데이터.
- **M1 결정성(H1a):** 같은 커밋 2회 도출 → 동일 지문.
- **M2 파싱 정확(H1b):** 실제 C015 커밋 subject에서 open/step/close 분류·N/5 추출이 정확(step 5개·open 1·close 1).
- **M3 C018 통합(H1c):** 도출 지문을 격리 저장소에 재현(v2 스타일 커밋 만들고) → retro_imprint → rebuild가 s1~s5를 노드로.
- **M4 근사 명시(H1d):** V2_STEP_TO_KIND 테이블이 문서화, 도출기가 근사임을 출력에 표기.

## 정직한 경계
- 한 사이클 도출 규칙만(189 전량은 다음 카브).
- v2 5스텝 → v3 kind 근사(무손실 아님, 위상은 보존).
- 선형만(v2에 백트래킹 데이터 없음).
- 위상 접합(사이클 간 v3 체인 DAG)은 ④ 복원.
- 실제 원장 커밋은 **읽기만**(소급각인 실측은 격리 저장소에서 — 우리 원장을 이 카브에서 안 건드림).
