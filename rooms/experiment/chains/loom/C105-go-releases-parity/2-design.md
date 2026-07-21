# 2. 실험 설계

## 절차

1. **참조 정독**: gil.py의 `cmd_releases`(line ~4397)와 헬퍼 `_parse_changelog_releases`·`_git_release_tags`·`_release_drift`, argparse의 `releases` 서브파서(`--package` 기본 `rooms/deployment/ariadne-spec`)를 읽어 계약면(종료코드·stdout 라인 포맷·stderr·훅)을 목록화한다.
2. **Go 델타 식별**: Go에 이미 있는 `gitReleaseTags`·`parseChangelogReleases`(뷰어용, C006/loomlight)를 확인하고, 참조에만 있는 `cycles`(근거 사이클) 필드가 Go `clEntry`·파서에 빠졌음을 찾는다.
3. **이식**: (a) `clEntry`에 `cycles` 필드 추가 + 파서에 `- 근거 사이클:` 분기 추가, (b) `cmdReleases(pkg string) int` 신설 — 참조 문면 그대로(anchor 유추, git 부재 시 stderr 안내 + CHANGELOG-only, SemVer 역순 정렬, drift 카운트, `  v%-9s %-10s [marks]` 라인, `gil:release …` 훅, `gil:releases N drift=D` 요약, drift>0 stderr 경고), (c) `b2i` 헬퍼.
4. **등록**: commandTable에 `releases` 엔트리 추가(단일소스 — help·gil:commands 자동 파생), main() 디스패치에 `case "releases"` 추가(`--package` 플래그 파싱).
5. **빌드**: 세션-로컬 격리 경로 `/tmp/gil-go-c105-weft`로 빌드(공유 `/tmp/gil-go` 금지 — C060 flaky 함정).

## 준비물

- Go 1.26.5, Python 3.9+ (표준 라이브러리), git.
- 참조 계약: gil.py(2.49.0), 판정기 conformance.py(무수정).
- 격리 워크트리 `loom-go-releases-parity`, 브랜치 `weft/loom-go-releases-parity`.

## 측정 방법

- **판정기 실측**: `python3 conformance.py --gil /tmp/gil-go-c105-weft` — DEPLOY-NAMESPACE PASS + 회귀 0 (이전 114 유지→상승). RELEASE-LIST는 `help releases` rc0 게이트라 이식 후 새로 활성화될 것으로 예상.
- **참조 무회귀**: `--gil "python3 gil.py"`가 이식 전과 동일 전항목 통과.
- **바이트 대조(C017·C021 방식)**: 태그 v1.0.0(TC)·v1.1.0(T만 drift)·cycle/*·deploy/art/1.0.0 + CHANGELOG(1.2.0 C만, 근거사이클 포함)를 심은 격리 저장소에서 참조와 Go의 stdout/stderr/exit를 `diff`. 성공 기준: 3면 모두 동일. git-부재 분기도 별도 대조.
- **성공/기각**: DEPLOY-NAMESPACE PASS ∧ 회귀 0 ∧ 바이트 동일 → 채택. 하나라도 어긋나면 기각.

## 사용자 컨펌

- 생략 — 소환 브리핑이 이식 범위(releases만)·검증 방법(판정기+바이트diff)·경계(범위 밖 결함은 이월)를 명시했다. 갈래 분기 없음.

- [x] 컨펌 받음 (일자: 2026-07-21, 소환 브리핑으로)
