# 3. 가설 검증 — 재현 절차

준비 없는 gil 채택을 실제 레거시 레포(Flask)에서 관찰해 마찰을 지도로 그렸다.

## 재현 방법

```bash
GIL=$(pwd)/rooms/deployment/ariadne-spec/gil.py   # Ariadne 레포 루트에서
S=/tmp/graft-C001 && mkdir -p "$S"
git clone --depth 200 https://github.com/pallets/flask.git "$S/flask"
FLASK="$S/flask"

# F1 — log/fsck는 --root를 모른다 (open 전용)
python3 "$GIL" log  --root "$FLASK"     # error: unrecognized arguments: --root
python3 "$GIL" fsck --root "$FLASK"     # 동일

# F2 — 골격 없으면 조회 명령 사망 (Flask 안에서)
( cd "$FLASK" && python3 "$GIL" log  )  # 오류: 체인 루트가 없다
( cd "$FLASK" && python3 "$GIL" fsck )
( cd "$FLASK" && python3 "$GIL" web -o /tmp/x.html )

# F3 — releases가 Flask의 16개 실태그·CHANGES.rst를 0으로 침묵
( cd "$FLASK" && python3 "$GIL" releases )   # 배포 계보 — 0개 릴리스

# F4 — open --new-chain --new-root 만이 유일 진입, 골격 자동 생성
( cd "$FLASK" && python3 "$GIL" open mychain first-cycle --title test --author alice --new-chain --new-root )
( cd "$FLASK" && python3 "$GIL" fsck )   # 이제 OK — 위반 0
( cd "$FLASK" && python3 "$GIL" log  )

# F5 — 존재의 방 없는 author 통과 / F6 — git author 불일치 / F7 — 커밋 격리
( cd "$FLASK" && python3 "$GIL" open mychain second-cycle --title "git test" --author alice --parent C001-first-cycle --git )
( cd "$FLASK" && git show --stat --oneline HEAD )          # rooms/ 6파일만 (F7 격리 OK)
( cd "$FLASK" && git log -1 --format='%an' )               # Flask 로컬 config, alice 아님 (F6)
```

## 실행 기록

- 실행: 2026-07-19, macOS(darwin 25.5.0), python3, gil.py 로컬 v2.35 상당.
- Flask 클론 규모: 676커밋 · 16태그(`2.2.3`…`3.x`) · 281파일. 모든 명령 체감 지연 0(규모 마찰 미관찰).
- 특이사항: 모든 gil 호출을 Flask 레포 밖(Ariadne)의 gil.py 절대경로로 수행 — Flask 안에 gil을 설치하지 않음(백지 사용자는 이 경로를 모른다는 것 자체가 F1의 배경). transcript/에 raw 출력 전부 캡처.

## 산출물

- [friction-log.md](friction-log.md) — 마찰 원장 (F1~F7, 4범주 분류, 요약 통계). **이 사이클의 핵심 산출물.**
- [transcript/](transcript/) — 각 명령의 raw 출력 캡처(재현 대조용).
