#!/usr/bin/env python3
"""gilv3 derive-fingerprint (C019) — v2 커밋 메타를 v3 지문으로 자동 도출.

마이그레이션 ③ 소급각인의 실전화. C018은 지문 값을 손으로 줬다 — 189 사이클을
손으로 매핑하는 건 불가능. 이 도출기는 v2 커밋 subject(이미 규칙적인 메타)를 파싱해
v3 지문(Step-Id·Kind·Parent) 시퀀스로 자동 매핑한다. 그러면 189 전량 소급이
스크립트 한 번(derive → retro_imprint) 이 된다.

⭐ 순수 함수 — v2 커밋 리스트를 받아 v3 지문을 낸다(부작용 0, 결정성). 각인은
C018 retro_imprint가 별도로 수행(도출과 각인의 분리).

⭐ 근사 정직 — v2 5스텝과 v3 kind 집합이 1:1이 아니므로(v2=5스텝, v3=4kind) 매핑은
무손실이 아니라 **위상 보존적 근사**다. v2 원장의 위상(선형 5노드)은 완전 보존되고,
잃는 것은 "설계"라는 v2 스텝명이 v3 kind에 정확히 안 담기는 것뿐 — 그건 커밋 subject에
원문으로 남아 손실 아님(notes는 지문만, subject는 v2 원문 그대로).
"""
import re, sys

# v2 5스텝 → v3 노드 1:1 매핑 (구조 보존). v2엔 백트래킹 데이터 없어 전부 선형.
V2_STEP_TO_KIND = {1: "define", 2: "hypothesis", 3: "verify", 4: "analyze", 5: "analyze"}
V2_STEP_PARENT  = {1: None, 2: "s1", 3: "s2", 4: "s3", 5: "s4"}
# 근사 지점(무손실 아님): 2/5 '설계'→hypothesis, 4/5 '분석'→analyze, 5/5 '보고'→analyze/success.
V2_APPROXIMATE_STEPS = {2, 4, 5}  # v3 kind에 정확히 안 담기는 스텝 (근사 명시용)

# 실제 원장 subject 3종 파서
RE_OPEN  = re.compile(r"^gil: open\s+(\S+)\s+—\s+\d+/5")
RE_STEP  = re.compile(r"^gil: step\s+(\S+)\s+→\s+(\d+)/5\s+(\S+)")
RE_CLOSE = re.compile(r"^gil: close\s+(\S+)")


def classify(subject):
    """커밋 subject를 (kind, cycle, step_n, step_name) 로 분류.
    kind ∈ {open, step, close, unknown}. step만 step_n/step_name 채움."""
    m = RE_STEP.match(subject)
    if m:
        return ("step", m.group(1), int(m.group(2)), m.group(3))
    m = RE_OPEN.match(subject)
    if m:
        return ("open", m.group(1), None, None)
    m = RE_CLOSE.match(subject)
    if m:
        return ("close", m.group(1), None, None)
    return ("unknown", None, None, None)


def derive_cycle(commits, verdict="supported"):
    """v2 사이클 커밋 리스트 → v3 지문 시퀀스.

    commits: [(hash, subject), ...] 시간순.
    반환: [(hash, [(key,val)...], approximate_bool), ...] — step 커밋만 (open/close 스킵).
    순수 함수(결정성, H1a). verdict는 5/5 보고의 outcome 결정에 반영."""
    out = []
    for h, subj in commits:
        kind, cyc, n, name = classify(subj)
        if kind != "step":
            continue  # open/close는 트리 노드 아님 (스킵)
        v3_kind = V2_STEP_TO_KIND.get(n)
        if v3_kind is None:
            continue  # 5스텝 밖 (방어적)
        parent = V2_STEP_PARENT[n]
        trailers = [("Step-Id", "s%d" % n),
                    ("Kind", v3_kind),
                    ("Parent", parent if parent else "null")]
        if n == 5:
            # 5/5 보고 = 산 잎. verdict 반영(supported→success, 그 외→fail 근사).
            outcome = "success" if verdict == "supported" else "fail"
            trailers.append(("Outcome", outcome))
        approximate = n in V2_APPROXIMATE_STEPS
        out.append((h, trailers, approximate))
    return out


def main():
    # 사용법: derive_fingerprint.py <repo> <chain>/<cycle> [verdict]
    #   실제 원장에서 그 사이클의 step 커밋들을 읽어 v3 지문을 출력.
    import subprocess
    if len(sys.argv) < 3:
        sys.exit("사용법: derive_fingerprint.py <repo> <chain>/<cycle> [verdict]")
    repo, target = sys.argv[1], sys.argv[2]
    verdict = sys.argv[3] if len(sys.argv) > 3 else "supported"
    out = subprocess.run(
        ["git", "-C", repo, "log", "--reverse", "--format=%H\x1f%s"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    commits = []
    for line in out.splitlines():
        if "\x1f" not in line:
            continue
        h, subj = line.split("\x1f", 1)
        _, cyc, _, _ = classify(subj)
        if cyc == target:
            commits.append((h, subj))
    derived = derive_cycle(commits, verdict)
    n_approx = sum(1 for _, _, ap in derived if ap)
    for h, trailers, ap in derived:
        mark = " [근사]" if ap else ""
        print("%s  %s%s" % (h[:8], " ".join("%s=%s" % t for t in trailers), mark))
    sys.stderr.write("도출 %d노드 (근사 %d개 — v2 5스텝→v3 4kind, 위상 보존·kind 근사)\n"
                     % (len(derived), n_approx))


if __name__ == "__main__":
    main()
