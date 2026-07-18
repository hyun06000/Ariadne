# 4. 결과 분석

## 통계적 결과

| 기각 조건 | 기준 | 실측 | 판정 |
|---|---|---|---|
| 1. 비원자성 | 부분 생성 후 잔여 | open 실패 시 워크트리·브랜치 제거(undo) — 잔여 0 | 통과 |
| 2. 메인 오염 | spawn 후 main에 사이클 커밋 | 판정기 `iso=True noopen=True` — main 작업트리·log 무변화 | 통과 |
| 3. 번호/스키마 | 워크트리 사이클 fsck 위반 | fsck 위반 0(64사이클) | 통과 |
| 4. 회귀 | 기존 항목 회귀 | 참조·Go 77→**78/78**, 기존 77 유지 | 통과 |
| 5. 두 몸 불일치 | 참조≠Go | 양 구현 WORKTREE-SPAWN·HELP-COMPLETE PASS | 통과 |

변이 격추: self-invoke `--root`를 메인 chains로 바꾼 변이 → `iso=False noopen=False cyc=False`로 **WORKTREE-SPAWN FAIL(77/78)**.

## 데이터 직접 관찰

- **격리를 눈으로 확인**: spawn 후 메인 `git log main`은 `init`에 그대로, 메인 작업트리에 `demo/` 없음. 사이클 커밋은 워크트리 브랜치 `tester/demo-para`에만. **C050의 "메인에 잘못 open"이 물리적으로 불가능**해졌다.
- **참조·Go 동일 행동**: 둘 다 워크트리를 sibling(`<repo>-worktrees/<chain>-<slug>`)에 만들고, 브랜치 `<author>/<chain>-<slug>`, 워크트리 안에 C001 사이클을 열었다. 비저장소에서 둘 다 거부.
- **self-invoke가 각 구현 안에 머문다**: 참조는 `sys.executable+__file__`, Go는 `os.Executable()` — 참조가 참조 open을, Go가 Go open을 부른다. 도구가 자기 이름을 하드코딩 안 하는 §7 계약이 여기서도 지켜진다.

## 예상과 달랐던 것

- **격리를 강제하는 것은 cwd가 아니라 `--root`였다.** 첫 변이(self-invoke `cwd`를 wt_path→repo로)가 **살아남았다(78/78)** — cwd를 바꿔도 격리가 유지됐기 때문. 원인: 재호출 open에 넘긴 `--root wt_chains`가 절대 경로라, open의 `_repo_root(wt_chains)`가 **워크트리 toplevel**을 반환해 커밋이 워크트리 브랜치로 간다 — cwd와 무관하게. 진짜 봉인 지점은 `--root`다. 두 번째 변이(`--root`를 메인으로)가 비로소 격추됐다. **변이가 살아남는 것은 실패가 아니라 진단이다**(C011): 첫 변이가 내 봉인의 진짜 축을 가르쳐 줬다. (cwd=wt_path는 여전히 위생상 유지 — git 명령의 기본 대상이 워크트리가 되게.)
- **작업 중 2-design.md가 템플릿 스텁으로 되돌아갔다.** 원인 미상(하네스/도구 아티팩트 추정 — 1-hypothesis는 42줄로 온전). 재현성이 존재 조건이라 원 설계를 복원하고 문서 상단에 복구 메모를 남겼다. 닫힌 사이클은 불변이므로 스텁으로 닫지 않는다.

## 판정

**채택 (supported).** 기각 조건 5건 전부 통과, 변이 격추, 두 구현 78/78. 병렬 사이클 모드의 진입점 `gil worktree add`가 섰다 — 지금까지 손으로 하던 워크트리+브랜치+사이클 결속을 한 명령으로, 그리고 C050의 뼈아픈 사고를 도구가 구조적으로 봉인한다. land/merge(C059)와 뷰어 가시화(loomlight 후속)가 이 결정론적 매핑 위에 설 수 있다.
