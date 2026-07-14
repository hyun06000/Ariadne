#!/usr/bin/env bash
# C042 픽스처 — maru의 상황을 그대로 재현한다: 로컬 뷰어를 쓰는 저장소.
#   사용: bash fixture.sh <작업디렉토리> <gil 호출 문법>
set -euo pipefail
WORK="$1"; shift
GIL="$*"

rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK"
git init -q -b main .
git config user.email fixture@ariadne.test
git config user.name fixture

$GIL open demo first --title "첫 사이클" --author maru --new-chain >/dev/null
printf '# 5. 결과 보고\n\n## 요약\n\n첫 사이클의 보고. 채택.\n' > rooms/experiment/chains/demo/C001-first/5-report.md
$GIL web -o chains.html >/dev/null          # ← 사용자가 뷰어를 굽는다 = "나는 뷰어를 쓴다"는 선언
git add -A && git commit -q -m "seed + 뷰어"

echo "--- 픽스처: 뷰어를 쓰는 저장소 ---"
ls *.html
python3 - <<'PY'
import re, json
d = json.loads(re.search(r'id="gil-data">(.*?)</script>', open("chains.html").read(), re.S).group(1))
print("뷰어가 보고하는 상태:", {c: v["cycles"][list(v["cycles"])[0]]["step"] for c, v in d["chains"].items()})
print("굽기 자기보고 (bake):", d.get("bake"))
PY
