# 3. 검증 — v3 쓰기(open/step/close)를 배포판 gil에 통합 ("v3가 v2를 대체" 첫 조각)

C030이 v3 네이티브 도그푸딩으로 "v3는 눈이면서 손"을 실증하고 대체 걸림돌 4개를 명시했다. 이 카브는 걸림돌 ①(v3 쓰기 배포판 미통합)을 넘어 — gilv3의 open/step/close를 배포판 gil.py에 `gil v3 <cmd>`로 통합한다.

## ⭐ 상현님 방향 — 궁극은 버전리스, 전환은 안내로

- **"결국엔 v3가 표준이 될 거야. 나중엔 gil 명령어 뒤에 무슨 버전인지 몰라도 되게."** → 최종엔 `gil open`이 곧 v3. 이 사이클은 그 토대(`gil v3` 옵트인), 승격은 후속.
- **"에러 메시지랑 온보딩 문서를 잘 쓰면 해결될 문제."** → 버전리스 마찰(v2 습관 vs v3)을 도구 복잡화가 아니라 친절한 에러·온보딩으로. genesis "포인터 한 줄"·C069 "안내가 모델을 전달"의 연장.

## 명령 표면 — gil v3 서브명령 그룹 (후보 B)

v2 open/step/close와 이름·인자 충돌(v2 step=번호, v3 step=--kind)을 **네임스페이스 분리**로 해소:
```
gil v3 open <dir> --title       # 루트 define s1
gil v3 step <dir> --kind verify --outcome ... --to s1
gil v3 close <dir> --verdict
gil v3 status <dir>
```
백엔드 함수는 cmd_v3open/step/close/status(v2 cmd_open 등과 충돌 회피).

## 재현

```bash
# 오라클 대조: gilv3 vs 배포판 gil v3
python3 <C025>/gilv3.py open/step/close <dirA>
python3 <배포판>/gil.py v3 open/step/close <dirB>
diff dirA/steps.yaml dirB/steps.yaml   # 바이트 동일
python3 conformance.py --gil "python3 gil.py"   # v2 무회귀
```

## 5측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 오라클 대조** | gil v3 steps.yaml == gilv3 (digest 262d3523) | PASS |
| **M2 트리 표현** | gil v3 step으로 백트래킹(s4→s1)·죽은 잎·형제·산 잎 실제 생성 | PASS |
| **M3 v2 무회귀** | conformance 134/134 (v2 open/step/close 무손상) | PASS |
| **M4 자기완결** | gil.py 격리 복사해도 v3 동작 (import 0) | PASS |
| **M5 전환 안내** | v2 습관(kind 없이 step)에 친절한 에러가 v3 방식 안내 | PASS |

## ⭐ M5 정점 — 친절한 에러가 버전리스의 다리

`gil v3 step <dir>` (v2 습관, 번호 기대)를 치면:
```
거부: v3 스텝은 번호가 아니라 kind로 전이한다.
  v2 습관: gil step <chain> <cycle> 3   (번호)
  v3 방식: gil v3 step <dir> --kind verify
  순환: define → hypothesis → verify → analyze ...
  되돌아감: --kind analyze --outcome backtrack --to s1 (죽은 잎+백트래킹).
```
상현님 통찰의 실현 — **전환의 마찰을 도구가 아니라 안내가 흡수**한다. 사용자가 v2/v3 차이를 몰라도 에러가 가르친다. 이게 버전리스로 가는 다리다.

## ⭐ 정점 결과 — 실사이클을 배포판 gil로 v3 네이티브로 열 수 있다

이제 `gil v3 open`으로 실제 문제를 v3 스텝 트리로 굴린다 — 배포된 도구 하나로. C030이 "gilv3(실험 산출물)에만 있다"고 남긴 걸림돌 ①이 해소됐다. "v3가 v2를 대체"의 첫 실질 조각: v3 쓰기가 배포판에 섰다.

## 결론

**ALL PASS → supported.** v3 쓰기가 배포판 gil에 `gil v3 <cmd>`로 통합됐다. 오라클 대조 바이트 동일(262d3523), v2 무회귀(134/134), 자기완결, 친절한 전환 안내. 걸림돌 ① 해소 — 실사이클을 배포판 gil로 v3 네이티브로 연다.

## 정직한 경계

- **gil v3는 전환기 표면** — 궁극은 gil open=v3(버전리스). 이 사이클은 토대, 승격은 별도(v2 은퇴 계획 포함).
- **view는 이 카브 밖** — open/step/close/status만. v3 시각화는 gil web --v3(C028) 또는 후속.
- **격리 검증** — v3 사이클 생성은 스크래치. 실사이클을 gil v3로 여는 건 다음(도그푸딩).
- **친절한 에러는 씨앗** — 전면 온보딩 문서(v2→v3 대응표)는 문서 갱신 사이클로.
- **5스텝 규율(걸림돌②)·인프라(③)·공존(④)은 여전히 이월** — 이 카브는 걸림돌 ①만.
