# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 (2-design) | 결과 | 판정 |
|---|---|---|---|
| G1 스텝=커밋 (K1) | 11 커밋·순서==시간순·커밋당 스텝1 | 11/11, 순서 일치, per-step 파일 정확 | PASS |
| G2 뷰어 배선 (K2) | view == C004 render 바이트 동일 + C004 measure ALL PASS | 둘 다 True | PASS |
| M3 모델 무오염 (K3) | steps.yaml 필드 == C002 6개, 깃 메타 0 | 밖 필드 없음 | PASS |

세 kill 조건(K1·K2·K3) 미발동.

## 데이터 직접 관찰

수치 뒤로 들어가 실제 커밋 로그와 산출 HTML을 본다:

- **커밋 로그가 곧 스텝 트리의 시간축이다**: `git log --reverse`가
  `s1 define → s2 hypothesis → … → s10 analyze/success → close(봉인)` 순서를 그대로
  뱉었다. 되돌아감 스텝(s4·s7 analyze/backtrack)도 각각 커밋 하나 — **깃엔 선형
  히스토리로 남는다.** 그런데 그 커밋이 담은 steps.yaml의 s4 노드는 `backtrack=s1`을
  들고 있다. 즉 **깃은 시간순(11 커밋 일렬), steps.yaml은 논리 트리(backtrack 포인터)** —
  두 층이 한 저장소에 공존하되 안 섞인다. C002 불변식("트리는 포인터, 깃은 별개")이
  각인 층에서 실증됐다.
- **G2 바이트 동일**: `gilv3 view`가 낸 HTML을 C004 render.py 산출과 diff하니 cycle
  라벨(dir 이름)만 다르고 나머지 전 바이트 일치. 이것은 배선이 C004 steptree를 **호출**할
  뿐 재구현하지 않았다는 직접 증거 — 닫힌 사이클 C004의 코드를 import로 재사용해
  "한 생성기, 두 호출 지점(C004 render·C005 view)"을 이뤘다.
- **close 커밋의 diff가 비어 있다**: `git show`로 봉인 커밋을 보면 파일 변경 0(빈 커밋).
  close는 파일을 안 쓰고 봉인의 *의미*만 각인하기 때문. 스텝=커밋 1:1은 지켜지되, close는
  "순수 의미 스텝"으로 다른 스텝과 성격이 다름이 데이터로 드러났다.

## 예상과 달랐던 것

- **close가 각인에서 처음으로 특수했다**: 설계 땐 open/step/close를 균일하게 `--git`
  각인으로 봤으나, 실행에서 close만 파일 변경이 없어 커밋이 죽었다(nothing to commit).
  진단 후 `--allow-empty`로 봉인 커밋을 냈다. → **씨앗**: close에 verdict를 파일
  (`cycle.yaml` 상당)로 남기면 빈 커밋이 아니게 되고, 그건 v2 gil의 close가 cycle.yaml을
  갱신·태그하는 것과 같은 방향. v3 close의 봉인 표현(파일 vs 빈 커밋 vs 태그)은 후속 카브.
- **깃 각인이 데이터 모델을 전혀 안 건드렸다**: K3를 걱정했으나(깃 해시를 steps.yaml에
  넣어야 할까), 실제론 깃이 steps.yaml을 **읽지도 쓰지도 않고** 그냥 커밋만 했다. 커밋
  해시는 깃 오브젝트에만 살고 데이터엔 안 온다 — "스텝=커밋"은 해시 저장이 아니라
  **id 순서 == 커밋 순서**라는 대응으로 충분했다. 예상보다 깔끔.

## 판정

**채택 (supported).** 가설대로 `gilv3 step`에 스텝 단위 깃 커밋을 붙이고 `gilv3 view`로
C004 steptree를 배선하니, 각인 켠 재구성에서 (G1) 스텝=커밋 1:1·순서 일치, (G2) view가
C004 생성기와 바이트 동일 + measure ALL PASS, (M3) steps.yaml 무오염이 성립했다. 세
kill 조건 미발동, 산 잎(built s10 success) 도달 → 닫는다(그리디). close 봉인 표현·본문
펼침 상호작용·라이브 폴링·BFS는 정직히 이월.
