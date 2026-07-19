def spins(edges, order):
    ch={k:[] for k in order}
    for k in order:
        for p in edges[k]:
            if p in ch: ch[p].append(k)
    depth={}
    for n in order:
        ps=[p for p in edges[n] if p in depth]
        depth[n]=(max(depth[p] for p in ps)+1) if ps else 0
    pos,tracks,occ={},[],set()
    def fs():
        for i,t in enumerate(tracks):
            if t is None: return i
        tracks.append(None); return len(tracks)-1
    g=0
    for n in order:
        row=depth[n]; inc=[i for i,t in enumerate(tracks) if t==n]
        if inc:
            col=inc[0]
            for i in inc[1:]: tracks[i]=None
        else: col=fs()
        while (row,col) in occ:
            g+=1
            if g>20000: return True
            if tracks[col]==n: tracks[col]=None
            col=fs()
        occ.add((row,col)); pos[n]=(row,col)
        kids=ch[n]
        if kids:
            tracks[col]=kids[0]
            for k in kids[1:]: tracks[fs()]=k
        else: tracks[col]=None
    return False

import glob,re,os
os.chdir("/Users/davi/Desktop/code/my_project/Ariadne")
edges={}
for y in sorted(glob.glob("rooms/experiment/chains/loom/*/cycle.yaml")):
    t=open(y).read()
    cid=re.search(r'^id: *(\S+)',t,re.M).group(1)
    pm=re.search(r'^parent: *(.+)$',t,re.M)
    par=pm.group(1).strip() if pm else "null"
    edges[cid]=[] if par in ("null","") else [par]
order=list(edges)
# prefix를 늘려가며 스핀이 처음 발생하는 지점 (구조 보존)
for end in range(1,len(order)+1):
    sub=order[:end]
    ed={k:edges[k] for k in sub}
    if spins(ed, sub):
        print(f"스핀 최초 발생: prefix 길이 {end}, 마지막 노드 {order[end-1]}")
        # 이 prefix의 분기 노드(자식 2+) 나열
        ch={k:[] for k in sub}
        for k in sub:
            for p in ed[k]:
                if p in ch: ch[p].append(k)
        branches=[(k,len(v)) for k,v in ch.items() if len(v)>=2]
        print(f"  분기 노드들: {branches}")
        break
else:
    print("prefix에선 스핀 안 함")

# 이제 인공 최소 그래프: 선형 사슬 길이 L, 중간 노드에서 분기 1개. 스핀하는 최소 (L, 분기위치) 찾기
print("\n=== 인공 최소 재현 탐색 ===")
def make(L, branch_at, branch_len):
    # C00..C0L 선형, branch_at에서 별도 가지 B0..B{branch_len}
    e={}
    for i in range(L):
        e[f"C{i:02}"]=[f"C{i-1:02}"] if i>0 else []
    for j in range(branch_len):
        e[f"B{j:02}"]=[f"C{branch_at:02}"] if j==0 else [f"B{j-1:02}"]
    return e, list(e)
found=None
for L in range(3,40):
    for ba in range(0,L):
        for bl in range(1,L):
            e,o=make(L,ba,bl)
            if spins(e,o):
                found=(L,ba,bl,len(o))
                break
        if found: break
    if found: break
print("최소 스핀 인공 그래프:", found, "(L=사슬, branch_at, branch_len, 총노드)")
if found:
    L,ba,bl,_=found
    e,o=make(L,ba,bl)
    print("  노드 순서:", o)
    print("  edges:", {k:v for k,v in e.items()})

# loom prefix 36을 (id 무관) 순수 위상으로 추출 — 노드는 N00..N35, parent 인덱스만
print("\n=== 박제용 위상 (prefix 36) ===")
sub=order[:36]
idx={c:i for i,c in enumerate(sub)}
topo=[]
for c in sub:
    ps=[idx[p] for p in edges[c] if p in idx]
    topo.append(ps)
# 검증: 이 위상이 스핀하나
e2={f"N{i:02}":[f"N{p:02}" for p in ps] for i,ps in enumerate(topo)}
print("박제 위상 스핀 확인:", spins(e2, list(e2)))
print("parent 인덱스 리스트:")
print([ps for ps in topo])
