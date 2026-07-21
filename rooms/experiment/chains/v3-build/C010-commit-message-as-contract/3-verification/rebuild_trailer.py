#!/usr/bin/env python3
"""gilv3 rebuild (trailer) — git trailer 계약으로 스텝 트리를 복원한다 (C010).

C009 rebuild.py의 후계: C009는 subject의 자연어 서술을 정규식으로 파싱했다
(서술 형식에 결합). C010은 **git trailer**(Step-Id·Kind·Parent·Outcome·
Backtrack-To)를 읽는다 — subject 자연어를 한 글자도 안 본다. 서술 문구가
어떻게 바뀌든 trailer만 있으면 복원이 불변이다 (계약면이 구조로 승격).

오직 `git log --format=%(trailers…)`만 — steps.yaml·show·diff 안 씀.
"""
import sys, os, subprocess

FIELDS = ["id", "kind", "parent", "outcome", "backtrack", "body"]
KEYS = ["Step-Id", "Kind", "Parent", "Outcome", "Backtrack-To"]

# 커밋당 trailer를 한 레코드로 뽑는 포맷 — 커밋 경계는 유니크 구분자로.
SEP = "\x1e"        # record separator (커밋 사이)
FSEP = "\x1f"       # field separator (키 사이)
# git pretty 포맷은 %(trailers…) 리터럴 — 파이썬 % 포맷과 충돌하므로 문자열 연결로.
_FMT = SEP + FSEP.join(
    "%(trailers:key=" + k + ",valueonly)" for k in KEYS)


def rebuild(repo):
    """git trailer만으로 노드 리스트 복원 (시간순). 자연어 subject 미사용."""
    out = subprocess.run(
        ["git", "-C", repo, "log", "--reverse", "--format=" + _FMT],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    nodes = []
    for rec in out.split(SEP):
        rec = rec.strip("\n")
        if not rec:
            continue
        vals = rec.split(FSEP)
        # 각 valueonly는 trailer 값 or 빈 문자열(그 키 없음). 개행 잔여 제거.
        vals = [v.strip() for v in vals]
        d = dict(zip(KEYS, vals))
        sid = d.get("Step-Id", "")
        if not sid:
            continue  # close 커밋 등 trailer 없는 커밋은 트리 무관
        node = {"id": sid,
                "kind": d["Kind"],
                "parent": None if d["Parent"] in ("", "null") else d["Parent"],
                "outcome": d["Outcome"] or None,
                "backtrack": d["Backtrack-To"] or None,
                "body": "steps/%s.md" % sid}
        nodes.append(node)
    return nodes


def serialize(nodes):
    lines = ["# v3 스텝 트리 — gilv3 생성. 트리는 parent/backtrack 포인터로만 담긴다."]
    for n in nodes:
        lines.append("- id: " + n["id"])
        for f in FIELDS[1:]:
            v = n.get(f)
            lines.append("  %s: %s" % (f, "null" if v is None else v))
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: rebuild_trailer.py <git_repo> [--yaml]")
    repo = sys.argv[1]
    nodes = rebuild(repo)
    if "--yaml" in sys.argv:
        sys.stdout.write(serialize(nodes))
    else:
        for n in nodes:
            print("%s %s parent=%s%s%s" % (
                n["id"], n["kind"], n["parent"],
                (" outcome=" + n["outcome"]) if n["outcome"] else "",
                (" backtrack=" + n["backtrack"]) if n["backtrack"] else ""))


if __name__ == "__main__":
    main()
