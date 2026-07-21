# 3. 검증 — v3 데이터 모델 왕복

설계(2-design)의 스키마·디스크 표현을 실사례로 검증한 산출물.

## 파일

- `schema.md` — 확정된 STEP 노드 스키마 + kind 상태기계 + 디스크 표현 명세.
- `case-c012-c014/steps.yaml` — 실사례 loomlight C012→C013→C014를 **하나의 스텝
  트리**로 재표현. 봉인된 세 5-report가 근거.
- `case-c012-c014/steps/s1..s10.md` — 10개 노드 본문.
- `roundtrip.py` — stdlib 자작 파서로 로드→스키마검증→트리복원→재직렬화→비교→명령파생.

## 재현 방법

```bash
cd 3-verification
python3 roundtrip.py case-c012-c014/steps.yaml
```

환경: Python 3 (stdlib만, 의존 0). macOS Darwin. 2026-07-21 실행, 전부 PASS.

## 결과 (전부 PASS)

| 측정 | 기준 | 결과 |
|---|---|---|
| 스키마 불변식 | 위반 0 | ✅ |
| 본문 존재 | 10/10 | ✅ |
| **M1** 왜곡 0 | 백트래킹·죽은 잎·산 잎 보존 | ✅ backtrack=[(s4→s1),(s7→s1)], 죽은잎=[s4,s7], 산잎=[s10] |
| **M2** 왕복 무손실 | 재직렬화 정규형 일치·노드수 보존 | ✅ 10→10, 일치 |
| **M3** 명령 파생 | 트리만으로 다음 행동 유일 결정 | ✅ 스키마 밖 관습 0 |

## 실측 트리 위상

```
s1 [define]                        ← P0: 카드 닫힘 (뿌리·되돌아갈 갈림길)
  s2 [hypothesis] (C012)
    s3 [verify]
      s4 [analyze/backtrack→s1]    ← 죽은 잎: 상호작용·아코디언·detKey 배제
  s5 [hypothesis] (C013)
    s6 [verify]
      s7 [analyze/backtrack→s1]    ← 죽은 잎: 폴링 이분 = 실브라우저 계측기 필요
  s8 [hypothesis] (C014)
    s9 [verify]
      s10 [analyze/success]        ← 산 잎: 노드 정체성 보존 (채택)
```

## 실행 기록

**v2의 죄가 사라졌다**: s10(C014)의 `parent`는 자기 가지의 s9다 — v2처럼 s7(C013)을
선형 계승하지 않는다. 세 가지가 s1의 형제이며, s4·s7의 `backtrack→s1`이 "되돌아가
난 형제"라는 진실을 명시적 데이터로 담는다. 세 kill 조건(K1·K2·K3) 모두 미발동.
