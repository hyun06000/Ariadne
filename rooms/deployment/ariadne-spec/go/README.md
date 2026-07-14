# gil — Go 구현

Ariadne Spec의 구현 독립 계약(§7)을 이행하는 두 번째 구현.
직조: Weft (loom/C012→C014→C017→C020→C036).

```bash
go build -o gil main.go     # 의존성 0 — Go 표준 라이브러리만
./gil fsck && ./gil log && ./gil web -o chains.html
```

자격 판정: `python3 ../conformance.py --gil "$PWD/gil"` — **28/28**이면 이 바이너리는 gil이다.
(⚠️ `--gil`에는 **절대 경로**를 줄 것 — 판정기는 자체 샌드박스 cwd에서 구현을 실행한다. Weft가 C020에서 발견한 함정.)

`release`만 참조 구현(`gil.py`) 전용이다. `open --git/--push`는 **번호 원장 규율**(SPEC §6-6)
까지 이식되어 있다 — push 거절을 "원장이 앞섰다"는 신호로 받아 fetch·rebase 후 번호 경합이면
자동 재번호하고 재시도한다 (loom/C036).
