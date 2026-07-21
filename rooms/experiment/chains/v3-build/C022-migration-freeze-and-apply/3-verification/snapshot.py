#!/usr/bin/env python3
"""C022 snapshot — 원장 불변 검증 계측기.

마이그레이션이 refs/notes/* 밖의 어떤 것도 안 바꾼다는 것을 증명하기 위한 스냅샷.
캡처 대상:
  - 원장 커밋 SHA 목록 (refs/notes/* 제외 — C018 함정 회피): notes 커밋은 원장이 아님.
  - 작업 트리 상태 (git status --porcelain): 청결해야 함.
  - cycle.yaml 전량 해시: 파일 불변 확인.

두 스냅샷을 diff 하면 마이그레이션의 부작용면이 refs/notes로 한정됐는지 판정된다.
"""
import os, sys, subprocess, hashlib, glob, json


def commit_shas(repo):
    """원장 커밋 SHA (refs/notes/* 제외). C018 계약: notes는 원장 아님."""
    out = subprocess.run(
        ["git", "-C", repo, "rev-list", "--exclude=refs/notes/*", "--all"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    return sorted(out.split())


def worktree_status(repo):
    """작업 트리 상태 (청결하면 빈 문자열)."""
    return subprocess.run(
        ["git", "-C", repo, "status", "--porcelain"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()


def cycle_yaml_hash(repo):
    """cycle.yaml 전량의 결합 해시 (내용 불변 확인)."""
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(repo, "rooms/experiment/chains/*/*/cycle.yaml"))):
        h.update(p.encode())
        h.update(open(p, "rb").read())
    return h.hexdigest()


def notes_ref(repo):
    """refs/notes/commits 의 현재 값 (없으면 None) — 변경면 관찰용."""
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q",
                        "refs/notes/commits"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    v = r.stdout.decode().strip()
    return v or None


def snapshot(repo):
    return {
        "commit_shas": commit_shas(repo),
        "commit_count": len(commit_shas(repo)),
        "worktree_status": worktree_status(repo),
        "cycle_yaml_hash": cycle_yaml_hash(repo),
        "notes_ref": notes_ref(repo),
    }


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    snap = snapshot(repo)
    # 커밋 SHA 목록은 길어서 개수+해시로 압축 출력
    compact = dict(snap)
    compact["commit_shas_digest"] = hashlib.sha256(
        "\n".join(snap["commit_shas"]).encode()).hexdigest()
    del compact["commit_shas"]
    print(json.dumps(compact, indent=2, ensure_ascii=False))
