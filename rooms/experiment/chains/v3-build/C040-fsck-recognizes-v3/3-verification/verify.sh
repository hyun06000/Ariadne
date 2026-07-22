#!/bin/bash
# C040 재현: fsck가 v3 사이클(steps.yaml)을 인식·번호중복 검출·루트define 검사
GIL=${GIL:-/Users/davi/Desktop/code/my_project/Ariadne/rooms/deployment/ariadne-spec/gil.py}
T=$(mktemp -d); cd $T
git init -q -b main && git config user.name t && git config user.email t@t
mkdir -p rooms/experiment/chains/demo && printf '# Chain: demo\n' > rooms/experiment/chains/demo/chain.md
echo "=== M1 v3 인식 (사이클 1개 기대) ==="
python3 $GIL v3 open rooms/experiment/chains/demo/C001-native --title native >/dev/null
python3 $GIL fsck 2>&1 | tail -1
echo "=== M2 번호중복 검출 (R1 기대) ==="
python3 $GIL v3 open rooms/experiment/chains/demo/C001-dup --title dup >/dev/null
python3 $GIL fsck 2>&1 | grep "R1" || echo "(no R1 — FAIL)"
echo "=== M4 루트define 훼손 (V3-ROOT 기대) ==="
rm -rf rooms/experiment/chains/demo/C001-dup
sed -i.bak 's/kind: define/kind: hypothesis/' rooms/experiment/chains/demo/C001-native/steps.yaml
python3 $GIL fsck 2>&1 | grep "V3-ROOT" || echo "(no V3-ROOT — FAIL)"
