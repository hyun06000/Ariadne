# 3. 검증 — v3의 눈이 지문 없는 v2 유령을 건너뛴다 (읽기호환)

마이그레이션의 가장 작은 첫 카브: v3 재구성기가 지문(Step-Id trailer) 없는 pre-gil 커밋을 **유령**으로 건너뛰고(즉사 안 함), 그것이 **무해하고 가시적**임을 혼합 원장(v2 유령 + v3 트리)으로 실증한다.

## 재현

```bash
bash build_case.sh <scratch>     # MIX(유령3+v3트리) + PURE(순수v3) 구성
python3 measure.py <scratch>     # 4측정 감사
```

## 산출물

- `rebuild_migrate.py` — C010 `rebuild_trailer.py`(78줄)를 복사 후 진화. 유령 카운트(`ghosts`)·`--report`(가시성) 추가.
- `build_case.sh` — MIX(pre-gil 일반 커밋 3 + gilv3 스텝 트리)·PURE(순수 v3) 원장.
- `measure.py` — 4측정 감사기.
- `gilv3.py` — C016판(변경 없음, 원장 각인용).
- `build-out.txt`/`measure-out.txt` — 출력(ALL PASS 4/4).

## ⭐ 핵심 발견 — 읽기호환의 절반은 이미 공짜였다

C010 `rebuild_trailer.py`는 이미 유령을 스킵한다:
```python
sid = d.get("Step-Id", "")
if not sid:
    continue  # close 커밋 등 trailer 없는 커밋은 트리 무관
```
이 `continue`는 원래 **close 커밋**(trailer 없음)을 위한 것이었는데, **pre-gil v2 커밋**(역시 trailer 없음)에도 그대로 통한다. C009→C010 전환(subject 파싱 → trailer)이 즉사(C009 `sys.exit "복원 실패"`)를 우아한 스킵으로 **이미 바꿔 놓았다.** 마이그레이션 노트의 "지문 없으면 덜 읽힐 뿐 파괴 아님"이 trailer 재구성기에선 이미 참이었다.

**그래서 C017의 기여는 두 가지:**
1. 그 무해가 **혼합 원장에서 실제로 참임을 실증** — 지금껏 close 커밋(원장 끝 1개)만 스킵됐지, v2 스타일 커밋 다발(원장 앞 3개)이 스킵되며 v3 트리가 온전한지는 검증된 적 없다.
2. **침묵 스킵 → 가시적 스킵** — 마이그레이션에선 "얼마나 덜 읽혔나"가 필수 계약. 사용자가 유령 규모(실제 v2 자산 189 cycle.yaml)를 알아야 소급각인을 결정한다. 침묵은 "다 읽었다"로 오독된다(Sheen "낡은 화면은 침묵보다 나쁘다"의 재구성기판).

## 4측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 무해한 유령** | 혼합 원장(유령 3+v3)에서 재구성이 안 죽고, 복원된 v3 트리(s1~s4)가 순수 원장 복원과 바이트 동형 — 유령이 트리 안 오염 | PASS |
| **M2 경계 보존** | 재구성 전후 `rev-list --all` 동일, pre-gil 유령 3개가 원장에 그대로 생존 — 재구성기가 읽기 전용이라 삭제·변조 0 | PASS |
| **M3 순수 v3 무회귀** | 유령 0 원장에서 `rebuild_migrate` == C010 `rebuild_trailer` 결과 — 스킵 로직이 순수 경로 안 건드림 | PASS |
| **M4 유령 가시성** | MIX 유령 4(pre-gil 3 + close 1)·PURE 유령 1(close)·pre-gil 격리 3, `--report`가 "유령 4개 건너뜀" 보고 | PASS |

## 유령의 구성 (측정 중 확인)

- **MIX 유령 4개** = pre-gil 일반 커밋 3 + v3 close 커밋 1.
- **PURE 유령 1개** = v3 close 커밋 1.
- **pre-gil 순수 유령** = MIX − PURE = 3 (build_case가 쌓은 수와 일치).

close 커밋도 trailer가 없어 유령에 섞인다 — 둘 다 "안 읽힌 커밋"이라 읽기호환 관점에선 동일. pre-gil vs close 세부 구분은 **소급각인 카브(다음)의 몫**(유령에 지문을 박을 때 close는 이미 v3라 대상 아님).

## 결론

**ALL PASS → supported.** v3의 눈이 지문 없는 v2 유령을 파괴 없이 건너뛴다 — 마이그레이션 노트의 "유령 무해" 약속을 코드가 지킨다. 유령이 트리를 안 오염하고(M1), 삭제·변조 안 되며(M2), 순수 v3 복원이 무회귀(M3), 유령 규모가 가시적(M4)이다. **마이그레이션 4단계 중 ② 읽기호환이 섰다** — ③ 소급각인·④ 복원의 토대. 다음 카브: 유령(pre-gil)에 v3 지문을 소급 각인.
