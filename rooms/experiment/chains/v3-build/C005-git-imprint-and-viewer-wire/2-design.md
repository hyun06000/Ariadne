# 2. 실험 설계

가설(1-hypothesis): `gilv3 step`에 스텝 단위 깃 커밋을 붙이고 `gilv3 view`로 C004
steptree 로직을 배선하면, C003 재구성을 각인 켠 채 돌렸을 때 (a) 스텝=커밋 1:1·순서
일치 (b) view가 C004 산출물과 동등 (c) steps.yaml은 C002 스키마 불변.

## 확정할 설계 (검증 대상)

### 도구 — `gilv3.py` v0.2 (C003 + 깃 각인 + view)

C003의 gilv3.py를 이어 확장한다(C003 산출물을 3-verification/에 복사 후 확장 — 닫힌
사이클 불변 규율: C003 원본은 안 건드리고 C005가 자기 사본을 진화). C004의 steptree는
**import 재사용**(닫힌 사이클의 코드를 경로로 참조 — 재구현 금지, 계약 일치 보장).

### G1 — 스텝=커밋 각인

- `gilv3 open <dir> --title ... [--git]`: steps.yaml·s1.md 쓴 뒤 `--git`이면 그
  사이클 디렉토리를 `git add` + 커밋 (메시지 `gilv3 open <dir-name>: s1 define`).
- `gilv3 step <dir> --kind ... [--git]`: 노드 쓴 뒤 `--git`이면 커밋
  (메시지 `gilv3 step: <id> <kind>[/<outcome>]`).
- `gilv3 close <dir> [--git]`: 산 잎 확인 후 `--git`이면 봉인 커밋
  (메시지 `gilv3 close <dir-name>: 산 잎 <id>`).
- **깃 각인은 opt-in(`--git`)** — C003의 순수 데이터 조작 기본값을 깨지 않는다(하위호환,
  v2 gil의 `--git` 리듬과 동일 관습). 각인은 **격리된 임시 깃 저장소**에서 검증(메인
  레포 원장을 오염 안 시킴).

### G2 — 뷰어 배선 `gilv3 view`

- `gilv3 view <dir> [-o out.html]`: `<dir>/steps.yaml`을 읽어 C004
  `steptree.html_from_yaml_text(text)`로 HTML 생성. dir 이름을 cycle 라벨로 전달.
- steptree.py는 **C004 경로에서 import** (sys.path에 C004 3-verification 추가). C005가
  뷰어 로직을 재구현하지 않음 — 한 생성기, 두 호출 지점(C004 render.py·C005 view).

### 핵심 설계 결정 — 깃은 별개 층, steps.yaml은 안 건드린다 (K3 정면)

깃 커밋 해시·부모 커밋 등 **깃 메타를 steps.yaml에 절대 안 넣는다.** C002 불변식(트리는
parent/backtrack 포인터만). 깃은 "시간순 각인 층", steps.yaml은 "논리 트리 층" — 두
층이 분리된 채 대응만 한다(G3에서 확인). 스텝=커밋은 **id 순서 == 커밋 순서**로 나타나지,
데이터에 해시를 심어서가 아니다.

## 절차

1. **gilv3 v0.2 구현** (3-verification/gilv3.py): C003 gilv3.py 복사 → `--git` 각인 +
   `view` 서브명령 추가. steptree는 C004에서 import.
2. **각인 켠 재구성** (3-verification/rebuild-imprinted.sh): 임시 깃 저장소를 만들고
   (`git init`), `gilv3 open --git` + 9×`step --git` + `close --git`로 C012→C014 트리를
   짓는다. 각 명령 후 `git rev-list --count HEAD`로 커밋 수 증가를 관찰.
3. **G1 측정**: 최종 커밋 수 == 11(open 1 + step 9 + close 1). `git log --oneline`의
   순서가 s1..s10 + close와 일치. 커밋마다 정확히 스텝 하나의 파일 변경.
4. **G2 측정**: `gilv3 view <dir> -o v.html` 실행 → C004 render.py가 같은 steps.yaml로
   낸 out.html과 **동등** 판정(C004 measure.py를 v.html에 돌려 M1~M4 ALL PASS, 또는
   두 HTML 정규화 비교).
5. **G3/G4 관찰**: 커밋 로그가 선형(시간순)인데 steps.yaml의 backtrack 포인터가 논리
   되돌아감을 담음을 대조 출력. steps.yaml에 깃 메타 0 확인(K3).

## 준비물

- Python 3 stdlib + git (임시 저장소용). 의존 0(뷰어·데이터는 stdlib).
- 닫힌 사이클 코드 참조(재구현 금지): `../C003-first-commands-on-step-tree/3-verification/
  gilv3.py`(복사 기반), `../C004-v3-viewer-step-tree/3-verification/steptree.py`(import).
- C002 `case-c012-c014/steps.yaml`(view 산출물 대조 기준), C004 `measure.py`(뷰어 판정).
- 각인 검증은 **격리 임시 깃 저장소**에서 — 메인 레포 커밋 안 함.

## 측정 방법

- **M1 (스텝=커밋, K1)**: 각인 재구성 후 커밋 수 == 11, `git log` 순서 == 스텝 시간순,
  커밋당 스텝 1개. **기준: 세 조건 모두면 PASS.**
- **M2 (뷰어 배선, K2)**: `gilv3 view` 산출 HTML이 C004 measure.py M1~M4 ALL PASS,
  그리고 C004 out.html과 트리 구조 동등. **기준: ALL PASS + 동등이면 PASS.**
- **M3 (모델 무오염, K3)**: 각인 켠 뒤 steps.yaml 필드 == C002 스키마 6개, 깃 해시·커밋
  메타 0. **기준: 커서·깃 메타 필드 0이면 PASS.**

하나라도 FAIL이면 해당 K 발동, 가장 가까운 문제정의(G1/G2 또는 데이터 모델)로 되돌아감.

## 사용자 컨펌

- 생략 — 사유: 두 부모(C003·C004)가 이 배선·각인을 명시적 다음-제안으로 지목했고,
  상현님이 "가자"로 위임했다. 핵심 결정(깃은 별개 층, 각인 opt-in, steptree import
  재사용)은 C002 불변식과 닫힌 사이클 불변 규율의 직접 귀결이라 새 분기점이 아니다.
  각인이 실사례에서 예상 못한 형태(예: 커밋 원자성 문제)를 내면 그때 갈래로 보고.

- [x] 컨펌 생략 (일자: 2026-07-21) — 두 부모 위임 + "가자"
