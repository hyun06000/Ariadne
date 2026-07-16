# 3. 가설 검증 — 산출물과 재현 절차

설계(2-design.md) A·B·C를 그대로 실행한 기록. 모든 명령은 저장소 루트에서 실행.
환경: macOS(darwin 25.2.0), Python 3, Go(표준 라이브러리만), 2026-07-16.

## 파일

| 파일 | 내용 |
|---|---|
| `before-reference.txt` | 수정 전 참조 판정 — **75/76**, PATH-SYMLINK-GIT **FAIL** |
| `before-go.txt` | 수정 전 Go 판정 — **76/76** (Go는 이미 옳음) |
| `after-reference.txt` | 수정 후 참조 판정 — **76/76**, PATH-SYMLINK-GIT PASS, NO-GIT/NO-REMOTE 회귀 0 |
| `after-go.txt` | 수정 후 Go 판정 — **76/76** (무변경, 교차 검증) |
| `mutation-reference.txt` | 변이(realpath 제거) 참조 — **75/76**, PATH-SYMLINK-GIT FAIL (항목이 실제 가드) |
| `direct-repro-after.txt` | 수정된 참조로 심링크 `--root` 직접 재현 — `열림` + 커밋 성공 |
| `real-repo-fsck.txt` | 비심링크 원 저장소 fsck — 위반 0 (회귀 없음) |
| `real-repo-verify.txt` | 비심링크 원 저장소 verify — 변조 0 (회귀 없음) |

## 재현 절차

```bash
# Go 빌드 (표준 라이브러리만)
(cd rooms/deployment/ariadne-spec/go && GO111MODULE=off go build -o /tmp/gil-go main.go)

# 판정기 (양 구현) — 수정 후 76/76 이어야 한다
python3 rooms/deployment/ariadne-spec/conformance.py --gil "python3 $(pwd)/rooms/deployment/ariadne-spec/gil.py"
python3 rooms/deployment/ariadne-spec/conformance.py --gil "/tmp/gil-go"

# 심볼릭 링크 --root 직접 재현 (macOS)
D=$(mktemp -d); mkdir -p "$D/realdir"; ln -s realdir "$D/symrepo"
(cd "$D/realdir" && git init -q && git config user.email t@t && git config user.name t \
  && mkdir -p rooms/experiment/_template/3-verification rooms/experiment/chains \
  && echo x > README.md && git add -A && git commit -qm init)
python3 rooms/deployment/ariadne-spec/gil.py open demo sym-test \
  --root "$D/symrepo/rooms/experiment/chains" --title t --author clew --new-chain --git --no-web
git -C "$D/realdir" log --oneline   # "gil: open demo/C001-sym-test" 커밋이 있어야 한다
```

## 관찰 요약 (수정 전 참조의 붕괴)

```
오류: git add -A -- ../../../../../../../../var/folders/…/C001-sym-test … 'is outside repository'
```

`git rev-parse --show-toplevel`(realpath)과 절대 `--root`(심링크 그대로)의 공간 불일치로
`os.path.relpath`가 저장소를 탈출하는 `../…`를 만들었다. 사이클 디렉토리는 디스크에
생겼으나(`yaml=True`) 커밋은 실패(`committed=False`) — 반쪽 상태.

## 실행 기록 / 판정

| 가설 | 결과 |
|---|---|
| H1 (참조 수정) | **지지** — 심링크 `--root`에서 참조가 Go와 동일하게 정상 커밋 |
| H1-2 (회귀 0) | **지지** — 76/76 ×2, NO-GIT/NO-REMOTE PASS, 원 저장소 fsck·verify 무손상 |
| H2 (계약면) | **지지** — 수정 전 참조 FAIL/Go PASS로 비대칭 포착, 변이 격추(75/76) |

이탈 0. 설계에서 벗어난 절차 없음.
