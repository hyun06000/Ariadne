#!/bin/bash
# C039 재현: v3 worktree add 격리·병렬·land·계보 검증
set -e
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
head0=$(git rev-parse HEAD)
# M1 v3 격리
python3 $GIL worktree add demo mycycle --author clew --v3 >/dev/null
[ "$head0" = "$(git rev-parse HEAD)" ] && echo "M1 main-unchanged ✓"
ls ../$(basename $T)-worktrees/demo-mycycle/rooms/experiment/chains/demo/C002-mycycle/steps.yaml >/dev/null && echo "M1 steps.yaml ✓"
# M2 병렬 무충돌 (경로)
python3 $GIL worktree add demo other-cycle --author weft --v3 >/dev/null && echo "M2 parallel-slug ✓"
# M4 land
python3 $GIL worktree land demo mycycle --author clew >/dev/null && echo "M4 land ✓"
python3 $GIL worktree land demo other-cycle --author weft >/dev/null
echo "메인 사이클: $(ls rooms/experiment/chains/demo/ | grep C0 | tr '\n' ' ')"
echo "fsck: $(python3 $GIL fsck 2>&1 | tail -1)"
