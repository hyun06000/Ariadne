# 2. 실험 설계

## 접근법 선택 (판단 근거)

세 후보 중 **① meta refresh 제거 + 자기완결 JS 폴링(fetch → 부분 갱신)**을 채택.
(② sessionStorage 저장·복원, ③ 그 외는 기각.)

**①을 택한 이유**: 결함의 근원은 "전체 문서 리로드가 DOM을 새로 쓴다"이다(1-hypothesis의
재현 실측: 리로드 후 프로브 details가 소멸). ②는 리로드를 그대로 두고 상태를 사후 복원하는
봉합이라 — (a) 매 5초 화면이 깜빡이고, (b) 복원 타이밍 경합에 취약하며, (c) JS로 온-디맨드
구축되는 사이클 body(`.cycbody`)는 리로드 시 빈 마운트로 돌아가 복원 대상조차 사라진다.
①은 **리로드 자체를 없애** DOM을 유지한 채 데이터만 갈아끼우므로 깜빡임 0·상태 소멸 0.
C049가 meta refresh를 고른 건 "그때는 JS 0줄이 계약"이라서였는데, C075/C088에서 이미
자기완결 JS가 표준이 됐으니 그 전제가 사라졌다.

## 절차 (구현)

`_WEB_APP_JS`(참조)와 `webAppJS`(Go)에 폴링 루프를 추가한다. `bake.refresh`(초)가 >0이면:

1. `setInterval(poll, refresh*1000)`.
2. `poll()`: `fetch(location.href,{cache:'no-store'})` → 텍스트 → `DOMParser`로 detached 문서
   파싱(스크립트 실행 안 됨 = 안전).
3. **데이터 갱신**: 새 문서의 `#gil-data` textContent를 현재 `#gil-data`에 복사, `data` 재파싱.
4. **구조 영역 in-place 교체 + details.open 보존**: 서버 렌더 동적 컨테이너(`.mapchains`,
   헤더 통계 `<p>`, 배너, 지도, releases/beings 패널, toc)를 새 문서 동형 노드로 교체하되,
   교체 직전 열린 `<details>`의 안정 id(`chain-*` 등)를 수집하고 교체 후 다시 open.
5. **JS 구축 body 재적용**: 교체된 `#cycdoc-*`·`#being-*` 마운트 중 `done{}`에 있던(열린) 것을
   새 `data`로 다시 build. 안의 `.hstep` 열림·`rendered` 토글은 build 전 저장→후 복원.
6. **스크롤 보존**: poll 전 `scrollY` 저장 → 교체 후 복원.

**절제**: body innerHTML 통스왑은 안 한다(JS 마운트를 빈 상태로 되돌려 C075 온-디맨드 구축을
깸). "구조 영역 교체 + 상태 재적용"으로 파괴를 국소화. 정확성은 실측이 판정(§3.1).

## 준비물

- gil.py(참조) / go/main.go(Go), Python3, Go(/opt/homebrew/bin/go, 세션-로컬 빌드).
- 헤드리스 Chrome(`/Applications/Google Chrome.app/...`) + stdlib CDP 드라이버(`cdp.py`).
- `python3 -m http.server`로 same-origin 서빙(폴링 fetch는 same-origin 필요).

## 측정 방법

1. **처치군**: 폴링 뷰어를 서빙, details 열고 프로브 심기 → 원장 변경(사이클 추가) 재굽기 →
   폴링 주기 통과 대기 → (a) 프로브 details 여전히 open·존재, (b) 데이터 갱신(새 사이클 보임),
   (c) 스크롤 유지, (d) 렌더 토글 유지. **성공 = a·c·d 유지 AND b 갱신.**
2. **자기완결**: 산출물 외부 URL 0(grep), meta refresh 부재.
3. **회귀 0**: 참조 conformance(128→유지), Go conformance(110→유지), 참조↔Go 기본 parity(cmp).

## 사용자 컨펌

생략 — 소환자 Clew가 임무에서 "설계 단계에서 접근법이 갈리면 네가 판단해 진행하되 근거를
5-report에 남겨라"라고 위임했다. 접근법 ①의 근거를 위에 남긴다.

- [x] 컨펌 받음 (위임: Clew, 일자: 2026-07-20)
