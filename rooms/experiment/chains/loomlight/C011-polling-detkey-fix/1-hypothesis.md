# 1. 가설 수립

## 이전 사이클의 교훈

부모 loomlight/C010(refresh 상태보존, Sheen, supported). C010이 meta refresh(전체 리로드)를 자기완결 JS 라이브 폴링으로 대체해 "열린 카드가 5초마다 닫히는" 필드 결함을 고쳤다 — 그리고 헤드리스 CDP로 상태보존을 실측 증명했다. **그런데 상현님이 필드에서 결함이 여전히 남아있다고 보고했다("자꾸 열었던 카드가 닫힌다").**

## 문제 분할 — 결함 재현 및 근본 원인 특정 (이미 실측 완료)

상현님 보고를 받고 실제 뷰어를 구워 CDP로 재현·진단했다:

**재현 (데이터가 실제 바뀌는 폴링)**: 기본 hierarchy 뷰어에서 체인 카드(`details.hchain`)를 열고 → 사이클 노드 클릭해 `.cycbody` 열고 → **데이터가 바뀐 새 문서로 폴링**(v1=loom만 → v2=전체 체인, 그래프 구조 변화)하니:
- `PRE_chainOpen: true` → `POST_chainOpen: **false**` (카드 닫힘)
- `PRE_cycbodyFilled: true` → `POST_cycbodyFilled: **false**` (열어둔 상세 사라짐)

**근본 원인 = `detKey` 버그 (gil.py:1636)**:
```js
function detKey(d){
  var anc=d, id=null;
  while(anc){ if(anc.id){ id=anc.id; break; } anc=anc.parentNode; }  // d 자신이 id를 가지면 id=자기 id
  var scope=id?document.getElementById(id):document;                  // scope = d 자신
  var all=scope.getElementsByTagName("details"), idx=-1;              // scope의 '자손' details만 — 자기 자신은 없음
  for(var i=0;i<all.length;i++){ if(all[i]===d){ idx=i; break; } }    // d를 못 찾음 → idx = -1
  return (id||"~root")+"#"+idx;                                        // "chain-loom#-1"
}
```
**id를 가진 `<details>`(체인 카드 `id="chain-loom"`·사이클 마운트 `#cycdoc-*`)는 자기 자신이 scope가 되어 `idx`가 항상 -1**이 된다. 그래서 키가 `<own-id>#-1`로 뭉개진다. 진단 실측: `keyBEFORE: chain-loom#-1`, 데이터 스왑 후 `keyAFTER: chain-gateway#-1` — 스왑으로 첫 details가 바뀌자 키가 어긋나 `restoreOpen`이 열림을 못 되살린다.

**왜 C010 테스트가 못 잡았나**: Sheen의 steps-2는 **데이터가 안 바뀌는** 폴링(동일 문서 재fetch)을 테스트했다. 그 경우 스왑 전후 DOM이 동일해 `idx=-1`이어도 `getElementsByTagName` 순서가 같아 우연히 복원됐다. steps-3의 sentinel도 그래프 구조(details 순번)를 안 바꿨다. **데이터 변경이 그래프를 바꾸는 실제 시나리오가 검증 공백**이었다.

## 가설

> **가설**: `detKey`가 id를 가진 `<details>` 자신을 순번 대상에서 제외해 `idx=-1`로 뭉개는 것이, 데이터 변경 폴링에서 열린 카드가 닫히는 근본 원인이다. `detKey`를 **id를 가진 details는 그 id 자체를 안정 키로 쓰고(순번 불요), id 없는 details만 '가장 가까운 id 조상 + 그 조상 subtree 내 순번'으로 식별**하도록 고치면 — 데이터가 바뀌어 그래프 구조가 변해도 열린 카드·상세·스텝이 폴링을 가로질러 보존될 것이다.

## 기각 조건

1. **데이터 변경 폴링에서 카드가 닫히면 기각**: 수정 후에도 재현 시나리오(v1→v2 스왑)에서 `POST_chainOpen`이 false면 기각.
2. **id 없는 details 보존이 깨지면 기각**: `.hstep`(JS 구축, id 없음)의 열림이 데이터 무변경/변경 폴링에서 유지 안 되면 기각.
3. **C010이 통과시킨 케이스가 회귀하면 기각**: 데이터 무변경 폴링 상태보존(C010 steps-2)이 깨지면 기각.
4. **회귀가 나면 기각**: 참조 conformance 128 미만, Go 110 미만이면 기각.
5. **두 몸 불일치면 기각**: detKey는 참조·Go 폴링 JS에 바이트 동일하게 있어야(C010 계약). 한쪽만 고치면 기각.

## 범위 밖

- **C010의 폴링 아키텍처 자체**는 옳다(근원 제거 방향). 이건 그 안의 키 함수 버그만 고친다.
- Sheen 이월(CSS drift line36·mdtoggle 소실)은 별개.
