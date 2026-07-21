# 1. 가설 수립

## 이전 사이클의 교훈

부모 loom/C103(deploy-go-parity)에서 나는 `gil deploy` 명령군 전체를 Go에 이식해 Go 114/115를 달성하고, 미달 1항목 DEPLOY-NAMESPACE를 정직히 이월했다. 그 항목은 `deploy`가 아니라 `releases`(도구 릴리스 축)를 판정 대상으로 삼는데, Go는 releases를 C036 이래 참조 전용(referenceOnly)으로만 두어 exit 3 → FAIL이었다. C103 보고서의 이월 문장: "releases를 Go에 이식하면 115/115 — 릴리스 축은 C036 이래 마지막 미이식 명령군." 교훈: **판정 항목이 두 축(deploy·release)을 결합하면 만점은 다른 축의 이식을 인질로 잡는다**(C046 재현). 이 사이클은 그 인질을 되찾는다.

## 문제 분할

1. 참조 `cmd_releases`(gil.py) + 헬퍼(`_parse_changelog_releases`, `_git_release_tags`, SemVer 정렬)의 행동을 정독한다.
2. Go에 이미 존재하는 부분(`gitReleaseTags`, `parseChangelogReleases` — 뷰어용)을 재사용하고, 참조에만 있고 Go에 없는 조각(`cycles`/근거사이클 필드, `cmdReleases` CLI 본체)을 채운다.
3. commandTable에 `releases`를 등록해 help·gil:commands 훅이 자동 나열하게 하고, main() 디스패치에 `case "releases"`를 추가한다.
4. 종료코드·stdout·stderr를 참조와 **바이트 단위 동등**하게 만든다. 핵심은 deploy/* 태그가 v* 릴리스 조회에 새지 않는 네임스페이스 분리.

첫 번째로 정복할 문제: releases의 CLI 본체(cmdReleases)를 참조 문면 그대로 이식하는 것 — 나머지(등록·디스패치)는 C036~C050에서 확립한 단일소스 테이블 패턴의 기계적 적용이다.

## 가설

> **가설**: 참조 `cmd_releases`의 행동(git 태그 v<semver> ∪ CHANGELOG 대조, drift 표시, deploy/*·cycle/* 태그 배제)을 Go `main.go`에 이식하고 commandTable에 등록하면, 무수정 conformance에서 DEPLOY-NAMESPACE가 PASS로 돌고 회귀 0으로 Go 판정이 이전 114에서 오른다(115 이상). 참조는 releases를 이미 갖고 있어 무회귀.

## 기각 조건

- DEPLOY-NAMESPACE가 여전히 FAIL이거나, 이식으로 기존 통과 항목이 하나라도 회귀하면 기각.
- Go releases 출력이 참조와 바이트 단위로 어긋나면(문면급 미달) 기각 — 참조가 계약이다(§7).
- deploy/* 또는 cycle/* 태그가 releases 조회에 새어 나오면 기각(네임스페이스 분리 실패).
