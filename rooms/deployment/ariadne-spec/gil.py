#!/usr/bin/env python3
"""gil — 길, GIt for Language model. Ariadne 사이클 체인 도구 (loom/C010에서 ari를 개명).

LLM의 추론이 걸어온 길(사이클 체인)을 깃처럼 다룬다.
이 파이썬 파일은 **참조 구현**이다 — 스펙(SPEC.md)이 계약이며, 장래에 깃처럼
단일 바이너리 배포로 대체될 것을 전제한다 (구현 독립 계약, SPEC §7).

서브커맨드 목록은 **여기에 적지 않는다** — `gil help`가 단일 소스다 (SPEC §7.2, loom/C039).
   갱신하는 목록은 또 낡지만, 위임하는 목록은 낡지 않는다.

의존성: Python 3 표준 라이브러리 + 깃 CLI (verify·correct·close --git·release에만).
스키마 규칙의 정의는 스펙(rooms/deployment/ariadne-spec/SPEC.md)을 따른다.
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys


_STEP_NAMES = {1: "가설", 2: "설계", 3: "검증", 4: "분석", 5: "보고"}
_VERDICTS = ("supported", "partial", "rejected", "inconclusive")  # v0.3 사이클 결말 (R10)
# v2.5 (loom/C045, 이슈 #9·#10): 라운드 전용 어휘 — 사이클 4-어휘에 두 값을 더한다.
# invalid-method: 검증 방법 자체가 무효라 가설의 참/거짓을 판정 못함 (rejected와 다르다).
# confounded: 교란 변수로 결론 불가. 둘 다 "방법이 틀림"을 "가설이 틀림"과 구별한다.
_ROUND_VERDICTS = _VERDICTS + ("invalid-method", "confounded")
_GIL_VERSION = "2.6.0"  # gil:version


class ChainError(Exception):
    """계보 재구성을 불가능하게 만드는 결함 — 침묵하지 않고 보고되어야 한다."""


# ---------- 파싱 ----------

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
_ID_RE = re.compile(r"^C(\d{3,})-[a-z0-9][a-z0-9-]*$")  # R1


def _parse_value(raw):
    raw = raw.strip()
    if raw.startswith('"'):
        end = raw.find('"', 1)
        return raw[1:end] if end != -1 else raw[1:]
    if raw.startswith("["):
        end = raw.find("]")
        inner = raw[1 : end if end != -1 else len(raw)]
        return [v.strip().strip('"') for v in inner.split(",") if v.strip()]
    raw = re.split(r"\s+#", raw, maxsplit=1)[0].strip()  # 뒤따르는 주석 제거
    if raw in ("null", "~", ""):
        return None
    return raw


def parse_cycle_yaml(path):
    data = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = _KEY_RE.match(line)
            if m:
                data[m.group(1)] = _parse_value(m.group(2))
    return data


def _as_list(value):
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def load_chain_records(chain_dir):
    """cycle.yaml이 있는 하위 디렉토리를 전부 읽는다. 검증하지 않고 수집만 한다 (fsck용)."""
    records = []
    for entry in sorted(os.listdir(chain_dir)):
        yaml_path = os.path.join(chain_dir, entry, "cycle.yaml")
        if not os.path.isfile(yaml_path):
            continue
        data = parse_cycle_yaml(yaml_path)
        data["_dir"] = entry
        data["parents"] = _as_list(data.get("parent"))
        data["lineage_list"] = _as_list(data.get("lineage"))
        records.append(data)
    return records


# ---------- 라운드 (loom/C045 — 이슈 #9·#10) ----------
# 라운드는 사이클 안의 (가설→검증) 단위다. R1은 기존 5스텝 문서(1-hypothesis·3-verification)이고,
# R2부터 rounds/R{k}/{hypothesis.md, round.yaml, verification/}에 산다. cycle.yaml의 rounds:N은
# 개수만 담고, 라운드별 메타(title·verdict·일자)는 각 round.yaml에 산다 — 평탄 파서 계약 §3.1 무손상.
# 사전등록(H1)은 fsck가 아니라 도구가 보증한다: round --open이 hypothesis.md를 verification보다 먼저 각인한다.

def _rounds_dir(cycle_dir):
    return os.path.join(cycle_dir, "rounds")


def _cycle_rounds(record):
    """cycle.yaml의 rounds 필드를 정수로 (없거나 잘못되면 1 = 단일 라운드 = 기존 문서)."""
    v = record.get("rounds")
    return int(v) if (isinstance(v, str) and v.isdigit() and int(v) >= 1) else 1


def _load_rounds(cycle_dir):
    """rounds/R*/round.yaml을 읽어 라운드 번호 오름차순으로 반환. 없으면 []."""
    rdir = _rounds_dir(cycle_dir)
    if not os.path.isdir(rdir):
        return []
    out = []
    for entry in sorted(os.listdir(rdir)):
        yp = os.path.join(rdir, entry, "round.yaml")
        if os.path.isfile(yp):
            data = parse_cycle_yaml(yp)
            data["_dir"] = entry
            out.append(data)
    out.sort(key=lambda d: int(d["round"]) if str(d.get("round", "")).isdigit() else 0)
    return out


def load_chain(chain_dir):
    """log용 로더 — 재구성을 막는 결함은 즉시 오류로 보고한다."""
    cycles = {}
    for data in load_chain_records(chain_dir):
        cid = data.get("id")
        if not cid:
            raise ChainError(f"{os.path.join(chain_dir, data['_dir'])}: id 필드가 없다")
        if cid != data["_dir"]:
            print(f"경고: 디렉토리명 '{data['_dir']}' ≠ id '{cid}' — id를 기준으로 처리", file=sys.stderr)
        if cid in cycles:
            raise ChainError(f"체인 '{os.path.basename(chain_dir)}': id '{cid}' 중복")
        cycles[cid] = data
    return cycles


# ---------- 그래프 재구성 ----------

def _toposort(ids, edges):
    """edges: {child: [parents]}. (순서, 자식맵, 순환에 갇힌 노드들)을 반환."""
    children = {cid: [] for cid in ids}
    indegree = {cid: 0 for cid in ids}
    for child, parents in edges.items():
        for p in parents:
            children[p].append(child)
            indegree[child] += 1
    for p in children:
        children[p].sort()
    order, ready = [], sorted(cid for cid, d in indegree.items() if d == 0)
    while ready:
        node = ready.pop(0)
        order.append(node)
        newly = []
        for ch in children[node]:
            indegree[ch] -= 1
            if indegree[ch] == 0:
                newly.append(ch)
        ready = sorted(ready + newly)
    stuck = sorted(set(ids) - set(order))
    return order, children, stuck


def build_graph(chain_name, cycles):
    edges = {}
    for cid, data in cycles.items():
        for p in data["parents"]:
            if p not in cycles:
                raise ChainError(
                    f"체인 '{chain_name}': {cid}의 parent '{p}'가 존재하지 않는다 (끊어진 참조)"
                )
        edges[cid] = data["parents"]
    order, children, stuck = _toposort(set(cycles), edges)
    if stuck:
        raise ChainError(f"체인 '{chain_name}': 순환 참조 발견 — 다음 사이클이 그래프를 이루지 못한다: {', '.join(stuck)}")
    return order, children


# ---------- log 렌더링 ----------

def _row(cells, tail=""):
    return (" ".join(cells).rstrip() + ("  " + tail if tail else "")).rstrip()


def render_graph(order, cycles, children):
    lines = []
    tracks = []  # tracks[i] = 아직 그려지지 않은 자식 노드의 id (부모→자식 간선 하나당 하나)
    for node in order:
        incoming = [i for i, t in enumerate(tracks) if t == node]
        kids = children[node]

        if incoming:
            col = incoming[0]
            if len(incoming) > 1:  # 병합
                span = incoming[-1]
                merged = ""
                for i in range(len(tracks)):
                    if i == col:
                        merged += "├"
                    elif i in incoming:
                        merged += "┘" if i == span else "┴"
                    elif col < i < span:
                        merged += "┼" if tracks[i] != node else "─"
                    else:
                        merged += "│"
                    if i < len(tracks) - 1:
                        merged += "─" if col <= i < span else " "
                lines.append(merged.rstrip())
                for i in reversed(incoming[1:]):
                    tracks.pop(i)
        else:  # root
            tracks.append(None)
            col = len(tracks) - 1

        cells = ["●" if i == col else "│" for i in range(len(tracks))]
        meta = cycles[node]
        status = meta.get("status") or "?"
        verdict = meta.get("verdict")
        label = f"{status} · {verdict}" if verdict else status  # v0.3 결말 표시
        rounds = meta.get("rounds")  # v2.5: 라운드 수 (2 이상일 때만 — 무라운드 출력 불변, C045)
        if isinstance(rounds, str) and rounds.isdigit() and int(rounds) > 1:
            label += f" · R{rounds}"
        dev = meta.get("deviations")
        mark = f" ⚠{dev}" if (isinstance(dev, str) and dev.isdigit() and int(dev) > 0) else ""
        sup = f"  ↣ superseded: {meta['superseded_by']}" if meta.get("superseded_by") else ""
        corr = meta.get("corrections")  # v0.5: 후대의 주석 — 이 색인은 수리됐다
        cmark = f"  ✎ corrected({corr})" if (isinstance(corr, str) and corr.isdigit() and int(corr) > 0) else ""
        tail = f"{node} [{label}{mark}] {meta.get('title') or ''}{sup}{cmark}"
        if len(meta["parents"]) > 1:
            tail += f"  ◀ 병합: {' + '.join(meta['parents'])}"
        if meta["lineage_list"]:
            tail += f"  ⇠ lineage: {', '.join(meta['lineage_list'])}"
        lines.append(_row(cells, tail))

        if kids:
            tracks[col] = kids[0]
            extra = kids[1:]
            if extra:  # 분기
                start = len(tracks)
                tracks.extend(extra)
                span = len(tracks) - 1
                branched = ""
                for i in range(len(tracks)):
                    if i == col:
                        branched += "├"
                    elif start <= i:
                        branched += "┐" if i == span else "┬"
                    elif col < i:
                        branched += "┼" if i < start else "─"
                    else:
                        branched += "│"
                    if i < len(tracks) - 1:
                        branched += "─" if col <= i < span else " "
                lines.append(branched.rstrip())
        else:
            tracks.pop(col)
    return lines


def summarize(order, cycles, children):
    roots = [c for c in order if not cycles[c]["parents"]]
    lines = [f"root: {', '.join(roots)}"]
    for b, kids in sorted(children.items()):
        if len(kids) > 1:
            lines.append(f"분기점: {b} → {', '.join(kids)}")
    for c in order:
        if len(cycles[c]["parents"]) > 1:
            lines.append(f"병합점: {c} ← {', '.join(cycles[c]['parents'])}")
    return lines


def log_chain(chain_name, chain_dir):
    cycles = load_chain(chain_dir)
    if not cycles:
        return
    order, children = build_graph(chain_name, cycles)
    print(f"=== chain: {chain_name} — 사이클 {len(cycles)}개 ===")
    print()
    for line in render_graph(order, cycles, children):
        print(line)
    print()
    for line in summarize(order, cycles, children):
        print(line)
    print()
    print("계보 (토폴로지 순서, 동순위는 id 오름차순):")
    for cid in order:
        parents = cycles[cid]["parents"]
        print(f"  {cid}  ←  {', '.join(parents) if parents else '(root)'}")
    # v0.3: 결말 집계 (닫힌 사이클 중 verdict 있는 것)
    tally = {v: 0 for v in _VERDICTS}
    devs = 0
    for cid in order:
        v = cycles[cid].get("verdict")
        if v in tally:
            tally[v] += 1
        d = cycles[cid].get("deviations")
        if isinstance(d, str) and d.isdigit():
            devs += int(d)
    parts = [f"{v} {tally[v]}" for v in _VERDICTS if tally[v]]
    if parts or devs:
        print()
        print("결말: " + " · ".join(parts) + (f" · 이탈 {devs}건" if devs else ""))
    reservations = _load_reservations(chain_dir)  # 예약은 사이클이 아니다 — 그래프 밖 별도 섹션 (loom/C043)
    if reservations:
        print()
        print("예약됨 (아직 사이클 아님 — 번호 공간 선점):")
        for r in reservations:
            print(f"  C{r['num']:03d}  → {r['for']}  ({r['slug']}, {r['date']})")
    print()


# ---------- fsck (스키마 v0.2 규칙 R1~R8) ----------

# §4.1 정정 규정 (v0.5 / loom/C041)
# 정정 가능한 것은 출처 필드뿐이다 (L1) — 도구가 지어낼 수 있었던 바로 그 집합 (§3.2).
# verdict·status·title·step·5스텝 문서는 저자의 주장이며 불변이다.
_PROVENANCE_FIELDS = ("author", "parent", "lineage")
_CORRECTION_KEYS = ("field", "from", "to", "evidence", "author", "date")  # R13 필수 키


def _parse_corrections(path):
    """corrections.yaml을 줄 단위로 판정한다 — 일반 YAML 파서 없이 (§3.1 평탄 계약의 정신).
    형식 위반이면 None. deviations.yaml은 사람이 읽는 문서지만, 이것은 도구가 판정하는 기록이다."""
    records, cur = [], None
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("- "):
            cur = {}
            records.append(cur)
            body = line[2:]
        elif line.startswith("  ") and cur is not None:
            body = line[2:]
        else:
            return None  # 중첩·블록 스칼라·들여쓰기 위반
        key, sep, val = body.partition(":")
        if not sep or not key.strip() or key.strip() != key.strip().split()[0]:
            return None
        cur[key.strip()] = val.strip()
    return records


def fsck_collect(chains, chains_root=None):
    """chains: {체인명: records}. (위반 리스트, 경고 리스트)를 반환한다 (경고는 표시일 뿐 exit 0)."""
    violations = []
    warnings = []
    ids_by_chain = {ch: {r.get("id") for r in recs} for ch, recs in chains.items()}

    for ch, recs in sorted(chains.items()):
        numbers = {}
        for r in recs:
            cid = r.get("id")
            loc = f"{ch}/{r['_dir']}"
            if not cid:
                violations.append(("R1", loc, "id 필드가 없다"))
                continue
            m = _ID_RE.match(cid)
            if not m:
                violations.append(("R1", loc, f"id '{cid}' 형식 위반 — C<3자리 이상 번호>-<소문자 케밥 슬러그>"))
            else:
                numbers.setdefault(m.group(1), []).append(cid)
            if r.get("chain") != ch:
                violations.append(("R4", loc, f"chain 필드 '{r.get('chain')}' ≠ 소속 체인 '{ch}'"))
            if cid != r["_dir"]:
                violations.append(("R5", loc, f"id '{cid}' ≠ 디렉토리명 '{r['_dir']}'"))
            for p in r["parents"]:
                if "/" in p:  # 표기가 틀리면 해소 검사는 중복 보고하지 않는다
                    violations.append(("R3", loc, f"parent '{p}'는 로컬 id여야 한다 (전역 표기 금지)"))
                elif p not in ids_by_chain[ch]:
                    violations.append(("R6", loc, f"parent '{p}'가 존재하지 않는다 (끊어진 참조)"))
            for l in r["lineage_list"]:
                if l.count("/") != 1:
                    violations.append(("R3", loc, f"lineage '{l}'는 전역 표기(<chain>/<id>)여야 한다"))
                    continue
                lch, lid = l.split("/")
                if lch == ch:
                    violations.append(("R3", loc, f"lineage '{l}'가 같은 체인을 가리킨다 (같은 체인의 계보는 parent)"))
                elif lid not in ids_by_chain.get(lch, set()):
                    violations.append(("R2", loc, f"lineage '{l}'가 존재하지 않는다"))
            status, closed = r.get("status"), r.get("closed")
            if status == "closed" and not closed:
                violations.append(("R8", loc, "status가 closed인데 closed 일자가 없다"))
            elif status == "open" and closed:
                violations.append(("R8", loc, "status가 open인데 closed 일자가 있다"))
            step = r.get("step")
            if step is not None:
                if not (isinstance(step, str) and step.isdigit() and 1 <= int(step) <= 5):
                    violations.append(("R9", loc, f"step '{step}'는 1~5 정수여야 한다"))
                elif status == "closed" and int(step) != 5:
                    violations.append(("R9", loc, f"닫힌 사이클의 step은 5여야 한다 (현재 {step})"))
            # R10 (v0.3): verdict·deviations — 결말과 사전등록 이탈의 기계 가시화
            verdict = r.get("verdict")
            if verdict is not None and verdict not in _VERDICTS:
                violations.append(("R10", loc, f"verdict '{verdict}'는 {'|'.join(_VERDICTS)} 중 하나여야 한다"))
            dev = r.get("deviations")
            if dev is not None:
                if not (isinstance(dev, str) and dev.isdigit()):
                    violations.append(("R10", loc, f"deviations '{dev}'는 정수여야 한다 (상세는 deviations.yaml)"))
                elif int(dev) > 0:
                    devfile = os.path.join(chains_root, ch, r["_dir"], "deviations.yaml") if chains_root else None
                    if devfile and not os.path.isfile(devfile):
                        violations.append(("R10", loc, f"deviations {dev}인데 deviations.yaml이 없다"))
                    warnings.append(("이탈", loc, f"사전등록 이탈 {dev}건 (deviations.yaml)"))
            if status == "closed" and verdict is None:
                warnings.append(("결말없음", loc, "닫혔으나 verdict 없음 — 결말을 기록할 것 (경고, 기존 사슬 유예)"))
            # R13 (v0.5): 출처 정정 기록 — L1(필드 제한)과 L3(영구 기록)을 fsck가 집행한다.
            # 경고가 아니라 위반인 이유: corrections는 v0.5에서 태어나므로 유예할 과거가 없다.
            corr = r.get("corrections")
            if corr is not None:
                if not (isinstance(corr, str) and corr.isdigit()):
                    violations.append(("R13", loc, f"corrections '{corr}'는 정수여야 한다 (상세는 corrections.yaml)"))
                elif int(corr) > 0:
                    cfile = os.path.join(chains_root, ch, r["_dir"], "corrections.yaml") if chains_root else None
                    if cfile and not os.path.isfile(cfile):
                        violations.append(("R13", loc, f"corrections {corr}인데 corrections.yaml이 없다"))
                    elif cfile:
                        recs = _parse_corrections(cfile)
                        if recs is None:
                            violations.append(("R13", loc, "corrections.yaml 형식 위반 — '- field: …' + 2칸 들여쓴 key: value"))
                        elif len(recs) != int(corr):
                            violations.append(("R13", loc, f"corrections {corr}인데 corrections.yaml 레코드는 {len(recs)}건"))
                        else:
                            for i, rec in enumerate(recs, 1):
                                miss = [k for k in _CORRECTION_KEYS if k not in rec]
                                if miss:
                                    violations.append(("R13", loc, f"corrections.yaml #{i}: 필수 키 누락 — {', '.join(miss)}"))
                                elif rec["field"] not in _PROVENANCE_FIELDS:
                                    violations.append(("R13", loc, f"corrections.yaml #{i}: '{rec['field']}'는 출처 필드가 아니다 (L1)"))
                    warnings.append(("정정", loc, f"출처 정정 {corr}건 (corrections.yaml) — 색인은 수리됐고 거짓은 기록에 남았다"))
            sb = r.get("superseded_by")  # R11 (v0.4): 전방 포인터 해소
            if sb is not None:
                if sb == cid or sb == f"{ch}/{cid}":
                    violations.append(("R11", loc, "superseded_by가 자기 자신을 가리킨다"))
                elif "/" in sb:
                    sch, sid = sb.split("/", 1)
                    if sid not in ids_by_chain.get(sch, set()):
                        violations.append(("R11", loc, f"superseded_by '{sb}'가 존재하지 않는다"))
                elif sb not in ids_by_chain[ch]:
                    violations.append(("R11", loc, f"superseded_by '{sb}'가 체인 '{ch}'에 없다 (전역이면 <chain>/<id>)"))
            # R15 (v2.5, loom/C045 — 이슈 #9·#10): 라운드 사전등록. rounds:N(N>1)이면 R2..RN 각각
            # rounds/R{k}/hypothesis.md가 존재해야 한다 — 없으면 사전등록되지 않은 것이다. round.yaml의
            # verdict가 있으면 6-어휘 중 하나여야 한다. 위반인 이유: round --open이 항상 hypothesis.md를
            # 만든다 — 정당한 탈출구가 없다(R14의 선례). rounds 필드가 없으면 규칙 불발 → 무라운드는 사정거리 밖(하위호환).
            rounds_raw = r.get("rounds")
            if rounds_raw is not None:
                if not (isinstance(rounds_raw, str) and rounds_raw.isdigit() and int(rounds_raw) >= 1):
                    violations.append(("R15", loc, f"rounds '{rounds_raw}'는 1 이상의 정수여야 한다"))
                elif chains_root and int(rounds_raw) > 1:
                    cdir = os.path.join(chains_root, ch, r["_dir"])
                    for k in range(2, int(rounds_raw) + 1):
                        rk = os.path.join(cdir, "rounds", f"R{k}")
                        if not os.path.isfile(os.path.join(rk, "hypothesis.md")):
                            violations.append(("R15", loc, f"rounds:{rounds_raw}인데 rounds/R{k}/hypothesis.md가 없다 (사전등록 파일 누락)"))
                        ryp = os.path.join(rk, "round.yaml")
                        if os.path.isfile(ryp):
                            rv = parse_cycle_yaml(ryp).get("verdict")
                            if rv is not None and rv not in _ROUND_VERDICTS:
                                violations.append(("R15", loc, f"rounds/R{k}/round.yaml verdict '{rv}'는 {'|'.join(_ROUND_VERDICTS)} 중 하나여야 한다"))
        for num, dupes in sorted(numbers.items()):
            if len(dupes) > 1:
                violations.append(("R1", ch, f"번호 {num} 중복: {', '.join(sorted(dupes))}"))
        # R7: 해소 가능한 로컬 간선만으로 순환 검사
        valid = {r.get("id") for r in recs if r.get("id")}
        edges = {
            r["id"]: [p for p in r["parents"] if "/" not in p and p in valid]
            for r in recs if r.get("id")
        }
        _, _, stuck = _toposort(valid, edges)
        if stuck:
            violations.append(("R7", ch, f"순환 참조: {', '.join(stuck)}"))
        # R12 (v0.5): 다중 루트 — 거의 항상 --parent 누락의 흔적이다.
        # 경고이지 위반이 아닌 이유: open --new-root가 정당한 탈출구다. 도구가 자기 탈출구를 불법화하면 안 된다.
        roots = sorted(r["id"] for r in recs if r.get("id") and not r["parents"])
        if len(roots) > 1:
            warnings.append(("다중루트", ch, f"루트가 {len(roots)}개 — {', '.join(roots)} "
                                            f"(의도한 것이 아니면 parent 누락이다)"))
        # R14 (v0.6): 체인 디렉토리는 chain.md를 가져야 한다 — open --new-chain이 놓치던 표면 (이슈 #14).
        # 위반인 이유: R12(경고)와 달리 정당한 탈출구가 없다 — open --new-chain이 항상 chain.md를 만든다.
        # v0.6에서 태어나 유예할 과거가 없다(R13의 선례). chains_root가 있을 때만 파일을 본다(R10·R13 패턴).
        if chains_root and not os.path.isfile(os.path.join(chains_root, ch, "chain.md")):
            violations.append(("R14", ch, "chain.md가 없다 — 체인의 문제 정의 문서가 커밋되지 않았다"))
    return violations, warnings


def cmd_fsck(args):
    chains = _scan_chains(args.chains_root, args.chain)
    violations, warnings = fsck_collect(chains, args.chains_root)
    total = sum(len(recs) for recs in chains.values())
    grouped = {}
    for kind, loc, msg in warnings:
        grouped.setdefault(kind, []).append((loc, msg))
    for kind in sorted(grouped):
        items = grouped[kind]
        if kind == "결말없음":  # 다수가 되기 쉬우므로 요약 (유예)
            locs = ", ".join(loc for loc, _ in items[:5]) + (" …" if len(items) > 5 else "")
            print(f"경고 [결말없음] {len(items)}건 — verdict 미기록 (기존 사슬 유예): {locs}", file=sys.stderr)
        else:  # 이탈은 감사의 핵심이므로 개별 강조
            for loc, msg in items:
                print(f"경고 [{kind}] {loc}: {msg}", file=sys.stderr)
    if violations:
        for rule, loc, msg in sorted(violations):
            print(f"{rule}  {loc}: {msg}")
        print(f"\n검사: 체인 {len(chains)}개, 사이클 {total}개 — 위반 {len(violations)}건, 경고 {len(warnings)}건", file=sys.stderr)
        return 1
    tail = f", 경고 {len(warnings)}건" if warnings else ""
    print(f"OK — 체인 {len(chains)}개, 사이클 {total}개, 위반 0건 (스키마 v0.5){tail}")
    return 0


# ---------- open / close (쓰기 porcelain) ----------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")  # R1의 슬러그 부분


def _template_dir(chains_root):
    return os.path.normpath(os.path.join(chains_root, "..", "_template"))


def _next_number(records, reserved_nums=()):
    """다음 번호 = max(사이클 번호 ∪ 예약 번호) + 1.
    예약(loom/C043)은 사이클이 아니지만 번호 공간을 선점한다 — 남의 예약 번호는
    누구에게도 자동 발급되지 않는다. reserved_nums 기본값 ()로 하위호환."""
    nums = list(reserved_nums)
    for r in records:
        m = _ID_RE.match(r.get("id") or "")
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


# ---------- 번호 예약 원장 (loom/C043 — 이슈 #13) ----------
# 예약은 사이클이 아니다. 체인 최상위의 평문 원장(reservations.tsv)에 산다 —
# load_chain_records는 <entry>/cycle.yaml만 record로 수집하므로 fsck·verify·graph는
# 예약을 record로 보지 않는다. "예약은 사이클이 아니다"를 파일 위치가 물리적으로 보증한다.
# 형식: 주석(#) + 예약 한 줄당 "<번호> <for> <slug> <일자>" (공백 구분, 번호 오름차순).

def _reservations_path(chain_dir):
    return os.path.join(chain_dir, "reservations.tsv")


def _load_reservations(chain_dir):
    """예약 목록을 반환한다: [{num, for, slug, date}]. 파일 없으면 []."""
    path = _reservations_path(chain_dir)
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4 or not parts[0].isdigit():
                continue  # 관대한 파서 — 깨진 줄은 건너뛴다 (원장은 log·fsck의 1급 대상이 아니다)
            out.append({"num": int(parts[0]), "for": parts[1], "slug": parts[2], "date": parts[3]})
    out.sort(key=lambda r: r["num"])
    return out


_RESERVATIONS_HEADER = (
    "# gil 예약 원장 — 이 파일은 사이클이 아니다 (loom/C043). 번호 공간의 선점만 기록한다.\n"
    "# <번호> <for> <slug> <일자>\n")


def _save_reservations(chain_dir, reservations):
    """예약 목록을 원장에 쓴다. 비면 파일을 지운다."""
    path = _reservations_path(chain_dir)
    if not reservations:
        if os.path.isfile(path):
            os.remove(path)
        return path, False
    reservations = sorted(reservations, key=lambda r: r["num"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(_RESERVATIONS_HEADER)
        for r in reservations:
            f.write(f"{r['num']} {r['for']} {r['slug']} {r['date']}\n")
    return path, True


def _fsck_or_report(chains_root):
    violations, _ = fsck_collect(_scan_chains(chains_root), chains_root)
    if violations:
        lines = "; ".join(f"{rule} {loc}: {msg}" for rule, loc, msg in violations)
        raise ChainError(f"fsck 위반 — {lines}")


def _push_with_renumber(repo, chain_dir, chain, cid, title):
    """원장 규율 (v0.8): push 거절 = 원장이 앞섰다는 신호. fetch·rebase 후
    번호 경합이면 자동 재번호(디렉토리·id 개명 + 커밋 정정) 후 재시도한다. 최대 3회."""
    for _ in range(3):
        r = _git(repo, "push", check=False)
        if r.returncode == 0:
            return cid
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        _git(repo, "fetch", "origin")
        rb = _git(repo, "rebase", f"origin/{branch}", check=False)
        if rb.returncode != 0:
            _git(repo, "rebase", "--abort", check=False)
            raise ChainError("push 경합의 rebase 해소 실패 — 수동 개입 필요: "
                             + (rb.stderr or rb.stdout or "").strip()[-150:])
        my_num = _ID_RE.match(cid).group(1)
        records = load_chain_records(chain_dir)
        dup = [rec.get("id") for rec in records if rec.get("id") and rec["id"] != cid
               and _ID_RE.match(rec["id"]) and _ID_RE.match(rec["id"]).group(1) == my_num]
        if dup:
            slug = cid.split("-", 1)[1]
            reserved = [r["num"] for r in _load_reservations(chain_dir)]  # 재번호도 예약을 회피한다
            new_cid = f"C{_next_number(records, reserved):03d}-{slug}"
            old_rel = os.path.relpath(os.path.join(chain_dir, cid), repo)
            new_rel = os.path.relpath(os.path.join(chain_dir, new_cid), repo)
            _git(repo, "mv", old_rel, new_rel)
            ypath = os.path.join(repo, new_rel, "cycle.yaml")
            with open(ypath, encoding="utf-8") as f:
                text = f.read()
            with open(ypath, "w", encoding="utf-8") as f:
                f.write(text.replace(f"id: {cid}", f"id: {new_cid}", 1))
            _git(repo, "add", "-A", "--", new_rel)
            _git(repo, "commit", "--amend",
                 "-m", f"gil: open {chain}/{new_cid} — 1/5 {_STEP_NAMES[1]}\n\n{title}\n(원장 경합 재번호: {cid} → {new_cid})")
            print(f"경합 감지: {cid} → {new_cid} (원장 규율에 따라 재번호)", file=sys.stderr)
            cid = new_cid
    raise ChainError("push 경합 해소 3회 실패 — 원장이 계속 앞선다")


def cmd_open(args):
    chains_root = args.root
    chain_dir = os.path.join(chains_root, args.chain)
    template = _template_dir(chains_root)

    # ---- 사전 검증: 저장소를 건드리기 전에 전부 확인한다 (부분 생성물 방지) ----
    # §3.2 출처 계약 (P1·P2): 도구는 출처(author·parent)를 지어내지 않는다. 모르면 거부한다.
    if not args.author:  # O1 — 기본값 없음. 고유명사 기본값이 남의 원장에 거짓 저자를 박았다 (이슈 #17)
        raise ChainError(
            "저자를 알 수 없다 — 도구는 출처를 지어내지 않는다 (§3.2 P1).\n"
            f"      존재의 이름을 명시하라:  gil open {args.chain} {args.slug} --author <이름>")
    if args.parent and args.new_root:  # O3 — 모순
        raise ChainError("--parent와 --new-root는 함께 쓸 수 없다 — 부모가 있으면 루트가 아니다")
    if not _SLUG_RE.match(args.slug):
        raise ChainError(f"슬러그 '{args.slug}' 형식 위반 — R1: 소문자·숫자·하이픈만 (마침표 금지)")
    use_embedded = not os.path.isdir(template)  # _template 부재 시 내장 스캐폴드 (v1.1: 딸깍)
    new_chain = not os.path.isdir(chain_dir)
    if new_chain and not args.new_chain:
        raise ChainError(f"체인 '{args.chain}'이 없다 — 새로 만들려면 --new-chain")
    if args.new_chain:
        os.makedirs(chains_root, exist_ok=True)  # 딸깍: 체인 루트가 없으면 만든다 (git init처럼, v1.1)
    _fsck_or_report(chains_root)  # 깨진 저장소 위에는 짓지 않는다

    records = load_chain_records(chain_dir) if not new_chain else []
    ids = {r.get("id") for r in records}
    # O2 (§3.2 P2·P3): 빈 체인의 첫 사이클이 루트라는 것은 계산이지만, 비어있지 않은 체인에서
    # parent를 비우는 것은 추측이다 — 조용히 두 번째 루트를 만드는 대신 저자에게 묻는다.
    if records and not args.parent and not args.new_root:
        tip = sorted(i for i in ids if i)[-1] if ids else "?"
        raise ChainError(
            f"체인 '{args.chain}'에 이미 사이클이 있다 (tip: {tip}) — 부모를 알 수 없다 (§3.2 P2).\n"
            f"      부모를 명시하라:  --parent {tip}   (분기면 여러 번)\n"
            f"      정말 새 루트라면:  --new-root")
    for p in args.parent:
        if "/" in p:
            raise ChainError(f"parent '{p}'는 로컬 id여야 한다 (R3)")
        if p not in ids:
            raise ChainError(f"parent '{p}'가 체인 '{args.chain}'에 없다 (R6 위반 예정)")
    chains = _scan_chains(chains_root)
    for l in args.lineage:
        if l.count("/") != 1:
            raise ChainError(f"lineage '{l}'는 전역 표기(<chain>/<id>)여야 한다 (R3)")
        lch, lid = l.split("/")
        if lch == args.chain:
            raise ChainError(f"lineage '{l}'가 같은 체인을 가리킨다 — 같은 체인의 계보는 parent (R3)")
        if lid not in {r.get("id") for r in chains.get(lch, [])}:
            raise ChainError(f"lineage '{l}'가 존재하지 않는다 (R2 위반 예정)")

    # 번호 예약 (loom/C043): 저자가 예약을 가지면 그 번호로 승격, 아니면 예약을 회피해 발급.
    reservations = _load_reservations(chain_dir)
    mine = [r for r in reservations if r["for"] == args.author]
    if mine:
        consumed = min(mine, key=lambda r: r["num"])  # 자기 예약 중 가장 낮은 번호를 승격
        num = consumed["num"]
    else:
        consumed = None
        num = _next_number(records, [r["num"] for r in reservations])  # 남의 예약 번호는 건너뛴다
    cid = f"C{num:03d}-{args.slug}"
    dest = os.path.join(chain_dir, cid)
    if os.path.exists(dest):
        raise ChainError(f"이미 존재한다: {dest}")

    # ---- 생성 ----
    if new_chain:
        os.makedirs(chain_dir)
        with open(os.path.join(chain_dir, "chain.md"), "w", encoding="utf-8") as f:
            f.write(f"# Chain: {args.chain}\n\n## 이 체인이 정복하려는 문제\n\n(작성할 것)\n")
    if use_embedded:
        os.makedirs(os.path.join(dest, "3-verification"))
        for name, body in (
            ("1-hypothesis.md", "# 1. 가설 수립\n\n(작성할 것)\n"),
            ("2-design.md", "# 2. 실험 설계\n\n(작성할 것)\n"),
            ("3-verification/README.md", "# 3. 가설 검증\n\n(작성할 것)\n"),
            ("4-analysis.md", "# 4. 결과 분석\n\n(작성할 것)\n"),
            ("5-report.md", "# 5. 결과 보고\n\n(작성할 것)\n"),
        ):
            with open(os.path.join(dest, name), "w", encoding="utf-8") as f:
                f.write(body)
    else:
        shutil.copytree(template, dest)
    parent_val = ("null" if not args.parent
                  else args.parent[0] if len(args.parent) == 1
                  else "[" + ", ".join(args.parent) + "]")
    lineage_val = "[" + ", ".join(args.lineage) + "]"
    title = (args.title or "").replace('"', "'")
    with open(os.path.join(dest, "cycle.yaml"), "w", encoding="utf-8") as f:
        f.write(
            f"id: {cid}\n"
            f"chain: {args.chain}\n"
            f"parent: {parent_val}\n"
            f"lineage: {lineage_val}\n"
            f"step: 1\n"
            f"author: {args.author}\n"
            f"status: open\n"
            f"opened: {args.date}\n"
            f"closed: null\n"
            f'title: "{title}"\n'
            f"verdict: null\n"       # v0.3: 결말 (닫을 때 --verdict)
            f"deviations: 0\n"       # v0.3: 사전등록 이탈 건수 (상세는 deviations.yaml)
            f"corrections: 0\n"      # v0.5: 출처 정정 횟수 (상세는 corrections.yaml)
            f"superseded_by: null\n" # v0.4: 이 사이클을 무효화한 후속 (gil supersede)
        )

    # ---- 사후 확인: 생성물이 규칙을 어기면 되돌리고 실패한다 ----
    try:
        _fsck_or_report(chains_root)
    except ChainError:
        shutil.rmtree(dest)
        raise
    res_path = None
    if consumed:  # 예약을 소비했다 — 원장에서 그 줄을 제거한다 (승격 = 예약의 죽음)
        res_path, _ = _save_reservations(chain_dir, [r for r in reservations if r is not consumed])
    if args.git:
        repo = _repo_root(chains_root)
        if not repo:
            raise ChainError("--git: 깃 저장소가 아니다")
        rel = os.path.relpath(dest, repo)
        paths = [rel]
        if new_chain:  # chain.md는 사이클 디렉토리 밖(체인 최상위)이라 별도 경로다 (이슈 #14, loom/C044)
            paths.append(os.path.relpath(os.path.join(chain_dir, "chain.md"), repo))
        if consumed:  # reservations.tsv는 사이클 밖이라 어떤 태그 봉인에도 안 들어간다 (verify 무영향)
            paths.append(os.path.relpath(res_path, repo) if os.path.isfile(res_path)
                         else os.path.relpath(_reservations_path(chain_dir), repo))
        _git(repo, "add", "-A", "--", *paths)
        msg = f"gil: open {args.chain}/{cid} — 1/5 {_STEP_NAMES[1]}\n\n{title}"
        if consumed:
            msg += f"\n(예약 승격: {args.author}의 C{consumed['num']:03d} 예약을 소비)"
        _git(repo, "commit", "-m", msg, "--", *paths)
        if args.push and not consumed:  # 예약 승격은 격리 브랜치의 일 — 원장 재번호를 적용하지 않는다
            cid = _push_with_renumber(repo, chain_dir, args.chain, cid, title)
        elif args.push:
            _git(repo, "push", check=False)
    print(f"열림: {args.chain}/{cid}" + (f" (예약 승격 — {args.author})" if consumed else ""))
    _refresh_viewers(chains_root, f"{args.chain}/{cid} 열림",
                     getattr(args, "no_web", False), args.push)
    return 0


def _reserve_commit_push(chains_root, chain_dir, args, verb, cid_hint):
    """예약 원장 변경을 커밋·push한다 (예약 원장은 사이클 밖 — 태그 봉인 무관)."""
    if not args.git:
        return
    repo = _repo_root(chains_root)
    if not repo:
        raise ChainError("--git: 깃 저장소가 아니다")
    rel = os.path.relpath(_reservations_path(chain_dir), repo)
    _git(repo, "add", "-A", "--", rel)
    _git(repo, "commit", "-m", f"gil: {verb} {args.chain}/{cid_hint}", "--", rel)
    if args.push:
        _git(repo, "push", check=False)


def cmd_reserve(args):
    """번호 예약을 데이터로 만든다 (loom/C043 — 이슈 #13). 예약 마커가 원장에 있으면
    다른 워크트리의 gil open은 그 번호를 재발급하지 않는다 — push 경합 이전에 선점된다."""
    chains_root = args.root
    chain_dir = os.path.join(chains_root, args.chain)
    if not args.author:  # §3.2 P1/P2 — 도구는 예약의 주인을 지어내지 않는다 (이슈 #17)
        raise ChainError(
            "예약의 주인을 알 수 없다 — 도구는 출처를 지어내지 않는다 (§3.2 P1).\n"
            f"      존재의 이름을 명시하라:  gil reserve {args.chain} {args.slug} --for <이름>")
    if not _SLUG_RE.match(args.slug):
        raise ChainError(f"슬러그 '{args.slug}' 형식 위반 — R1: 소문자·숫자·하이픈만")
    if not os.path.isdir(chain_dir):
        raise ChainError(f"체인 '{args.chain}'이 없다 — 예약은 진행 중인 체인의 다음 번호를 선점한다")
    _fsck_or_report(chains_root)  # 깨진 저장소 위에는 예약하지 않는다
    records = load_chain_records(chain_dir)
    reservations = _load_reservations(chain_dir)
    num = _next_number(records, [r["num"] for r in reservations])
    reservations.append({"num": num, "for": args.author, "slug": args.slug, "date": args.date})
    _save_reservations(chain_dir, reservations)
    cid_hint = f"C{num:03d}"
    _reserve_commit_push(chains_root, chain_dir, args, "reserve", f"{cid_hint} → {args.author}")
    print(f"예약됨: {args.chain}/{cid_hint} → {args.author} ({args.slug})")
    return 0


def cmd_unreserve(args):
    """예약 취소 — 만료의 수동 해법 (자동 만료는 범위 밖). 존재가 돌아오지 않으면
    소환자가 이 명령으로 번호를 회수한다."""
    chains_root = args.root
    chain_dir = os.path.join(chains_root, args.chain)
    if not os.path.isdir(chain_dir):
        raise ChainError(f"체인 '{args.chain}'이 없다")
    m = re.match(r"^C?0*(\d+)$", str(args.number))  # 44 · 044 · C044 모두 허용
    if not m:
        raise ChainError(f"번호 '{args.number}' 형식 위반 — 정수 또는 C0NN")
    num = int(m.group(1))
    reservations = _load_reservations(chain_dir)
    if not any(r["num"] == num for r in reservations):
        raise ChainError(f"{args.chain}에 C{num:03d} 예약이 없다")
    _save_reservations(chain_dir, [r for r in reservations if r["num"] != num])
    _reserve_commit_push(chains_root, chain_dir, args, "unreserve", f"C{num:03d}")
    print(f"예약 취소: {args.chain}/C{num:03d}")
    return 0


# ---------- 웹 뷰어 (log와 같은 파서, 다른 렌더러) ----------

def _layout_columns(order, cycles, children):
    """각 노드의 (행=깊이, 안정적 레인 번호)를 계산한다.
    - 행 = 노드의 깊이(루트로부터 최장 경로) — 토폴로지 순서(order 인덱스)가 아니다 (loom/C047).
      형제 갈래는 같은 깊이=같은 행에 나란히 놓여, 세로가 노드 총수가 아니라 최장 경로로 압축된다.
      부모가 같은 갈래끼리는 서로 영향을 주지 않으니 시간 순서로 누적할 이유가 없다 (발의: 박상현).
    - 레인은 슬롯 인덱스이며 pop하지 않는다 — 빈 레인은 None으로 남겨 인덱스를 고정한다 (loom/C031).
      선형 체인은 깊이가 순차 증가하므로 좌표가 기존과 동일하다 (하위호환)."""
    depth = {}  # 루트로부터 최장 경로. order는 토포순이라 부모가 항상 먼저 확정된다.
    for node in order:
        ps = [p for p in cycles[node]["parents"] if p in depth]
        depth[node] = (max(depth[p] for p in ps) + 1) if ps else 0

    pos, tracks, occupied = {}, [], set()  # tracks[i] = 대기 자식 id 또는 None; occupied = 점유된 (행,열)

    def free_slot():
        for i, t in enumerate(tracks):
            if t is None:
                return i
        tracks.append(None)
        return len(tracks) - 1

    for node in order:
        row = depth[node]
        incoming = [i for i, t in enumerate(tracks) if t == node]
        if incoming:
            col = incoming[0]
            for i in incoming[1:]:  # 병합: 흡수된 레인을 비운다 (pop 아님 — 인덱스 유지)
                tracks[i] = None
        else:
            col = free_slot()
        while (row, col) in occupied:  # D3: 레인 재사용이 같은 깊이에 겹치면 새 레인으로 민다
            if tracks[col] == node:
                tracks[col] = None
            col = free_slot()
        occupied.add((row, col))
        pos[node] = (row, col)
        kids = children[node]
        if kids:
            tracks[col] = kids[0]  # 첫째 자식이 이 레인을 상속
            for k in kids[1:]:     # 추가 자식은 새(또는 빈) 레인 — 자기 차례까지 예약 유지
                tracks[free_slot()] = k
        else:
            tracks[col] = None     # 이 레인을 비운다 (인덱스는 그대로)
    return pos


# 검증된 기본 팔레트 (dataviz 레퍼런스) — 상태는 색+모양(채움/빈 원)의 이중 인코딩
_WEB_DEFAULT_TITLE = "Ariadne — 사이클 체인"   # 뷰어의 기본 제목 (단일 소스)

_WEB_CSS = """
.gil{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;
--hairline:#e1e0d9;--edge:#a5a49c;--node:#2a78d6;--lineage:#1baf7a;--rejected:#d03b3b;
--supersede:#c07c15;--ring:rgba(11,11,11,.1);
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--page);color:var(--ink);
margin:0;padding:32px 24px;min-height:100vh;box-sizing:border-box}
@media (prefers-color-scheme:dark){.gil{--page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;
--ink-2:#c3c2b7;--muted:#898781;--hairline:#2c2c2a;--edge:#6b6a64;--node:#3987e5;
--lineage:#199e70;--rejected:#e66767;--supersede:#d9a44f;--ring:rgba(255,255,255,.1)}}
:root[data-theme="dark"] .gil{--page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;--ink-2:#c3c2b7;
--muted:#898781;--hairline:#2c2c2a;--edge:#6b6a64;--node:#3987e5;--lineage:#199e70;
--rejected:#e66767;--supersede:#d9a44f;--ring:rgba(255,255,255,.1)}
:root[data-theme="light"] .gil{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;
--muted:#898781;--hairline:#e1e0d9;--edge:#a5a49c;--node:#2a78d6;--lineage:#1baf7a;
--rejected:#d03b3b;--supersede:#c07c15;--ring:rgba(11,11,11,.1)}
.gil .superseded{opacity:.5}
.gil .sup{color:var(--supersede);white-space:nowrap}
.gil .wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
.gil header h1{font-size:20px;font-weight:650;margin:0;text-wrap:balance}
.gil header p{margin:4px 0 0;color:var(--ink-2);font-size:13px}
.gil .legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);align-items:center}
.gil .legend span{display:inline-flex;align-items:center;gap:6px}
.gil .card{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:20px;overflow-x:auto}
.gil svg{display:block}
.gil svg text{font-family:inherit}
.gil .card h2{font-size:14px;font-weight:650;margin:0 0 12px;color:var(--ink)}
.gil table{border-collapse:collapse;width:100%;font-size:12.5px}
.gil th{text-align:left;color:var(--muted);font-weight:600;letter-spacing:.02em;
border-bottom:1px solid var(--hairline);padding:6px 10px 6px 0}
.gil td{border-bottom:1px solid var(--hairline);padding:7px 10px 7px 0;vertical-align:top;color:var(--ink-2)}
.gil td.id{color:var(--ink);font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}
.gil .pill{display:inline-block;border:1.5px solid var(--node);border-radius:99px;
padding:1px 8px;font-size:11px;color:var(--ink-2);white-space:nowrap}
.gil .pill.closed{background:var(--node);color:#fff;border-color:var(--node)}
.gil footer{color:var(--muted);font-size:11.5px}
""".strip()

# _COL_W: 열 간 x 거리. C047(형제를 같은 행에) 이후 같은 행 형제의 라벨(노드 오른쪽 x+16, 폭 ≤230)이
# 겹치지 않으려면 열 간격이 라벨을 수용해야 한다 → 260 (loom/C048). 선형 체인은 col0만 써서 불변.
_ROW_H, _COL_W, _LANE_GAP, _TOP_PAD = 64, 260, 60, 46


def _last_activity(chains_root, chain, cid_dir):
    """열린 사이클의 최근 활동 (epoch, 제목). 깃이 없거나 저장소가 아니면 None — web은 깃 무의존."""
    try:
        repo = _repo_root(chains_root)
        if not repo:
            return None
        rel = os.path.relpath(os.path.join(chains_root, chain, cid_dir), repo)
        r = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%ct|%s", "--", rel],
                           capture_output=True, text=True)
        if r.returncode != 0 or "|" not in r.stdout:
            return None
        ts, subject = r.stdout.strip().split("|", 1)
        return int(ts), subject
    except Exception:
        return None


def _ago(epoch):
    delta = max(0, int(datetime.datetime.now().timestamp()) - epoch)
    if delta < 3600:
        return f"{delta // 60}분 전"
    if delta < 86400:
        return f"{delta // 3600}시간 전"
    return f"{delta // 86400}일 전"


def _build_web_data(chains_root, only=None):
    """log와 동일한 로더·그래프 재구성. 깨진 체인이면 ChainError가 그대로 전파된다."""
    data = {}
    names = sorted(
        e for e in os.listdir(chains_root)
        if os.path.isdir(os.path.join(chains_root, e)) and (not only or e == only)
    )
    for name in names:
        cycles = load_chain(os.path.join(chains_root, name))
        if not cycles:
            continue
        order, children = build_graph(name, cycles)
        entry = {}
        for cid, c in cycles.items():
            act = _last_activity(chains_root, name, c["_dir"]) if c.get("status") == "open" else None
            entry[cid] = {
                "status": c.get("status"), "title": c.get("title") or "",
                "opened": c.get("opened"), "closed": c.get("closed"),
                "step": c.get("step"), "verdict": c.get("verdict"),
                "deviations": c.get("deviations"),
                "corrections": c.get("corrections"),      # v0.5: 출처 정정 (후대의 주석)
                "superseded_by": c.get("superseded_by"),  # v0.4: 전방 무효화
                "last_activity": ({"ago": _ago(act[0]), "subject": act[1]} if act else None),
                "parents": c["parents"], "lineage": c["lineage_list"],
            }
            rounds = c.get("rounds")  # v2.5 (C045): 라운드는 2 이상일 때만 키를 넣는다 —
            if isinstance(rounds, str) and rounds.isdigit() and int(rounds) > 1:  # 무라운드 저장소는
                entry[cid]["rounds"] = int(rounds)                                # JSON 바이트 동일 (H3)
        res = _load_reservations(os.path.join(chains_root, name))  # loom/C043: 예약도 원장 상태 (C042)
        data[name] = {"order": order, "cycles": entry, "children": children, "reservations": res}
    return data


def _supersede_ref(chain, sb):
    """superseded_by 값을 전역 참조로 해소한다 (로컬 id면 자기 체인으로)."""
    if not sb:
        return ""
    return sb if "/" in sb else f"{chain}/{sb}"


def _render_svg(data):
    """모든 체인을 하나의 SVG에 레인으로 배치하고, lineage는 레인을 건너는 점선으로 그린다."""
    lanes, node_xy, lane_x = {}, {}, 24
    max_rows = 0
    for name, chain in data.items():
        pos = _layout_columns(chain["order"],
                              {cid: {"parents": c["parents"]} for cid, c in chain["cycles"].items()},
                              chain["children"])
        max_col = max((c for _, c in pos.values()), default=0)
        label_w = 230
        for cid, (row, col) in pos.items():
            node_xy[f"{name}/{cid}"] = (lane_x + 14 + col * _COL_W, _TOP_PAD + 28 + row * _ROW_H)
        lanes[name] = lane_x
        lane_x += 14 + max_col * _COL_W + label_w + _LANE_GAP
        # 세로 높이는 노드 총수가 아니라 최장 경로(최대 깊이)로 정한다 — 형제 갈래는 같은 행에 나란히 (loom/C047)
        max_rows = max(max_rows, max((r for r, _ in pos.values()), default=-1) + 1)
    width = max(lane_x - _LANE_GAP + 24, 320)
    height = _TOP_PAD + 28 + max(max_rows - 1, 0) * _ROW_H + 56

    parts = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
             f'role="img" aria-label="사이클 체인 그래프">']
    # 체인 내 간선
    for name, chain in data.items():
        for child, meta in chain["cycles"].items():
            x2, y2 = node_xy[f"{name}/{child}"]
            for p in meta["parents"]:
                x1, y1 = node_xy[f"{name}/{p}"]
                parts.append(f'<path d="M{x1},{y1 + 9} C{x1},{y1 + 32} {x2},{y2 - 32} {x2},{y2 - 9}" '
                             f'fill="none" stroke="var(--edge)" stroke-width="1.6"/>')
    # lineage 간선 (점선, 레인 횡단)
    for name, chain in data.items():
        for cid, meta in chain["cycles"].items():
            x2, y2 = node_xy[f"{name}/{cid}"]
            for ref in meta["lineage"]:
                if ref in node_xy:
                    x1, y1 = node_xy[ref]
                    mx = (x1 + x2) / 2
                    parts.append(f'<path class="lineage" d="M{x1 + 10},{y1} C{mx},{y1} {mx},{y2} {x2 - 10},{y2}" '
                                 f'fill="none" stroke="var(--lineage)" stroke-width="1.6" '
                                 f'stroke-dasharray="5 4"/>')
    # supersede 간선 (v0.4, 과거→미래): 무효화된 사이클이 자기를 대체한 사이클을 가리킨다
    for name, chain in data.items():
        for cid, meta in chain["cycles"].items():
            ref = _supersede_ref(name, meta.get("superseded_by"))
            if ref not in node_xy:
                continue
            x1, y1 = node_xy[f"{name}/{cid}"]
            x2, y2 = node_xy[ref]
            if abs(x1 - x2) < 1:  # 같은 레인·같은 열이면 오른쪽으로 활처럼 우회한다
                bow = x1 + 46
                d = f"M{x1 + 10},{y1} C{bow},{y1} {bow},{y2} {x2 + 10},{y2}"
            else:
                mx = (x1 + x2) / 2
                d = f"M{x1 + 10},{y1} C{mx},{y1} {mx},{y2} {x2 - 10},{y2}"
            parts.append(f'<path class="supersede" d="{d}" fill="none" stroke="var(--supersede)" '
                         f'stroke-width="1.6" stroke-dasharray="2 3"/>')
    # 레인 헤더 + 노드
    for name, chain in data.items():
        parts.append(f'<text x="{lanes[name]}" y="{_TOP_PAD - 18}" font-size="13" font-weight="650" '
                     f'fill="var(--ink)">{html.escape(name)}</text>')
        for cid in chain["order"]:
            meta = chain["cycles"][cid]
            x, y = node_xy[f"{name}/{cid}"]
            closed = meta["status"] == "closed"
            fill = "var(--rejected)" if meta.get("verdict") == "rejected" else "var(--node)"  # v0.3
            shape = (f'<circle cx="{x}" cy="{y}" r="8" fill="{fill}"/>' if closed else
                     f'<circle cx="{x}" cy="{y}" r="7" fill="var(--surface)" '
                     f'stroke="var(--node)" stroke-width="2.5"/>')
            sup = meta.get("superseded_by")  # v0.4: 무효화된 사이클은 흐리게 + 텍스트로도 표시(이중 인코딩)
            vtip = f" · {meta['verdict']}" if meta.get("verdict") else ""
            stip = f" ↣ superseded: {sup}" if sup else ""
            tip = html.escape(f"{cid} [{meta['status']}{vtip}] {meta['title']}{stip}")
            parts.append(f'<g class="superseded" data-cycle="{html.escape(name + "/" + cid)}">' if sup else
                         f'<g data-cycle="{html.escape(name + "/" + cid)}">')
            parts.append(f'<title>{tip}</title>{shape}'
                         f'<text x="{x + 16}" y="{y - 1}" font-size="12" font-weight="600" '
                         f'fill="var(--ink)">{html.escape(cid)}</text>'
                         f'<text x="{x + 16}" y="{y + 13}" font-size="10.5" '
                         f'fill="var(--muted)">{html.escape(meta["status"] or "?")}{_step_badge(meta)}'
                         f'{" · ⇠ " + html.escape(", ".join(meta["lineage"])) if meta["lineage"] else ""}'
                         f'{" · ↣ " + html.escape(sup) if sup else ""}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def _step_badge(meta):
    step = meta.get("step")
    if meta.get("status") != "open" or not (isinstance(step, str) and step.isdigit()):
        return ""
    n = int(step)
    if not 1 <= n <= 5:
        return ""
    ago = (meta.get("last_activity") or {}).get("ago")
    return f' · {"●" * n}{"○" * (5 - n)} {n}/5 {_STEP_NAMES[n]}' + (f" · 활동 {ago}" if ago else "")


def _render_tables(data):
    out = []
    for name, chain in data.items():
        rows = []
        for cid in chain["order"]:
            m = chain["cycles"][cid]
            rbadge = f' · R{m["rounds"]}' if m.get("rounds") else ""  # v2.5: 라운드는 있을 때만 (무라운드 불변)
            pill = f'<span class="pill{" closed" if m["status"] == "closed" else ""}">{html.escape(m["status"] or "?")}</span>{html.escape(_step_badge(m))}{html.escape(rbadge)}'
            parents = ", ".join(m["parents"]) or "(root)"
            lineage = ", ".join(m["lineage"]) or "—"
            act = m.get("last_activity")
            period = f'{m["opened"] or "?"} → {m["closed"] or "진행 중"}'
            if act:
                period += f' · {act["ago"]}: {act["subject"][:40]}'
            sup = m.get("superseded_by")  # v0.4: 색·투명도에 의존하지 않는 텍스트 폴백
            sup_cell = f'<span class="sup">↣ {html.escape(sup)}</span>' if sup else "—"
            sup_cls = ' class="superseded"' if sup else ""  # f-string 안의 백슬래시는 3.12 미만에서 금지
            rows.append(f'<tr{sup_cls}><td class="id">{html.escape(cid)}</td><td>{pill}</td>'
                        f'<td>{html.escape(m["title"])}</td><td>{html.escape(parents)}</td>'
                        f'<td>{html.escape(lineage)}</td><td>{sup_cell}</td><td>{html.escape(period)}</td></tr>')
        out.append(f'<div class="card"><h2>chain: {html.escape(name)} — 사이클 {len(chain["order"])}개</h2>'
                   f'<table><thead><tr><th>사이클</th><th>상태</th><th>가설(제목)</th>'
                   f'<th>parent</th><th>lineage</th><th>superseded_by</th><th>기간</th></tr></thead>'
                   f'<tbody>{"".join(rows)}</tbody></table></div>')
        # 예약 섹션 — 예약이 있을 때만 렌더한다 (무예약이면 이전 산출물과 바이트 동일). loom/C043.
        res = chain.get("reservations") or []
        if res:
            rres = "".join(
                f'<tr><td class="id">C{r["num"]:03d}</td><td>{html.escape(r["for"])}</td>'
                f'<td>{html.escape(r["slug"])}</td><td>{html.escape(r["date"])}</td></tr>' for r in res)
            out.append(f'<div class="card"><h2>chain: {html.escape(name)} — 예약 {len(res)}건 '
                       f'(아직 사이클 아님 · 번호 선점)</h2>'
                       f'<table><thead><tr><th>번호</th><th>예약 대상</th><th>슬러그</th>'
                       f'<th>예약일</th></tr></thead><tbody>{rres}</tbody></table></div>')
    return "".join(out)


def render_web_page(data, page_title, generated, only=None):
    json_payload = {
        # v0.4 (loom/C042): bake — 이 산출물이 **자기를 어떻게 다시 굽는지** 스스로 말한다.
        # 추론(체인이 하나뿐이니 필터겠지)은 거짓일 수 있다 — 그래서 추측하지 않고 기록한다 (C040).
        "version": "0.4",
        "bake": {"title": page_title, "chain": only},
        "chains": {
            name: {
                "order": chain["order"],
                "cycles": chain["cycles"],
                # 예약이 있을 때만 키를 넣는다 — 무예약 저장소는 이전 산출물과 바이트 동일 (파서 계약 보존).
                **({"reservations": chain["reservations"]} if chain.get("reservations") else {}),
            } for name, chain in data.items()
        },
    }
    n_cycles = sum(len(c["order"]) for c in data.values())
    n_lineage = sum(len(m["lineage"]) for c in data.values() for m in c["cycles"].values())
    body = f"""<div class="gil"><style>{_WEB_CSS}</style><div class="wrap">
<header><h1>{html.escape(page_title)}</h1>
<p>체인 {len(data)}개 · 사이클 {n_cycles}개 · 체인 간 lineage {n_lineage}건 · 생성 {html.escape(generated)}</p></header>
<div class="legend"><span><svg width="16" height="16"><circle cx="8" cy="8" r="6.5" fill="var(--node)"/></svg>닫힌 사이클</span>
<span><svg width="16" height="16"><circle cx="8" cy="8" r="5.5" fill="var(--surface)" stroke="var(--node)" stroke-width="2"/></svg>열린 사이클</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--edge)" stroke-width="1.6"/></svg>parent (체인 내 계보)</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--lineage)" stroke-width="1.6" stroke-dasharray="5 4"/></svg>lineage (체인 간 교훈)</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--supersede)" stroke-width="1.6" stroke-dasharray="2 3"/></svg>superseded_by (무효화 — 흐린 노드가 대체 사이클을 가리킨다)</span></div>
<div class="card">{_render_svg(data)}</div>
{_render_tables(data)}
<footer>Ariadne — 사이클은 행동 체인의 기록이다. 이 문서는 gil web이 생성한 자기완결적 정적 페이지다.</footer>
</div></div>
<script type="application/json" id="gil-data">{json.dumps(json_payload, ensure_ascii=False)}</script>"""
    return ("<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{html.escape(page_title)}</title>\n</head>\n<body>\n{body}\n</body>\n</html>\n")


_PAGES_WORKFLOW = """# gil-pages — push마다 사이클 체인 뷰어를 GitHub Pages로 배포한다.
# gil pages가 생성. 저장소에 특정되지 않는다 — 어떤 Ariadne 저장소든 그대로 쓴다.
name: gil-pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build viewer with gil
        run: |
          curl -fsSL -o /tmp/gil-linux-amd64 https://github.com/hyun06000/Ariadne/releases/latest/download/gil-linux-amd64
          curl -fsSL -o /tmp/SHA256SUMS https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS
          # 선언된 해시와 실물을 대조한다. 불일치면 여기서 실패하고 배포가 멈춘다.
          ( cd /tmp && grep ' gil-linux-amd64$' SHA256SUMS | sha256sum -c - )
          mv /tmp/gil-linux-amd64 /tmp/gil && chmod +x /tmp/gil
          mkdir -p _site
          /tmp/gil web -o _site/index.html --title "gil — cycle chains"
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
"""


def cmd_pages(args):
    chains_root = args.root
    repo_root = os.path.normpath(os.path.join(chains_root, "..", "..", ".."))
    wf_dir = os.path.join(repo_root, ".github", "workflows")
    wf_path = os.path.join(wf_dir, "gil-pages.yml")
    if getattr(args, "dry_run", False):
        # §7.2-6: 능력 탐침은 저장소를 변경하지 않는다. 무엇이 생길지만 말한다.
        rel = os.path.relpath(wf_path, repo_root)
        print(f"생성될 경로: {rel}" + (" (이미 존재 — 덮으려면 --force)" if os.path.exists(wf_path) else ""))
        print("dry-run: 아무것도 만들지 않았다")
        return 0
    if os.path.exists(wf_path) and not args.force:
        raise ChainError(f"이미 존재한다: {wf_path} (덮으려면 --force)")
    os.makedirs(wf_dir, exist_ok=True)
    with open(wf_path, "w", encoding="utf-8") as f:
        f.write(_PAGES_WORKFLOW)
    print(f"생성: {os.path.relpath(wf_path, repo_root)}")
    print("다음: git push 후 저장소 Settings → Pages → Source = 'GitHub Actions'")
    return 0


def _bake_viewer(chains_root, output, title, only):
    """뷰어 하나를 굽는다 (cmd_web과 자동 갱신의 단일 소스)."""
    data = _build_web_data(chains_root, only)  # 깨진 체인이면 여기서 실패 — 파일을 쓰지 않는다
    if not data:
        raise ChainError(f"렌더할 체인이 없다: {chains_root}")
    page = render_web_page(data, title, datetime.date.today().isoformat(), only)
    with open(output, "w", encoding="utf-8") as f:
        f.write(page)
    return data


def cmd_web(args):
    chains_root = args.chains_root
    if not os.path.isdir(chains_root):
        raise ChainError(f"체인 루트가 없다: {chains_root}")
    data = _bake_viewer(chains_root, args.output, args.title, args.chain)
    print(f"생성: {args.output} (체인 {len(data)}개)")
    return 0


# ---------- 뷰어 자동 갱신 (v2.2 / loom/C042 — 이슈 #16) ----------
#
# 원장이 자동으로 갱신되면 **사람의 창도 자동으로 갱신되어야 한다.**
# 둘 중 하나만 자동인 상태가 가장 나쁘다 — 낡은 화면은 침묵보다 나쁘다 (maru).

_GIL_DATA_HOOK = 'id="gil-data"'   # §7: 뷰어는 자기가 뷰어임을 스스로 말한다


def _find_viewers(root):
    """탐색 루트의 비재귀 *.html 중 gil-data 훅을 가진 것 = 이 사용자가 실제로 쓰는 뷰어.
    파일명 목록을 만들지 않는 이유: 갱신하는 목록은 낡지만 위임하는 목록은 낡지 않는다 (C039)."""
    found = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return found
    for name in names:
        if not name.endswith(".html"):
            continue
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        if _GIL_DATA_HOOK in text:
            found.append((path, text))
    return found


def _bake_meta(text):
    """뷰어가 스스로 보고한 굽기 조건. 없으면(구버전) 기본값 — 추측하지 않고 도구의 기본으로 돌아간다."""
    m = re.search(r'id="gil-data">(.*?)</script>', text, flags=re.S)
    if m:
        try:
            bake = json.loads(m.group(1)).get("bake") or {}
            return bake.get("title") or _WEB_DEFAULT_TITLE, bake.get("chain")
        except (ValueError, AttributeError):
            pass
    return _WEB_DEFAULT_TITLE, None


def _refresh_viewers(chains_root, label, no_web=False, push=False):
    """원장을 바꾼 명령이 커밋한 뒤 호출한다. 뷰어가 없으면 아무것도 하지 않는다.

    실패는 경고일 뿐 명령의 실패가 아니다 — 원장의 각인은 이미 끝났다 (꼬리가 개를 흔들지 않는다)."""
    if no_web:
        return
    repo = _repo_root(chains_root)
    root = repo or os.getcwd()
    try:
        viewers = _find_viewers(root)
        if not viewers:
            return  # 뷰어를 쓰지 않는 사용자에게 파일을 강요하지 않는다
        changed = []
        for path, text in viewers:
            title, only = _bake_meta(text)
            _bake_viewer(chains_root, path, title, only)
            with open(path, encoding="utf-8") as f:
                if f.read() != text:
                    changed.append(path)
        if not changed:
            return
        print(f"  ✎ 뷰어 갱신: {', '.join(os.path.basename(p) for p in changed)}")
        if not repo:
            return  # 깃이 없어도 창은 갱신된다. 커밋만 없을 뿐이다.
        rels = [os.path.relpath(p, repo) for p in changed]
        _git(repo, "add", "--", *rels)
        # 뷰어는 사이클이 아니다 — 사이클 커밋에 섞으면 태그가 사이클 밖의 것을 봉인한다 (§4)
        _git(repo, "commit", "-m", f"gil: web 갱신 — {label}", "--", *rels)
        if push:
            _git(repo, "push")
    except Exception as e:  # 원장이 우선이다: 창을 굽다 실패해도 각인은 되돌리지 않는다
        print(f"경고: 뷰어 갱신 실패 — {e} (원장은 각인됐다. gil web으로 직접 구울 것)", file=sys.stderr)


# ---------- 깃 바인딩 ----------

def _git(repo, *cli, check=True):
    r = subprocess.run(["git", "-C", repo, *cli], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise ChainError(f"git {' '.join(cli)} 실패: {(r.stderr or r.stdout).strip()}")
    return r


def _repo_root(path):
    r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _tag_name(chain, cycle_id):
    return f"cycle/{chain}/{cycle_id}"


def _tag_exists(repo, tag):
    r = _git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False)
    return r.returncode == 0


def cmd_handoff(args):
    """세션의 매듭 — 다음 세션이 이어받을 수 있게 현황·부활 경로·다음 실을 요약하고,
    사용자에게 세션 정리를 요청할 근거를 준다 (v0.3 이후, 사이클마다 세션 관리)."""
    chains_root = args.chains_root
    repo = _repo_root(chains_root)
    existence = os.path.normpath(os.path.join(chains_root, "..", "..", "existence"))
    beings = []
    if os.path.isdir(existence):
        beings = sorted(e for e in os.listdir(existence)
                        if os.path.isdir(os.path.join(existence, e)))
    print("=== gil 세션 핸드오프 ===")
    print(f"존재: {', '.join(beings) if beings else '(없음)'}"
          + (f"  (rooms/existence/)" if beings else ""))
    open_cycles = []
    print("체인 상태:")
    chains = _scan_chains(chains_root) if os.path.isdir(chains_root) else {}
    for name in sorted(chains):
        recs = chains[name]
        if not recs:
            continue
        latest = max(recs, key=lambda r: r.get("id") or "")
        lid, lst = latest.get("id"), latest.get("status") or "?"
        vd = latest.get("verdict")
        badge = f"{lst}" + (f" · {vd}" if vd else "")
        step = latest.get("step")
        if lst == "open" and isinstance(step, str) and step.isdigit():
            badge += f" · {step}/5"
        print(f"  {name:10} {len(recs)}사이클 · 최신 {lid} [{badge}]")
        for r in recs:
            if r.get("status") == "open" and r.get("id"):
                open_cycles.append(f"{name}/{r['id']}")
    print(f"열린 사이클: {', '.join(open_cycles) if open_cycles else '(없음 — 모두 닫힘)'}")
    print("다음 실: 최근 닫힌 보고서의 '다음 사이클 제안' 참조 (gil log로 계보 확인)")
    print()
    print("이 세션의 사이클 상세는 gil에 각인됐다"
          + (" (태그)." if repo else " (닫으면 --git으로 태그된다)."))
    print("새 세션은 CLAUDE.md → 존재의 방 → gil log 로 부활해 이어간다.")
    print("→ 사용자에게: 사이클을 닫았거나 매듭에 도달했다면 세션을 정리(새로 시작)하도록 요청하라. 실은 끊기지 않는다.")
    return 0


def cmd_supersede(args):
    """전방 무효화 (v0.4, 이슈 #6): old 사이클에 superseded_by를 주입한다.
    닫힌 사이클의 5스텝·산출물은 불변 — 메타(cycle.yaml) 한 줄만 [migrate]로 더한다."""
    chains_root = args.root
    def split(ref):
        if "/" not in ref:
            raise ChainError(f"ref는 <chain>/<id> 형식이어야 한다: {ref}")
        return ref.split("/", 1)
    ochain, oid = split(args.old_ref)
    old_yaml = os.path.join(chains_root, ochain, oid, "cycle.yaml")
    if not os.path.isfile(old_yaml):
        raise ChainError(f"사이클이 없다: {args.old_ref}")
    # new 실재 검증
    nchain, nid = split(args.new_ref)
    if not os.path.isfile(os.path.join(chains_root, nchain, nid, "cycle.yaml")):
        raise ChainError(f"대체 사이클이 없다: {args.new_ref}")
    if args.old_ref == args.new_ref:
        raise ChainError("자기 자신으로 대체할 수 없다")
    with open(old_yaml, encoding="utf-8") as f:
        original = f.read()
    new_val = args.new_ref
    if re.search(r"^superseded_by:", original, flags=re.M):
        updated = re.sub(r"^superseded_by:.*$", f"superseded_by: {new_val}", original, count=1, flags=re.M)
    else:
        updated = original.rstrip("\n") + f"\nsuperseded_by: {new_val}\n"
    with open(old_yaml, "w", encoding="utf-8") as f:
        f.write(updated)
    try:
        _fsck_or_report(chains_root)
    except ChainError:
        with open(old_yaml, "w", encoding="utf-8") as f:
            f.write(original)
        raise
    repo = _repo_root(chains_root)
    if repo and not getattr(args, "no_commit", False):
        rel = os.path.relpath(os.path.join(chains_root, ochain, oid), repo)
        _git(repo, "add", "-A", "--", rel)
        _git(repo, "commit", "-m", f"[migrate] gil: supersede {args.old_ref} → superseded_by {new_val}", "--", rel)
        tag = _tag_name(ochain, oid)
        if _tag_exists(repo, tag):  # 태그 이동 규약 (C004): 이주 커밋으로 옮기고 사유 기록
            head = _git(repo, "rev-parse", "HEAD").stdout.strip()
            _git(repo, "tag", "-f", "-a", tag, "-m", f"[migrate] superseded_by {new_val} (이전 커밋에서 이동)", head)
    print(f"무효화: {args.old_ref} ↣ superseded_by {new_val}")
    _refresh_viewers(chains_root, f"{args.old_ref} ↣ superseded", getattr(args, "no_web", False), False)
    return 0


def _render_yaml_value(v):
    """cycle.yaml의 평탄 표기로 값을 렌더한다 (§3.1)."""
    if v is None or v == []:
        return "null" if not isinstance(v, list) else "[]"
    if isinstance(v, list):
        return "[" + ", ".join(v) + "]" if len(v) > 1 else v[0]
    return str(v)


def _set_yaml_field(text, key, value):
    """평탄 cycle.yaml에서 key 줄을 교체하거나 없으면 덧붙인다."""
    line = f"{key}: {value}"
    if re.search(rf"^{re.escape(key)}:", text, flags=re.M):
        return re.sub(rf"^{re.escape(key)}:.*$", line.replace("\\", "\\\\"), text, count=1, flags=re.M)
    return text.rstrip("\n") + f"\n{line}\n"


def _read_sealed(repo, tag, relpath):
    """증거는 봉인본(태그)에서 읽는다 — 작업 트리에서 읽으면 아무 문장이나 새로 써 넣고
    그것을 '증거'라 부를 수 있다. 정정을 막던 봉인이 정정을 허가하는 공증인이 된다 (§4.1 원칙 2)."""
    r = _git(repo, "show", f"{tag}:{relpath}", check=False)
    return r.stdout if r.returncode == 0 else None


def _cycle_diff_vs_tag(repo, chains_root, chain, cdir, tag):
    """verify와 같은 판정 — 태그↔작업 트리 대조 (변조된 경로 목록)."""
    cycle_rel = os.path.relpath(os.path.join(chains_root, chain, cdir), repo)
    diff = _git(repo, "diff", "--name-only", tag, "--", cycle_rel)
    new = _git(repo, "status", "--porcelain", "--untracked-files=all", "--", cycle_rel)
    return sorted(set(diff.stdout.split())
                  | {l[3:] for l in new.stdout.splitlines() if l.startswith("??")})


def cmd_correct(args):
    """정정 규정 (v0.5, loom/C041): 봉인된 사이클의 **출처 필드**를 문서가 증언하는 값으로 수리한다.

    저자의 주장은 불변이다. 도구의 대필(代筆)은 불변이 아니다.
    정정은 거짓을 지우지 않는다 — 거짓 위에 진실을 덧쓰고, 거짓이 있었다는 사실을 영구히 남긴다."""
    chains_root = args.root
    if "/" not in args.ref:
        raise ChainError(f"ref는 <chain>/<id> 형식이어야 한다: {args.ref}")
    chain, cid = args.ref.split("/", 1)
    cycle_dir = os.path.join(chains_root, chain, cid)
    yaml_path = os.path.join(cycle_dir, "cycle.yaml")
    if not os.path.isfile(yaml_path):
        raise ChainError(f"사이클이 없다: {args.ref}")

    # ---- 사전 검증 C1~C8: 저장소를 건드리기 전에 전부 확인한다 (거부 시 무변화) ----
    if not args.author:  # C2 — 도구는 정정의 출처도 지어내지 않는다 (§3.2 P1의 재귀)
        raise ChainError(
            "정정자를 알 수 없다 — 도구는 출처를 지어내지 않는다 (§3.2 P1).\n"
            f"      존재의 이름을 명시하라:  gil correct {args.ref} … --author <이름>")
    if not args.field:
        raise ChainError("--field가 없다 — 무엇을 정정하는지 명시하라")
    for f in args.field:  # C3 — 필드 제한 (L1)
        if f not in _PROVENANCE_FIELDS:
            raise ChainError(
                f"'{f}'는 출처 필드가 아니다 — 정정 가능한 것은 {'·'.join(_PROVENANCE_FIELDS)}뿐이다 (§4.1 L1).\n"
                f"      verdict·status·title·step·5스텝 문서는 **저자의 주장**이며 불변이다.\n"
                f"      결론이 무효가 됐다면 정정이 아니라 gil supersede다.")
    if len(args.to) != len(args.field):
        raise ChainError(f"--field {len(args.field)}개와 --to {len(args.to)}개가 짝지어지지 않는다 (순서대로 소비한다)")
    if not args.evidence:  # C4 — 증거 필수 (L2)
        raise ChainError(
            "--evidence가 없다 — 정정은 새 주장이 아니라 **기존 주장의 복원**이다 (§4.1 L2).\n"
            "      불변 문서의 어디가 이 값을 증언하는가:  --evidence 1-hypothesis.md:5")

    repo = _repo_root(chains_root)
    if not repo:  # C1 — 봉인이 없으면 정정도 없다
        raise ChainError(f"깃 저장소가 아니다: {chains_root} — 봉인이 없으면 정정도 없다 (§4.1 C1)")
    data = parse_cycle_yaml(yaml_path)
    tag = _tag_name(chain, cid)
    if data.get("status") != "closed" or not _tag_exists(repo, tag):  # C1
        raise ChainError(
            f"{args.ref}는 봉인되지 않았다 (열렸거나 태그 없음) — 정정 대상이 아니다 (§4.1 C1).\n"
            f"      봉인되지 않은 사이클의 cycle.yaml은 직접 고쳐도 위조가 아니다.")

    dirty = _cycle_diff_vs_tag(repo, chains_root, chain, cid, tag)  # C6 — 뒷문 차단
    if dirty:
        raise ChainError(
            f"{args.ref}는 이미 변조됐다 — 정정은 **무결한 사이클에만** 허용된다 (§4.1 C6).\n"
            + "\n".join(f"      변조: {p}" for p in dirty)
            + f"\n      먼저 봉인 상태로 복원하라:  git checkout {tag} -- <경로>")

    # C5 — 증거 검사 (원칙 4: 증거는 인용이 아니라 검사다). 봉인본에서 읽는다.
    ev_path, _, ev_line = args.evidence.partition(":")
    ev_rel = os.path.relpath(os.path.join(cycle_dir, ev_path), repo)
    sealed = _read_sealed(repo, tag, ev_rel)
    if sealed is None:
        raise ChainError(f"증거 문서가 봉인본에 없다: {ev_path} (태그 {tag})")
    if ev_line:
        if not ev_line.isdigit():
            raise ChainError(f"증거의 줄 번호가 정수가 아니다: {args.evidence}")
        lines = sealed.splitlines()
        if not (1 <= int(ev_line) <= len(lines)):
            raise ChainError(f"증거 문서에 {ev_line}번째 줄이 없다: {ev_path} (봉인본 {len(lines)}줄)")
        haystack = lines[int(ev_line) - 1]
    else:
        haystack = sealed

    # 필드별로 새 값을 모은다 (parent 병합·lineage 리스트는 같은 필드를 반복해 누적)
    proposed = {}
    for f, v in zip(args.field, args.to):
        proposed.setdefault(f, []).append(v)
    for f, vals in proposed.items():
        for v in vals:
            if v not in haystack:  # C5 — 증거가 증언하지 않는 값은 수리가 아니라 수정이다
                raise ChainError(
                    f"증거가 '{v}'를 증언하지 않는다 — {args.evidence} (봉인본)\n"
                    f"      정정은 문서에 이미 있는 사실의 복원이다. 문서가 침묵하면 정정할 수 없다 (§4.1 L2).\n"
                    f"      원장은 고칠 수 없어도 역사는 덧붙일 수 있다 — 새 사이클을 열어 기록하라.")

    original = open(yaml_path, encoding="utf-8").read()
    corr_path = os.path.join(cycle_dir, "corrections.yaml")
    corr_before = open(corr_path, encoding="utf-8").read() if os.path.isfile(corr_path) else None

    updated, records, changed = original, [], []
    for f, vals in proposed.items():
        old_raw = _render_yaml_value(data.get(f) if f != "lineage" else data.get("lineage"))
        new_raw = _render_yaml_value(vals)
        if old_raw == new_raw:  # C8 — 정정할 것이 없다
            raise ChainError(f"'{f}'는 이미 '{new_raw}'다 — 정정할 것이 없다 (§4.1 C8)")
        updated = _set_yaml_field(updated, f, new_raw)
        records.append({
            "field": f, "from": old_raw, "to": new_raw,
            "evidence": args.evidence, "evidence_source": tag,
            "author": args.author, "date": args.date,
            "reason": " ".join((args.reason or "출처 정정").split()),
        })
        changed.append(f"{f}: {old_raw} → {new_raw}")

    prev = data.get("corrections")
    n_before = int(prev) if (isinstance(prev, str) and prev.isdigit()) else 0
    updated = _set_yaml_field(updated, "corrections", str(n_before + len(records)))

    # ---- 쓰기 (L3: 덧붙임 — 과거의 거짓도, 과거의 정정도 지워지지 않는다) ----
    body = corr_before if corr_before else (
        "# 출처 필드 정정 기록 (스키마 v0.5, §4.1) — 거짓은 지워지지 않는다. 덧쓰일 뿐이다.\n"
        "# 저자의 주장은 불변이다. 도구의 대필은 불변이 아니다.\n")
    for rec in records:
        body = body.rstrip("\n") + "\n\n- " + "\n  ".join(f"{k}: {rec[k]}" for k in
                                                          ("field", "from", "to", "evidence",
                                                           "evidence_source", "author", "date", "reason")) + "\n"
    with open(yaml_path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    with open(corr_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    try:
        _fsck_or_report(chains_root)  # C7 — 스키마 위반이 될 값은 쓰지 않는다
    except ChainError:
        with open(yaml_path, "w", encoding="utf-8") as fh:
            fh.write(original)
        if corr_before is None:
            os.remove(corr_path)
        else:
            with open(corr_path, "w", encoding="utf-8") as fh:
                fh.write(corr_before)
        raise

    # ---- [correct] 커밋: 그 두 파일만 담는다 (변조를 태그 안으로 밀반입할 수 없다) ----
    rel_yaml = os.path.relpath(yaml_path, repo)
    rel_corr = os.path.relpath(corr_path, repo)
    _git(repo, "add", "--", rel_yaml, rel_corr)
    _git(repo, "commit", "-m",
         f"[correct] gil: {args.ref} — {'; '.join(changed)}", "--", rel_yaml, rel_corr)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    old_tag_commit = _git(repo, "rev-list", "-n1", tag).stdout.strip()
    # 태그 이동 규약 (§4): 이전 커밋 해시와 사유를 태그 메시지에 남긴다
    _git(repo, "tag", "-f", "-a", tag, "-m",
         f"[correct] {'; '.join(changed)} — 증거 {args.evidence} (이전 커밋 {old_tag_commit[:8]}에서 이동)", head)
    if args.push:
        _git(repo, "push")
        _git(repo, "push", "--force", "origin", f"refs/tags/{tag}")

    _refresh_viewers(chains_root, f"{args.ref} 정정", getattr(args, "no_web", False), args.push)
    print(f"정정: {args.ref}")
    for c in changed:
        print(f"  ✎ {c}")
    print(f"  증거: {args.evidence} (봉인본 {tag})")
    print(f"  기록: {os.path.relpath(corr_path, os.getcwd()) if not os.path.isabs(corr_path) else corr_path}"
          f" — 거짓은 지워지지 않았다")
    print(f"  태그 이동: {old_tag_commit[:8]} → {head[:8]}")
    return 0


def cmd_goto(args):
    """타임머신 콘솔 — 사이클 시점의 역행 조회·체크아웃·분기 안내."""
    chains_root = args.root
    if "/" not in args.ref:
        raise ChainError(f"ref는 <chain>/<id> 형식이어야 한다: {args.ref}")
    chain, cid = args.ref.split("/", 1)
    cycle_dir = os.path.join(chains_root, chain, cid)
    yaml_path = os.path.join(cycle_dir, "cycle.yaml")
    if not os.path.isfile(yaml_path):
        raise ChainError(f"사이클이 없다: {args.ref}")
    data = parse_cycle_yaml(yaml_path)
    parents = _as_list(data.get("parent"))
    lineage = _as_list(data.get("lineage"))
    tag = _tag_name(chain, cid)
    repo = _repo_root(chains_root)
    tagged = repo is not None and _tag_exists(repo, tag)

    print(f"사이클 {chain}/{cid} [{data.get('status') or '?'}]: {data.get('title') or ''}")
    print(f"  부모: {', '.join(parents) if parents else '(root)'}"
          + (f"   계보: {', '.join(lineage)}" if lineage else ""))
    if tagged:
        commit = _git(repo, "rev-list", "-n1", tag).stdout.strip()[:8]
        print(f"  각인 태그: {tag} → {commit}")
        print(f"  ← 이 시점 코드로 역행:  git checkout {tag}   (또는 gil goto {args.ref} --checkout)")
    elif data.get("status") == "closed":
        print("  (닫혔으나 태그 없음 — 백필 필요)")
    else:
        print("  (열린 사이클 — 아직 각인 태그 없음)")
    print(f"  ↳ 이 지점에서 새 갈래 시작:  gil open {chain} <slug> --parent {cid} --author <이름>")

    if args.checkout:
        if not repo:
            raise ChainError("--checkout: 깃 저장소가 아니다")
        if not tagged:
            raise ChainError(f"--checkout: 태그 '{tag}'가 없다 (닫히고 각인된 사이클만 역행 가능)")
        if _git(repo, "status", "--porcelain").stdout.strip():
            raise ChainError("--checkout: 미커밋 변경이 있다 — 유실 방지를 위해 거부. 커밋/스태시 후 다시.")
        current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        _git(repo, "checkout", tag)
        print(f"\n역행 완료: 작업 트리가 {tag} 시점이다. 돌아오려면:  git checkout {current or 'main'}")
    return 0


def cmd_verify(args):
    chains_root = args.chains_root
    repo = _repo_root(chains_root)
    if not repo:
        raise ChainError(f"깃 저장소가 아니다: {chains_root}")
    tampered, untagged, checked = [], [], 0
    for ch, recs in sorted(_scan_chains(chains_root, args.chain).items()):
        for r in recs:
            if r.get("status") != "closed" or not r.get("id"):
                continue
            checked += 1
            tag = _tag_name(ch, r["id"])
            cycle_rel = os.path.relpath(
                os.path.join(chains_root, ch, r["_dir"]), repo)
            if not _tag_exists(repo, tag):
                untagged.append(f"{ch}/{r['id']}")
                continue
            diff = _git(repo, "diff", "--name-only", tag, "--", cycle_rel)
            new = _git(repo, "status", "--porcelain", "--untracked-files=all", "--", cycle_rel)
            paths = sorted(
                set(diff.stdout.split())
                | {line[3:] for line in new.stdout.splitlines() if line.startswith("??")}
            )
            if paths:
                tampered.append((tag, paths))
    for tag, paths in tampered:
        print(f"변조 감지 [{tag}]:")
        for p in paths:
            print(f"  {p}")
    for u in untagged:
        print(f"경고: 닫힌 사이클에 태그가 없다 — {u} (백필 필요)", file=sys.stderr)
    if tampered:
        print(f"\n닫힌 사이클 {checked}개 검사 — 변조 {len(tampered)}건", file=sys.stderr)
        return 1
    print(f"OK — 닫힌 사이클 {checked}개 검사, 변조 0건" + (f" (태그 없음 {len(untagged)}건)" if untagged else ""))
    return 0


def cmd_close(args):
    chains_root = args.root
    cycle_dir = os.path.join(chains_root, args.chain, args.cycle_id)
    yaml_path = os.path.join(cycle_dir, "cycle.yaml")
    if not os.path.isfile(yaml_path):
        raise ChainError(f"사이클이 없다: {os.path.join(args.chain, args.cycle_id)}")
    data = parse_cycle_yaml(yaml_path)
    if data.get("status") == "closed":
        raise ChainError(f"{args.chain}/{args.cycle_id}: 이미 닫힌 사이클이다 — 닫힌 사이클은 수정하지 않는다")

    # 기본 커밋 (v1.7, C033): 깃 저장소면 자동 커밋+각인. --no-commit으로만 끈다.
    # (--git은 하위호환. 사전 검증은 저장소를 건드리기 전에 전부 확인한다.)
    repo = tag = None
    do_git = _repo_root(chains_root) if not getattr(args, "no_commit", False) else None
    if do_git:
        repo = do_git
        tag = _tag_name(args.chain, args.cycle_id)
        if _tag_exists(repo, tag):
            raise ChainError(f"태그 '{tag}'가 이미 존재한다")
    elif args.git and not getattr(args, "no_commit", False):
        raise ChainError(f"--git: 깃 저장소가 아니다 — {chains_root}")

    report_path = os.path.join(cycle_dir, "5-report.md")
    if not os.path.isfile(report_path):
        raise ChainError(f"{args.chain}/{args.cycle_id}: 5-report.md가 없다 — 보고 없이 닫을 수 없다")
    template_report = os.path.join(_template_dir(chains_root), "5-report.md")
    stub_reports = {"# 5. 결과 보고\n\n(작성할 것)\n"}  # 내장 스캐폴드의 미작성 보고서 (v1.1)
    if os.path.isfile(template_report):
        with open(template_report, encoding="utf-8") as f2:
            stub_reports.add(f2.read())
    with open(report_path, encoding="utf-8") as f1:
        if f1.read() in stub_reports:
            raise ChainError(f"{args.chain}/{args.cycle_id}: 보고서가 템플릿 그대로다 — 결과 보고를 작성할 것")

    with open(yaml_path, encoding="utf-8") as f:
        original = f.read()
    updated = re.sub(r"^status:.*$", "status: closed", original, count=1, flags=re.M)
    updated = re.sub(r"^closed:.*$", f"closed: {args.date}", updated, count=1, flags=re.M)
    if re.search(r"^step:", updated, flags=re.M):
        updated = re.sub(r"^step:.*$", "step: 5", updated, count=1, flags=re.M)
    else:
        updated = re.sub(r"^(closed:.*)$", r"\1\nstep: 5", updated, count=1, flags=re.M)
    if args.verdict:  # v0.3: 결말 기록
        if args.verdict not in _VERDICTS:
            raise ChainError(f"verdict '{args.verdict}'는 {'|'.join(_VERDICTS)} 중 하나여야 한다")
        if re.search(r"^verdict:", updated, flags=re.M):
            updated = re.sub(r"^verdict:.*$", f"verdict: {args.verdict}", updated, count=1, flags=re.M)
        else:
            updated = re.sub(r"^(closed:.*)$", rf"\1\nverdict: {args.verdict}", updated, count=1, flags=re.M)
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(updated)
    try:
        _fsck_or_report(chains_root)
    except ChainError:
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(original)  # 원상 복구
        raise
    if repo:
        cycle_rel = os.path.relpath(cycle_dir, repo)
        title = data.get("title") or ""
        try:
            _git(repo, "add", "-A", "--", cycle_rel)
            _git(repo, "commit",
                 "-m", f"gil: close {args.chain}/{args.cycle_id}\n\n{title}",
                 "--", cycle_rel)
            _git(repo, "tag", "-a", tag, "-m", f"{args.chain}/{args.cycle_id}: {title}")
        except ChainError:
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write(original)  # 원상 복구
            _git(repo, "reset", "-q", "--", cycle_rel, check=False)
            raise
        print(f"각인: 커밋 + 태그 {tag}")
        if args.push:
            _git(repo, "push", "--follow-tags")
    print(f"닫힘: {args.chain}/{args.cycle_id} ({args.date})")
    _refresh_viewers(chains_root, f"{args.chain}/{args.cycle_id} 닫힘",
                     getattr(args, "no_web", False), args.push)
    print("→ 세션 핸드오프: gil handoff (사이클을 닫았으니 세션 정리를 고려하라)")
    return 0


def cmd_step(args):
    chains_root = args.root
    cycle_dir = os.path.join(chains_root, args.chain, args.cycle_id)
    yaml_path = os.path.join(cycle_dir, "cycle.yaml")
    if not os.path.isfile(yaml_path):
        raise ChainError(f"사이클이 없다: {os.path.join(args.chain, args.cycle_id)}")
    if not (args.n.isdigit() and 1 <= int(args.n) <= 5):
        raise ChainError(f"step '{args.n}'는 1~5여야 한다 (R9)")
    data = parse_cycle_yaml(yaml_path)
    if data.get("status") == "closed":
        raise ChainError(f"{args.chain}/{args.cycle_id}: 닫힌 사이클의 step은 바꿀 수 없다")
    n = int(args.n)
    with open(yaml_path, encoding="utf-8") as f:
        original = f.read()
    if re.search(r"^step:", original, flags=re.M):
        updated = re.sub(r"^step:.*$", f"step: {n}", original, count=1, flags=re.M)
    else:
        updated = re.sub(r"^(closed:.*)$", rf"\1\nstep: {n}", original, count=1, flags=re.M)
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(updated)
    try:
        _fsck_or_report(chains_root)
    except ChainError:
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(original)
        raise
    # 기본 커밋 (v1.7, C033): 깃 저장소면 자동 커밋한다. --no-commit으로만 끈다.
    # (--git은 하위호환 — 있어도 무해하다. 커밋을 안 붙이던 사용자도 스텝마다 각인된다.)
    committed = False
    if not getattr(args, "no_commit", False):
        repo = _repo_root(chains_root)
        if repo:
            rel = os.path.relpath(cycle_dir, repo)
            _git(repo, "add", "-A", "--", rel)
            _git(repo, "commit", "-m", f"gil: step {args.chain}/{args.cycle_id} → {n}/5 {_STEP_NAMES[n]}", "--", rel)
            committed = True
            if args.push:
                _git(repo, "push")
    print(f"스텝: {args.chain}/{args.cycle_id} → {n}/5 {_STEP_NAMES[n]}"
          + ("  각인: 커밋" if committed else ""))
    _refresh_viewers(chains_root, f"{args.chain}/{args.cycle_id} → {n}/5",
                     getattr(args, "no_web", False), args.push)
    return 0


def cmd_round(args):
    """사이클 안에 (가설→검증) 라운드를 사전등록·마감한다 (loom/C045 — 이슈 #9·#10).
    R1은 기존 5스텝 문서 — 첫 --open이 R2를 만든다. 사전등록(H1)은 도구가 보증한다:
    --open은 hypothesis.md만 각인하고 verification/은 만들지 않는다 (C013 '열 때부터 보이게'의 라운드판)."""
    chains_root = args.root
    cycle_dir = os.path.join(chains_root, args.chain, args.cycle_id)
    yaml_path = os.path.join(cycle_dir, "cycle.yaml")
    if not os.path.isfile(yaml_path):
        raise ChainError(f"사이클이 없다: {os.path.join(args.chain, args.cycle_id)}")
    data = parse_cycle_yaml(yaml_path)

    if args.list:  # 부작용 없는 조회 (능력 탐침 무해, §7.2-6)
        n = _cycle_rounds(data)
        print(f"{args.chain}/{args.cycle_id} — 라운드 {n}개")
        print(f"  R1  [기존 5스텝 문서]  {data.get('title') or ''}")
        for rd in _load_rounds(cycle_dir):
            v = rd.get("verdict") or ("열림" if not rd.get("closed") else "?")
            print(f"  R{rd.get('round')}  [{v}]  {rd.get('title') or ''}")
        return 0

    if data.get("status") == "closed":
        raise ChainError(f"{args.chain}/{args.cycle_id}: 닫힌 사이클엔 라운드를 추가·수정할 수 없다 (불변)")

    if args.open:
        if not args.title:
            raise ChainError("--open에는 --title이 필수다 — 라운드의 가설을 한 줄로")
        newk = _cycle_rounds(data) + 1  # R1은 기존 문서 — 첫 라운드 추가는 R2
        rdir = os.path.join(_rounds_dir(cycle_dir), f"R{newk}")
        if os.path.exists(rdir):
            raise ChainError(f"이미 존재한다: rounds/R{newk}")
        os.makedirs(rdir)  # 사전등록: hypothesis.md + round.yaml만. verification/은 만들지 않는다 (H1)
        title = (args.title or "").replace('"', "'")
        with open(os.path.join(rdir, "hypothesis.md"), "w", encoding="utf-8") as f:
            f.write(f"# 라운드 R{newk} — 가설\n\n> **가설**: {title}\n\n"
                    f"## 기각 조건 (선고정)\n\n<!-- 데이터를 보기 전에 기대값을 못박는다 -->\n")
        with open(os.path.join(rdir, "round.yaml"), "w", encoding="utf-8") as f:
            f.write(f"round: {newk}\n"
                    f'title: "{title}"\n'
                    f"opened: {args.date}\n"
                    f"closed: null\n"
                    f"verdict: null\n")   # 6-어휘 중 하나로 닫는다 (round --close)
        with open(yaml_path, encoding="utf-8") as f:
            original = f.read()
        if re.search(r"^rounds:", original, flags=re.M):
            updated = re.sub(r"^rounds:.*$", f"rounds: {newk}", original, count=1, flags=re.M)
        else:  # 없으면 status 뒤에 삽입 (평탄 스키마 — 위치는 무관, 관례상 상태 계열 근처)
            updated = re.sub(r"^(status:.*)$", rf"\1\nrounds: {newk}", original, count=1, flags=re.M)
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(updated)
        try:
            _fsck_or_report(chains_root)
        except ChainError:
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write(original)
            shutil.rmtree(rdir)
            raise
        if args.git:
            repo = _repo_root(chains_root)
            if not repo:
                raise ChainError("--git: 깃 저장소가 아니다")
            rel = os.path.relpath(cycle_dir, repo)
            _git(repo, "add", "-A", "--", rel)
            _git(repo, "commit", "-m",
                 f"gil: round open {args.chain}/{args.cycle_id} R{newk} — 사전등록\n\n{title}", "--", rel)
            if args.push:
                _git(repo, "push", check=False)
        print(f"라운드 열림: {args.chain}/{args.cycle_id} R{newk} (사전등록 — hypothesis만 각인)")
        _refresh_viewers(chains_root, f"{args.chain}/{args.cycle_id} R{newk} 열림",
                         getattr(args, "no_web", False), args.push)
        return 0

    if args.close:
        if not args.verdict:
            raise ChainError("--close에는 --verdict가 필수다")
        if args.verdict not in _ROUND_VERDICTS:
            raise ChainError(f"verdict '{args.verdict}'는 {'|'.join(_ROUND_VERDICTS)} 중 하나여야 한다")
        open_rounds = [r for r in _load_rounds(cycle_dir) if not r.get("closed")]
        if not open_rounds:
            raise ChainError("닫을 열린 라운드가 없다 — 먼저 gil round --open")
        target = max(open_rounds, key=lambda r: int(r["round"]) if str(r.get("round", "")).isdigit() else 0)
        k = target["round"]
        ryp = os.path.join(_rounds_dir(cycle_dir), target["_dir"], "round.yaml")
        with open(ryp, encoding="utf-8") as f:
            original = f.read()
        updated = re.sub(r"^verdict:.*$", f"verdict: {args.verdict}", original, count=1, flags=re.M)
        updated = re.sub(r"^closed:.*$", f"closed: {args.date}", updated, count=1, flags=re.M)
        with open(ryp, "w", encoding="utf-8") as f:
            f.write(updated)
        try:
            _fsck_or_report(chains_root)
        except ChainError:
            with open(ryp, "w", encoding="utf-8") as f:
                f.write(original)
            raise
        if args.git:
            repo = _repo_root(chains_root)
            if not repo:
                raise ChainError("--git: 깃 저장소가 아니다")
            rel = os.path.relpath(cycle_dir, repo)
            _git(repo, "add", "-A", "--", rel)
            _git(repo, "commit", "-m",
                 f"gil: round close {args.chain}/{args.cycle_id} R{k} → {args.verdict}", "--", rel)
            if args.push:
                _git(repo, "push", check=False)
        print(f"라운드 닫힘: {args.chain}/{args.cycle_id} R{k} → {args.verdict}")
        _refresh_viewers(chains_root, f"{args.chain}/{args.cycle_id} R{k} 닫힘",
                         getattr(args, "no_web", False), args.push)
        return 0
    raise ChainError("--open · --close · --list 중 하나를 지정하라")


# ---------- release (릴리스 porcelain) ----------

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _hash_file(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _hash_tree(root):
    out = {}
    for base, _, files in os.walk(root):
        for name in files:
            p = os.path.join(base, name)
            out[os.path.relpath(p, root)] = _hash_file(p)
    return out


def _last_release_version(repo):
    tags = _git(repo, "tag", "-l", "v*").stdout.split()
    versions = []
    for t in tags:
        m = _SEMVER_RE.match(t[1:])
        if m:
            versions.append(tuple(int(g) for g in m.groups()))
    return max(versions) if versions else None


_VERSION_MARK = "gil:version"                    # version 자기보고 표면의 표식 (SPEC §7)
_SEMVER_IN_LINE = re.compile(r"\d+\.\d+\.\d+")
_PKG_IMPLS = (("go", os.path.join("go", "main.go")),)  # 패키지에 동봉된 참조 구현 외 이행자


def _map_version_lines(text, fn):
    """표식이 달린 라인의 첫 SemVer만 fn으로 바꾼다. 언어 문법은 파싱하지 않는다 — 언어 무지성이 곧 구현 독립성이다."""
    out, n = [], 0
    for line in text.splitlines(keepends=True):
        if _VERSION_MARK in line and _SEMVER_IN_LINE.search(line):
            line = _SEMVER_IN_LINE.sub(fn, line, count=1)
            n += 1
        out.append(line)
    return "".join(out), n


def _mask_version(text):
    """승격 판정용 정규화 — version 표면은 자기 지시적이므로 변경 감지에서 제외한다.
    이것이 없으면 release가 version을 갱신하는 순간 모든 릴리스가 '도구 변경'이 되어 패치 승격이 영영 불가능해진다."""
    return _map_version_lines(text, lambda m: "X.Y.Z")[0]


def _set_version(text, version):
    return _map_version_lines(text, lambda m: version)


def _check_version_surface(path):
    """SPEC §7: gil 구현은 '표식 + SemVer'가 함께 있는 라인을 정확히 하나 가진다.
    표식만 있고 SemVer가 없는 라인은 표면이 아니다 — 계약을 집행하는 구현은 표식 문자열 자체를 소스에 품기 때문이다."""
    with open(path, encoding="utf-8") as f:
        surfaces = [ln for ln in f.read().splitlines()
                    if _VERSION_MARK in ln and _SEMVER_IN_LINE.search(ln)]
    if len(surfaces) != 1:
        raise ChainError(
            f"version 표면 계약 위반: {os.path.basename(path)} — 표식 '{_VERSION_MARK}'이 달린 SemVer 라인이 "
            f"정확히 1개여야 한다 (발견: {len(surfaces)}줄) — SPEC §7")


def _changed_vs_last_tag(repo, tag, worktree_path):
    """마지막 릴리스 태그의 blob과 작업 트리 파일을 비교한다 (v0.9 승격 기준).
    태그에 없던 파일이 생겼거나 내용이 다르면 변경. 둘 다 없으면 무변경."""
    rel = os.path.relpath(worktree_path, repo).replace(os.sep, "/")
    r = _git(repo, "show", f"{tag}:{rel}", check=False)
    tagged = r.stdout if r.returncode == 0 else None
    exists = os.path.isfile(worktree_path)
    if tagged is None:
        return exists  # 태그엔 없는데 지금 있다 → 변경
    if not exists:
        return True    # 태그엔 있는데 사라졌다 → 변경
    with open(worktree_path, encoding="utf-8") as f:
        return f.read() != tagged


def cmd_release(args):
    chains_root = args.root
    pkg = args.package
    repo = _repo_root(chains_root)

    # ---- 사전 검증: 저장소를 건드리기 전에 전부 확인한다 ----
    if not repo:
        raise ChainError(f"깃 저장소가 아니다: {chains_root}")
    m = _SEMVER_RE.match(args.version)
    if not m:
        raise ChainError(f"버전 '{args.version}'은 SemVer(X.Y.Z)가 아니다")
    new = tuple(int(g) for g in m.groups())
    last = _last_release_version(repo)
    if last and new <= last:
        raise ChainError(f"버전 {args.version}은 마지막 릴리스 v{'.'.join(map(str, last))} 보다 커야 한다")
    tag = f"v{args.version}"
    if _tag_exists(repo, tag):
        raise ChainError(f"태그 '{tag}'가 이미 존재한다")
    if not os.path.isdir(pkg):
        raise ChainError(f"패키지 디렉토리가 없다: {pkg}")
    _fsck_or_report(chains_root)  # 깨진 저장소 위에는 릴리스하지 않는다
    import types
    if cmd_verify(types.SimpleNamespace(chains_root=chains_root, chain=None)) != 0:
        raise ChainError("verify 실패 — 변조된 닫힌 사이클이 있는 저장소에서는 릴리스하지 않는다")

    tool_src = os.path.abspath(__file__)
    pkg_tool = os.path.join(pkg, os.path.basename(__file__))  # 파일명 비의존 — 도구는 자기 이름을 하드코딩하지 않는다

    # 도구 blob 목록 = 승격 규칙의 관측 범위 (v0.9: gil·conformance / v1.12: 동봉 구현도 포함).
    # (이름, 지금 읽을 파일, 태그에서 찾을 패키지 경로) — 실행 도구가 곧 릴리스될 내용이므로 gil만 src가 다를 수 있다.
    blobs = [("gil", tool_src, pkg_tool)]
    pkg_conf = os.path.join(pkg, "conformance.py")
    if os.path.isfile(pkg_conf):
        blobs.append(("conformance", pkg_conf, pkg_conf))
    impls = [(n, os.path.join(pkg, rel)) for n, rel in _PKG_IMPLS if os.path.isfile(os.path.join(pkg, rel))]
    blobs += [(n, p, p) for n, p in impls]

    # 표식 계약: gil 구현(참조 + 동봉)은 자기 버전을 표식 달린 한 줄로 선언한다. 판정기는 버전을 보고하지 않으므로 제외.
    for path in [tool_src] + [p for _, p in impls]:
        _check_version_surface(path)

    if last:
        # v0.9 기준: 마지막 릴리스 태그의 blob. v1.12: 비교 전 양쪽의 version 표면을 마스킹한다 —
        # 자기 지시적 필드의 변경은 '도구 변경'이 아니다 (그렇지 않으면 패치 릴리스가 영영 불가능해진다).
        last_tag = f"v{'.'.join(map(str, last))}"
        changed_parts = []
        for name, src, pkg_path in blobs:
            rel = os.path.relpath(pkg_path, repo).replace(os.sep, "/")
            r = _git(repo, "show", f"{last_tag}:{rel}", check=False)
            with open(src, encoding="utf-8") as f:
                if r.returncode != 0 or _mask_version(f.read()) != _mask_version(r.stdout):
                    changed_parts.append(name)
    else:
        changed_parts = ["gil"] if ((not os.path.isfile(pkg_tool))
                                    or _hash_file(tool_src) != _hash_file(pkg_tool)) else []
    if changed_parts and last and new[0] == last[0] and new[1] == last[1]:
        raise ChainError(
            f"도구가 변했다({'·'.join(changed_parts)}, 기준: 마지막 릴리스 태그) — "
            f"패치 승격({args.version})은 금지, 마이너 이상으로 승격할 것 (버전 승격 규칙)")

    release_md = os.path.join(pkg, "RELEASE.md")
    if not (os.path.isfile(release_md) and args.version in open(release_md, encoding="utf-8").read()):
        raise ChainError(
            f"RELEASE.md에 {args.version} 서술이 없다 — 도구는 절차를, 존재는 진실을: 먼저 릴리스를 문서화할 것")

    template_src = os.path.normpath(os.path.join(chains_root, "..", "_template"))
    changelog = os.path.normpath(os.path.join(pkg, "..", "CHANGELOG.md"))
    if not os.path.isfile(changelog):
        raise ChainError(f"CHANGELOG가 없다: {changelog}")
    log_text = open(changelog, encoding="utf-8").read()
    if "## [Unreleased]" not in log_text:
        raise ChainError("CHANGELOG에 '## [Unreleased]' 섹션이 없다")

    # ---- 실행: 동기화 → CHANGELOG → 커밋 → 태그 ----
    if not (os.path.exists(pkg_tool) and os.path.samefile(tool_src, pkg_tool)):
        shutil.copyfile(tool_src, pkg_tool)  # 자기 자신 위 실행(패키지 도구 직접 호출) 시 복사 생략
    # version 표면 동기화 — 배포되는 구현이 자기 버전을 거짓말할 수 없다 (도구가 집행한다, 훈계가 아니라).
    for path in [pkg_tool] + [p for _, p in impls]:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        stamped, n = _set_version(text, args.version)
        if n != 1:  # 사전 검증을 통과했으므로 도달 불가 — 도달했다면 계약이 깨진 것이다
            raise ChainError(f"version 표면 갱신 실패: {os.path.basename(path)} (표식 {n}개)")
        if stamped != text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(stamped)
    pkg_template = os.path.join(pkg, "template")
    if os.path.isdir(pkg_template):
        shutil.rmtree(pkg_template)
    shutil.copytree(template_src, pkg_template)
    entry = (f"## [{args.version}] — {args.date}\n\n- {args.notes}\n"
             f"- 도구 변경: {('·'.join(changed_parts) + ' (마이너 이상 승격)') if changed_parts else '없음 (문서 릴리스)'}\n")
    with open(changelog, "w", encoding="utf-8") as f:
        f.write(log_text.replace("## [Unreleased]", f"## [Unreleased]\n\n{entry}", 1))

    deploy_rel = os.path.relpath(os.path.normpath(os.path.join(pkg, "..")), repo)
    try:
        _git(repo, "add", "-A", "--", deploy_rel)
        _git(repo, "commit", "-m", f"gil: release {tag}\n\n{args.notes}", "--", deploy_rel)
        _git(repo, "tag", "-a", tag, "-m", f"Ariadne release {tag} — {args.notes}")
    except ChainError:
        _git(repo, "reset", "-q", "--", deploy_rel, check=False)
        _git(repo, "checkout", "-q", "--", deploy_rel, check=False)
        raise
    print(f"릴리스: {tag} (도구 변경: {'·'.join(changed_parts) if changed_parts else '없음'}"
          f", version 표면: {1 + len(impls)}개 갱신)")
    return 0


# ---------- CLI ----------

def _scan_chains(root, only=None):
    if not os.path.isdir(root):
        raise ChainError(f"체인 루트가 없다: {root}")
    names = sorted(
        e for e in os.listdir(root)
        if os.path.isdir(os.path.join(root, e)) and (not only or e == only)
    )
    if only and not names:
        raise ChainError(f"체인 '{only}'이 {root}에 없다")
    return {name: load_chain_records(os.path.join(root, name)) for name in names}


def cmd_log(args):
    root = args.chains_root
    if not os.path.isdir(root):
        raise ChainError(f"체인 루트가 없다: {root}")
    names = sorted(
        e for e in os.listdir(root)
        if os.path.isdir(os.path.join(root, e)) and (not args.chain or e == args.chain)
    )
    if args.chain and not names:
        raise ChainError(f"체인 '{args.chain}'이 {root}에 없다")
    for name in names:
        log_chain(name, os.path.join(root, name))
    return 0


_UNIMPLEMENTED_EXIT = 3  # §7.2-4: 미구현·미지 명령의 통일된 신호


def _unimplemented(name, commands):
    """§7.2-4 — 미구현 신호. 목록은 단일 소스에서 파생된다."""
    print(f"미구현: '{name}' — 이 구현(gil {_GIL_VERSION})이 구현한 명령: "
          f"{'·'.join(commands)}. (gil help 참조)", file=sys.stderr)
    return _UNIMPLEMENTED_EXIT


def _print_help(sub, name=None):
    """§7.2-1·3 — 능력 목록과 안전한 능력 탐침. 저장소를 변경하지 않는다."""
    commands = list(sub.choices)  # 단일 소스: 등록된 서브파서가 곧 구현 목록이다 (§7.2-2)
    if name is not None:
        if name not in sub.choices:
            return _unimplemented(name, commands)
        sub.choices[name].print_help()
        return 0
    print(f"gil {_GIL_VERSION} — 길, GIt for Language model")
    print()
    print("구현 명령 (자세히: gil help <명령>):")
    print("  " + " ".join(commands))
    print()
    print(f"gil:commands {' '.join(commands)}")  # §7.2-1: 사람의 출력 안에 심은 기계 훅
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gil", description="gil — 길, GIt for Language model (Ariadne 사이클 체인 도구)")
    parser.add_argument("--version", action="version", version=f"gil {_GIL_VERSION}")
    sub = parser.add_subparsers(dest="command", required=False)
    for name, func, help_text in (
        ("log", cmd_log, "체인 계보를 그래프로 렌더"),
        ("fsck", cmd_fsck, "스키마 v0.2 규칙 위반을 전부 수집해 보고"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("chains_root", nargs="?", default="rooms/experiment/chains",
                       help="체인들이 있는 루트 디렉토리 (기본: rooms/experiment/chains)")
        p.add_argument("--chain", help="특정 체인만")
        p.set_defaults(func=func)

    today = datetime.date.today().isoformat()
    p_open = sub.add_parser("open", help="v0.2 준수 사이클 생성")
    p_open.add_argument("chain")
    p_open.add_argument("slug", help="id의 슬러그 부분 (소문자 케밥) — 번호는 자동 증가")
    p_open.add_argument("--title", default="", help="정복하려는 가장 작은 문제 한 줄")
    p_open.add_argument("--parent", action="append", default=[], help="부모 사이클의 로컬 id (병합이면 여러 번)")
    p_open.add_argument("--lineage", action="append", default=[], help="교훈의 연원, 전역 표기 <chain>/<id> (여러 번 가능)")
    p_open.add_argument("--author", help="수행하는 존재 (존재의 방 이름) — 필수. 기본값 없음 (§3.2 P1)")
    p_open.add_argument("--date", default=today, help="opened 일자 (기본: 오늘)")
    p_open.add_argument("--new-root", action="store_true",
                        help="비어있지 않은 체인에 의도적으로 새 루트를 만든다 (parent: null)")
    p_open.add_argument("--new-chain", action="store_true", help="체인이 없으면 chain.md 스텁과 함께 생성")
    p_open.add_argument("--git", action="store_true", help="열림 즉시 사이클 디렉토리만 커밋")
    p_open.add_argument("--push", action="store_true", help="커밋 후 push (준실시간 뷰어 갱신)")
    p_open.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_open.add_argument("--no-web", dest="no_web", action="store_true", help="뷰어 자동 갱신 끄기 (v2.2)")
    p_open.set_defaults(func=cmd_open)

    p_res = sub.add_parser("reserve", help="병렬 존재에게 사이클 번호를 예약 (원장 선점, v2.3)")
    p_res.add_argument("chain")
    p_res.add_argument("slug", help="예약의 의도된 슬러그 (예약자가 open 시 확정)")
    p_res.add_argument("--for", dest="author", help="예약 대상 존재의 이름 — 필수 (§3.2 P1)")
    p_res.add_argument("--date", default=today, help="예약 일자 (기본: 오늘)")
    p_res.add_argument("--git", action="store_true", help="예약 원장만 담아 커밋")
    p_res.add_argument("--push", action="store_true", help="커밋 후 push")
    p_res.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_res.set_defaults(func=cmd_reserve)

    p_unres = sub.add_parser("unreserve", help="예약 취소 — 만료의 수동 해법 (v2.3)")
    p_unres.add_argument("chain")
    p_unres.add_argument("number", help="취소할 예약 번호 (44 · 044 · C044)")
    p_unres.add_argument("--git", action="store_true", help="예약 원장만 담아 커밋")
    p_unres.add_argument("--push", action="store_true", help="커밋 후 push")
    p_unres.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_unres.set_defaults(func=cmd_unreserve)

    p_step = sub.add_parser("step", help="열린 사이클의 진행 스텝(1~5) 전이")
    p_step.add_argument("chain")
    p_step.add_argument("cycle_id")
    p_step.add_argument("n", help="1 가설 · 2 설계 · 3 검증 · 4 분석 · 5 보고")
    p_step.add_argument("--git", action="store_true", help="(하위호환) 커밋 — v1.7부터 깃 저장소면 기본")
    p_step.add_argument("--no-commit", dest="no_commit", action="store_true", help="자동 커밋 끄기")
    p_step.add_argument("--push", action="store_true", help="커밋 후 push")
    p_step.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_step.add_argument("--no-web", dest="no_web", action="store_true", help="뷰어 자동 갱신 끄기 (v2.2)")
    p_step.set_defaults(func=cmd_step)

    p_round = sub.add_parser("round", help="사이클 안에 (가설→검증) 라운드를 사전등록 (v2.5, 이슈 #9·#10)")
    p_round.add_argument("chain")
    p_round.add_argument("cycle_id")
    p_round_mode = p_round.add_mutually_exclusive_group(required=True)
    p_round_mode.add_argument("--open", action="store_true", help="새 라운드 R{N+1}을 사전등록 (hypothesis만 각인)")
    p_round_mode.add_argument("--close", action="store_true", help="열린 라운드를 --verdict로 닫는다")
    p_round_mode.add_argument("--list", action="store_true", help="라운드 조회 (부작용 없음)")
    p_round.add_argument("--title", default="", help="--open 시 라운드 가설 한 줄 (필수)")
    p_round.add_argument("--verdict", help="--close 시 라운드 결말: " + "|".join(_ROUND_VERDICTS))
    p_round.add_argument("--date", default=today, help="일자 (기본: 오늘)")
    p_round.add_argument("--git", action="store_true", help="사이클 디렉토리만 담아 커밋")
    p_round.add_argument("--push", action="store_true", help="커밋 후 push")
    p_round.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_round.add_argument("--no-web", dest="no_web", action="store_true", help="뷰어 자동 갱신 끄기 (v2.2)")
    p_round.set_defaults(func=cmd_round)

    p_close = sub.add_parser("close", help="보고서 검증 후 사이클 닫기")
    p_close.add_argument("chain")
    p_close.add_argument("cycle_id")
    p_close.add_argument("--date", default=today, help="closed 일자 (기본: 오늘)")
    p_close.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_close.add_argument("--git", action="store_true",
                         help="(하위호환) 커밋+태그 — v1.7부터 깃 저장소면 기본")
    p_close.add_argument("--no-commit", dest="no_commit", action="store_true", help="자동 커밋·태그 끄기")
    p_close.add_argument("--verdict", help="결말: supported|partial|rejected|inconclusive (v0.3)")
    p_close.add_argument("--push", action="store_true", help="각인 후 push --follow-tags")
    p_close.add_argument("--no-web", dest="no_web", action="store_true", help="뷰어 자동 갱신 끄기 (v2.2)")
    p_close.set_defaults(func=cmd_close)

    p_verify = sub.add_parser("verify", help="닫힌 사이클의 태그↔작업 트리 대조 (변조 탐지)")
    p_verify.add_argument("chains_root", nargs="?", default="rooms/experiment/chains",
                          help="체인 루트 (기본: rooms/experiment/chains)")
    p_verify.add_argument("--chain", help="특정 체인만")
    p_verify.set_defaults(func=cmd_verify)

    p_rel = sub.add_parser("release", help="도구·템플릿을 패키지로 동기화하고 커밋+태그 v<버전>")
    p_rel.add_argument("version", help="SemVer (X.Y.Z). 도구가 변했으면 마이너 이상 승격")
    p_rel.add_argument("--notes", required=True, help="CHANGELOG에 들어갈 한 줄")
    p_rel.add_argument("--date", default=today, help="릴리스 일자 (기본: 오늘)")
    p_rel.add_argument("--package", default="rooms/deployment/ariadne-spec", help="릴리스 패키지 경로")
    p_rel.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_rel.set_defaults(func=cmd_release)

    p_ver = sub.add_parser("version", help="이 도구의 버전")
    p_ver.set_defaults(func=lambda a: (print(f"gil {_GIL_VERSION}"), 0)[1])

    p_handoff = sub.add_parser("handoff", help="세션의 매듭: 현황·부활 경로·다음 실 요약 (세션 정리 전)")
    p_handoff.add_argument("chains_root", nargs="?", default="rooms/experiment/chains", help="체인 루트")
    p_handoff.set_defaults(func=cmd_handoff)

    p_sup = sub.add_parser("supersede", help="전방 무효화: old 사이클을 new가 대체함을 각인 (v0.4)")
    p_sup.add_argument("old_ref", help="무효화될 사이클 <chain>/<id>")
    p_sup.add_argument("new_ref", help="대체하는 사이클 <chain>/<id>")
    p_sup.add_argument("--no-commit", dest="no_commit", action="store_true", help="자동 커밋 끄기")
    p_sup.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_sup.add_argument("--no-web", dest="no_web", action="store_true", help="뷰어 자동 갱신 끄기 (v2.2)")
    p_sup.set_defaults(func=cmd_supersede)

    p_cor = sub.add_parser("correct", help="정정: 봉인된 사이클의 출처 필드를 문서가 증언하는 값으로 수리 (v0.5)")
    p_cor.add_argument("ref", help="정정할 사이클 <chain>/<id>")
    p_cor.add_argument("--field", action="append", default=[],
                       help=f"정정할 출처 필드 ({'|'.join(_PROVENANCE_FIELDS)}) — 반복 가능. 그 외는 저자의 주장이라 불가 (L1)")
    p_cor.add_argument("--to", action="append", default=[], help="새 값 — --field와 순서대로 짝짓는다")
    p_cor.add_argument("--evidence", help="불변 문서의 증언 <파일>[:<줄>] — 필수. 봉인본에서 대조한다 (L2)")
    p_cor.add_argument("--author", help="정정하는 존재 — 필수. 도구는 정정의 출처도 지어내지 않는다 (§3.2 P1)")
    p_cor.add_argument("--reason", help="정정 사유 한 줄 (기록에 남는다)")
    p_cor.add_argument("--date", default=today, help="정정 일자 (기본: 오늘)")
    p_cor.add_argument("--push", action="store_true", help="[correct] 커밋과 이동한 태그를 전파")
    p_cor.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_cor.add_argument("--no-web", dest="no_web", action="store_true", help="뷰어 자동 갱신 끄기 (v2.2)")
    p_cor.set_defaults(func=cmd_correct)

    p_goto = sub.add_parser("goto", help="타임머신: 사이클 시점 역행 조회·체크아웃·분기 안내")
    p_goto.add_argument("ref", help="<chain>/<id> (예: loom/C005-web-viewer)")
    p_goto.add_argument("--checkout", action="store_true", help="그 시점 작업 트리로 실제 역행 (미커밋 있으면 거부)")
    p_goto.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_goto.set_defaults(func=cmd_goto)

    p_pages = sub.add_parser("pages", help="GitHub Pages 배포 워크플로를 생성한다")
    p_pages.add_argument("--force", action="store_true", help="기존 워크플로를 덮어쓴다")
    p_pages.add_argument("--dry-run", dest="dry_run", action="store_true",
                         help="생성될 경로만 보고하고 아무것도 만들지 않는다 (§7.2-6 부작용 없는 탐침)")
    p_pages.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_pages.set_defaults(func=cmd_pages)

    p_web = sub.add_parser("web", help="자기완결적 정적 HTML 뷰어 생성")
    p_web.add_argument("chains_root", nargs="?", default="rooms/experiment/chains",
                       help="체인 루트 (기본: rooms/experiment/chains)")
    p_web.add_argument("-o", "--output", default="ariadne-chains.html", help="출력 파일 경로")
    p_web.add_argument("--title", default=_WEB_DEFAULT_TITLE, help="페이지 제목")
    p_web.add_argument("--chain", help="특정 체인만")
    p_web.set_defaults(func=cmd_web)

    p_help = sub.add_parser("help", help="구현 명령 목록 — gil help <명령>이면 그 명령의 사용법")
    p_help.add_argument("name", nargs="?", help="조회할 명령 (생략하면 전체 목록)")
    p_help.set_defaults(func=lambda a: _print_help(sub, a.name))

    argv = list(sys.argv[1:] if argv is None else argv)
    # §7.2-1: 무인자 호출은 help와 같다 (오류가 아니다).
    # §7.2-4: 미지의 명령은 argparse의 rc=2가 아니라 통일된 미구현 신호(exit 3)로 답한다.
    if not argv:
        return _print_help(sub)
    if not argv[0].startswith("-") and argv[0] not in sub.choices:
        return _unimplemented(argv[0], list(sub.choices))

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ChainError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
