# 1. 가설 수립 — github.io 뷰어가 전 릴리스를 "CHANGELOG만"으로 오표시 (발의: 박상현)

## 이전 사이클의 교훈

lineage **loomlight/C006**(releases-in-viewer): 배포 계보를 뷰어에 담고 태그↔CHANGELOG 대조로 drift(⚠)를 자기표현. drift = 한쪽에만 있는 릴리스. 정상 경로(gil release)는 둘을 한 커밋에 쓰므로 drift 0이어야 한다.

## 문제 분할

상현님: "길 뷰어에 모든 버전이 '⚠ CHANGELOG만'이라고 적혀있다." 관찰:
- **CLI `gil releases`는 전부 `[TC]`(정상, drift 0)**, 로컬 태그 71개 다 존재.
- **로컬에서 `gil web`으로 구운 데이터도 `in_tag=True`(정상).**
- 그런데 **github.io(CI 배포) 뷰어만** 전부 "CHANGELOG만".

원인 후보: CI(GitHub Actions)의 `actions/checkout@v4`는 **기본적으로 태그를 안 가져온다**(shallow, no tags). 그래서 CI에서 뷰어를 구울 때 `_git_release_tags`가 빈 결과 → 모든 entry `in_tag=False` → 전부 "CHANGELOG만". `_build_releases_data`([1256])는 "태그를 못 읽음"과 "이 버전만 태그 없음"을 구별 못 해 `tags={}`로만 처리한다.

## 가설

> **가설**: 두 수정 — ① `_PAGES_WORKFLOW`의 checkout에 `fetch-depth: 0`(태그 포함)을 넣어 CI가 태그를 읽게 하고, ② `_build_releases_data`가 **태그를 전혀 못 읽은 상황**(tags 비어있고 CHANGELOG엔 릴리스가 있음)이면 drift 판정을 억제(CLI의 `git_absent`처럼) — 하면, github.io 뷰어가 정상 `[TC]`를 보이고, 설령 CI 설정이 옛것이어도 오탐 배지가 안 뜬다.

## 기각 조건

- fetch-depth만으로 안 고쳐지면(다른 원인) 가설 부분 기각 → 재조사.
- 억제 로직이 **진짜 drift**(태그는 읽혔는데 특정 버전만 없음)까지 숨기면 기각(진짜 신호를 죽이면 안 됨).
- 기존 WEB-RELEASES 등 회귀가 나면 기각.
