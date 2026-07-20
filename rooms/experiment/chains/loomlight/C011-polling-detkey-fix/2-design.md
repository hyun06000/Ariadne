# 2. 실험 설계

가설: `detKey`가 id 가진 details를 idx=-1로 뭉개는 것이 카드 닫힘의 원인. id 가진 details는 id 자체를 키로 쓰게 고치면 데이터 변경 폴링에서도 열림이 보존된다.

## 수정 (참조 gil.py + Go main.go, 바이트 동일)

`detKey`를 다음으로 교체 — **id를 가진 details는 그 id가 곧 안정 키**(순번 불요), id 없는 details만 조상 id + 순번:

```js
function detKey(d){
  if(d.id) return "#"+d.id;                         // id 가진 details는 id 자체가 안정 키 (체인 카드·마운트)
  var anc=d.parentNode, id=null;                     // d 자신은 제외하고 '조상'에서 id를 찾는다
  while(anc){ if(anc.id){ id=anc.id; break; } anc=anc.parentNode; }
  var scope=id?document.getElementById(id):document;
  var all=scope.getElementsByTagName("details"), idx=-1;
  for(var i=0;i<all.length;i++){ if(all[i]===d){ idx=i; break; } }
  return (id||"~root")+"@"+idx;                       // id 없는 자손(.hstep 등)만 순번으로
}
```

**두 수정 포인트**:
1. `if(d.id) return "#"+d.id;` — id 가진 details는 자기 id를 키로. 순번 계산 안 함(-1 버그 원천 차단).
2. id 탐색을 `d.parentNode`부터 시작 — id 없는 details의 '가장 가까운 id **조상**'을 찾는다(자기 자신 제외). scope도 그 조상이므로 `getElementsByTagName`에 d가 포함돼 idx가 올바르다.

키 접두 `#`(id 기반) vs `@`(조상+순번)로 두 종류를 구분해 우연한 충돌도 방지.

## 절차

1. **참조 gil.py `detKey` 교체** (위 코드). `_WEB_APP_JS` 안.
2. **Go main.go 이식** — `webAppJS`의 detKey를 바이트 동일하게. (C010 계약: 폴링 JS 참조↔Go 바이트 동일.)
3. **재현 스크립트로 검증** — 데이터 변경 폴링(v1→v2 스왑)에서 `POST_chainOpen: true`, `POST_cycbodyFilled: true` 확인.
4. **회귀 검증** — C010 steps-2(무변경 폴링 상태보존) 재실행, 참조·Go conformance.
5. **detKey 참조↔Go 바이트 동일** cmp 확인.
6. **conformance 항목 보강 검토**: C010의 WEB-REFRESH가 구조(meta 부재·폴링 마운트)만 판정한다. detKey 정확성은 렌더/런타임이라 conformance가 못 본다(§3.1) → 헤드리스 실측으로. conformance 신규 항목은 불필요(구조 계약 이미 있음), 총점 유지 확인만.

## 준비물

- gil v2.47.0(main). `python3 rooms/deployment/ariadne-spec/gil.py`. 저장소 루트 실행.
- Go 세션-로컬 격리 빌드(`/tmp/gil-go-c011`).
- 헤드리스 검증: C010의 `cdp.py` 재사용 + **새 재현 스텝**(데이터 변경 시나리오 — C010 검증 공백을 메움). Chrome `/Applications/Google Chrome.app`.
- 재현 데이터: v1(loom만)·v2(전체 체인) 뷰어 — 폴링 중 파일 교체로 그래프 구조 변화 모사.

## 측정 방법

| # | 측정 | 기준 (kill 대응) |
|---|---|---|
| M1 | 데이터 변경 폴링에서 체인 카드 | `POST_chainOpen: true` (kill 1) |
| M2 | 데이터 변경 폴링에서 cycbody·스텝 | `POST_cycbodyFilled: true`, 스텝 열림 유지 (kill 1·2) |
| M3 | detKey 진단 | id 가진 details 키가 `#chain-loom` 안정(스왑 전후 동일) (kill 1) |
| M4 | 무변경 폴링 회귀 | C010 steps-2 여전히 통과 (kill 3) |
| M5 | conformance | 참조 128·Go 110 유지 (kill 4) |
| M6 | detKey 참조↔Go | cmp 바이트 동일 (kill 5) |

## 사용자 컨펌

- 생략 — 상현님이 "왜 그런거지?"로 원인 규명을 요청했고, 재현·진단으로 근본 원인(detKey -1 버그)을 특정했다. 수정은 그 버그의 직접 교정이라 추가 컨펌 불요(전권 위임). 이 사이클은 상현님 필드 보고에 대한 직접 응답.

- [x] 컨펌 받음 (일자: 2026-07-20, 필드 결함 보고 + 전권 위임으로 갈음)
