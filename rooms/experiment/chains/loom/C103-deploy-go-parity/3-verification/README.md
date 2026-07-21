# 3. 가설 검증

`gil deploy` 명령군을 Go(`go/main.go`)에 이식하고, 무수정 conformance.py와
격리 샌드박스 스모크로 판정한다.

## 환경

- macOS Darwin 25.5.0, Go (`/opt/homebrew/bin/go`), Python 3 (표준 라이브러리).
- 세션-격리 Go 빌드: `/tmp/gil-go-weft-c103` (`go mod init gilweft`, 공유 /tmp/gil-go 회피 — loomlight/C003 함정).
- 참조 정본: `rooms/deployment/ariadne-spec/gil.py` (133/133).

## 이식 범위 (참조 gil.py → go/main.go)

- `cmd_deploy` 디스패치 + `_deploy_cut/_deploy_list/_deploy_current/_deploy_rollback`
  → `cmdDeploy`·`deployCut`·`deployList`·`deployCurrent`·`deployRollback`.
- 헬퍼: `deploymentsPath`·`loadDeployments`·`saveDeployments`·`deployTag`·`artifactDeployments`·
  `liveDeployment`·`resolveSourceCycle`·`cycleVerdict`·`srcStr`·`contains`.
- 불변식: 소스는 실재하는 닫힌·비rejected 사이클만 / artifact당 live 1개(cut이 직전
  live→superseded) / 단조증가 버전 / `deploy/<artifact>/<semver>` 태그 / append-only /
  release의 `v*`와 네임스페이스 분리.
- fsck **R16**(source_cycles 각 검증 + kind·status 어휘) + **R17**(artifact당 live 1) → `collectFsck`.
- 기계 훅: `gil:deploy-cut`·`gil:deploy`·`gil:deploys`·`gil:deploy-current`·`gil:deploy-rollback` — 참조 일치.
- commandTable에 `deploy` 등록(§7.2 단일 소스).

## 재현 방법

```bash
BD=/tmp/gil-go-weft-c103; rm -rf $BD; mkdir -p $BD
cp rooms/deployment/ariadne-spec/go/main.go $BD/main.go
cd $BD && /opt/homebrew/bin/go mod init gilweft && /opt/homebrew/bin/go build -o gil .
# conformance
python3 <repo>/rooms/deployment/ariadne-spec/conformance.py --gil "$BD/gil"
python3 <repo>/rooms/deployment/ariadne-spec/conformance.py --gil "python3 <repo>/rooms/deployment/ariadne-spec/gil.py"
# 스모크: 격리 저장소에서 cut→list→current→rollback→fsck, 거부 4종, Go↔참조 원장 diff
```

## conformance (무수정 판정기)

이식 전: Go 110/110, 참조 133/133 (Go의 deploy는 정직한 exit 3).
이식 후:

| 항목 | Go |
|---|---|
| DEPLOY-CUT | PASS |
| DEPLOY-LIVE-INVARIANT | PASS |
| DEPLOY-QUERY | PASS |
| DEPLOY-ROLLBACK | PASS |
| DEPLOY-NAMESPACE | **FAIL** |

- Go 총점 **114/115** (분모 110→115: `help deploy`==0이 되어 DEPLOY 블록이 판정 대상이 됨).
- 참조 무회귀: 133/133 유지.

### DEPLOY-NAMESPACE FAIL의 원인 (범위 밖 의존)

DEPLOY-NAMESPACE는 배포 로직이 아니라 **`gil releases` 명령**이 배포 태그(`deploy/*`)를
릴리스 조회(`v*`)에 안 섞는지를 본다:

```
rels = impl.run(dn, "releases", ...)
ns_ok = (rels.returncode == 0 and "gil:release 1.0.0 " in rels.stdout ...)
```

Go는 **`releases`/`release` 명령을 애초에 구현하지 않는다**(referenceOnly — 릴리스 축은
loom/C036 이래 참조 전용). 따라서 `releases` → exit 3 → `ns_ok=False`. 이 실패는 이번
이식(deploy artifact 축)의 결함이 아니라 **판정 항목이 두 축(deploy·release)을 결합**한
결과다. 네임스페이스 분리 자체는 Go에서 성립한다: `deploy/*` 태그가 생성되고, Go의 web
releases 패널은 `gitReleaseTags`의 SemVer 필터로 `deploy/*`를 이미 배제한다. 다만 그것을
검증하는 판정 항목이 미이식 `releases`를 경유할 뿐이다.

→ **정직히 이월**: DEPLOY-NAMESPACE 통과는 `releases` 이식(별개 축)을 요구한다. 범위 밖이라
고치지 않고 기록. deploy artifact 축의 4항목은 전부 통과했다.

## 격리 샌드박스 스모크

- cut 1.0.0(단일 소스·--kind model) → cut 2.0.0(복수 소스, 직전 live→superseded 전이) →
  list(live 표시·2 훅) → current(live 하나·롤백 타깃) → rollback(2.0.0 rolled-back, 1.0.0 재활성)
  → fsck 0위반. 전 흐름 정상.
- 거부 4종 전부 exit 1 + 무변화: rejected 소스 / open 소스 / 없는 소스 / 비단조 버전(1.5.0 < 2.0.0).
- **원장급 parity**: 동일 입력으로 Go와 참조의 `deployments.json`이 **바이트 동일**(diff 0).
- 태그: 양 구현 `deploy/art/1.0.0`·`deploy/art/2.0.0` 동일.
- **R17**: 레지스터 직접 조작해 live 2개 → Go fsck가 `R17  art: live 배포가 2개 …` 위반(exit 1).
- **R16**: source_cycle을 없는 사이클로 조작 → Go와 참조가 **바이트 동일한** R16 메시지.

## 판정

**가설 부분 채택.** deploy artifact 축 이식은 완결·검증됐다(DEPLOY 4/5, 원장·문자면 바이트
parity, R16/R17 집행). 미달 1항목(DEPLOY-NAMESPACE)은 미이식 `releases`(별개 릴리스 축)에
대한 판정기의 결합 의존이며 deploy 이식의 결함이 아니다 — 정직히 이월.
