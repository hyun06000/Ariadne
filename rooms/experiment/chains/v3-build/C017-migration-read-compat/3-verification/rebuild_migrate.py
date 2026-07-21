#!/usr/bin/env python3
"""gilv3 rebuild (migrate) — git trailer 계약으로 스텝 트리를 복원한다 (C017).

C010 rebuild_trailer.py의 후계: C010은 subject 파싱(C009)에서 git trailer로 옮겼다.
C017은 그 위에 **마이그레이션 읽기호환**을 얹는다 — 지문(Step-Id trailer) 없는 커밋을
유령(pre-gil)으로 세어 건너뛰고 보고한다.

⭐ C017 발견: C010 trailer 재구성기는 이미 유령을 스킵했다(close 커밋을 위한
`if not sid: continue`). 그 로직이 pre-gil v2 커밋(역시 trailer 없음)에도 그대로
통한다 — C009→C010 전환(subject→trailer)이 즉사(C009 sys.exit)를 우아한 스킵으로
이미 바꿔 놓았다. 마이그레이션 노트의 "지문 없으면 덜 읽힐 뿐 파괴 아님"이 여기서 참.

C017의 기여: ① 그 무해가 혼합 원장(v2 유령 + v3 트리)에서 실제로 참임을 실증.
② 침묵 스킵 → **가시적 스킵**(유령 수 보고). 마이그레이션에선 "얼마나 덜 읽혔나"가
필수 계약 — 사용자가 유령 규모를 알아야 소급각인을 결정한다(침묵은 "다 읽었다"로 오독).

오직 `git log --format=%(trailers…)`만 — steps.yaml·show·diff 안 씀. 읽기 전용이라
유령을 삭제·이동·변조하지 않는다(경계 불변 = 구조적 보장).
"""
import sys, os, subprocess

FIELDS = ["id", "kind", "parent", "outcome", "backtrack", "body"]
KEYS = ["Step-Id", "Kind", "Parent", "Outcome", "Backtrack-To"]

# 커밋당 trailer를 한 레코드로 뽑는 포맷 — 커밋 경계는 유니크 구분자로.
SEP = "\x1e"        # record separator (커밋 사이)
FSEP = "\x1f"       # field separator (키 사이)
# git pretty 포맷은 %(trailers…) 리터럴 — 파이썬 % 포맷과 충돌하므로 문자열 연결로.
# %H(커밋 해시)를 맨 앞에 — 유령을 되짚을 수 있게(pre-gil vs close 구분은 다음 카브).
_FMT = SEP + "%H" + FSEP + FSEP.join(
    "%(trailers:key=" + k + ",valueonly)" for k in KEYS)


def rebuild(repo, report=False):
    """git trailer만으로 노드 리스트 복원 (시간순). 자연어 subject 미사용.

    지문(Step-Id) 없는 커밋은 유령(pre-gil 또는 close)으로 건너뛴다 — 즉사 안 함.
    report=True면 (nodes, ghosts) 반환 — ghosts는 건너뛴 커밋 해시 리스트(가시성).
    유령을 삭제·변조하지 않는다(메모리에서 건너뛸 뿐, 깃 읽기 전용)."""
    out = subprocess.run(
        ["git", "-C", repo, "log", "--reverse", "--format=" + _FMT],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    nodes = []
    ghosts = []   # 지문 없는 커밋 해시 — 유령(안 읽힌 커밋)
    for rec in out.split(SEP):
        rec = rec.strip("\n")
        if not rec:
            continue
        vals = rec.split(FSEP)
        # 각 valueonly는 trailer 값 or 빈 문자열(그 키 없음). 개행 잔여 제거.
        vals = [v.strip() for v in vals]
        commit_hash = vals[0]
        d = dict(zip(KEYS, vals[1:]))
        sid = d.get("Step-Id", "")
        if not sid:
            ghosts.append(commit_hash)  # 침묵 continue 대신 기록 — 가시성(H1d)
            continue
        node = {"id": sid,
                "kind": d["Kind"],
                "parent": None if d["Parent"] in ("", "null") else d["Parent"],
                "outcome": d["Outcome"] or None,
                "backtrack": d["Backtrack-To"] or None,
                "body": "steps/%s.md" % sid}
        nodes.append(node)
    if report:
        return nodes, ghosts
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
        sys.exit("사용법: rebuild_migrate.py <git_repo> [--yaml] [--report]")
    repo = sys.argv[1]
    nodes, ghosts = rebuild(repo, report=True)
    if "--report" in sys.argv:
        # 가시성(H1d): 얼마나 덜 읽혔나 — 사용자가 유령 규모를 알아야 소급각인 결정.
        # 침묵 스킵은 "다 읽었다"로 오독된다 (마이그레이션 필수 계약).
        sys.stderr.write("유령(지문 없음) %d개 건너뜀 (v3 스텝 %d개 복원)\n"
                         % (len(ghosts), len(nodes)))
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
