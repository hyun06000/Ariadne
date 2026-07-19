# _layout_columns를 그대로 복제 + while 루프에 계측 카운터. eda parent 데이터로 스핀 재현.
import sys

# eda parent 데이터 (방금 스냅)
edges = {
 "C001":[], "C002":["C001"], "C003":["C002"], "C004":["C003"], "C005":["C004"],
 "C006":["C005"], "C007":["C006"], "C008":["C007"], "C009":["C008"], "C010":["C009"],
 "C011":["C010"], "C012":["C011"], "C013":["C012"], "C014":["C013"], "C015":["C014"],
 "C016":["C015"], "C017":["C016"], "C018":["C017"], "C019":["C012"], "C020":["C009"],
 "C021":["C003"], "C022":["C014"], "C023":["C002"], "C024":["C011"], "C025":["C009"],
 "C026":["C025"], "C027":["C026"], "C028":["C027"], "C029":["C028"], "C030":["C029"],
 "C031":["C030"], "C032":["C027"], "C033":["C032"], "C034":["C033"], "C035":["C034"],
 "C036":["C034"], "C037":["C036"], "C038":["C037"], "C039":["C038"], "C040":["C039"],
 "C041":["C040"], "C042":["C039"], "C043":["C040"], "C044":["C041"],
}
order = list(edges.keys())
cycles = {k: {"parents": v} for k, v in edges.items()}
children = {k: [] for k in order}
for k, ps in edges.items():
    for p in ps:
        children[p].append(k)

depth = {}
for node in order:
    ps = [p for p in cycles[node]["parents"] if p in depth]
    depth[node] = (max(depth[p] for p in ps) + 1) if ps else 0

pos, tracks, occupied = {}, [], set()
def free_slot():
    for i, t in enumerate(tracks):
        if t is None:
            return i
    tracks.append(None)
    return len(tracks) - 1

GUARD = 0
for node in order:
    row = depth[node]
    incoming = [i for i, t in enumerate(tracks) if t == node]
    if incoming:
        col = incoming[0]
        for i in incoming[1:]:
            tracks[i] = None
    else:
        col = free_slot()
    spins = 0
    while (row, col) in occupied:
        spins += 1
        GUARD += 1
        if GUARD > 100000:
            print(f"!!! 무한 루프 확증 — node={node} row={row} col={col} spins={spins}")
            print(f"    tracks={tracks}")
            print(f"    occupied at row {row}: {sorted(c for r,c in occupied if r==row)}")
            sys.exit(7)
        if tracks[col] == node:
            tracks[col] = None
        col = free_slot()
    occupied.add((row, col))
    pos[node] = (row, col)
    kids = children[node]
    if kids:
        tracks[col] = kids[0]
        for k in kids[1:]:
            tracks[free_slot()] = k
    else:
        tracks[col] = None
print("정상 종료 — 스핀 아님. max_lane=", max(c for _,c in pos.values()))
