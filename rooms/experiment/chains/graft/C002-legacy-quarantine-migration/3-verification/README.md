# 3. 가설 검증 — legacy/ 이주 절차 실 적용

신선 Flask에 M0~M3 절차를 실행해 (1) 히스토리 보존, (2) 마찰 완화를 관찰했다.

## 재현 방법

```bash
GIL=$(pwd)/rooms/deployment/ariadne-spec/gil.py   # Ariadne 레포 루트에서
S=/tmp/graft-C002 && rm -rf "$S" && mkdir -p "$S"
git clone --depth 200 https://github.com/pallets/flask.git "$S/flask"
FLASK="$S/flask"

# M0. 사전 캡처
git -C "$FLASK" log --oneline | wc -l                       # 676
git -C "$FLASK" log --oneline -5 -- src/flask/app.py        # 기준 이력

# M1. 작업트리 격리 (git mv, .git 제외 전 항목)
cd "$FLASK" && mkdir -p legacy
git ls-tree --name-only HEAD | while read i; do git mv "$i" "legacy/$i"; done
git status --short | grep -c '^R'                           # 236 (전부 rename 인식)
git commit -m "chore: quarantine legacy tree into legacy/"

# 측정1: 히스토리 보존
git -C "$FLASK" log --oneline | wc -l                       # 677 (+1만)
git -C "$FLASK" log --follow --oneline -6 -- legacy/src/flask/app.py  # 이주前 이력 그대로

# M2. gil 골격 심기 (rooms/는 legacy/ 밖 = 루트)
( cd "$FLASK" && python3 "$GIL" open flaskwork adopt-flask \
    --title "Flask에 gil 채택" --author maintainer --new-chain --new-root --git )
git -C "$FLASK" ls-tree --name-only HEAD                    # legacy  rooms (두 세계)
git -C "$FLASK" show --stat --oneline HEAD                  # rooms/만, legacy 무접촉 (F7)

# 측정2: 마찰 완화
( cd "$FLASK" && python3 "$GIL" fsck )       # OK 위반 0  (F2/F4 완화)
( cd "$FLASK" && python3 "$GIL" log  )
( cd "$FLASK" && python3 "$GIL" releases )   # 0개 릴리스  (F3 그대로 — 미완화!)
git -C "$FLASK" tag -l | wc -l               # 16 (태그는 ref라 git mv와 무관하게 살아있음)
```

## 실행 기록

- 실행: 2026-07-19, macOS(darwin 25.5.0), python3, gil.py 로컬 v2.35 상당. 신선 Flask 676커밋·16태그.
- **결과 요약**: M1 236항목 전부 rename 인식·커밋. 히스토리 보존 ✓(677=676+1, `--follow`가 이주前 이력 추적). M2 rooms/·legacy/ 물리 분리, 커밋 격리 ✓. **마찰: F2/F4/F7 완화, F3(releases) 미완화** — 태그는 ref라 git mv로 안 옮겨지고, CHANGES.rst는 legacy/로 옮겨졌어도 여전히 저장소 안. 격리는 "파일 세계"만 분리하고 "ref 세계"는 못 건드림.
- 특이사항: `--author maintainer`가 존재의 방 없이 통과(F5 재현). M3 존재 방 스텁은 gil이 강제 안 함 — 절차상 '권장'이나 필수 아님.

## 산출물

- [transcript/](transcript/) — M0~M3 + 두 측정의 raw 출력.
- 대조·분석은 [4-analysis.md](../4-analysis.md) 참조(before-after 표 포함).
