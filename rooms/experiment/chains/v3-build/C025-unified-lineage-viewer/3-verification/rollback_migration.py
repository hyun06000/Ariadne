#!/usr/bin/env python3
"""C022 rollback_migration — 동결백업 지점으로 되돌려 notes 완전 제거 실증.

국면 C — 되돌림 실증:
  적용 전 refs/notes가 부재였으면(백업 kind="absent") 되돌림 = refs/notes/commits 삭제.
  적용 전 refs/notes가 있었으면 백업 ref 값으로 refs/notes/commits 리셋.

되돌림 후 notes 완전 제거(또는 백업 상태 정확 복귀)를 검증한다.
커밋·트리는 애초에 안 건드렸으므로 되돌림도 refs/notes만 만진다.

사용법:
  python3 rollback_migration.py <repo>
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snapshot as SNAP

BACKUP_REF = "refs/notes-backup/pre-c022"
NOTES_REF = "refs/notes/commits"


def _rev(repo, ref):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", ref],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.stdout.decode().strip() or None


def rollback(repo):
    """백업 ref로 되돌림. 백업 없으면(적용 전 부재) refs/notes/commits 삭제."""
    backup = _rev(repo, BACKUP_REF)
    if backup:
        subprocess.run(["git", "-C", repo, "update-ref", NOTES_REF, backup], check=True)
        return ("reset", backup)
    else:
        # 적용 전 notes 부재 — 되돌림 = 삭제
        cur = _rev(repo, NOTES_REF)
        if cur:
            subprocess.run(["git", "-C", repo, "update-ref", "-d", NOTES_REF], check=True)
        return ("delete", None)


def main():
    repo = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    print("=== C022 rollback_migration — REAL_REPO=%s ===" % repo)

    before = SNAP.snapshot(repo)
    print("되돌림 전: notes_ref=%s" % before["notes_ref"])

    kind, val = rollback(repo)
    print("되돌림 수행: %s (%s)" % (kind, (val or "삭제")[:12]))

    after = SNAP.snapshot(repo)
    print("되돌림 후: notes_ref=%s" % after["notes_ref"])

    # 검증: 적용 전 부재였으면 notes_ref = None 이어야 (잔재 0)
    if kind == "delete" and after["notes_ref"] is not None:
        sys.exit("❌ 되돌림 불완전: notes 잔재 남음 (%s)" % after["notes_ref"])
    # 커밋·트리 불변
    if before["commit_shas"] != after["commit_shas"]:
        sys.exit("❌ 되돌림이 커밋 SHA를 바꿈")
    if before["cycle_yaml_hash"] != after["cycle_yaml_hash"]:
        sys.exit("❌ 되돌림이 cycle.yaml을 바꿈")
    print("✅ 되돌림 완전: notes 제거%s, 커밋·cycle.yaml 불변" %
          (" (잔재 0)" if kind == "delete" else " (백업 복원)"))


if __name__ == "__main__":
    main()
