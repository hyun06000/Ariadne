# 수정안 후보를 eda + 정상 그래프(선형·단순분기)로 검증.
# 관심: (1) eda에서 종료하는가 (2) 정상 그래프에서 좌표 불변인가.

def layout(order, cycles, children, FIX):
    depth = {}
    for node in order:
        ps = [p for p in cycles[node]["parents"] if p in depth]
        depth[node] = (max(depth[p] for p in ps) + 1) if ps else 0
    pos, tracks, occupied = {}, [], set()
    def free_slot():
        for i, t in enumerate(tracks):
            if t is None:
                return i
        tracks.append(None); return len(tracks) - 1
    guard = 0
    for node in order:
        row = depth[node]
        incoming = [i for i, t in enumerate(tracks) if t == node]
        if incoming:
            col = incoming[0]
            for i in incoming[1:]:
                tracks[i] = None
        else:
            col = free_slot()
        if FIX == "orig":
            while (row, col) in occupied:
                guard += 1
                if guard > 200000: return None, "SPIN"
                if tracks[col] == node: tracks[col] = None
                col = free_slot()
        elif FIX == "increment":
            # occupied면 col을 단조 증가시켜 미점유 좌표 확보.
            # track 예약과 일관: 원래 col의 예약을 옮겨야 자식 상속 유지.
            if (row, col) in occupied:
                if tracks[col] == node: tracks[col] = None
                newcol = col
                while (row, newcol) in occupied:
                    guard += 1
                    if guard > 200000: return None, "SPIN"
                    newcol += 1
                # tracks 리스트를 newcol까지 확장
                while len(tracks) <= newcol: tracks.append(None)
                col = newcol
        occupied.add((row, col))
        pos[node] = (row, col)
        kids = children[node]
        if kids:
            tracks[col] = kids[0]
            for k in kids[1:]:
                tracks[free_slot()] = k
        else:
            tracks[col] = None
    return pos, "OK"

def build(edges):
    order=list(edges); cycles={k:{"parents":v} for k,v in edges.items()}
    ch={k:[] for k in order}
    for k,ps in edges.items():
        for p in ps: ch[p].append(k)
    return order,cycles,ch

# eda
eda={"C001":[],"C002":["C001"],"C003":["C002"],"C004":["C003"],"C005":["C004"],"C006":["C005"],"C007":["C006"],"C008":["C007"],"C009":["C008"],"C010":["C009"],"C011":["C010"],"C012":["C011"],"C013":["C012"],"C014":["C013"],"C015":["C014"],"C016":["C015"],"C017":["C016"],"C018":["C017"],"C019":["C012"],"C020":["C009"],"C021":["C003"],"C022":["C014"],"C023":["C002"],"C024":["C011"],"C025":["C009"],"C026":["C025"],"C027":["C026"],"C028":["C027"],"C029":["C028"],"C030":["C029"],"C031":["C030"],"C032":["C027"],"C033":["C032"],"C034":["C033"],"C035":["C034"],"C036":["C034"],"C037":["C036"],"C038":["C037"],"C039":["C038"],"C040":["C039"],"C041":["C040"],"C042":["C039"],"C043":["C040"],"C044":["C041"]}
# 정상 케이스들
linear={f"C{i:03}":([f"C{i-1:03}"] if i>1 else []) for i in range(1,11)}
simplebranch={"A":[],"B":["A"],"C":["A"],"D":["B"],"E":["C"]}  # A→B,C ; B→D ; C→E
merge={"A":[],"B":["A"],"C":["A"],"D":["B","C"]}               # 병합

for name,edges in [("eda",eda),("linear",linear),("simplebranch",simplebranch),("merge",merge)]:
    o,c,ch=build(edges)
    po,so=layout(o,c,ch,"orig")
    pf,sf=layout(o,c,ch,"increment")
    same = (po==pf) if (so=="OK" and sf=="OK") else None
    print(f"{name:14} orig={so:5} fix={sf:5} coords_identical={same}")
