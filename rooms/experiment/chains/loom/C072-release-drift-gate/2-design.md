# 2. 실험 설계

가설(1-hypothesis.md): `gil release` 사전 검증에 배포 계보 drift 하드 게이트를 더하면 drift 저장소는 무변화로 거부·일치 저장소는 통과하고, 판정 항목으로 계약화된다.

## 구현 절차 (참조 구현 gil.py)

### A. 게이트 헬퍼 — C061 로직 재사용

`cmd_releases`의 drift 정의를 그대로 쓰는 작은 헬퍼를 추가한다. **새 drift 판정을 발명하지 않는다** — 조회와 게이트가 같은 진실을 봐야 한다(재사용 = DRY이자 계약 일치).

```python
def _release_drift(repo, changelog_path):
    """배포 계보의 drift = 태그 v<semver>와 CHANGELOG 중 정확히 한쪽에만 있는 릴리스.
    cmd_releases와 같은 두 헬퍼를 재사용해 조회와 게이트가 같은 drift를 본다.
    git 부재/비저장소(tags is None)면 대조 불가 → drift 없음으로 본다(게이트는 조용히 통과;
    verify/‌fsck가 이미 비저장소를 걸러낸다). 반환: 정렬된 drift 버전 리스트."""
    tags = _git_release_tags(repo)
    if not tags:                      # None(비저장소/‌git부재) 또는 {} (태그 없음) → 대조할 태그가 없다
        return []
    cl = _parse_changelog_releases(changelog_path)
    drifted = [v for v in (set(tags) | set(cl)) if (v in tags) != (v in cl)]
    return sorted(drifted, key=lambda v: tuple(int(x) for x in v.split(".")), reverse=True)
```

- `tags is None`(비저장소): `cmd_release`는 이미 line 2863에서 비저장소를 거부하므로 이 경로엔 도달하지 않으나, 헬퍼는 방어적으로 빈 리스트를 돌려 크래시하지 않는다.
- `tags == {}`(태그 없음): 대조 기준(깃의 진실)이 없다. CHANGELOG-only 항목이 있어도 "정상 경로 이전의 원장"일 수 있어 drift로 몰지 않는다 — 게이트는 **태그가 하나라도 있을 때** 작동한다. (첫 릴리스는 태그 0 → 게이트 무해 통과.)

### B. 게이트 배치 — 사전 검증 안, 변이 전

`cmd_release`의 사전 검증 블록(line 2862~) 안, **버전·태그 검증 직후**(line 2874, `_tag_exists` 체크 뒤)에 삽입한다. 이 자리의 근거:

- **변이 전**: 아직 아무것도 쓰지 않았다 → 거부 시 자동으로 무변화(open 계열 규율 계승).
- **계보 검증과 이웃**: 바로 위 `_last_release_version`·`_tag_exists`가 **새** 버전의 계보 정합을 보고, drift 게이트가 **기존** 계보의 정합을 본다 — 같은 관심사(배포 계보 무결성)를 한자리에 모은다.
- verify 게이트(line 2879)보다 앞: 둘 다 무변화 거부이므로 순서는 계약 무관하나, drift는 태그·CHANGELOG 읽기만으로 판정되는 값싼 결정적 검사라 앞에 둔다.

```python
    tag = f"v{args.version}"
    if _tag_exists(repo, tag):
        raise ChainError(f"태그 '{tag}'가 이미 존재한다")
    # ---- drift 게이트 (loom/C072): 봉인 전, 기존 배포 계보의 두 기록 일치를 요구한다 ----
    # cmd_release는 태그와 CHANGELOG를 한 커밋에 각인하므로 정상 경로의 drift는 0이다.
    # 한쪽에만 있는 릴리스(drift)는 정상 경로 밖의 손댐의 신호 — 어긋난 계보 위에 새 봉인을
    # 얹으면 어긋남이 봉인된다. 하드 위반: 무변화로 거부·처방한다(인접 verify 게이트와 같은 등급).
    changelog = os.path.normpath(os.path.join(pkg, "..", "CHANGELOG.md"))
    drifted = _release_drift(repo, changelog)
    if drifted:
        raise ChainError(
            f"배포 계보 drift {len(drifted)}건 — 태그와 CHANGELOG가 어긋난 릴리스가 있다"
            f"({', '.join('v'+v for v in drifted)}). 어긋난 계보 위엔 새 릴리스를 봉인할 수 없다: "
            f"'gil releases'로 확인하고 두 기록을 일치시킨 뒤 다시 릴리스할 것")
    if not os.path.isdir(pkg):
        ...
```

- `changelog` 경로 계산을 여기로 끌어올리고, 하류(line 2923 부근)의 중복 계산은 이 변수를 재사용하도록 정리한다(DRY, 값 동일).

### C. 판정기 계약 — conformance.py

새 판정 항목 **`RELEASE-DRIFT-GATE`**를 GIT 블록(RELEASE-LIST 인접)에 추가한다. `release`는 Go에서 `referenceOnly`이므로, RELEASE-LIST와 같은 **능력 게이트**(`impl.run(help, "release").returncode == 0`)로 감싸 참조 구현에서만 판정한다 — 미이식 구현의 정직한 부재는 HELP-COMPLETE가 이미 본다(부분 구현 합법, C043 리듬).

판정 항목이 봐야 하는 것(가설의 관측 가능한 결과):
1. **거부**: drift 저장소에서 `release`가 exit≠0.
2. **무변화**: 거부 시 저장소 스냅샷 before==after.
3. **처방**: stderr/stdout에 "drift" 문구.
4. **위양성 0(양성 대조)**: 일치(drift 없는) 저장소에서 release가 **drift를 이유로** 막지 않는다(에러 메시지에 "drift" 없음 — 게이트를 통과해 하류에서 다른 사유로 멈춘다).

## 준비물

- 참조 구현: gil.py (이 워크트리, gil 2.25.0 기준).
- 판정기: conformance.py (현재 90/90 통과 — 이 값이 게이트 추가 후 91/91이 되어야).
- Go: `/tmp/gil-go` (임시 모듈 빌드; go.mod 부재로 `/private/tmp`에 main.go 복사 후 `go mod init`). 현재 83/83.

### 게이트 테스트용 최소 샌드박스 (판정기 내부에 구축)

drift 게이트는 사전 검증 앞부분에서 발화하므로, 아래만 갖추면 게이트에 도달한다(RELEASE.md·template·Unreleased 등 하류 요건은 **음성(거부) 경로에선 불필요**):

- git init/config, `rooms/deployment/ariadne-spec` 패키지 디렉토리, `rooms/experiment/chains`(빈 체인 루트 — verify/fsck 무해 통과, 양성 대조가 게이트를 지나 하류에 닿게).
- **drift 조성**: 태그 `v1.0.0`만 생성(CHANGELOG 엔트리 없음) → v1.0.0가 태그-only drift.
- 릴리스 시도: `release 1.1.0 --notes … --package … --root …` (1.1.0 > last=1.0.0, 태그 미존재 → 게이트까지 도달).
- **양성 대조 샌드박스**: 위와 같되 CHANGELOG에 `## [1.0.0] — …` 엔트리를 추가(v1.0.0 = 태그+CHANGELOG 일치, drift 0) → release가 게이트 통과 후 RELEASE.md 부재 등 **비-drift** 사유로 멈춤.

## 측정 방법

| 관측 | 성공 기준 | 기각 |
|---|---|---|
| drift 저장소 release 종료코드 | exit ≠ 0 | exit 0 |
| drift 저장소 스냅샷 | before == after (무변화) | 변화 |
| 거부 메시지 | "drift" 포함 | 미포함 |
| 일치 저장소 release 메시지 | "drift" **미**포함 (게이트 통과) | "drift" 포함(위양성) |
| 기존 판정 항목 | 90개 전부 유지 → 총 91/91 (Python) | 하나라도 회귀 |
| Go | 83/83 유지 (release referenceOnly, 게이트 미노출 정직) | 회귀 또는 정직성 파괴 |

## 사용자 컨펌

- 생략 — 상현님이 4트랙 병렬 실행을 승인했고 소환자 Clew가 배포 갈래로 이 카브(C061 이월 #2)를 지정했다. 갈래가 나뉘는 새 결정 지점 아님(예약된 사이클의 명시된 임무).

- [x] 컨펌 받음 (일자: 2026-07-19, 소환 지시로 대체)
