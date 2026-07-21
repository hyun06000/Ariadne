#!/usr/bin/env python3
"""C022 apply_migration — 실제 원장에 마이그레이션을 되돌림 가능하게 적용.

⚠️ 이 스크립트는 격리 복제본이 아니라 REAL_REPO(우리 실제 저장소)를 대상으로 한다.
   그러나 C018 계약상 refs/notes/* 밖은 하나도 안 바뀐다 — snapshot 으로 자기 집행.

국면:
  A. 동결백업(①): 적용 직전 refs/notes 상태를 refs/notes-backup/pre-c022 로 못박음.
     적용 전 refs/notes 부재면 백업 = "부재 기록"(백업 ref 미생성 = 되돌림 시 삭제).
  B. 적용: full_ledger_migrate --apply(노드 소급) + splice_topology(위상 접합).
  각 국면 전후 snapshot 으로 커밋·트리·cycle.yaml 불변 검증.

사용법:
  python3 apply_migration.py <repo>          # 백업 + 적용
  python3 apply_migration.py <repo> --dry     # 스냅샷만(적용 안 함)
"""
import os, sys, subprocess, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snapshot as SNAP

BACKUP_REF = "refs/notes-backup/pre-c022"
NOTES_REF = "refs/notes/commits"


def _git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and r.returncode != 0:
        sys.exit("git 실패: %s\n%s" % (" ".join(args), r.stderr.decode()))
    return r.stdout.decode().strip()


def freeze_backup(repo):
    """국면 A — 적용 직전 refs/notes 상태를 백업 ref로 동결."""
    cur = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", NOTES_REF],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                         ).stdout.decode().strip()
    if cur:
        _git(repo, "update-ref", BACKUP_REF, cur)
        return ("present", cur)
    else:
        # refs/notes 부재 — 백업 = 부재 기록(백업 ref 미생성). 되돌림 = notes 삭제.
        return ("absent", None)


def apply(repo):
    """국면 B — 노드 소급 + 위상 접합을 실제 refs/notes에 각인."""
    print("  [B.1] full_ledger_migrate --apply (노드 소급)...")
    r = subprocess.run([sys.executable, os.path.join(HERE, "full_ledger_migrate.py"),
                        repo, "--apply"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("    " + "\n    ".join(r.stdout.decode().strip().splitlines()[:4]))
    if r.returncode != 0:
        sys.exit("노드 소급 실패:\n" + r.stderr.decode())
    print("  [B.2] splice_topology (위상 접합)...")
    r = subprocess.run([sys.executable, os.path.join(HERE, "splice_topology.py"), repo],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("    " + "\n    ".join(r.stdout.decode().strip().splitlines()[:4]))
    if r.returncode != 0:
        sys.exit("위상 접합 실패:\n" + r.stderr.decode())


def assert_invariant(before, after, label):
    """커밋 SHA·트리·cycle.yaml 불변 게이트 — 하나라도 다르면 중단."""
    problems = []
    if before["commit_shas"] != after["commit_shas"]:
        problems.append("커밋 SHA 목록 변화 (%d→%d)" %
                        (before["commit_count"], after["commit_count"]))
    if before["worktree_status"] != after["worktree_status"]:
        problems.append("작업 트리 상태 변화")
    if before["cycle_yaml_hash"] != after["cycle_yaml_hash"]:
        problems.append("cycle.yaml 해시 변화")
    if problems:
        sys.exit("❌ 불변 위반 (%s): %s" % (label, "; ".join(problems)))
    print("  ✅ 불변 확인 (%s): 커밋·트리·cycle.yaml 전부 동일" % label)


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    repo = os.path.abspath(repo)
    dry = "--dry" in sys.argv
    print("=== C022 apply_migration — REAL_REPO=%s ===" % repo)

    before = SNAP.snapshot(repo)
    print("적용 전: 커밋 %d개, notes_ref=%s, 트리=%s" %
          (before["commit_count"], before["notes_ref"],
           "청결" if not before["worktree_status"].strip() else "변경있음"))

    if dry:
        print(json.dumps({k: v for k, v in before.items() if k != "commit_shas"},
                         indent=2, ensure_ascii=False, default=str))
        return

    print("\n[국면 A] 동결백업(①)...")
    kind, val = freeze_backup(repo)
    print("  백업: refs/notes = %s (%s)" % (kind, (val or "")[:12]))

    print("\n[국면 B] 실제 적용...")
    apply(repo)

    after = SNAP.snapshot(repo)
    print("\n[검증] 불변 게이트...")
    assert_invariant(before, after, "적용 후")
    print("  적용 후: notes_ref=%s (변경면은 refs/notes 뿐)" % after["notes_ref"])


if __name__ == "__main__":
    main()
