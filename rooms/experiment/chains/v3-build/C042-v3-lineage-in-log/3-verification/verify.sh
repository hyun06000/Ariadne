#!/bin/bash
# C042 재현: log가 v3 계보를 trailer에서 복원해 그린다
GIL=${GIL:-/Users/davi/Desktop/code/my_project/Ariadne/rooms/deployment/ariadne-spec/gil.py}
T=$(mktemp -d); cd $T
git init -q -b main && git config user.name t && git config user.email t@t
mkdir -p rooms/experiment/chains/demo && printf '# Chain: demo\n' > rooms/experiment/chains/demo/chain.md
python3 $GIL v3 open rooms/experiment/chains/demo/C001-root --title root --author clew --git >/dev/null 2>&1
python3 $GIL v3 open rooms/experiment/chains/demo/C002-child --title child --author weft --parent C001-root --git >/dev/null 2>&1
echo "=== M1 log 계보 (C002-child ← C001-root 기대) ==="
python3 $GIL log 2>&1 | grep "←"
echo "=== M4 비-git 폴백 (crash 없이 root) ==="
cp -r $T ${T}-nogit && rm -rf ${T}-nogit/.git
(cd ${T}-nogit && python3 $GIL log 2>&1 | grep "←")
echo "rc=$?"
