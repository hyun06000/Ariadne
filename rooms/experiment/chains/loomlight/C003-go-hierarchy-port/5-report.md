# 5. 결과 보고

## 요약

부모 loomlight/C002가 "Go 툴체인 없어 실측 불가"라며 정직히 이월했던 Go 위계 이식을 되찾았다.
참조 gil.py의 위계 렌더 경로(`_render_hierarchy_body`·`_render_cycle_detail`·`_read_step`·
`_WEB_HIER_CSS`·`_verdict_tally`·`_chain_recent`)를 Go `main.go`에 동형 이식하고, `--hierarchy`
플래그를 CLI·`bakeMeta`·`refreshViewers`까지 배선했다. 결과: 참조·Go의 `gil web --hierarchy`
출력이 **바이트 동일**(5체인·67사이클·1.16MB), 기본 출력·conformance는 **회귀 0**(78/78) —
6측정 전부 통과, 가설 **채택(supported)**.

## 교훈

1. **바이트 동일은 "같은 언어"가 아니라 "같은 계약"이 만든다.** Python f-string과 Go
   `strings.Builder`, `json.dumps`와 손으로 짠 직렬화기 — 도구가 전혀 다른 두 몸이 1.16MB를 한
   바이트도 안 갈린 건, 양쪽이 같은 출력 계약(키 순서·이스케이프·구분자)을 문자 단위로 지켰기
   때문이다. C020이 세운 "두 몸 한 계약"은 위계에서도 성립했다. 정확성을 판정기가 못 보는 렌더
   영역(§3.1)에서, 두 구현 `cmp`가 그 공백을 메우는 증명이 된다는 C047의 방법을 재확인했다.

2. **바이트 동일의 열쇠는 이스케이프의 층위였다.** 참조 CSS의 `content:"\25B8"`(백슬래시 1개)를
   Go에서 일반 문자열로 옮겼다면 `\2`가 해석돼 갈렸다. Go **원문자열**(백틱)을 골라 소스 바이트를
   그대로 출력 바이트로 흘려보낸 것이 일치의 조건이었다. 이식은 "의미"가 아니라 "바이트"를 옮기는 일.

3. **opt-in은 회귀를 구조적으로 0으로 만든다.** `--hierarchy` 없는 경로를 완전히 분기해 두니
   (`webJSONPayload`가 `dirs`를 안 보고, bake에 hierarchy 키를 안 넣음) 변경 전 Go와 변경 후 Go의
   기본 출력이 바이트 동일(M2b)했다. C002가 참조에서 쓴 절제를 Go에서 그대로 재현 — 능력 추가가
   병합 안전을 위협하지 않는다.

4. **격리의 원칙은 빌드 산출물에도 든다.** 공유 `/tmp/gil-go`가 병렬 세션과 충돌해 스테일 바이너리를
   잡는 사고를 겪었다(C002의 "공유 상태 = 병렬 위험"이 워크트리 아닌 `/tmp`에서 재발). 세션-로컬
   경로로 옮겨 재현성을 되찾았고, verify.sh는 `mktemp -d`로 산출물을 격리한다.

## 다음 사이클을 위한 제안 (예언 아님 — 이 보고서의 교훈에서만)

- **`--hierarchy`를 기본으로 승격하는 선택지가 열렸다.** 이제 두 몸이 위계를 알고 바이트 동일이므로,
  C002가 남긴 "완료되면 기본 승격" 옵션이 실현 가능하다. 단 그건 두 몸의 기본 출력을 동시에 바꾸는
  일이라 C020 계약을 깨지 않게 **한 커밋에 양 구현 동시** 반영해야 한다(별도 사이클 권장).
- **미지 verdict 위계 픽스처.** `_verdict_tally`의 삽입-순서 보존 경로는 실 저장소에 미지 verdict가
  없어 방어적 상태다. conformance에 위계 전용 픽스처(미지 verdict 포함)를 신설하면 이 경로가 실증된다.
- **stdout 계약화 여부 판단.** Go·참조의 `web` 로그 정렬이 미묘히 달랐다(이번에 위계 로그만 수렴).
  로그를 계약으로 볼지(conformance 항목화) 자유로 둘지는 설계자 판단 영역 — 표식으로 남긴다.

## 사이클 닫기

- [x] 검증 산출물 3-verification/에 저장 (`verify.sh`로 재현, `sample-hierarchy-go-loomlight.html`)
- [ ] `cycle.yaml` `status: closed`·`closed`·`verdict: supported` — `gil close`가 수행
- [ ] 존재의 방 `memory.md`·`relations.md` 갱신
- [ ] `gil close … --verdict supported --push` — 각인·전파
- [ ] 병합·main 반영은 소환자 Clew의 몫 (브랜치 `worktree-agent-a0663f6f0b528f2ee` push 완료)
