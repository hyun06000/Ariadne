# 이월분 — 다중부모 문서 개선 (죽은 C096에서 구조)

이 디렉토리는 **사이클이 아니다**(cycle.yaml 없음 → fsck·verify·그래프 무관). 죽은 가지 loom/C096-multiparent-docs(rejected, 절차 위반)에서 **검증까지 통과했으나 봉인 못 하고 이월된 문서 개선 산출물**을 다음 세션이 재현 없이 이어받도록 담는다.

## 배경

C096은 열린 부모 C095에서 태어난 절차 위반이라 rejected로 죽었다(상세: `../C096-multiparent-docs/5-report.md`). 그러나 그 안에서 만든 **다중부모 how-to 문서 개선 6곳**은 옳은 작업이고 참조 123·Go 105 무회귀로 검증됐다. `gil step`이 문서 변경을 커밋하지 않아(사이클 파일만 봉인) git 역사에 안 남았으므로, 여기 **패치로 보존**한다.

## 담긴 것 — 5개 패치

각 패치는 `현재본 → 개선본` diff다. 다음 세션에서 C091 새 가지의 "문서 개선" 스텝에 그대로 적용:

| 패치 | 대상 | 내용 |
|---|---|---|
| README.ai.md.patch | 저장소 루트 README.ai.md:102 | 병합(`--parent A --parent B`→`[A,B]`) 명시 + lineage 다른 체인 전용 |
| QUICKSTART.md.patch | ariadne-spec/QUICKSTART.md:86 | 병합 워크드 예제(C036 인용) 블록 |
| SPEC.md.patch | ariadne-spec/SPEC.md §3.2 O-table 뒤 | `--parent` 반복·병합=`[A,B]`·lineage 다른 체인 전용 명문화 |
| gil.py.patch | ariadne-spec/gil.py:694·4233 | open 부모누락 에러 "분기·병합이면", --lineage help "같은 체인은 --parent" |
| main.go.patch | ariadne-spec/go/main.go:952 | Go 에러 메시지 parity |

## 적용 방법 (다음 세션)

```bash
# 저장소 루트에서. 줄번호가 밀렸으면 patch가 fuzz로 흡수하거나 수동 적용.
patch -p0 < rooms/experiment/chains/loom/_carryover-multiparent-docs/README.ai.md.patch
patch -p0 < rooms/experiment/chains/loom/_carryover-multiparent-docs/QUICKSTART.md.patch
patch -p0 < rooms/experiment/chains/loom/_carryover-multiparent-docs/SPEC.md.patch
patch -p0 < rooms/experiment/chains/loom/_carryover-multiparent-docs/gil.py.patch
patch -p0 < rooms/experiment/chains/loom/_carryover-multiparent-docs/main.go.patch
```

> **주의**: 패치의 원본 경로는 diff 생성 시점(저장소 루트 cwd) 기준 상대경로다. 적용 후 반드시 검증 재실행: 참조 `conformance.py` 123, Go 빌드+`conformance.py` 105, `gil help open`의 --lineage/--parent 문안, open 에러 실출력. (C096 3-verification의 재현법과 동일.)

> **더 나은 길**: 패치를 기계 적용하기보다, C091 새 가지에서 C096의 4-analysis·5-report를 읽고 **문안을 다시 쓰는** 편이 계보상 정직하다. 패치는 "무엇을 어디에" 넣었는지의 확실한 기록이자 대조 기준으로 쓴다.

## 다음 세션 전체 순서 (C091에서 새 가지, memory.md와 동일)

1. **(A) open 부모-닫힘 게이트** — 열린 부모면 `open` 거부(C095·C096을 죽인 결함의 직접 수정) + **미완 step도 rejected close 가능**(1스텝 사이클을 그래프에 죽은 가지로 남기는 정당 기제 — 이번 R9 우회의 근본).
2. **(B) 문서 개선 재적용** — 이 디렉토리 패치. 참조 123·Go 105 재검.
3. **(C) 잃은 계보 복원** — C043·C057·C018·C041 (correct, 문서가 부모/근원/만난다로 명시한 것만). correct 단일 `--evidence` 제약(여러 줄 흩어진 부모 복원 불가)이 걸림돌이면 그 확장을 (C)의 전제 사이클로.
3. **(D) deploy 축** — #25. 인프라 조사 완료: `_resolve_source_cycle` 재사용, `gil deploy cut <chain> <cycle> --version <semver>` + `deploy/<chain>/<semver>` 태그 + append-only 레코드, worktree식 sub-action 디스패치, DEPLOY-* conformance.
