#!/usr/bin/env python3
"""gilv3 rebuild — 깃 로그만으로 스텝 트리를 복원한다 (C009).

C008의 역방향: C008은 steps.yaml → 깃(각인)을 실증했다. 여기선 깃 → 스텝 트리
(복원)를 검증한다. steps.yaml 파일도, 커밋 diff도 읽지 않는다 — 오직
`git log --reverse --format=%s`(커밋 시간순 + subject)만.

원리 (C003 상태기계의 거울):
  - parent는 대개 '시간순 직전 노드'(순환 계승) — 쓰기 때 팁 자동이었던 것.
  - 예외는 백트래킹 후 새 가지뿐 — 서술 'new branch from sM'로 parent=sM.
    쓰기 때 `--to sM` 명시였던 것이 읽기 때 `from sM` 파싱이 된다.
  - 되돌아감 목적지·outcome은 잎 커밋 서술 '(backtrack to sM)'·'analyze/success'에.

입력이 오직 커밋 순서 + 메시지이므로, 깃이 스텝 트리의 진실원이 될 수 있는지를
가른다 (steps.yaml=파생 캐시).
"""
import sys, re, subprocess

FIELDS = ["id", "kind", "parent", "outcome", "backtrack", "body"]


def git_log_subjects(repo):
    """오직 이 한 명령만 — git log. steps.yaml·show·diff·cat-file 안 씀 (C009 K3)."""
    out = subprocess.run(
        ["git", "-C", repo, "log", "--reverse", "--format=%s"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    return [ln for ln in out.splitlines() if ln.strip()]


# 커밋 subject 파서 — 케이스 배타적 (C009 M4 결정성)
RE_OPEN = re.compile(r"^gilv3 open [^:]*:\s*(s\d+) define$")
RE_STEP = re.compile(
    r"^gilv3 step:\s*(s\d+)\s+(\w+)"
    r"(?:/(\w+))?"                                    # analyze/<outcome>
    r"(?:\s+\(backtrack to (s\d+)\))?"                # 죽은 잎 목적지
    r"(?:\s+\(new branch from (s\d+) after backtrack\))?$")  # 새 가지 parent
RE_CLOSE = re.compile(r"^gilv3 close ")


def rebuild(repo):
    """깃 로그 → 노드 리스트. C003 순환 상태기계를 복원 방향으로."""
    nodes = []          # 시간순
    prev_id = None      # 직전(시간순) 노드 = open_branch 계승의 부모
    for subj in git_log_subjects(repo):
        m = RE_OPEN.match(subj)
        if m:
            sid = m.group(1)
            nodes.append({"id": sid, "kind": "define", "parent": None,
                          "outcome": None, "backtrack": None,
                          "body": "steps/%s.md" % sid})
            prev_id = sid
            continue
        m = RE_STEP.match(subj)
        if m:
            sid, kind, outcome, bt_to, from_m = m.groups()
            node = {"id": sid, "kind": kind, "parent": None, "outcome": None,
                    "backtrack": None, "body": "steps/%s.md" % sid}
            if from_m is not None:
                # 백트래킹 후 새 형제 가지 — parent=명시된 조상 (유일한 비-직전 부모)
                node["parent"] = from_m
            else:
                # 순환 계승 — parent = 시간순 직전
                node["parent"] = prev_id
            if outcome is not None:
                node["outcome"] = outcome
                if outcome == "backtrack":
                    node["backtrack"] = bt_to  # 서술 '(backtrack to sM)'
            nodes.append(node)
            prev_id = sid
            continue
        if RE_CLOSE.match(subj):
            continue  # 봉인 — 트리 구조 무관
        # 알 수 없는 커밋은 정직하게 실패 (모호성=K4 신호)
        sys.exit("복원 실패: 해석 불가 커밋 subject: %r" % subj)
    return nodes


def serialize(nodes):
    """복원 트리를 steps.yaml 텍스트로 (C002 dump 형식과 동일 — 왕복 대조용)."""
    lines = ["# v3 스텝 트리 — gilv3 생성. 트리는 parent/backtrack 포인터로만 담긴다."]
    for n in nodes:
        lines.append("- id: " + n["id"])
        for f in FIELDS[1:]:
            v = n.get(f)
            lines.append("  %s: %s" % (f, "null" if v is None else v))
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: rebuild.py <git_repo> [--yaml]")
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
