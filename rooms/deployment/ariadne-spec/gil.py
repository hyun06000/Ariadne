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
import math
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
_GIL_VERSION = "2.31.0"  # gil:version


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


def _count_deviations(path):
    """deviations.yaml의 최상위 레코드(‘- ’로 시작하는 시퀀스 항목) 수를 센다 (loom/C057).
    deviations.yaml은 corrections.yaml과 달리 사람이 읽는 자유 서술 문서다(블록 스칼라 `|` 허용) —
    그래서 R13처럼 스키마를 강제하지 않고 '몇 건인가'만 계약한다. 계약면은 스키마가 아니라
    레코드 수다 (R10 유예-경고 등급과 정합). 블록 스칼라 내용은 ≥3칸 들여쓰기라 오계수 불가.
    읽기 실패 시 None."""
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for line in f if line.startswith("- "))
    except OSError:
        return None


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
                else:
                    n_field = int(dev)
                    devfile = os.path.join(chains_root, ch, r["_dir"], "deviations.yaml") if chains_root else None
                    exists = bool(devfile) and os.path.isfile(devfile)
                    if n_field > 0:
                        if devfile and not exists:
                            violations.append(("R10", loc, f"deviations {dev}인데 deviations.yaml이 없다"))
                        warnings.append(("이탈", loc, f"사전등록 이탈 {dev}건 (deviations.yaml)"))
                    # 역방향 (loom/C057): 파일이 있는데 레코드 수 ≠ 카운트 — C053 슬립을 가시화.
                    # 위반이 아니라 경고 — R10은 v0.3 유예-경고라 이미 봉인된 사슬(C053)이 fsck rc를 바꾸지 않는다.
                    if exists:
                        n_rec = _count_deviations(devfile)
                        if n_rec is not None and n_rec != n_field:
                            warnings.append(("이탈카운트", loc, f"deviations.yaml {n_rec}건인데 cycle.yaml deviations: {dev} — 불일치 (봉인 전 조정, C057)"))
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
    if not _has_push_remote(repo):  # 원격 없으면 경합할 원장이 없다 — 재번호 불필요, 날것 fetch fatal 회피 (loom/C054)
        _warn_no_remote_once()
        return cid
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
            old_rel = _rel_to_repo(os.path.join(chain_dir, cid), repo)
            new_rel = _rel_to_repo(os.path.join(chain_dir, new_cid), repo)
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
    # C062 — 주 체크아웃 오염 방지 · C078 — 예약된 open은 예약 대상 author에게 허용
    _guard_primary_owner(_repo_root(chains_root), args.author, chain_dir, args.slug)
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
        if not repo and not _git_available():
            _warn_git_missing_once()  # git 부재: 크래시·하드에러 대신 파일만 남기고 강등 (loom/C052)
        elif not repo:
            raise ChainError("--git: 깃 저장소가 아니다")  # git 있는데 저장소 아님 = 진짜 사용자 오류
        else:
            rel = _rel_to_repo(dest, repo)
            paths = [rel]
            if new_chain:  # chain.md는 사이클 디렉토리 밖(체인 최상위)이라 별도 경로다 (이슈 #14, loom/C044)
                paths.append(_rel_to_repo(os.path.join(chain_dir, "chain.md"), repo))
            if consumed:  # reservations.tsv는 사이클 밖이라 어떤 태그 봉인에도 안 들어간다 (verify 무영향)
                res_rel = _rel_to_repo(res_path or _reservations_path(chain_dir), repo)
                # 마지막 예약을 소비하면 _save_reservations가 파일을 지운다 (loom/C079). 삭제된 경로는
                # tracked일 때만 git add에 넘긴다 — 삭제 스테이징은 되지만, tracked인 적 없이(예약이
                # 커밋 전) 삭제되면 `git add -- <부재경로>`가 pathspec 거부로 커밋을 통째 실패시킨다.
                if os.path.isfile(res_path or "") or _git(
                        repo, "ls-files", "--error-unmatch", res_rel, check=False).returncode == 0:
                    paths.append(res_rel)
            _git(repo, "add", "-A", "--", *paths)
            msg = f"gil: open {args.chain}/{cid} — 1/5 {_STEP_NAMES[1]}\n\n{title}"
            if consumed:
                msg += f"\n(예약 승격: {args.author}의 C{consumed['num']:03d} 예약을 소비)"
            _git(repo, "commit", "-m", msg, "--", *paths)
            if args.push and not consumed:  # 예약 승격은 격리 브랜치의 일 — 원장 재번호를 적용하지 않는다
                cid = _push_with_renumber(repo, chain_dir, args.chain, cid, title)
            elif args.push:
                _push(repo)
    print(f"열림: {args.chain}/{cid}" + (f" (예약 승격 — {args.author})" if consumed else ""))
    _refresh_viewers(chains_root, f"{args.chain}/{cid} 열림",
                     getattr(args, "no_web", False), args.push)
    return 0


def _reserve_commit_push(chains_root, chain_dir, args, verb, cid_hint):
    """예약 원장 변경을 커밋·push한다 (예약 원장은 사이클 밖 — 태그 봉인 무관)."""
    if not args.git:
        return
    repo = _repo_root(chains_root)
    if not repo and not _git_available():
        _warn_git_missing_once()  # git 부재: 예약 원장은 저장됨, 각인만 건너뜀 (loom/C052)
        return
    if not repo:
        raise ChainError("--git: 깃 저장소가 아니다")
    rel = _rel_to_repo(_reservations_path(chain_dir), repo)
    _git(repo, "add", "-A", "--", rel)
    _git(repo, "commit", "-m", f"gil: {verb} {args.chain}/{cid_hint}", "--", rel)
    if args.push:
        _push(repo)


def _branch_exists(repo, branch):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                       capture_output=True, text=True)
    return r.returncode == 0


def cmd_worktree(args):
    """병렬 사이클 모드 (loom/C058·C060, 발의: 박상현 #1). git worktree 명사에 올라탄다."""
    if args.wt_action == "add":
        return _worktree_add(args)
    if args.wt_action == "land":
        return _worktree_land(args)
    raise ChainError(f"알 수 없는 worktree 하위명령: {args.wt_action}")


def _worktree_add(args):
    """워크트리 생성 + 새 브랜치 + 사이클 열기를 원자적으로 묶는다 (loom/C058).

    open을 복제하지 않고 워크트리 안에서 gil을 self-invoke한다 — 두 이득:
    (1) open의 계약(번호 규율·fsck·스키마)이 검증된 한 곳에만 산다,
    (2) open이 워크트리 안(git toplevel=워크트리)에서 돌아 커밋이 그 브랜치에만 간다 —
        '메인에 잘못 open'(C050의 뼈아픈 사고)이 구조적으로 불가능해진다. cwd 계약을 도구가 집행한다."""
    chains_root = args.root
    if not _git_available():
        raise ChainError("worktree add: git이 필요하다 (병렬 사이클 모드는 워크트리 격리를 쓴다)")
    repo = _repo_root(chains_root)
    if not repo:
        raise ChainError(f"worktree add: 깃 저장소가 아니다 — {chains_root}")
    if not args.author:
        raise ChainError("worktree add: 저자를 알 수 없다 — --author <이름> (§3.2 P1)")
    if not _SLUG_RE.match(args.slug):
        raise ChainError(f"슬러그 '{args.slug}' 형식 위반 — R1: 소문자·숫자·하이픈만")

    # 결정론적 유도 — 사이클에서 브랜치·경로를 계산한다 (하네스 무의존, §7 이식 계약).
    branch = f"{args.author}/{args.chain}-{args.slug}"
    wt_path = os.path.join(os.path.dirname(repo),
                           f"{os.path.basename(repo)}-worktrees", f"{args.chain}-{args.slug}")
    if os.path.exists(wt_path):
        raise ChainError(f"worktree add: 경로가 이미 있다 — {wt_path}")
    if _branch_exists(repo, branch):
        raise ChainError(f"worktree add: 브랜치가 이미 있다 — {branch}")

    os.makedirs(os.path.dirname(wt_path), exist_ok=True)
    _git(repo, "worktree", "add", "-b", branch, wt_path, "HEAD")  # 새 브랜치로 격리 체크아웃

    # 워크트리 안의 chains 경로를 대상으로 gil self-invoke → open이 그 브랜치에 사이클을 커밋.
    chains_rel = _rel_to_repo(chains_root, repo)
    wt_chains = os.path.join(wt_path, chains_rel)
    cmd = [sys.executable, os.path.abspath(__file__), "open", args.chain, args.slug,
           "--author", args.author, "--root", wt_chains, "--date", args.date, "--git", "--no-web"]
    for p in args.parent:
        cmd += ["--parent", p]
    for l in args.lineage:
        cmd += ["--lineage", l]
    if args.new_chain:
        cmd.append("--new-chain")
    if args.new_root:
        cmd.append("--new-root")
    r = subprocess.run(cmd, cwd=wt_path, capture_output=True, text=True)
    if r.returncode != 0:
        # 원자성: open이 실패하면 워크트리·브랜치를 잔여 없이 되돌린다 (open 계열 무변화 규율 계승).
        _git(repo, "worktree", "remove", "--force", wt_path, check=False)
        _git(repo, "branch", "-D", branch, check=False)
        raise ChainError(f"worktree add: 워크트리 안 open 실패 — 되돌림\n{(r.stderr or r.stdout).strip()}")

    print(f"워크트리: {wt_path}")
    print(f"브랜치:   {branch}")
    print(f"→ 존재는 여기서 일한다:  cd {wt_path}  (메인 저장소로 돌아오지 말 것 — C050)")
    print(f"→ 돌아오면 소환자가 병합한다:  gil worktree land {args.chain} {args.slug} --author {args.author}")
    return 0


def _worktree_land(args):
    """병렬 사이클의 머지백 — add의 결정론적 매핑을 역산해 브랜치를 main에 --no-ff로 봉합한다 (loom/C060).

    add가 '여는 반쪽'(워크트리+브랜치+사이클)이면 land는 '닫는 반쪽'이다. open/close 로직을
    복제하지 않고 순수 git 오케스트레이션만 한다 — git merge --no-ff + worktree remove + branch -d.
    충돌은 삼키지 않는다: 병합이 실패하면 merge --abort로 무흔적 복귀 + 워크트리·브랜치 보존
    (사람이 해소). 정리는 병합 성공 시에만 — 병합 안 된 브랜치는 -d(안전 삭제)가 지키고 거부한다."""
    chains_root = args.root
    if not _git_available():
        raise ChainError("worktree land: git이 필요하다 (병렬 사이클 모드는 워크트리 격리를 쓴다)")
    repo = _repo_root(chains_root)
    if not repo:
        raise ChainError(f"worktree land: 깃 저장소가 아니다 — {chains_root}")
    if not args.author:
        raise ChainError("worktree land: 저자를 알 수 없다 — --author <이름> (§3.2 P1)")
    if not _SLUG_RE.match(args.slug):
        raise ChainError(f"슬러그 '{args.slug}' 형식 위반 — R1: 소문자·숫자·하이픈만")

    # 역산 — add와 동일 공식. 열 때 쓴 좌표가 곧 닫을 때 쓰는 좌표다.
    branch = f"{args.author}/{args.chain}-{args.slug}"
    wt_path = os.path.join(os.path.dirname(repo),
                           f"{os.path.basename(repo)}-worktrees", f"{args.chain}-{args.slug}")
    if not _branch_exists(repo, branch):
        raise ChainError(f"worktree land: 브랜치가 없다 — {branch} (되돌릴 것이 없다)")

    # --no-ff 병합: 병렬 작업의 봉합을 항상 한 병합 커밋으로 각인한다.
    msg = f"gil: land {args.chain}/{args.slug} ({branch})"
    r = _git(repo, "merge", "--no-ff", "--no-edit", "-m", msg, branch, check=False)
    if r.returncode != 0:
        # 충돌 등: 무흔적 복귀 + 워크트리·브랜치 보존 (충돌을 삼키지 않는다).
        _git(repo, "merge", "--abort", check=False)
        raise ChainError(
            f"worktree land: 병합 충돌 — 되돌림, 워크트리·브랜치 보존\n"
            f"  워크트리에서 해소 후 다시 land하라: {wt_path}\n{(r.stderr or r.stdout).strip()}")

    merge_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # 정리 (병합 성공 시에만). -d는 병합 안 된 브랜치를 거부하는 안전 삭제 — '정말 병합됐나'의 마지막 단언.
    if os.path.exists(wt_path):
        _git(repo, "worktree", "remove", "--force", wt_path, check=False)
    rd = _git(repo, "branch", "-d", branch, check=False)
    branch_pruned = rd.returncode == 0

    print(f"착지: {branch} → {repo} (병합 {merge_sha[:8]}, --no-ff)")
    print(f"정리: 워크트리 제거" + ("  + 브랜치 삭제" if branch_pruned else "  (브랜치 삭제 실패 — 수동 확인)"))
    if args.push:
        _push(repo)
    return 0


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
        if (row, col) in occupied:  # D3: 레인 재사용이 같은 깊이에 겹치면 미점유 열로 민다
            # free_slot(빈 트랙)과 occupied(빈 좌표)가 분리돼, 트랙이 비었는데 그 좌표가
            # 점유되면 free_slot이 같은 col을 무한 반환한다(loom/C076). 좌표 기준으로 통합해
            # col을 단조 증가시키면 유한 DAG에서 반드시 종료한다 — 정상 그래프 좌표는 불변.
            if tracks[col] == node:
                tracks[col] = None
            while (row, col) in occupied:
                col += 1
            while len(tracks) <= col:
                tracks.append(None)
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
.gil .parbanner{background:color-mix(in srgb,var(--lineage) 14%,var(--surface));
border:1px solid var(--lineage);border-radius:8px;padding:10px 14px;margin:0 0 20px;
font-size:14px;color:var(--ink);display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.gil .parbanner .picon{color:var(--lineage);font-weight:700}
.gil .parbanner .pchip{background:var(--surface);border:1px solid var(--ring);border-radius:999px;
padding:2px 10px;font-size:13px;color:var(--ink-2)}
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
        rel = _rel_to_repo(os.path.join(chains_root, chain, cid_dir), repo)
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
        # _dirs: cid → 디스크 디렉토리명. 위계 뷰어(loomlight/C002)가 스텝 파일을 찾는 데만 쓴다.
        # json_payload는 이 키를 직렬화하지 않으므로 기본 web 산출물은 바이트 동일로 남는다.
        dirs = {cid: c["_dir"] for cid, c in cycles.items()}
        data[name] = {"order": order, "cycles": entry, "children": children,
                      "reservations": res, "_dirs": dirs}
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


# ---------- 위계(드릴다운) 뷰어 (v2.16 / loomlight/C002) ----------
#
# 사이클이 많아질수록 평면 그래프 하나는 한눈에 안 들어온다. 위계로 나눠 드릴다운한다:
#   L1 체인 목록(요약) → L2 체인 그래프(지금의 평면 뷰어를 체인 하나로) → L3 사이클 5스텝 보고서.
# 근본 계약을 지킨다: JS 0줄·외부 리소스 0·자기완결. 드릴다운은 순수 HTML <details>/<summary>로,
# 딥링크는 앵커 id(#chain-*, #cycle-*)로 — 프래그먼트로 이동하면 브라우저가 조상 details를 자동으로
# 연다(HTML 표준). 이 위계는 한 화면에 전부를 안 그리므로 백로그 B1·B2·B3(가로·lineage밀도·라벨)을
# 구조적으로 완화한다.

_STEP_FILES = [("1 · 가설", "1-hypothesis.md"), ("2 · 설계", "2-design.md"),
               ("3 · 검증", "3-verification"),  # 디렉토리 — README + 산출물 목록
               ("4 · 분석", "4-analysis.md"), ("5 · 보고", "5-report.md")]

# [loom/C075] 완전한 앱 — 문서를 초기 DOM에 굽지 않고 gil-data JSON에 내장, 노드 클릭 시 JS가
# 그 하나의 DOM을 구축한다(fetch 없음 → 자기완결 유지). 초기 DOM은 그래프+메타만이라 계보 깊이에
# 무관하게 가볍다. 참조 구현(파이썬)이 생성하는 JS 문자열 — Go는 같은 문자열을 내야 parity(이번 이월).
_WEB_APP_JS = r"""
(function(){
  var data=null;
  try{ data=JSON.parse(document.getElementById("gil-data").textContent); }catch(e){ return; }
  var STEP_LABELS=["1 · 가설","2 · 설계","3 · 검증","4 · 분석","5 · 보고"];
  var done={};  // anchor -> true, 이미 그린 문서는 다시 안 그린다
  function esc(s){ var d=document.createElement("div"); d.textContent=(s==null?"":s); return d.innerHTML; }
  function metaRows(m){
    var f=[["status",m.status||"?"],["verdict",m.verdict||"—"],["step",m.step||"—"],
      ["parent",(m.parents&&m.parents.length?m.parents.join(", "):"(root)")],
      ["lineage",(m.lineage&&m.lineage.length?m.lineage.join(", "):"—")],
      ["opened",m.opened||"—"],["closed",m.closed||"진행 중"],
      ["deviations",(m.deviations!=null?m.deviations:"—")],
      ["corrections",(m.corrections!=null?m.corrections:"—")],
      ["superseded_by",m.superseded_by||"—"]];
    if(m.rounds) f.push(["rounds",m.rounds]);
    var h=""; for(var i=0;i<f.length;i++){ h+="<tr><th>"+esc(f[i][0])+"</th><td>"+esc(String(f[i][1]))+"</td></tr>"; }
    return h;
  }
  // 한 사이클의 body(메타표+5스텝)를 구축한다. gil-data의 cycle 메타·docs를 출처로.
  function build(el){
    var chain=el.getAttribute("data-chain"), cid=el.getAttribute("data-cid");
    var ch=data.chains[chain]; if(!ch) return;
    var meta=ch.cycles?ch.cycles[cid]:null; if(!meta) return;
    var docs=(ch.docs&&ch.docs[cid])?ch.docs[cid]:null;
    var steps=(docs&&docs.steps)?docs.steps:[];
    var body=el.querySelector(".cycbody"); if(!body) return;
    var h='<table class="hmeta"><tbody>'+metaRows(meta)+'</tbody></table>';
    for(var i=0;i<STEP_LABELS.length;i++){
      var content=(steps[i]&&steps[i].content!=null)?steps[i].content:null;
      var pre=(content==null)?'<pre class="empty">(없음)</pre>':'<pre>'+esc(content)+'</pre>';
      h+='<details class="hstep"><summary>'+esc(STEP_LABELS[i])+'</summary>'+pre+'</details>';
    }
    body.innerHTML=h;
  }
  // 해시(#cycdoc-*)가 가리키는 사이클을 그린다. 조상 <details>도 열어 스크롤이 닿게 한다.
  function activate(){
    var hash=location.hash||""; if(hash.indexOf("#cycdoc-")!==0) return;
    var id=hash.slice(1);
    var el=document.getElementById(id); if(!el) return;
    var p=el.parentNode;  // 조상 details 열기
    while(p){ if(p.tagName&&p.tagName.toLowerCase()==="details"){ p.open=true; } p=p.parentNode; }
    if(!done[id]){ build(el); done[id]=true; }
    el.scrollIntoView({block:"nearest"});
  }
  // lineage/노드 링크 클릭도 처리(해시가 같아 hashchange가 안 뜨는 경우 대비)
  document.addEventListener("click",function(ev){
    var a=ev.target; while(a&&a.tagName&&a.tagName.toLowerCase()!=="a") a=a.parentNode;
    if(a&&a.getAttribute&&(a.getAttribute("href")||"").indexOf("#cycdoc-")===0){ setTimeout(activate,0); }
  });
  window.addEventListener("hashchange",activate);
  if(document.readyState!=="loading") activate();
  else document.addEventListener("DOMContentLoaded",activate);
})();
"""

_WEB_HIER_CSS = """
.gil .htoc{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:16px 20px}
.gil .htoc h2{font-size:14px;font-weight:650;margin:0 0 10px}
.gil .htoc ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px}
.gil .htoc li{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;font-size:13px}
.gil .htoc a{color:var(--node);text-decoration:none;font-weight:600}
.gil .htoc a:hover{text-decoration:underline}
.gil .toc-stat{color:var(--muted);font-size:12px}
.gil .hhint{color:var(--muted);font-size:12px;margin:6px 0 0}
.gil .card.hmap{overflow-x:auto;padding:8px 12px}
/* L0 체인 지도(카드 직계 svg)만 폭에 맞춘다. 가로 사이클 그래프(.cyclegraph 안 svg)는 자연 크기로 두고
   스크롤한다 — max-width:100%가 넓은 그래프를 축소해 작게 만들던 문제 수정 (loom/C068). */
.gil .card.hmap>svg{display:block;margin:0 auto;max-width:100%}
.gil a.chainnode{cursor:pointer}
.gil a.chainnode circle{transition:fill .12s,stroke-width .12s}
.gil a.chainnode:hover circle{fill:var(--page);stroke-width:3.5}
.gil a.chainnode:focus{outline:none}
.gil a.chainnode:focus circle{stroke-width:3.5}
.gil .hanchor{display:block;height:0;overflow:hidden;scroll-margin-top:10px}
/* 체인 아코디언을 지도 카드 안에 녹인다 (loom/C066): 서브카드 테두리 없이 구분선만 — 지도에서
   체인을 누르면 그 자리 카드 안에서 사이클 노드가 아래로 주르륵 등장한다. */
.gil .mapchains{margin-top:12px;border-top:1px solid var(--ring)}
.gil details.hchain{border-bottom:1px solid var(--ring)}
.gil details.hchain>summary{cursor:pointer;padding:11px 4px;font-size:14px;font-weight:650;
list-style:none;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.gil details.hchain>summary::-webkit-details-marker{display:none}
.gil details.hchain>summary::before{content:"\\25B8";color:var(--muted);font-weight:400}
.gil details.hchain[open]>summary::before{content:"\\25BE"}
.gil details.hchain[open]>summary{background:var(--page);border-radius:6px}
.gil .hname{color:var(--ink)}
.gil .hstat{color:var(--muted);font-size:12.5px;font-weight:400}
.gil .hbody{padding:2px 4px 16px 14px;display:flex;flex-direction:column;gap:0}
.gil .hbody .card{margin:0}
/* 가로 사이클 노드-엣지 그래프 (loom/C067): 체인 원을 누르면 그 자리에서 0—o—o—o 로 펼쳐진다.
   노드를 누르면 :target으로 그 사이클 문서가 그래프 아래에 뜬다(평소 숨김). */
.gil .cyclegraph{overflow-x:auto;padding:4px 0 2px}
.gil a.gnode{cursor:pointer}
.gil a.gnode circle{transition:stroke-width .1s}
.gil a.gnode:hover circle{stroke:var(--node);stroke-width:4}
.gil .cycdoc{display:none}
.gil .cycdoc:target{display:block;border-top:1px solid var(--ring);margin-top:6px;padding-top:12px}
.gil .cycdoc-head{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px;
font-size:13px;font-variant-numeric:tabular-nums}
.gil .ccid{color:var(--ink);font-weight:650}
.gil .cyst{color:var(--muted);font-size:11.5px}
.gil .cytitle{color:var(--ink-2);font-size:12px}
.gil .cyclin{display:inline-flex;gap:8px;flex-wrap:wrap;align-items:baseline}
.gil a.linchip{color:var(--lineage);text-decoration:none;font-size:11px;font-weight:600;white-space:nowrap}
.gil a.linchip:hover{text-decoration:underline}
.gil a.linchip.sup{color:var(--supersede)}
.gil .hcycles h3{font-size:13px;font-weight:650;margin:4px 0 8px;color:var(--ink-2)}
.gil details.hcycle{border:1px solid var(--hairline);border-radius:6px;margin-bottom:6px}
.gil details.hcycle>summary{cursor:pointer;padding:8px 12px;font-size:13px;font-weight:600;color:var(--ink);
list-style:none;font-variant-numeric:tabular-nums}
.gil details.hcycle>summary::-webkit-details-marker{display:none}
.gil details.hcycle>summary::before{content:"\\25B8  ";color:var(--muted)}
.gil details.hcycle[open]>summary::before{content:"\\25BE  "}
.gil .hcycle-body{padding:0 12px 12px}
.gil table.hmeta{width:auto;margin:4px 0 12px;font-size:12px}
.gil table.hmeta th{color:var(--muted);font-weight:600;padding:3px 14px 3px 0;text-align:left;
border:none;white-space:nowrap;vertical-align:top}
.gil table.hmeta td{color:var(--ink-2);padding:3px 0;border:none}
.gil details.hstep{margin:4px 0}
.gil details.hstep>summary{cursor:pointer;font-size:12px;font-weight:600;color:var(--node);
padding:3px 0;list-style:none}
.gil details.hstep>summary::-webkit-details-marker{display:none}
.gil details.hstep>summary::before{content:"+  "}
.gil details.hstep[open]>summary::before{content:"\\2212  "}
.gil details.hstep pre{background:var(--page);border:1px solid var(--hairline);border-radius:6px;
padding:12px;overflow-x:auto;font-size:12px;line-height:1.5;white-space:pre-wrap;word-break:break-word;
color:var(--ink-2);margin:4px 0 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.gil details.hstep pre.empty{color:var(--muted);font-style:italic}
/* 미니맵 (loomlight/C004): 넓은 체인 가로 그래프 위 전체 개요. max-width:100%로 카드 폭에 맞춰
   축소돼 전체 형상이 한 화면에 든다(C068의 자연크기 통찰을 미니맵엔 반대로=폭맞춤 적용). */
.gil .minimap{margin:2px 0 8px;padding:7px 10px;background:var(--surface);border:1px solid var(--ring);border-radius:8px}
.gil .minimap-cap{color:var(--muted);font-size:11.5px;margin-bottom:5px}
.gil .minimap svg{display:block;max-width:100%;height:auto}
.gil a.mnode{cursor:pointer}
.gil a.mnode circle{transition:stroke-width .1s}
.gil a.mnode:hover circle{stroke:var(--node);stroke-width:2.5}
""".strip()


def _verdict_tally(chain):
    """체인 요약: 닫힌 사이클을 verdict별로, 열린 사이클을 따로 센다."""
    counts, openn = {}, 0
    for cid in chain["order"]:
        m = chain["cycles"][cid]
        if m.get("status") == "closed":
            key = m.get("verdict") or "무결론"
            counts[key] = counts.get(key, 0) + 1
        else:
            openn += 1
    order = ["supported", "rejected", "refuted", "inconclusive", "무결론"]
    parts = [f"{v} {counts[v]}" for v in order if counts.get(v)]
    parts += [f"{v} {n}" for v, n in counts.items() if v not in order]  # 미지 verdict도 정직히
    if openn:
        parts.append(f"열림 {openn}")
    return " · ".join(parts) if parts else "—"


def _chain_recent(chain):
    """체인의 가장 최근 활동일 — opened/closed 중 최댓값(ISO 날짜는 문자열 비교로 정렬된다)."""
    dates = [d for cid in chain["order"]
             for d in (chain["cycles"][cid].get("closed") or chain["cycles"][cid].get("opened"),)
             if d]
    return f"최근 {max(dates)}" if dates else "최근 —"


def _read_step(chains_root, name, cdir, fname):
    """스텝 파일(또는 3-verification 디렉토리)의 원문을 읽는다. 없으면 None.
    렌더는 마크다운 파싱 없이 <pre>로 원문 그대로 — 정직하고 자기완결적이며 JS가 필요 없다."""
    if not chains_root:
        return None
    path = os.path.join(chains_root, name, cdir, fname)
    if fname == "3-verification":
        parts = []
        readme = os.path.join(path, "README.md")
        if os.path.isfile(readme):
            try:
                with open(readme, encoding="utf-8") as f:
                    parts.append(f.read())
            except OSError:
                pass
        try:
            entries = sorted(e for e in os.listdir(path) if e != "README.md")
        except OSError:
            entries = []
        if entries:
            parts.append("[검증 산출물]\n" + "\n".join("- " + e for e in entries))
        return "\n\n".join(parts) if parts else None
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None
    return None


_H_COLW, _H_ROWH, _H_X0, _H_Y0, _H_R = 116, 60, 50, 46, 9
# 미니맵 (loomlight/C004): 본 그래프와 같은 (깊이,레인)을 작은 정수 좌표로 압축. 삼각함수·나눗셈
# 없이 정수만 → 참조·Go 바이트 동일(C064). 깊이 < _MINI_MIN_DEPTH 인 좁은 체인은 미니맵 미출력.
_MINI_COLW, _MINI_ROWH, _MINI_R, _MINI_X0, _MINI_Y0, _MINI_MIN_DEPTH = 9, 9, 3, 6, 8, 12


def _render_cycle_graph_h(name, chain):
    """가로 사이클 노드-엣지 그래프 (loom/C067). x=깊이(루트→오른쪽), y=레인. 노드=사이클,
    실선=parent, 노드 아래 초록 ⇠=교차-체인 lineage. 노드를 누르면 #cycdoc-*로 이동해 그
    사이클의 5스텝 문서가 그래프 아래에 드러난다(:target). 좌표는 모두 정수(평면 그래프와 같은 스타일).
    체인 원(L0 지도)을 누르면 이 그래프가 그 자리에서 펼쳐진다 — 스케치의 0—o—o—o—o."""
    order = chain["order"]
    if not order:
        return ""
    cyc = chain["cycles"]
    pos = _layout_columns(order, {cid: {"parents": c["parents"]} for cid, c in cyc.items()},
                          chain["children"])
    node_xy = {cid: (_H_X0 + row * _H_COLW, _H_Y0 + col * _H_ROWH) for cid, (row, col) in pos.items()}
    max_depth = max((r for r, _ in pos.values()), default=0)
    max_lane = max((c for _, c in pos.values()), default=0)
    width = _H_X0 + max_depth * _H_COLW + 90
    height = _H_Y0 + max_lane * _H_ROWH + 46
    p = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
         f'aria-label="{html.escape(name)} 사이클 그래프">']
    # parent 실선 (왼쪽 부모 → 오른쪽 자식)
    for cid in order:
        x2, y2 = node_xy[cid]
        for par in cyc[cid]["parents"]:
            if par in node_xy:
                x1, y1 = node_xy[par]
                mx = (x1 + x2) // 2
                p.append(f'<path d="M{x1 + _H_R},{y1} C{mx},{y1} {mx},{y2} {x2 - _H_R},{y2}" '
                         f'fill="none" stroke="var(--edge)" stroke-width="1.6"/>')
    # 노드 (클릭 → 그 사이클 문서) + 교차-체인 lineage 표시
    for cid in order:
        x, y = node_xy[cid]
        meta = cyc[cid]
        closed = meta["status"] == "closed"
        fill = "var(--rejected)" if meta.get("verdict") == "rejected" else "var(--node)"
        shape = (f'<circle cx="{x}" cy="{y}" r="{_H_R}" fill="{fill}"/>' if closed else
                 f'<circle cx="{x}" cy="{y}" r="{_H_R - 1}" fill="var(--surface)" '
                 f'stroke="var(--node)" stroke-width="2.5"/>')
        num = html.escape(cid.split("-")[0])
        vtip = f" · {meta['verdict']}" if meta.get("verdict") else ""
        lin = meta.get("lineage") or []
        st = meta.get("status") or "?"  # statusText 의미 — Go(statusText)와 비트 동일
        tip = html.escape(f"{cid} [{st}{vtip}] {meta.get('title') or ''}"
                          + (f"  ⇠ {', '.join(lin)}" if lin else ""))
        lin_txt = ""
        if lin:
            first = lin[0].split("/", 1)[1] if "/" in lin[0] else lin[0]
            more = f" +{len(lin) - 1}" if len(lin) > 1 else ""
            lin_txt = (f'<text x="{x}" y="{y + _H_R + 28}" text-anchor="middle" font-size="9.5" '
                       f'fill="var(--lineage)">⇠ {html.escape(first)}{more}</text>')
        p.append(f'<a href="#cycdoc-{html.escape(name + "-" + cid)}" class="gnode">'
                 f'<title>{tip}</title>{shape}'
                 f'<text x="{x}" y="{y + _H_R + 14}" text-anchor="middle" font-size="10.5" '
                 f'font-weight="600" fill="var(--ink-2)">{num}</text>{lin_txt}</a>')
    p.append("</svg>")
    return "".join(p)


def _render_cycle_minimap(name, chain):
    """넓은 체인(깊이 ≥ _MINI_MIN_DEPTH) 가로 그래프 위에 얹는 미니맵 (loomlight/C004).
    본 그래프(`_render_cycle_graph_h`)와 같은 (깊이,레인)을 작은 정수 좌표로 압축한다. 각 노드는
    본 그래프 노드와 같은 #cycdoc-* 로 점프하는 <a> — 클릭하면 그 사이클 문서가 :target으로 열린다.
    CSS `.minimap svg{max-width:100%}`로 카드 폭에 맞춰 축소돼 전체 형상이 한 화면에 든다(축소는
    표시뿐, 좌표는 정수 → 참조·Go 바이트 동일). 좁은 체인은 "" 반환(출력 개선 전과 바이트 동일)."""
    order = chain["order"]
    if not order:
        return ""
    cyc = chain["cycles"]
    pos = _layout_columns(order, {cid: {"parents": c["parents"]} for cid, c in cyc.items()},
                          chain["children"])
    max_depth = max((r for r, _ in pos.values()), default=0)
    if max_depth < _MINI_MIN_DEPTH:
        return ""
    max_lane = max((c for _, c in pos.values()), default=0)
    node_xy = {cid: (_MINI_X0 + row * _MINI_COLW, _MINI_Y0 + col * _MINI_ROWH)
               for cid, (row, col) in pos.items()}
    width = _MINI_X0 + max_depth * _MINI_COLW + _MINI_X0
    height = _MINI_Y0 + max_lane * _MINI_ROWH + _MINI_Y0
    p = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
         f'aria-label="{html.escape(name)} 미니맵">']
    # parent 엣지 = 직선(정수 좌표, 삼각함수·나눗셈 없음)
    for cid in order:
        x2, y2 = node_xy[cid]
        for par in cyc[cid]["parents"]:
            if par in node_xy:
                x1, y1 = node_xy[par]
                p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                         f'stroke="var(--edge)" stroke-width="1"/>')
    # 노드 = 작은 원, 클릭 → 본 그래프와 같은 #cycdoc-* (색 규칙도 본 그래프와 동일)
    for cid in order:
        x, y = node_xy[cid]
        meta = cyc[cid]
        closed = meta["status"] == "closed"
        fill = "var(--rejected)" if meta.get("verdict") == "rejected" else "var(--node)"
        shape = (f'<circle cx="{x}" cy="{y}" r="{_MINI_R}" fill="{fill}"/>' if closed else
                 f'<circle cx="{x}" cy="{y}" r="{_MINI_R}" fill="var(--surface)" '
                 f'stroke="var(--node)" stroke-width="1.5"/>')
        p.append(f'<a href="#cycdoc-{html.escape(name + "-" + cid)}" class="mnode">'
                 f'<title>{html.escape(cid)}</title>{shape}</a>')
    p.append("</svg>")
    return (f'<div class="minimap"><div class="minimap-cap">미니맵 — 전체 개요 · '
            f'노드 클릭 → 그 사이클 문서</div>{"".join(p)}</div>')


def _collect_cycle_docs(chains_root, name, cid, meta, cdir):
    """한 사이클의 5스텝 문서 텍스트를 수집해 gil-data JSON에 내장할 dict로 반환한다 (loom/C075).
    무게 문제: 전문을 초기 HTML에 인라인하면 계보 깊이에 비례해 DOM(표·pre·details 수천)이
    항상 렌더 트리에 올라가 CPU가 치솟는다. 문서를 JSON에 담아 두고 JS가 노드 클릭 시에만
    그 하나의 DOM을 구축한다 — fetch 없이(자기완결) 초기 DOM은 그래프+메타만."""
    steps = [{"label": label, "content": _read_step(chains_root, name, cdir, fname)}
             for label, fname in _STEP_FILES]
    return {"steps": steps}


def _render_cycle_detail(name, cid, meta, chains_root, cdir):
    """가로 사이클 그래프(loom/C067)의 노드를 누르면 :target으로 드러나는 그 사이클의 5스텝 문서.
    평소엔 숨어 있고(display:none), #cycdoc-*가 타겟이면 그래프 아래에 나타난다.
    [loom/C075] 완전한 앱화 이후 초기 HTML에는 쓰이지 않는다 — 문서는 gil-data JSON에 내장되고
    JS가 클릭 시 DOM을 구축한다. 이 함수는 참조·회귀 비교용으로 보존."""
    status = meta.get("status") or "?"
    vtip = f" · {meta['verdict']}" if meta.get("verdict") else ""
    state = f"{status}{vtip}{_step_badge(meta)}"
    title = meta.get("title") or ""
    # lineage 칩 — 교훈 원천(다른 사이클) 문서로 점프. 그 체인 아코디언도 함께 열린다.
    lin = ""
    if meta.get("lineage"):
        chips = "".join(
            f'<a class="linchip" href="#cycdoc-{html.escape(ref.replace("/", "-"))}">⇠ {html.escape(ref)}</a>'
            for ref in meta["lineage"])
        lin = f'<span class="cyclin">{chips}</span>'
    sup = meta.get("superseded_by")
    sup_html = (f'<a class="linchip sup" href="#cycdoc-{html.escape(_supersede_ref(name, sup).replace("/", "-"))}">'
                f'↣ {html.escape(sup)}</a>') if sup else ""
    title_html = f'<span class="cytitle">{html.escape(title)}</span>' if title else ""

    fields = [("status", status), ("verdict", meta.get("verdict") or "—"),
              ("step", meta.get("step") or "—"),
              ("parent", ", ".join(meta.get("parents") or []) or "(root)"),
              ("lineage", ", ".join(meta.get("lineage") or []) or "—"),
              ("opened", meta.get("opened") or "—"),
              ("closed", meta.get("closed") or "진행 중"),
              ("deviations", meta.get("deviations") if meta.get("deviations") is not None else "—"),
              ("corrections", meta.get("corrections") if meta.get("corrections") is not None else "—"),
              ("superseded_by", meta.get("superseded_by") or "—")]
    if meta.get("rounds"):
        fields.append(("rounds", meta["rounds"]))
    meta_rows = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
                        for k, v in fields)
    steps = []
    for label, fname in _STEP_FILES:
        content = _read_step(chains_root, name, cdir, fname)
        pre = ('<pre class="empty">(없음)</pre>' if content is None
               else f"<pre>{html.escape(content)}</pre>")
        steps.append(f'<details class="hstep"><summary>{html.escape(label)}</summary>{pre}</details>')
    anchor = html.escape(f"{name}-{cid}")
    head = (f'<div class="cycdoc-head"><span class="ccid">{html.escape(cid)}</span>'
            f'<span class="cyst">{html.escape(state)}</span>{title_html}{lin}{sup_html}</div>')
    return (f'<div class="cycdoc" id="cycdoc-{anchor}">{head}'
            f'<table class="hmeta"><tbody>{meta_rows}</tbody></table>'
            f'{"".join(steps)}</div>')


def _render_cycle_mount(name, cid, meta):
    """[loom/C075] 경량 마운트 — 초기 HTML에 head(제목·상태·lineage 칩)만 두고, 무거운
    메타표+5스텝 문서는 비워 둔다. 노드를 누르면 JS가 gil-data의 docs로 `.cycbody`를 채운다.
    head를 남기는 이유: 클릭 전에도 무슨 사이클인지 보이고, JS 미실행 환경에서도 최소 정보 보존."""
    status = meta.get("status") or "?"
    vtip = f" · {meta['verdict']}" if meta.get("verdict") else ""
    state = f"{status}{vtip}{_step_badge(meta)}"
    title = meta.get("title") or ""
    title_html = f'<span class="cytitle">{html.escape(title)}</span>' if title else ""
    lin = ""
    if meta.get("lineage"):
        chips = "".join(
            f'<a class="linchip" href="#cycdoc-{html.escape(ref.replace("/", "-"))}">⇠ {html.escape(ref)}</a>'
            for ref in meta["lineage"])
        lin = f'<span class="cyclin">{chips}</span>'
    sup = meta.get("superseded_by")
    sup_html = (f'<a class="linchip sup" href="#cycdoc-{html.escape(_supersede_ref(name, sup).replace("/", "-"))}">'
                f'↣ {html.escape(sup)}</a>') if sup else ""
    anchor = html.escape(f"{name}-{cid}")
    head = (f'<div class="cycdoc-head"><span class="ccid">{html.escape(cid)}</span>'
            f'<span class="cyst">{html.escape(state)}</span>{title_html}{lin}{sup_html}</div>')
    return (f'<div class="cycdoc" id="cycdoc-{anchor}" data-chain="{html.escape(name)}" '
            f'data-cid="{html.escape(cid)}">{head}<div class="cycbody"></div></div>')


def _render_chain_map(data):
    """L0: 체인 하나가 큰 원인 상위 그래프 (loom/C064). 원=체인(크기 ∝ 사이클 수, 색=상태),
    점선 초록 화살표=체인 간 lineage(교훈 원천→인용 체인, 굵기·숫자 ∝ 건수). 원을 누르면 아래
    그 체인의 <details>가 열린다 — 프래그먼트(#chainbody-*)로 이동하면 브라우저가 조상 details를
    자동으로 연다. 한눈에 lineage를 보여주는 지도이자, 위계 드릴다운으로 내려가는 입구.
    허브(최다 연결 체인)를 가운데로, 엣지 끝점을 원 둘레에 부채꼴로 흩어 화살표 겹침을 줄인다."""
    names = list(data.keys())
    if not names:
        return ""

    def ncyc(nm):
        return len(data[nm]["order"])

    def openn(nm):
        return sum(1 for c in data[nm]["order"] if data[nm]["cycles"][c].get("status") != "closed")

    def has_rejected(nm):
        return any(data[nm]["cycles"][c].get("verdict") == "rejected" for c in data[nm]["order"])

    def first_date(nm):
        ds = [data[nm]["cycles"][c].get("opened") for c in data[nm]["order"]]
        ds = [d for d in ds if d]
        return (min(ds) if ds else "9999-99-99", nm)

    # 체인 간 엣지 집계: source(교훈 원천) → target(인용 체인), 방향은 기존 사이클 그래프와 동일.
    edges = {}
    for name in data:
        for cid in data[name]["order"]:
            for ref in data[name]["cycles"][cid]["lineage"]:
                other = ref.split("/", 1)[0]
                if other in data and other != name:
                    edges[(other, name)] = edges.get((other, name), 0) + 1
    nbr = {nm: set() for nm in names}
    for a, b in edges:
        nbr[a].add(b)
        nbr[b].add(a)

    # 순서: 연대순 기본 + 허브(최다 연결, 동률이면 사이클 많은 쪽)를 가운데로 — 허브의 스포크가 좌우 대칭이 되어 짧아진다.
    base = sorted(names, key=first_date)
    if len(base) > 2 and edges:
        # 허브 = 최다 연결(동률이면 사이클 많은 쪽). 정렬된 base에서 고른다 — 딕셔너리 순서에 의존하지
        # 않아 Go 이식과 동률 처리가 일치한다(첫 최대 = base의 앞쪽).
        hub = max(base, key=lambda nm: (len(nbr[nm]), ncyc(nm)))
        rest = [nm for nm in base if nm != hub]
        order = rest[:len(rest) // 2] + [hub] + rest[len(rest) // 2:]
    else:
        order = base

    def radius(nm):  # √(사이클 수)로 완만히, 클램프 — 큰 체인이 화면을 삼키지 않게.
        # math.sqrt는 IEEE 보장(correctly-rounded)이라 Go와 비트 동일 — 바이트 parity를 위해 **0.5 대신 이걸 쓴다.
        return max(16.0, min(46.0, 12.0 + 4.6 * math.sqrt(ncyc(nm))))
    rad = {nm: radius(nm) for nm in order}
    rmax = max(rad.values())
    spacing = 2 * rmax + 104
    x0 = 44 + rmax
    cx = {nm: x0 + i * spacing for i, nm in enumerate(order)}

    # 아치 높이 — 위쪽으로만 굽혀 아래 라벨과 안 겹치게. 양방향 쌍은 역방향을 바깥으로 겹쳐(nest) 구분.
    arc = {}
    for (src, tgt), n in edges.items():
        dist = abs(cx[tgt] - cx[src])
        extra = 26 if ((tgt, src) in edges and cx[src] > cx[tgt]) else 0
        arc[(src, tgt)] = 38 + 0.12 * dist + extra
    max_arc = max(arc.values(), default=0)
    # 2차 베지어 정점은 제어점 오프셋의 절반. 위 여백은 그만큼만, 원이 프레임 밖으로 안 나가게 하한.
    ycen = max(max_arc / 2 + 18, rmax + 8)
    width = x0 + (len(order) - 1) * spacing + rmax + 44
    height = ycen + rmax + 46

    p = [f'<svg viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}" '
         f'role="img" aria-label="체인 지도 — 체인 간 lineage 그래프">',
         '<defs><marker id="chainarrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" '
         'markerHeight="6.5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
         'fill="var(--lineage)"/></marker></defs>']
    # lineage 아치 (점선 화살표) — 노드보다 먼저 그려 노드가 위에 오게. 끝점을 아치 정점 방향의
    # 원 둘레에 놓아(부채꼴) 화살표가 한 점에 쌓이지 않게 한다.
    for (src, tgt), n in sorted(edges.items()):
        xs, xt = cx[src], cx[tgt]
        ah = arc[(src, tgt)]
        mx, apex = (xs + xt) / 2, ycen - ah
        # 끝점 = 원 중심에서 아치 정점 방향으로 반지름만큼. 삼각함수 대신 벡터 정규화(sqrt만) —
        # sin/cos/atan2는 IEEE correctly-rounded 미보장이라 Go와 마지막 ULP가 갈릴 수 있다(바이트 parity 위험).
        dx1, dy1 = mx - xs, apex - ycen
        l1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
        dx2, dy2 = mx - xt, apex - ycen
        l2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
        x1, y1 = xs + rad[src] * dx1 / l1, ycen + rad[src] * dy1 / l1
        x2, y2 = xt + rad[tgt] * dx2 / l2, ycen + rad[tgt] * dy2 / l2
        w = 1.2 + 0.55 * min(n, 5)
        p.append(f'<path d="M{x1:.1f},{y1:.1f} Q{mx:.1f},{apex:.1f} {x2:.1f},{y2:.1f}" '
                 f'fill="none" stroke="var(--lineage)" stroke-width="{w:.1f}" stroke-dasharray="5 4" '
                 f'marker-end="url(#chainarrow)" opacity="0.8"/>')
        if n > 1:  # 건수 라벨을 시각적 정점(정점 오프셋의 절반) 근처에 — 후광으로 선 위에서 읽히게
            vy = ycen - ah / 2
            p.append(f'<text x="{mx:.1f}" y="{vy - 3:.1f}" text-anchor="middle" font-size="10" '
                     f'font-weight="700" fill="var(--lineage)" stroke="var(--surface)" '
                     f'stroke-width="3" paint-order="stroke">{n}</text>')
    # 체인 노드 — 큰 원(안에 사이클 수), 아래 이름+요약. 색=상태(rejected→빨강, 열림→점선 링).
    for nm in order:
        x, r = cx[nm], rad[nm]
        chain = data[nm]
        nc, no = ncyc(nm), openn(nm)
        col = "var(--rejected)" if has_rejected(nm) else "var(--node)"
        tip = html.escape(f"{nm} — 사이클 {nc}개 · {_verdict_tally(chain)} · {_chain_recent(chain)}")
        num_fs = max(12, min(22, r * 0.82))
        ring = (f'<circle cx="{x:.0f}" cy="{ycen:.0f}" r="{r + 4:.0f}" fill="none" stroke="{col}" '
                f'stroke-width="1.2" stroke-dasharray="3 3" opacity="0.55"/>') if no else ""
        p.append(f'<a href="#chainbody-{html.escape(nm)}" class="chainnode" aria-label="{tip}">'
                 f'<title>{tip}</title>{ring}'
                 f'<circle cx="{x:.0f}" cy="{ycen:.0f}" r="{r:.0f}" fill="var(--surface)" '
                 f'stroke="{col}" stroke-width="2.5"/>'
                 f'<text x="{x:.0f}" y="{ycen + num_fs * 0.34:.0f}" text-anchor="middle" '
                 f'font-size="{num_fs:.0f}" font-weight="700" fill="{col}">{nc}</text>'
                 f'<text x="{x:.0f}" y="{ycen + r + 17:.0f}" text-anchor="middle" font-size="13" '
                 f'font-weight="650" fill="var(--ink)">{html.escape(nm)}</text>'
                 f'<text x="{x:.0f}" y="{ycen + r + 32:.0f}" text-anchor="middle" font-size="10.5" '
                 f'fill="var(--muted)">사이클 {nc}{" · 열림 " + str(no) if no else ""}</text>'
                 f'</a>')
    p.append("</svg>")
    return "".join(p)


def _render_parallel_banner(data):
    """진행 중 병렬 사이클(미소비 예약)을 페이지 상단 배너로 드러낸다 (loom/C073, #4·상현님 요청).
    워크트리 브랜치에 사는 병렬 사이클은 그래프에 아직 안 뜨지만 예약은 main에 커밋돼 있다 —
    `gil threads`가 CLI로 답하는 "뭐가 병렬로 도나"를 뷰어가 배너로 답한다. 데이터는 gil-data의
    reservations(계약면)에서 오고, 이 함수는 렌더일 뿐이다(C021). 예약 0이면 빈 문자열 → 바이트 동일."""
    items = []
    for name in sorted(data):
        for r in (data[name].get("reservations") or []):
            items.append((name, r))
    if not items:
        return ""
    chips = "".join(
        f'<span class="pchip">{html.escape(name)}/C{r["num"]:03d} → {html.escape(r["for"])}</span>'
        for name, r in items)
    return (f'<div class="parbanner" role="status">'
            f'<span class="picon">⟳</span> 병렬 진행 중 (예약, 아직 안 거둬짐): '
            f'<b>{len(items)}</b>{chips}</div>')


def _render_hierarchy_body(data, page_title, generated, n_cycles, n_lineage, chains_root, gil_data_json):
    """위계 뷰어 몸체. L0 체인 지도 → L1 목차 → 체인별 <details>(그래프+표) → 사이클별 <details>(5스텝)."""
    style = _WEB_CSS + "\n" + _WEB_HIER_CSS
    toc = []
    chains_html = []
    for name, chain in data.items():
        n = len(chain["order"])
        toc.append(f'<li><a href="#chain-{html.escape(name)}">{html.escape(name)}</a>'
                   f'<span class="toc-stat">사이클 {n}개 · {html.escape(_verdict_tally(chain))}</span></li>')
        stats = f"사이클 {n}개 · {_verdict_tally(chain)} · {_chain_recent(chain)}"
        dirs = chain.get("_dirs", {})
        # [loom/C075] 문서 전문 인라인(_render_cycle_detail) 대신 경량 마운트만. 문서는 gil-data에
        # 내장되고 JS가 클릭 시 채운다 — 초기 DOM이 계보 깊이에 무관하게 가벼워진다.
        cyc = [_render_cycle_mount(name, cid, chain["cycles"][cid])
               for cid in chain["order"]]
        # 체인을 누르면(지도 원·요약) 그 자리에서 가로 사이클 노드-엣지 그래프가 펼쳐진다 (loom/C067):
        # SVG 그래프(0—o—o—o) + 그 아래 숨은 문서들. 노드를 누르면 :target으로 그 사이클 문서가 뜬다.
        # name="hchain" 아코디언 — 하나 열면 나머지 접힘.
        chains_html.append(
            f'<details class="hchain" name="hchain" id="chain-{html.escape(name)}">'
            f'<summary><span class="hname">{html.escape(name)}</span>'
            f'<span class="hstat">{html.escape(stats)}</span></summary>'
            f'<div class="hbody"><span id="chainbody-{html.escape(name)}" class="hanchor"></span>'
            f'{_render_cycle_minimap(name, chain)}'
            f'<div class="cyclegraph">{_render_cycle_graph_h(name, chain)}</div>'
            f'<div class="cycdocs">{"".join(cyc)}</div></div></details>')
    return f"""<div class="gil"><style>{style}</style><div class="wrap">
<header><h1>{html.escape(page_title)}</h1>
<p>체인 {len(data)}개 · 사이클 {n_cycles}개 · 체인 간 lineage {n_lineage}건 · 생성 {html.escape(generated)}</p>
<p class="hhint">체인 지도의 원(=체인, 크기 ∝ 사이클 수)을 누르면 그 자리 카드 안에서 사이클 노드가 아래로 주르륵 펼쳐진다. 점선 화살표는 체인 간 lineage(교훈의 흐름). 노드를 누르면 그 자리에 5스텝 문서가 열린다.</p></header>
{_render_parallel_banner(data)}
<div class="card hmap">{_render_chain_map(data)}
<div class="mapchains">{"".join(chains_html)}</div></div>
<nav class="htoc"><h2>체인 목록</h2><ul>{"".join(toc)}</ul></nav>
<footer>Ariadne — 사이클은 행동 체인의 기록이다. 이 문서는 gil web이 생성한 자기완결적 정적 페이지다.</footer>
</div></div>
<script type="application/json" id="gil-data">{gil_data_json}</script>
<script>{_WEB_APP_JS}</script>"""


def _json_for_script(payload):
    """JSON을 <script> 안에 안전하게 넣는다 (loom/C075). 문서 텍스트가 `</script>`를 포함하면
    (사이클 문서가 gil web 코드를 인용한 경우 실제로 있다) 브라우저가 스크립트를 조기 종료해
    JSON 파싱이 깨진다. `</`를 `<\\/`로 치환 — JSON 값으로는 동일(역슬래시-슬래시=슬래시)하고
    HTML 파서는 `</script>`로 안 본다. 문서를 초기 DOM에서 뺀 뒤 표면화된 결함의 봉인."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_web_page(data, page_title, generated, only=None, refresh=None, hierarchy=False, chains_root=None):
    # [loom/C075] 완전한 앱: 위계 모드에선 5스텝 문서를 초기 HTML에 굽지 않고 gil-data JSON에 내장한다.
    # JS가 노드 클릭 시 그 하나의 DOM을 구축 → 초기 DOM은 그래프+메타만(계보 깊이에 무관하게 경량).
    # flat(--flat) 경로는 문서를 애초에 렌더하지 않으므로 무영향(바이트 동일).
    cyc_docs = {}
    if hierarchy:
        for name, chain in data.items():
            dirs = chain.get("_dirs", {})
            for cid in chain["order"]:
                cyc_docs.setdefault(name, {})[cid] = _collect_cycle_docs(
                    chains_root, name, cid, chain["cycles"][cid], dirs.get(cid, cid))
    json_payload = {
        # v0.4 (loom/C042): bake — 이 산출물이 **자기를 어떻게 다시 굽는지** 스스로 말한다.
        # 추론(체인이 하나뿐이니 필터겠지)은 거짓일 수 있다 — 그래서 추측하지 않고 기록한다 (C040).
        # v0.5 (loom/C049): refresh — 자동 리로드 주기. 자동 재굽기가 이 값을 보존해 실시간이 유지된다.
        "version": "0.4",
        "bake": {"title": page_title, "chain": only,
                 **({"refresh": refresh} if refresh else {}),  # 있을 때만 (C043) — 무리프레시 바이트 동일
                 # v2.16 (loomlight/C002): hierarchy — 위계(드릴다운) 모드. 자동 재굽기가 이 값을
                 # 보존해 위계가 유지된다(C042의 "창이 원장을 따른다"를 위계에도 확장). 무옵션 바이트 동일.
                 **({"hierarchy": True} if hierarchy else {})},
        "chains": {
            name: {
                "order": chain["order"],
                "cycles": chain["cycles"],
                # 예약이 있을 때만 키를 넣는다 — 무예약 저장소는 이전 산출물과 바이트 동일 (파서 계약 보존).
                **({"reservations": chain["reservations"]} if chain.get("reservations") else {}),
                # [loom/C075] 위계 모드에서만 5스텝 문서를 내장한다. flat은 이 키가 없어 바이트 동일.
                **({"docs": cyc_docs[name]} if hierarchy and name in cyc_docs else {}),
            } for name, chain in data.items()
        },
    }
    n_cycles = sum(len(c["order"]) for c in data.values())
    n_lineage = sum(len(m["lineage"]) for c in data.values() for m in c["cycles"].values())
    if hierarchy:
        # 위계(드릴다운) 몸체 — 기본 경로를 건드리지 않도록 완전히 분기한다 (아래 else는 개선 전과 바이트 동일).
        body = _render_hierarchy_body(data, page_title, generated, n_cycles, n_lineage,
                                      chains_root, _json_for_script(json_payload))
    else:
        body = f"""<div class="gil"><style>{_WEB_CSS}</style><div class="wrap">
<header><h1>{html.escape(page_title)}</h1>
<p>체인 {len(data)}개 · 사이클 {n_cycles}개 · 체인 간 lineage {n_lineage}건 · 생성 {html.escape(generated)}</p></header>
{_render_parallel_banner(data)}
<div class="legend"><span><svg width="16" height="16"><circle cx="8" cy="8" r="6.5" fill="var(--node)"/></svg>닫힌 사이클</span>
<span><svg width="16" height="16"><circle cx="8" cy="8" r="5.5" fill="var(--surface)" stroke="var(--node)" stroke-width="2"/></svg>열린 사이클</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--edge)" stroke-width="1.6"/></svg>parent (체인 내 계보)</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--lineage)" stroke-width="1.6" stroke-dasharray="5 4"/></svg>lineage (체인 간 교훈)</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--supersede)" stroke-width="1.6" stroke-dasharray="2 3"/></svg>superseded_by (무효화 — 흐린 노드가 대체 사이클을 가리킨다)</span></div>
<div class="card">{_render_svg(data)}</div>
{_render_tables(data)}
<footer>Ariadne — 사이클은 행동 체인의 기록이다. 이 문서는 gil web --flat이 생성한 자기완결적 정적 페이지다.</footer>
</div></div>
<script type="application/json" id="gil-data">{_json_for_script(json_payload)}</script>"""
    # v0.5 (loom/C049): meta refresh — JS 아닌 HTML 표준으로 N초마다 같은 URL 리로드 (자기완결 계약 유지)
    refresh_meta = (f"<meta http-equiv=\"refresh\" content=\"{refresh}\">\n" if refresh else "")
    return ("<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"{refresh_meta}"
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


def _bake_viewer(chains_root, output, title, only, refresh=None, hierarchy=False):
    """뷰어 하나를 굽는다 (cmd_web과 자동 갱신의 단일 소스)."""
    data = _build_web_data(chains_root, only)  # 깨진 체인이면 여기서 실패 — 파일을 쓰지 않는다
    if not data:
        raise ChainError(f"렌더할 체인이 없다: {chains_root}")
    page = render_web_page(data, title, datetime.date.today().isoformat(), only, refresh,
                           hierarchy=hierarchy, chains_root=chains_root)
    with open(output, "w", encoding="utf-8") as f:
        f.write(page)
    return data


def cmd_web(args):
    chains_root = args.chains_root
    if not os.path.isdir(chains_root):
        raise ChainError(f"체인 루트가 없다: {chains_root}")
    refresh = getattr(args, "refresh", None)
    # v2.19 (loom/C063): 위계가 기본. --flat만 평면으로 되돌린다 (--flat이 --hierarchy보다 우선).
    hierarchy = not getattr(args, "flat", False)
    if getattr(args, "watch", False):
        return _web_watch(args, chains_root, refresh, hierarchy)
    data = _bake_viewer(chains_root, args.output, args.title, args.chain, refresh, hierarchy)
    print(f"생성: {args.output} (체인 {len(data)}개)"
          + (" · 평면" if not hierarchy else "")
          + (f" · 자동 리로드 {refresh}초" if refresh else ""))
    return 0


def _web_watch(args, chains_root, refresh, hierarchy=False):
    """--watch: 원장 변경을 감시해 뷰어를 재생성한다 (loom/C049, 선택 기능).
    gil step을 거치지 않는 외부 변경(병합·pull)도 반영한다. Ctrl-C까지 지속.
    refresh 기본 5초 — meta refresh가 브라우저를 자동 리로드한다."""
    import time
    interval = getattr(args, "interval", None) or 5
    if not refresh:
        refresh = interval  # --watch는 자동 리로드를 함축한다
    def snapshot():
        out = {}
        for base, _, files in os.walk(chains_root):
            for n in files:
                if n == "cycle.yaml" or n.endswith(".tsv") or n == "round.yaml":
                    p = os.path.join(base, n)
                    try:
                        out[p] = os.path.getmtime(p)
                    except OSError:
                        pass
        return out
    data = _bake_viewer(chains_root, args.output, args.title, args.chain, refresh, hierarchy)
    print(f"감시 시작: {args.output} (체인 {len(data)}개, {interval}초 간격, 자동 리로드 {refresh}초). Ctrl-C로 종료.")
    last = snapshot()
    try:
        while True:
            time.sleep(interval)
            cur = snapshot()
            if cur != last:
                last = cur
                try:
                    d = _bake_viewer(chains_root, args.output, args.title, args.chain, refresh, hierarchy)
                    print(f"  ✎ 재생성: {args.output} (체인 {len(d)}개)")
                except ChainError as e:
                    print(f"경고: 재생성 실패 — {e}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\n감시 종료.")
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
    """뷰어가 스스로 보고한 굽기 조건. 없으면(구버전) 기본값 — 추측하지 않고 도구의 기본으로 돌아간다.
    refresh(loom/C049)도 함께 읽어 자동 재굽기가 자동 리로드를 보존하게 한다."""
    m = re.search(r'id="gil-data">(.*?)</script>', text, flags=re.S)
    if m:
        try:
            bake = json.loads(m.group(1)).get("bake") or {}
            # hierarchy(loomlight/C002)도 읽어 자동 재굽기가 위계 드릴다운을 잃지 않게 한다.
            return (bake.get("title") or _WEB_DEFAULT_TITLE, bake.get("chain"),
                    bake.get("refresh"), bool(bake.get("hierarchy")))
        except (ValueError, AttributeError):
            pass
    return _WEB_DEFAULT_TITLE, None, None, False


def _refresh_viewers(chains_root, label, no_web=False, push=False):
    """원장을 바꾼 명령이 커밋한 뒤 호출한다. 뷰어가 없으면 아무것도 하지 않는다.

    실패는 경고일 뿐 명령의 실패가 아니다 — 원장의 각인은 이미 끝났다 (꼬리가 개를 흔들지 않는다)."""
    if no_web:
        return
    repo = _repo_root(chains_root)
    # git 부재 시 repo가 None — 뷰어 검색을 임의의 cwd가 아니라 저장소 루트에 고정한다
    # (안 그러면 cwd의 무관한 HTML을 주워 "렌더할 체인이 없다" 헛경고를 낸다, loom/C052).
    root = repo or os.path.normpath(os.path.join(chains_root, "..", "..", ".."))
    try:
        viewers = _find_viewers(root)
        if not viewers:
            return  # 뷰어를 쓰지 않는 사용자에게 파일을 강요하지 않는다
        changed = []
        for path, text in viewers:
            title, only, refresh, hierarchy = _bake_meta(text)  # refresh·hierarchy 보존 (C049·C002)
            _bake_viewer(chains_root, path, title, only, refresh, hierarchy)
            with open(path, encoding="utf-8") as f:
                if f.read() != text:
                    changed.append(path)
        if not changed:
            return
        print(f"  ✎ 뷰어 갱신: {', '.join(os.path.basename(p) for p in changed)}")
        if not repo:
            return  # 깃이 없어도 창은 갱신된다. 커밋만 없을 뿐이다.
        rels = [_rel_to_repo(p, repo) for p in changed]
        _git(repo, "add", "--", *rels)
        # 뷰어는 사이클이 아니다 — 사이클 커밋에 섞으면 태그가 사이클 밖의 것을 봉인한다 (§4)
        _git(repo, "commit", "-m", f"gil: web 갱신 — {label}", "--", *rels)
        if push:
            _push(repo)
    except Exception as e:  # 원장이 우선이다: 창을 굽다 실패해도 각인은 되돌리지 않는다
        print(f"경고: 뷰어 갱신 실패 — {e} (원장은 각인됐다. gil web으로 직접 구울 것)", file=sys.stderr)


# ---------- 깃 바인딩 ----------

def _git_available():
    """git 실행 파일이 PATH에 있는가. 없으면 비개발자 환경 — 각인은 건너뛰고 파일만 남긴다."""
    return shutil.which("git") is not None


_GIT_MISSING_WARNED = False


def _warn_git_missing_once():
    """git 부재를 프로세스당 한 번만, 원인을 정확히 지목해 알린다 (하류 증상 오도 금지, loom/C052)."""
    global _GIT_MISSING_WARNED
    if _GIT_MISSING_WARNED:
        return
    _GIT_MISSING_WARNED = True
    print("ℹ git이 없어 각인(커밋)을 건너뛴다 — 사이클 파일은 저장됐다. "
          "git 설치(https://git-scm.com) 후 이력·되감기·뷰어 자동갱신이 켜진다.", file=sys.stderr)


def _git(repo, *cli, check=True):
    r = subprocess.run(["git", "-C", repo, *cli], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise ChainError(f"git {' '.join(cli)} 실패: {(r.stderr or r.stdout).strip()}")
    return r


def _has_push_remote(repo):
    """push할 원격이 있는가 (loom/C054). 없으면 --push는 우아하게 강등된다 — C052가
    git 부재를 다룬 방식의 원격판. (git이 없으면 애초에 커밋이 안 돼 이 경로에 닿지 않는다.)"""
    r = subprocess.run(["git", "-C", repo, "remote"], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


_NO_REMOTE_WARNED = False


def _warn_no_remote_once():
    """원격 부재를 프로세스당 한 번만, 원인을 정확히 지목해 알린다 (날것 fatal·침묵 금지, loom/C054)."""
    global _NO_REMOTE_WARNED
    if _NO_REMOTE_WARNED:
        return
    _NO_REMOTE_WARNED = True
    print("ℹ 원격이 없어 push를 건너뛴다 — 커밋은 로컬에 저장됐다. "
          "원격 연결(git remote add origin <URL>) 후 공유·뷰어 배포가 켜진다.", file=sys.stderr)


def _push(repo, *extra):
    """모든 push 경로의 단일 관문 (loom/C054). 원격 부재를 앞에서 감지해 크래시·날것 fatal·침묵
    대신 원인 한 줄 + rc0 유지로 강등한다. 원격이 있으면 기존 push 동작 그대로."""
    if not _has_push_remote(repo):
        _warn_no_remote_once()
        return False
    _git(repo, "push", *extra)
    return True


def _rel_to_repo(path, repo):
    """저장소 루트 기준 상대 경로. git rev-parse --show-toplevel(realpath화됨)과 사용자가 준
    --root(심볼릭 링크 그대로)가 서로 다른 심링크 공간에 있으면 os.path.relpath가 저장소를
    탈출하는 ../…를 만들어 git add가 거부한다(macOS /tmp·/var → /private/*). 양쪽을 realpath로
    정규화한 뒤 상대화해 이 불일치를 흡수한다 — Go relToRepo(EvalSymlinks)와 동치 (loom/C055)."""
    return os.path.relpath(os.path.realpath(path), os.path.realpath(repo))


def _repo_root(path):
    # git 부재(FileNotFoundError)는 예외라 returncode 가드가 못 잡는다 → 크래시 대신 None (loom/C052).
    # None은 호출부의 기존 우아한 "저장소 아님 → 각인 건너뜀" 경로로 수렴한다.
    if not _git_available():
        return None
    r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _is_primary_worktree(repo):
    """주 체크아웃(공유 main)인가 vs 링크드 워크트리인가 (loom/C062).
    링크드 워크트리는 --git-dir이 '.git/worktrees/<name>'이라 --git-common-dir과 다르다.
    주 체크아웃은 둘이 같다. harness가 만든 워크트리도 링크드라 여기서 걸러진다."""
    gd = _git(repo, "rev-parse", "--git-dir", check=False)
    gcd = _git(repo, "rev-parse", "--git-common-dir", check=False)
    if gd.returncode != 0 or gcd.returncode != 0:
        return False
    return (os.path.realpath(os.path.join(repo, gd.stdout.strip()))
            == os.path.realpath(os.path.join(repo, gcd.stdout.strip())))


def _guard_primary_owner(repo, author, chain_dir=None, slug=None):
    """주 체크아웃 소유 guard (loom/C062 — 상현님 발의: 사고를 도구가 막는다).
    존재가 자기 워크트리 밖 공유 main으로 cd해 커밋하는 C050 사고를 커밋 이전에 구조적으로 거부한다.
    - gil.owner 미설정이면 미적용 (opt-in — 기존 저장소·CI 무파손).
    - 링크드 워크트리(존재의 정당한 작업공간)는 미적용 — 오탐 0.
    - 예약 예외 (loom/C078): open의 slug이 그 author 앞으로 예약돼 있으면(reservations.tsv) 허용한다.
      예약은 소유자의 명시적 승인("이 존재가 이 사이클을 열 것")이라 사고가 아니라 계획된 협업이다.
      예약 없는 남 author open은 여전히 거부 — C050 방지는 유지된다. correct는 chain_dir/slug 없이
      호출되어 예약 예외가 미적용(정정은 owner만).
    규제 대상은 오직 주 체크아웃 = 모든 존재가 공유하는 유일한 공간이자 세 사고가 전부 난 곳."""
    if not repo or not _is_primary_worktree(repo):
        return
    r = _git(repo, "config", "gil.owner", check=False)
    owner = r.stdout.strip() if r.returncode == 0 else ""
    if owner and author and author != owner:
        # 예약 예외: 이 open이 그 author 앞으로 예약된 slug이면 허용 (C078).
        if chain_dir and slug:
            for res in _load_reservations(chain_dir):
                if res["for"] == author and res["slug"] == slug:
                    return
        raise ChainError(
            f"이 체크아웃은 '{owner}'의 주 작업공간이다 — author '{author}'로 여기서 커밋할 수 없다.\n"
            f"      네 워크트리에서 실행하라:  gil worktree add <chain> <slug> --author {author}\n"
            f"      또는 소유자가 예약하라:  gil reserve <chain> {slug or '<slug>'} --for {author}\n"
            f"      (병렬 사이클 모드 — 공유 main 오염 방지, C050·C062·C078)")


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
        rel = _rel_to_repo(os.path.join(chains_root, ochain, oid), repo)
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
    cycle_rel = _rel_to_repo(os.path.join(chains_root, chain, cdir), repo)
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
    _guard_primary_owner(_repo_root(chains_root), args.author)  # C062 — 주 체크아웃 오염 방지
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
    ev_rel = _rel_to_repo(os.path.join(cycle_dir, ev_path), repo)
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
    rel_yaml = _rel_to_repo(yaml_path, repo)
    rel_corr = _rel_to_repo(corr_path, repo)
    _git(repo, "add", "--", rel_yaml, rel_corr)
    _git(repo, "commit", "-m",
         f"[correct] gil: {args.ref} — {'; '.join(changed)}", "--", rel_yaml, rel_corr)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    old_tag_commit = _git(repo, "rev-list", "-n1", tag).stdout.strip()
    # 태그 이동 규약 (§4): 이전 커밋 해시와 사유를 태그 메시지에 남긴다
    _git(repo, "tag", "-f", "-a", tag, "-m",
         f"[correct] {'; '.join(changed)} — 증거 {args.evidence} (이전 커밋 {old_tag_commit[:8]}에서 이동)", head)
    if args.push:
        if _push(repo):  # 원격 없으면 커밋·이동한 태그는 로컬에 있고 안내 한 줄로 강등 (loom/C054)
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


# ---------- show: 지식그래프 노드 조회 (loom/C059 — #4 LLM 위키) ----------
# 사이클 DAG는 이미 지식그래프다(parent·lineage 엣지는 각 cycle.yaml에 데이터로 산다). 없던 것은
# ① 노드 단위 조회 표면과 ② 엣지 반전 = 백링크. show는 새 파서를 만들지 않고 이 둘만 더한다.
# web(사람용 렌더, 전체 그래프)의 machine-facing 짝: 한 노드 + 양방향 이웃을, 질의자가 파일을
# 하나도 안 읽고 얻는다(표적 탐색). 읽기 전용 — 커밋·상태 변경 0 (§7.2 안전한 탐침 정신).

def _node_exists(chains_root, ref):
    """전역 ref <chain>/<id>가 실재하는 사이클을 가리키는가."""
    if "/" not in ref:
        return False
    c, i = ref.split("/", 1)
    return os.path.isfile(os.path.join(chains_root, c, i, "cycle.yaml"))


def _collect_backlinks(chains_root, target_chain, target_cid):
    """이 노드를 인용하는 사이클들(cited-by). 두 종류:
    - parent 백링크: 같은 체인에서 이 노드를 parent로 나열한 사이클 (체인 내).
    - lineage 백링크: 아무 체인에서든 이 노드를 lineage(전역 ref)로 나열한 사이클 (cross-chain).
    엣지 집합의 반전 — build_graph가 그리는 정방향의 역방향이다."""
    target_ref = f"{target_chain}/{target_cid}"
    parent_bl, lineage_bl = [], []
    for name in sorted(e for e in os.listdir(chains_root)
                       if os.path.isdir(os.path.join(chains_root, e))):
        for rec in load_chain_records(os.path.join(chains_root, name)):
            cid = rec.get("id") or rec["_dir"]
            ref = f"{name}/{cid}"
            if name == target_chain and target_cid in rec["parents"]:
                parent_bl.append(ref)
            if target_ref in rec["lineage_list"]:
                lineage_bl.append(ref)
    return sorted(set(parent_bl)), sorted(set(lineage_bl))


def cmd_show(args):
    """지식그래프 노드 조회: 신원 + 정방향 엣지(parent·lineage) + 백링크(cited-by)."""
    chains_root = args.root
    if "/" not in args.ref:
        raise ChainError(f"ref는 <chain>/<id> 형식이어야 한다: {args.ref}")
    chain, cid = args.ref.split("/", 1)
    yaml_path = os.path.join(chains_root, chain, cid, "cycle.yaml")
    if not os.path.isfile(yaml_path):
        raise ChainError(f"사이클이 없다: {args.ref}")  # 지어내지 않는다 (§3.2 P2, C040)
    node = parse_cycle_yaml(yaml_path)
    parents = _as_list(node.get("parent"))
    lineage = _as_list(node.get("lineage"))
    # 정방향 엣지 — parent는 체인 내 로컬 id(전역 ref로 표기), lineage는 이미 전역 ref
    fwd_parents = [{"ref": f"{chain}/{p}", "exists": _node_exists(chains_root, f"{chain}/{p}")}
                   for p in parents]
    fwd_lineage = [{"ref": ln, "exists": _node_exists(chains_root, ln)} for ln in lineage]
    # 백링크 — 엣지 반전 (cited-by)
    bl_parents, bl_lineage = _collect_backlinks(chains_root, chain, cid)
    report_path = os.path.join(chains_root, chain, cid, "5-report.md")
    report = report_path if os.path.isfile(report_path) else None

    if args.json:
        payload = {
            "ref": f"{chain}/{cid}",
            "node": node,
            "forward": {"parents": fwd_parents, "lineage": fwd_lineage},
            "backlinks": {"parents": bl_parents, "lineage": bl_lineage},
            "report": report,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    # 사람용 렌더 (계약 아님 — §3.1, C021)
    print(f"● {chain}/{cid}  [{node.get('status') or '?'}]"
          + (f"  결말: {node.get('verdict')}" if node.get("verdict") else ""))
    if node.get("title"):
        print(f"  {node.get('title')}")
    line = f"  저자: {node.get('author') or '?'}"
    if node.get("opened"):
        line += f"   열림: {node.get('opened')}"
    if node.get("closed"):
        line += f"   닫힘: {node.get('closed')}"
    print(line)
    print("  ── 정방향 (이 노드가 인용하는) ──")
    for e in fwd_parents:
        print(f"    parent  → {e['ref']}" + ("" if e["exists"] else "  (끊어진 참조)"))
    for e in fwd_lineage:
        print(f"    lineage ⇠ {e['ref']}" + ("" if e["exists"] else "  (끊어진 참조)"))
    if not fwd_parents and not fwd_lineage:
        print("    (없음 — 루트)")
    print("  ── 백링크 (이 노드를 인용하는) ──")
    for r in bl_parents:
        print(f"    ← parent  {r}")
    for r in bl_lineage:
        print(f"    ← lineage {r}")
    if not bl_parents and not bl_lineage:
        print("    (없음 — 아직 인용되지 않음)")
    if report:
        print(f"  보고서: {report}")
    return 0


def cmd_threads(args):
    """열린 실 훑기 (loom/C070, #4 LLM 위키): 그래프 전역에서 loose end를 반환한다 —
    (1) 미소비 예약(= 진행 중 병렬 사이클, main에 커밋된 reservations.tsv), (2) status=open 사이클.
    show가 단일 노드의 이웃을 준다면 threads는 그 그래프 전역판이다. handoff(사람용 서사)와 달리
    기계 계약면(--json)을 가지며 예약(병렬 진행)을 인식한다. 지어내지 않는다: 이미 사이클로
    존재하는(소비된) 예약은 제외하고, 실재하는 것만 보고한다 (§3.2 P2, C040)."""
    chains_root = args.root
    chains = _scan_chains(chains_root, args.chain)
    reserved, open_cycles = [], []
    for chain in sorted(chains):
        records = chains[chain]
        have_ids = {r.get("id") or r.get("_dir") for r in records}
        # 열린 사이클 — status=open (전역, 전 체인)
        for r in records:
            if r.get("status") == "open" and r.get("id"):
                open_cycles.append({
                    "chain": chain, "id": r["id"],
                    "author": r.get("author") or "?",
                    "step": r.get("step"), "opened": r.get("opened"),
                })
        # 미소비 예약 — 그 트리에 아직 사이클로 존재하지 않는 예약만 (이중계상 방지, C040)
        chain_dir = os.path.join(chains_root, chain)
        for res in _load_reservations(chain_dir):
            prefix = f"C{res['num']:03d}-"
            if any(str(cid).startswith(prefix) for cid in have_ids):
                continue  # 이미 open됨 = 소비된 예약, 진행 중이 아니다
            reserved.append({
                "chain": chain, "num": res["num"], "ref": f"C{res['num']:03d}",
                "for": res["for"], "slug": res["slug"], "date": res["date"],
            })
    open_cycles.sort(key=lambda o: (o["chain"], o["id"]))
    reserved.sort(key=lambda r: (r["chain"], r["num"]))

    if args.json:
        payload = {
            "reserved": reserved, "open": open_cycles,
            "reserved_count": len(reserved), "open_count": len(open_cycles),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    # 사람용 렌더 (계약 아님 — §3.1, C021)
    print("=== gil threads — 열린 실 (loose ends) ===")
    print(f"⟳ 진행 중 병렬 사이클 (예약, 아직 안 거둬짐): {len(reserved)}")
    for r in reserved:
        print(f"    {r['chain']}/{r['ref']}  → {r['for']}  ({r['slug']})")
    if not reserved:
        print("    (없음 — 병렬로 물린 사이클 없음)")
    print(f"◐ 열린 사이클 (진행 중, 이 체크아웃): {len(open_cycles)}")
    for o in open_cycles:
        step = f"  {o['step']}/5" if (isinstance(o["step"], str) and o["step"].isdigit()) else ""
        print(f"    {o['chain']}/{o['id']}  · {o['author']}{step}")
    if not open_cycles:
        print("    (없음 — 이 체크아웃엔 열린 사이클 없음)")
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
            cycle_rel = _rel_to_repo(
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


# close 봉인 스코프 게이트 (loom/C081). 사이클 표준 산출물: 5스텝 문서 + cycle.yaml +
# deviations/corrections.yaml. 3-verification/ 안은 자유 산출물이 정상이라 게이트 대상이 아니다.
_CLOSE_STANDARD_FILES = {"cycle.yaml", "1-hypothesis.md", "2-design.md",
                         "4-analysis.md", "5-report.md",
                         "deviations.yaml", "corrections.yaml"}


def _close_unexpected_files(repo, cycle_dir, cycle_rel):
    """close가 새로 봉인할(untracked) 파일 중 '3-verification/ 밖 + 표준 산출물 밖'인 것을 반환한다.
    이것들은 흔한 오배치(사이클 루트나 잘못된 위치의 신규 파일)라 봉인 전 게이트한다. 3-verification/
    아래는 probe·데이터·fixtures 등 자유 산출물이 정상이므로 제외한다."""
    r = _git(repo, "status", "--porcelain", "--", cycle_rel, check=False)
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        if not line.startswith("??"):  # untracked(신규)만 — 이미 tracked는 재봉인이라 새 위험 아님
            continue
        path = line[3:].strip().strip('"')
        rel_in_cycle = os.path.relpath(path, cycle_rel)
        # 3-verification/ 안은 존중(자유 산출물). 그 밖에서 표준 문서가 아닌 것만 게이트.
        top = rel_in_cycle.split("/", 1)[0]
        if top == "3-verification":
            continue
        base = os.path.basename(rel_in_cycle)
        if base not in _CLOSE_STANDARD_FILES:
            out.append(rel_in_cycle)
    return sorted(out)


def cmd_close(args):
    chains_root = args.root
    cycle_dir = os.path.join(chains_root, args.chain, args.cycle_id)
    yaml_path = os.path.join(cycle_dir, "cycle.yaml")
    if not os.path.isfile(yaml_path):
        raise ChainError(f"사이클이 없다: {os.path.join(args.chain, args.cycle_id)}")
    data = parse_cycle_yaml(yaml_path)
    if data.get("status") == "closed":
        raise ChainError(f"{args.chain}/{args.cycle_id}: 이미 닫힌 사이클이다 — 닫힌 사이클은 수정하지 않는다")

    # deviations 카운트 관문 (loom/C057): deviations.yaml이 있으면 레코드 수 = deviations 필드여야 봉인한다.
    # C053 슬립(파일은 썼는데 cycle.yaml 카운트를 손으로 못 고침) 차단. auto-count가 아니라 거부 —
    # 카운트는 저자의 의도이므로 도구가 임의로 덮어쓰지 않고 의식적 조정을 강제한다 (저장소 무변화).
    devfile = os.path.join(cycle_dir, "deviations.yaml")
    if os.path.isfile(devfile):
        n_rec = _count_deviations(devfile)
        dev_field = data.get("deviations")
        try:
            n_field = int(dev_field) if dev_field is not None else 0
        except (TypeError, ValueError):
            n_field = None  # 비정수 필드는 이후 fsck의 R10이 잡는다
        if n_rec is not None and n_field is not None and n_rec != n_field:
            raise ChainError(
                f"{args.chain}/{args.cycle_id}: deviations.yaml에 {n_rec}건인데 "
                f"cycle.yaml deviations: {n_field} — 봉인 전에 카운트를 조정하라 "
                f"(손으로 세는 것을 잊지 말라, C053)")

    # 기본 커밋 (v1.7, C033): 깃 저장소면 자동 커밋+각인. --no-commit으로만 끈다.
    # (--git은 하위호환. 사전 검증은 저장소를 건드리기 전에 전부 확인한다.)
    repo = tag = None
    do_git = _repo_root(chains_root) if not getattr(args, "no_commit", False) else None
    if do_git:
        repo = do_git
        tag = _tag_name(args.chain, args.cycle_id)
        if _tag_exists(repo, tag):
            raise ChainError(f"태그 '{tag}'가 이미 존재한다")
    elif not getattr(args, "no_commit", False) and not _git_available():
        _warn_git_missing_once()  # git 부재: 보고서 저장은 되고 각인·태그만 건너뜀 (loom/C052)
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
        cycle_rel = _rel_to_repo(cycle_dir, repo)
        title = data.get("title") or ""
        # 봉인 스코프 게이트 (loom/C081, 이슈 #19): close는 불변 태그를 각인한다 — 오배치 파일이
        # 무심코 봉인되면 나중에 지울 때 verify가 변조로 보고 태그를 못 고쳐 중복 봉인이 영구화된다.
        # 봉인될 신규(untracked) 파일 중 "3-verification/ 밖 + 표준 산출물 밖"인 것은 흔한 오배치라
        # 게이트한다. 3-verification/ 안은 자유 산출물(probe·데이터·fixtures)이 정상이라 요약만.
        extra = _close_unexpected_files(repo, cycle_dir, cycle_rel)
        if extra:
            listing = "\n".join(f"        {p}" for p in extra)
            if not getattr(args, "allow_extra", False):
                with open(yaml_path, "w", encoding="utf-8") as f:
                    f.write(original)  # 게이트 거부 — yaml 원복(저장소 무변화)
                raise ChainError(
                    f"{args.chain}/{args.cycle_id}: 표준 산출물 밖의 신규 파일이 봉인 대상이다 "
                    f"(불변 태그에 들어가면 되돌리기 어렵다):\n{listing}\n"
                    f"      오배치면 정리하고, 의도한 것이면 --allow-extra 로 승인하라 (이슈 #19).")
            print(f"경고: 표준 밖 신규 파일을 봉인한다 (--allow-extra):\n{listing}")
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
            _push(repo, "--follow-tags")
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
            # 스텝 경계 스코프 (loom/C080, 이슈 #20): 사이클 디렉토리 전체가 아니라 cycle.yaml(전이 기록)
            # + 스텝 ≤N의 파일만 커밋한다. 뒷 스텝(>N) 파일을 미리 만들어 둬도 이 커밋엔 안 담겨,
            # 커밋이 스텝 단위를 반영한다. 존재하는 것만 넣어 정상 흐름(스텝마다 작성 후 전이)은 불변.
            wanted = [os.path.join(cycle_dir, "cycle.yaml")]
            for _label, fname in _STEP_FILES[:n]:
                wanted.append(os.path.join(cycle_dir, fname))
            rels = [_rel_to_repo(p, repo) for p in wanted if os.path.exists(p)]
            _git(repo, "add", "-A", "--", *rels)
            _git(repo, "commit", "-m", f"gil: step {args.chain}/{args.cycle_id} → {n}/5 {_STEP_NAMES[n]}", "--", *rels)
            committed = True
            if args.push:
                _push(repo)
        elif not _git_available():
            _warn_git_missing_once()  # git 부재: 파일은 저장됨, 각인만 건너뜀 (loom/C052)
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
            rel = _rel_to_repo(cycle_dir, repo)
            _git(repo, "add", "-A", "--", rel)
            _git(repo, "commit", "-m",
                 f"gil: round open {args.chain}/{args.cycle_id} R{newk} — 사전등록\n\n{title}", "--", rel)
            if args.push:
                _push(repo)
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
            rel = _rel_to_repo(cycle_dir, repo)
            _git(repo, "add", "-A", "--", rel)
            _git(repo, "commit", "-m",
                 f"gil: round close {args.chain}/{args.cycle_id} R{k} → {args.verdict}", "--", rel)
            if args.push:
                _push(repo)
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
    rel = _rel_to_repo(worktree_path, repo).replace(os.sep, "/")
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
    # ---- drift 게이트 (loom/C072): 봉인 전, 기존 배포 계보의 두 기록 일치를 요구한다 ----
    # cmd_release는 태그 v<semver>와 CHANGELOG를 한 커밋에 각인하므로 정상 경로의 drift는 0이다.
    # 한쪽 기록에만 있는 릴리스(drift)는 정상 경로 밖에서 배포 기록을 손댔다는 신호 — 어긋난 계보 위에
    # 새 봉인을 얹으면 어긋남이 봉인된다. 하드 위반: 무변화로 거부·처방한다(인접 verify 게이트와 같은 등급).
    # drift 정의는 cmd_releases(loom/C061)와 같은 헬퍼를 재사용해 조회와 게이트가 같은 진실을 본다.
    changelog = os.path.normpath(os.path.join(pkg, "..", "CHANGELOG.md"))
    drifted = _release_drift(repo, changelog)
    if drifted:
        raise ChainError(
            f"배포 계보 drift {len(drifted)}건 — 태그와 CHANGELOG가 어긋난 릴리스가 있다"
            f"({', '.join('v' + v for v in drifted)}). 어긋난 계보 위엔 새 릴리스를 봉인할 수 없다: "
            f"'gil releases'로 확인하고 두 기록을 일치시킨 뒤 다시 릴리스할 것")
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
            rel = _rel_to_repo(pkg_path, repo).replace(os.sep, "/")
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
    # changelog 경로는 drift 게이트에서 이미 계산됐다(사전 검증 상단) — 재사용.
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

    deploy_rel = _rel_to_repo(os.path.normpath(os.path.join(pkg, "..")), repo)
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


# ---------- releases (배포 계보 조회 — loom/C061 #3 배포 버저닝) ----------
# 배포는 이미 두 몸으로 기록된다: 깃 태그 v<semver>(cmd_release가 각인 — 깃의 진실)와
# CHANGELOG의 '## [X.Y.Z] — 날짜' 엔트리(사람의 원장). 없던 것은 그 둘을 대조해 조회하는 표면이다.
# gil log(사이클 계보)의 배포판 — 읽기 전용, 저장소 무변화(§7.2 안전한 탐침 정신).
# git tag -l을 넘어서는 값은 대조에 있다: 한 기록에만 있는 릴리스(drift)를 드러낸다.
# 출처를 지어내지 않는다(§3.2) — 태그와 CHANGELOG가 증언하는 것만 보고한다.

_CHANGELOG_HEADER_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]\s+—\s+(\S+)")


def _parse_changelog_releases(changelog_path):
    """CHANGELOG의 '## [X.Y.Z] — 날짜' 엔트리를 {version: {date, note, tools}} 로.
    '## [Unreleased]'는 SemVer 헤더가 아니므로 자동 제외된다."""
    out = {}
    if not os.path.isfile(changelog_path):
        return out
    lines = open(changelog_path, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        m = _CHANGELOG_HEADER_RE.match(line)
        if not m:
            continue
        version, date = m.group(1), m.group(2)
        note, tools = "", ""
        for body in lines[i + 1:]:               # 다음 헤더 전까지의 불릿을 노트/도구변경으로
            if body.startswith("## "):
                break
            s = body.strip()
            if s.startswith("- 도구 변경:") or s.startswith("- 도구 동기화:"):
                tools = s.split(":", 1)[1].strip()
            elif s.startswith("- ") and not note:
                note = s[2:].strip()
        out[version] = {"date": date, "note": note, "tools": tools}
    return out


def _git_release_tags(repo):
    """릴리스 태그 v<semver>를 {version: {date, subject}} 로. git 부재/비저장소면 None.
    cycle/… 태그는 v* 글롭 + SemVer 필터로 자동 배제된다."""
    if not repo:
        return None
    r = _git(repo, "for-each-ref", "--format=%(refname:short)\t%(creatordate:short)\t%(subject)",
             "refs/tags/v*", check=False)
    if r.returncode != 0:
        return {}
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        name = parts[0] if parts else ""
        if not (name.startswith("v") and _SEMVER_RE.match(name[1:])):
            continue
        out[name[1:]] = {"date": parts[1] if len(parts) > 1 else "",
                         "subject": parts[2] if len(parts) > 2 else ""}
    return out


def _release_drift(repo, changelog_path):
    """배포 계보의 drift = 태그 v<semver>와 CHANGELOG 중 정확히 한쪽에만 있는 릴리스.
    cmd_releases(loom/C061)와 같은 두 헬퍼를 재사용해 조회와 게이트가 같은 drift를 본다.
    태그가 하나도 없으면(None=비저장소/git부재 또는 {}=태그 없음) 대조 기준이 없어 drift 없음으로 본다
    — 첫 릴리스(태그 0)를 게이트가 막지 않게, 그리고 CHANGELOG-only 원장을 손댐으로 오판하지 않게.
    반환: 최신 우선 정렬된 drift 버전 리스트(빈 리스트면 게이트 통과)."""
    tags = _git_release_tags(repo)
    if not tags:                                 # None 또는 {} — 대조할 깃의 진실이 없다
        return []
    cl = _parse_changelog_releases(changelog_path)
    drifted = [v for v in (set(tags) | set(cl)) if (v in tags) != (v in cl)]
    return sorted(drifted, key=lambda v: tuple(int(x) for x in v.split(".")), reverse=True)


def cmd_releases(args):
    changelog = os.path.normpath(os.path.join(args.package, "..", "CHANGELOG.md"))
    cl = _parse_changelog_releases(changelog)
    # 저장소는 릴리스가 사는 곳(패키지)을 기준으로 유추한다 — 사이클 루트(--root)는 없을 수 있으나
    # 패키지는 CHANGELOG를 담으므로 존재한다. 그마저 없으면 cwd로 강등한다.
    anchor = args.package if os.path.isdir(args.package) else "."
    tags = _git_release_tags(_repo_root(anchor))
    git_absent = tags is None
    if git_absent:                               # git 부재 또는 비저장소 — 태그를 알 수 없으니 CHANGELOG만 (읽기 전용, 크래시 없이)
        print("ℹ 깃 저장소가 아니거나 git이 없어 태그 대조를 생략한다 — CHANGELOG만 보고한다.", file=sys.stderr)
        tags = {}

    ordered = sorted(set(cl) | set(tags),
                     key=lambda v: tuple(int(x) for x in v.split(".")), reverse=True)

    hooks, drift = [], 0
    print(f"배포 계보 — {len(ordered)}개 릴리스"
          + (" (git 부재: 태그 대조 생략)" if git_absent else "  [T=태그 C=CHANGELOG]"))
    for v in ordered:
        in_tag, in_cl = v in tags, v in cl
        date = cl[v]["date"] if in_cl else tags[v]["date"]
        note = cl[v]["note"] if in_cl else (tags[v]["subject"] if in_tag else "")
        tools = cl[v]["tools"] if in_cl else ""
        marks = ("T" if in_tag else "·") + ("C" if in_cl else "·")
        drifted = not git_absent and not (in_tag and in_cl)
        if drifted:
            drift += 1
        line = f"  v{v:<9} {date or '?':<10} [{marks}]{' ⚠drift' if drifted else ''}"
        if note:
            line += f"  {note}"
        if tools and not tools.startswith("없음"):
            line += f"  · 도구: {tools}"
        print(line)
        hooks.append(f"gil:release {v} {date or '-'} tags={int(in_tag)} changelog={int(in_cl)}")
    for h in hooks:                              # 사람 렌더 뒤에 기계 훅 블록 (§7.2 정신)
        print(h)
    print(f"gil:releases {len(ordered)} drift={drift}")
    if drift:
        print(f"⚠ drift {drift}건: 태그와 CHANGELOG가 어긋난 릴리스가 있다 "
              f"(한쪽 기록에만 존재). 봉인의 두 기록은 일치해야 한다.", file=sys.stderr)
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

    p_wt = sub.add_parser("worktree", help="병렬 사이클 모드 — add(열기)·land(머지백) (v2.15·v2.17, #1)")
    p_wt.add_argument("wt_action", choices=["add", "land"],
                      help="add: 격리 워크트리에서 새 사이클을 연다 / land: 브랜치를 main에 --no-ff 병합 후 워크트리 정리")
    p_wt.add_argument("chain")
    p_wt.add_argument("slug", help="id의 슬러그 부분 (소문자 케밥)")
    p_wt.add_argument("--author", help="이 워크트리에서 일할/일한 존재 — 필수 (§3.2 P1)")
    p_wt.add_argument("--parent", action="append", default=[], help="부모 사이클의 로컬 id (병합이면 여러 번; add 전용)")
    p_wt.add_argument("--lineage", action="append", default=[], help="교훈의 연원 <chain>/<id> (여러 번; add 전용)")
    p_wt.add_argument("--new-chain", action="store_true", help="체인이 없으면 생성 (add 전용)")
    p_wt.add_argument("--new-root", action="store_true", help="비어있지 않은 체인에 새 루트 (add 전용)")
    p_wt.add_argument("--push", action="store_true", help="land: 병합 성공 후 main push")
    p_wt.add_argument("--date", default=today, help="opened 일자 (기본: 오늘; add 전용)")
    p_wt.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_wt.set_defaults(func=cmd_worktree)

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
    p_close.add_argument("--allow-extra", dest="allow_extra", action="store_true",
                         help="3-verification/ 밖의 신규 비표준 파일 봉인을 승인 (이슈 #19, loom/C081)")
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

    p_rels = sub.add_parser("releases", help="배포 계보 조회: 깃 태그(v*)와 CHANGELOG를 대조해 릴리스 이력을 보고 (읽기 전용)")
    p_rels.add_argument("--package", default="rooms/deployment/ariadne-spec", help="릴리스 패키지 경로 (CHANGELOG는 <package>/../CHANGELOG.md, 저장소도 여기서 유추)")
    p_rels.set_defaults(func=cmd_releases)

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

    p_show = sub.add_parser("show", help="지식그래프 노드 조회: 신원+정방향 엣지+백링크 (loom/C059, #4 LLM 위키)")
    p_show.add_argument("ref", help="<chain>/<id> (예: loom/C029-time-machine)")
    p_show.add_argument("--json", action="store_true", help="기계 계약면 (지식그래프 JSON)")
    p_show.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_show.set_defaults(func=cmd_show)

    p_threads = sub.add_parser("threads", help="열린 실 훑기: 진행 중 병렬 사이클(예약)+열린 사이클을 전역 조회 (loom/C070, #4)")
    p_threads.add_argument("--chain", help="특정 체인만")
    p_threads.add_argument("--json", action="store_true", help="기계 계약면 (loose-end JSON)")
    p_threads.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_threads.set_defaults(func=cmd_threads)

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
    p_web.add_argument("--refresh", type=int, help="meta refresh 주기(초) — 새로고침 없이 자동 리로드 (v2.8, C049)")
    p_web.add_argument("--flat", action="store_true",
                       help="평면(SVG 그래프) 뷰어 — 위계가 기본이 된 뒤의 옵트아웃 (v2.19, loom/C063)")
    # v2.19 (loom/C063): 위계가 기본. --hierarchy는 하위호환 no-op 별칭 — 기존 스크립트가 깨지지 않게 조용히 수용한다.
    p_web.add_argument("--hierarchy", action="store_true", help=argparse.SUPPRESS)
    p_web.add_argument("--watch", action="store_true", help="원장 변경을 감시해 뷰어 재생성 (--refresh 함축, C049)")
    p_web.add_argument("--interval", type=int, help="--watch 감시 간격(초, 기본 5)")
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
