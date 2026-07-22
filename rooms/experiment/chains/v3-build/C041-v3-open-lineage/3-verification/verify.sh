#!/bin/bash
# C041 재현: v3 open --author --parent 계보 trailer + worktree add 전달
GIL=${GIL:-/Users/davi/Desktop/code/my_project/Ariadne/rooms/deployment/ariadne-spec/gil.py}
T=$(mktemp -d); cd $T
git init -q -b main && git config user.name t && git config user.email t@t
mkdir -p rooms/experiment/chains/demo && printf '# Chain: demo\n' > rooms/experiment/chains/demo/chain.md
mkdir -p rooms/experiment/chains/demo/C001-seed
cat > rooms/experiment/chains/demo/C001-seed/cycle.yaml <<Y
id: C001-seed
chain: demo
parent: null
lineage: []
author: seed
status: closed
opened: 2026-01-01
closed: 2026-01-02
title: "seed"
Y
git add -A && git commit -q -m seed
echo "=== M1+M2 계보+스텝트리 trailer 공존 ==="
python3 $GIL v3 open rooms/experiment/chains/demo/C002-mine --title mine --author clew --parent C001-seed --git >/dev/null 2>&1
git log -1 --format='%(trailers)'
echo "=== M3 인자없음 무회귀 (Cycle-Author 비어야) ==="
python3 $GIL v3 open rooms/experiment/chains/demo/C003-plain --title plain --git >/dev/null 2>&1
echo "[$(git log -1 --format='%(trailers:key=Cycle-Author)')]"
echo "=== M4 worktree add --v3 계보 전달 ==="
python3 $GIL worktree add demo wtcyc --author weft --parent C001-seed --v3 >/dev/null 2>&1
git -C $(dirname $T)/$(basename $T)-worktrees/demo-wtcyc log -1 --format='%(trailers:key=Cycle-Author,key=Cycle-Parent)'
