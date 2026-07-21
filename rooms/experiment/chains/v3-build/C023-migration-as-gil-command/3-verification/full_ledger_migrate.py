#!/usr/bin/env python3
"""gilv3 full-ledger-migrate (C020) — 실제 원장 전량을 순회 소급 (드라이런).

C019 도출기를 실제 원장 규모로 확장. 전수 조사가 드러낸 것: 실제 원장은 100+ 사이클에
걸쳐 커밋 관습이 진화했다(초기 `gil: C057 가설 작성`, 최신 `gil: step .../→ N/5`,
원장 관리 release/land/reserve…). subject만으로 전량 도출은 불가능 — 관습이 진화했기에.

⭐ 진실원 재선택: subject(관습 진화로 불안정) 대신 cycle.yaml(스키마 안정).
  - 사이클 발견: cycle.yaml 전량 → id·chain·parent·step·verdict.
  - 커밋 찾기: subject의 <chain>/<id> 로 open/step 커밋 해시만 (subject는 열쇠).
  - 도출: cycle.yaml step 수 + verdict 로 v3 지문 (C019 규칙).

⭐ 정직한 잔여(C017 가시성): 도출 가능한 건 도출하고, 못 하는 건 유령으로 남겨 정체를
  3종 분류 보고 — ①비-원장(memory·부트스트랩) ②원장 관리(release·land…) ③도출 실패.
  전량 도출을 억지 부리지 않는다.
"""
import os, re, sys, subprocess, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import derive_fingerprint as DF
import retro_imprint as RI

# 견고 파서: → 와 — 둘 다. gil: step <chain>/<id> [→|—] N/M <name>
RE_STEP2 = re.compile(r"^gil: step\s+(\S+)\s+(?:→|—|-)\s+(\d+)/\d+")
RE_OPEN2 = re.compile(r"^gil: open\s+(\S+)")
# 원장 관리 커밋(스텝 아님) — 정직한 스킵 대상
LEDGER_MGMT = re.compile(r"^gil: (release|land|reserve|unreserve|renumber|withdraw|"
                         r"supersede|hold|deploy|round|web|pages|v\d|_|gateway|loom|loomlight)")


def discover_cycles(repo):
    """cycle.yaml 전량 발견 → [{id, chain, parent, step, verdict, dir}]."""
    cycles = []
    for path in glob.glob(os.path.join(repo, "rooms/experiment/chains/*/*/cycle.yaml")):
        meta = {"dir": os.path.dirname(path)}
        for line in open(path, encoding="utf-8"):
            line = line.split("#")[0]  # 주석 제거
            if ":" not in line: continue
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        if "id" in meta and "chain" in meta:
            cycles.append(meta)
    return cycles


def cycle_step_commits(repo, chain, cid):
    """한 사이클의 step 커밋 해시를 subject로 찾음 (시간순, N/M 오름차순).
    subject의 <chain>/<id> 매칭 — cycle id는 관습 진화에도 안정적."""
    target = "%s/%s" % (chain, cid)
    out = subprocess.run(
        ["git", "-C", repo, "log", "--reverse", "--format=%H\x1f%s"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    found = []  # (n, hash)
    for line in out.splitlines():
        if "\x1f" not in line: continue
        h, subj = line.split("\x1f", 1)
        m = RE_STEP2.match(subj)
        if m and m.group(1) == target:
            found.append((int(m.group(2)), h))
    found.sort()
    return [h for _, h in found]


def migrate_all(repo, apply=False):
    """전량 순회. 각 사이클의 step 커밋에 derive→retro_imprint(notes).
    apply=False: 도출만 카운트(드라이런). True: 실제 notes 각인.
    반환: 통계 dict."""
    cycles = discover_cycles(repo)
    stats = {"cycles": len(cycles), "imprinted": 0, "derive_failed": [], "steps_derived": 0}
    for c in cycles:
        chain, cid = c["chain"], c["id"]
        verdict = c.get("verdict", "supported") or "supported"
        commits = cycle_step_commits(repo, chain, cid)
        if not commits:
            stats["derive_failed"].append("%s/%s" % (chain, cid))
            continue
        # C019 도출: subject를 다시 읽어 derive_cycle에 먹임
        pairs = [(h, subprocess.run(["git","-C",repo,"log","-1","--format=%s",h],
                  stdout=subprocess.PIPE).stdout.decode().strip()) for h in commits]
        derived = DF.derive_cycle(pairs, verdict)
        stats["steps_derived"] += len(derived)
        if apply:
            for h, trailers, ap in derived:
                RI.retro_imprint(repo, h, trailers)
                stats["imprinted"] += 1
    return stats


def classify_ghosts(repo):
    """소급 후 잔여 유령을 3종 분류 (C017 가시성 대규모판).
    ①비-원장(gil: 아님) ②원장관리(release·land…) ③도출실패(gil: step인데 notes 없음)."""
    out = subprocess.run(
        ["git", "-C", repo, "log", "--format=%H\x1f%s"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    non_ledger, mgmt, step_no_note = 0, 0, 0
    for line in out.splitlines():
        if "\x1f" not in line: continue
        h, subj = line.split("\x1f", 1)
        # trailer 있으면 유령 아님
        tr = subprocess.run(["git","-C",repo,"log","-1",
                             "--format=%(trailers:key=Step-Id,valueonly)",h],
                            stdout=subprocess.PIPE).stdout.decode().strip()
        if tr:
            continue  # v3 네이티브
        note = subprocess.run(["git","-C",repo,"notes","show",h],
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        if note.returncode == 0 and note.stdout.decode().strip():
            continue  # 소급됨 (유령 아님)
        # 여전히 유령 — 분류
        if not subj.startswith("gil: "):
            non_ledger += 1
        elif LEDGER_MGMT.match(subj) or subj.startswith("gil: close"):
            mgmt += 1
        elif subj.startswith("gil: step") or subj.startswith("gil: open"):
            step_no_note += 1
        else:
            mgmt += 1  # 기타 gil: 관리
    return {"non_ledger": non_ledger, "ledger_mgmt": mgmt, "step_no_note": step_no_note}


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    apply = "--apply" in sys.argv
    stats = migrate_all(repo, apply=apply)
    print("사이클 발견: %d" % stats["cycles"])
    print("도출된 스텝 노드: %d" % stats["steps_derived"])
    print("소급 각인(notes): %d %s" % (stats["imprinted"], "" if apply else "(드라이런 — 미각인)"))
    print("도출 실패(커밋 못 찾음): %d 사이클" % len(stats["derive_failed"]))
    if stats["derive_failed"][:5]:
        print("  예시:", ", ".join(stats["derive_failed"][:5]))
    if apply:
        g = classify_ghosts(repo)
        print("잔여 유령 분류: 비-원장 %d · 원장관리 %d · 도출실패-스텝 %d"
              % (g["non_ledger"], g["ledger_mgmt"], g["step_no_note"]))


if __name__ == "__main__":
    main()
