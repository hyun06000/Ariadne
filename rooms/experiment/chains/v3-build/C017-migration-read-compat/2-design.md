# 2. 설계 — trailer 기반 재구성기의 유령 스킵을 마이그레이션 계약으로

## ⭐ 설계 착수 중 발견 — 읽기호환의 절반은 이미 공짜다

C010의 `rebuild_trailer.py`를 부모로 읽다가 발견: **trailer 기반 재구성기는 이미 유령을 스킵한다.**

```python
sid = d.get("Step-Id", "")
if not sid:
    continue  # close 커밋 등 trailer 없는 커밋은 트리 무관
```

이 `continue`는 원래 close 커밋(trailer 없음)을 위한 것이었는데, **pre-gil v2 커밋(역시 trailer 없음)에도 그대로 통한다.** 즉 C009→C010의 전환(subject 파싱→trailer)이 즉사(C009 `sys.exit`)를 우아한 스킵으로 이미 바꿔 놓았다 — 마이그레이션 노트의 "지문 없으면 덜 읽힐 뿐 파괴 아님"이 **trailer 재구성기에선 이미 참**이다.

**그래서 이 사이클의 진짜 기여는 두 가지:**
1. 이 "우연한 무해"가 마이그레이션 관점에서 실제로 참임을 **혼합 원장으로 실증**(H1a·H1b·H1c) — 지금까진 close 커밋(원장 끝 1개)만 스킵됐지, v2 스타일 커밋 다발(원장 앞)이 스킵되는 건 검증된 적 없다.
2. **H1d 유령 가시성 추가** — 현재는 **침묵 스킵**이다. 마이그레이션에선 "얼마나 덜 읽혔나"가 필수 계약: 사용자가 유령 규모(예: v2 자산 189 cycle.yaml)를 알아야 소급각인을 결정한다. 침묵 스킵은 "다 읽었다"로 오독된다(C104 Sheen "낡은 화면은 침묵보다 나쁘다"의 재구성기판).

## 무엇을 만드나

C010 `rebuild_trailer.py`(78줄)를 복사해 `rebuild_migrate.py`로 진화:

### 변경 1 — 유령을 세고 구분한다 (침묵 스킵 → 가시적 스킵)
```python
def rebuild(repo, report=False):
    ghosts = []   # 지문 없는 커밋(pre-gil 유령)
    nodes = []
    for rec, commit_hash in <커밋들>:
        sid = trailer Step-Id
        if not sid:
            ghosts.append(commit_hash)   # 침묵 continue 대신 기록
            continue
        nodes.append(...)
    if report:
        return nodes, ghosts
    return nodes
```
- **왜 hash까지 세나:** close 커밋도 trailer 없어 유령에 섞인다. 마이그레이션 유령(pre-gil)과 close 유령을 구분하려면 hash로 되짚을 수 있어야 한다. 다만 이 카브에선 **총 유령 수**만 계약(둘 다 "안 읽힌 커밋"이라는 점은 같다) — pre-gil vs close 구분은 소급각인 카브(다음)의 몫.
- **가시성 출력:** `rebuild_migrate.py <repo> --report` 가 `유령(지문 없음) N개 건너뜀`을 stderr에 보고.

### 변경 2 — 경계 불변 보장 (읽기 전용)
재구성기는 **오직 `git log`만** 읽는다(C009·C010 규율). 유령을 삭제·이동·변조하지 않는다 — `continue`는 메모리에서 건너뛸 뿐 깃을 안 건드린다. 이 읽기 전용성이 H1b(경계 보존)를 구조적으로 보장.

## 측정 설계 (build_case + measure)

**혼합 원장 구성:** pre-gil 커밋(v2 스타일 — trailer 없는 일반 커밋 몇 개)을 먼저 쌓고, 그 위에 gilv3 명령으로 v3 스텝 트리를 각인.

```
[v2 유령 3개: 일반 커밋] → [gilv3 open s1 → step... → close]
```

- **M1 무해한 유령(H1a):** 혼합 원장에서 `rebuild_migrate`가 안 죽고, 복원된 v3 트리가 순수 v3 원장 복원과 동형(유령이 트리를 안 오염).
- **M2 경계 보존(H1b):** 유령 커밋이 `rev-list --all`에 그대로 생존, 재구성 전후 깃 그래프 불변(재구성기가 읽기 전용).
- **M3 순수 v3 무회귀(H1c):** 유령 0 원장(C016 caseB 재사용)에서 `rebuild_migrate` == C010 `rebuild_trailer` 결과.
- **M4 유령 가시성(H1d):** `--report`가 유령 수를 정확히 보고(pre-gil 3 + close N).

## 정직한 경계
- **읽기호환만.** 소급각인(유령에 지문 박기)·복원은 다음 카브. 이 카브는 "유령이 무해하고 가시적인가".
- pre-gil을 v2 스타일 일반 커밋으로 모사(실제 189 cycle.yaml 전량 적용은 규모 확장).
- pre-gil vs close 유령 구분은 총계만(세부 구분은 소급각인 카브). 둘 다 "안 읽힌 커밋"이라 읽기호환 관점에선 동일.
- trailer(Step-Id) 유무가 판별식 — C010 이후 진실원이 trailer라 근본적(subject 유령 판별 안 씀).
