#!/usr/bin/env python3
"""C024 renumber_map — 재번호 매핑을 두 진실원에서 수집 (순수 함수).

재번호 사이클은 cycle.yaml id가 새 번호인데 git 커밋 subject는 옛 번호를 담는다.
도출기가 새 id로 커밋을 못 찾는 원인. 매핑 {chain/new_id: old_id}를 만든다.

진실원 두 곳 (C020 "안정적 구조를 신뢰"):
  1. git 커밋 `gil: 재번호 C<old>→C<new>` / `gil: renumber ...C<old>... → C<new>` — 안정적 1순위.
  2. 5-report.md "번호 재발급 주석" `C<old>→C<new>` — Clew 병합 재번호 보완.
     ⭐ 오염 방지: 도출실패 사이클 디렉토리만 파싱.
"""
import os, re, sys, subprocess, glob

# git subject: "재번호 C082→C083" 또는 "renumber loom/C105-... → C106"
RE_GIT_KO = re.compile(r"재번호\s+C(\d+)\s*(?:→|->)\s*C(\d+)")
RE_GIT_EN = re.compile(r"renumber\s+(\S+?)C(\d+)\S*\s*(?:→|->)\s*C(\d+)")
# 5-report: "C003→C004" / "C003 → C004"
RE_REPORT = re.compile(r"C(\d+)\s*(?:→|->)\s*C(\d+)")


def _new_id_full(chain, num, repo):
    """chain + 번호로 실제 사이클 디렉토리의 전체 id를 찾음 (slug 포함)."""
    for p in glob.glob(os.path.join(repo, "rooms/experiment/chains", chain, "C%03d-*" % num)):
        return os.path.basename(p)
    return "C%03d" % num


def from_git(repo):
    """git 재번호 커밋에서 매핑. chain을 못 정하면 (None, new_num): old_num로 둔다
    (호출부가 도출실패 사이클의 new_num으로 역매칭). 반환: [(chain_or_None, new, old)]."""
    out = subprocess.run(
        ["git", "-C", repo, "log", "--all", "--format=%s"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    entries = []
    for line in out.splitlines():
        cm = re.search(r"\b(loom|v3-build|genesis|tapestry|loomlight)\b", line)
        chain = cm.group(1) if cm else None
        m = RE_GIT_KO.search(line)
        if m:
            entries.append((chain, int(m.group(2)), int(m.group(1))))  # (chain, new, old)
            continue
        m = RE_GIT_EN.search(line)
        if m:
            cm2 = re.search(r"\b(loom|v3-build|genesis|tapestry|loomlight)\b", m.group(1))
            entries.append((cm2.group(1) if cm2 else chain, int(m.group(3)), int(m.group(2))))
    return entries


def from_reports(repo, only_dirs):
    """5-report.md의 재번호 주석에서 {chain/new_id: old_num}. only_dirs만(오염 방지)."""
    mapping = {}
    for d in only_dirs:
        rep = os.path.join(d, "5-report.md")
        if not os.path.exists(rep):
            continue
        base = os.path.basename(d)               # C004-v3-viewer-step-tree
        chain = os.path.basename(os.path.dirname(d))
        m_new = re.match(r"C(\d+)", base)
        if not m_new:
            continue
        new_num = int(m_new.group(1))
        text = open(rep, encoding="utf-8").read()
        # "번호 재발급 주석" 블록에서 C<old>→C<new_num> 만 취함 (본문 인용 노이즈 배제)
        for mm in RE_REPORT.finditer(text):
            old, new = int(mm.group(1)), int(mm.group(2))
            if new == new_num:                    # 이 사이클로 재번호된 것만
                mapping["%s/%s" % (chain, base)] = old
                break
    return mapping


def build_map(repo, failed_dirs):
    """통합 매핑 {chain/new_id: old_num}. git + 5-report 합침."""
    result = {}
    git_entries = from_git(repo)   # [(chain_or_None, new, old)]
    for d in failed_dirs:
        base = os.path.basename(d)
        chain = os.path.basename(os.path.dirname(d))
        m = re.match(r"C(\d+)", base)
        if not m:
            continue
        new_num = int(m.group(1))
        key = "%s/%s" % (chain, base)
        # 1순위: git. chain 일치 우선, chain None이면 new_num 역매칭 허용.
        for gchain, gnew, gold in git_entries:
            if gnew != new_num:
                continue
            if gchain == chain or gchain is None:
                result[key] = gold
                break
    # 2순위: 5-report 보완 (git에 없는 것만)
    rep_map = from_reports(repo, failed_dirs)
    for k, v in rep_map.items():
        result.setdefault(k, v)
    return result


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    # 도출실패 디렉토리를 인자로 받거나 전량 스캔
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import full_ledger_migrate as FLM
    cycles = FLM.discover_cycles(repo)
    failed_dirs = []
    for c in cycles:
        if not FLM.cycle_step_commits(repo, c.get("chain", ""), c.get("id", "")):
            failed_dirs.append(c["dir"])
    m = build_map(repo, failed_dirs)
    print("재번호 매핑 %d건:" % len(m))
    for k, v in sorted(m.items()):
        print("  %s ← 옛 C%03d" % (k, v))
