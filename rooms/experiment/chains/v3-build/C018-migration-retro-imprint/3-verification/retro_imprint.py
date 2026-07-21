#!/usr/bin/env python3
"""gilv3 retro-imprint (C018) — 유령(pre-gil) 커밋에 v3 지문을 git notes로 소급 각인.

마이그레이션 4단계 중 ③ 소급각인. C017이 세운 읽기호환(유령 무해·가시) 위에서,
유령을 v3의 눈에 보이게 만든다 — 유령 수를 0으로.

⭐ 핵심 제약 — 커밋 불변(C014 append-only "커밋 불소멸").
닫힌 커밋에 trailer를 넣으려면 amend/rebase가 필요한데 그건 히스토리 재작성이라
_assert_append_only가 거부한다. git notes는 커밋을 안 건드리고 refs/notes/*의 별도
ref에 메타를 첨부한다 — 커밋 SHA 불변, append-only 완벽 준수. "깃도 옛 커밋에 서명
없어도 그래프가 읽히듯" notes는 서명처럼 커밋 밖에서 커밋을 가리킨다.

notes 본문 = trailer와 동일한 Key: Value 라인 → 재구성기가 같은 파서로 읽는다.
"""
import sys, subprocess


def _commit_shas(repo):
    """원장 커밋 SHA 집합 (불변 자기 집행용) — refs/notes/* 제외.

    ⭐ C018 함정(측정 중 발견): git notes는 refs/notes/commits라는 ref를 만드는데
    그 ref 자체가 커밋 객체다(notes는 커밋 트리로 저장). 그래서 `rev-list --all`은
    notes 커밋을 새로 센다 — 이걸 불변 위반으로 오판하면 안 된다. 진짜 계약은
    '원장 커밋(스텝·유령)이 불변인가'이지 'notes 메타 저장 커밋이 안 느나'가 아니다.
    → refs/notes/*를 제외하고, 원장이 보이는 ref(브랜치·태그·HEAD)만 순회한다.
    notes 각인은 원장 커밋 SHA를 하나도 안 바꾼다(probe: 첨부 전후 커밋 hash 동일)."""
    # --exclude 는 뒤따르는 --all/--branches 등에 적용되므로 --all 앞에 온다.
    r = subprocess.run(
        ["git", "-C", repo, "rev-list", "--exclude=refs/notes/*", "--all"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return set(r.stdout.decode().split())


def _is_v3_native(repo, commit):
    """이 커밋이 이미 v3 네이티브인가 — subject가 'gilv3 '로 시작(open/step/close).
    pre-gil vs close 구분(C017 이월): close 커밋도 trailer 없지만 v3 각인 이력이라
    소급 대상이 아니다. pre-gil(임의 subject)만 지문을 받는다 (H1d)."""
    subj = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%s", commit],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode().strip()
    return subj.startswith("gilv3 ")


def _has_trailer(repo, commit):
    """이미 Step-Id trailer가 있는 v3 커밋인가 (소급 불필요)."""
    v = subprocess.run(["git", "-C", repo, "log", "-1",
                        "--format=%(trailers:key=Step-Id,valueonly)", commit],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode().strip()
    return bool(v)


def retro_imprint(repo, commit, trailers):
    """유령 커밋에 v3 지문을 git notes로 소급 각인 — 커밋 불변.

    trailers: [(key, val), ...] → notes 본문 = trailer와 동일한 Key: Value 라인.
    커밋 불변 자기 집행: notes add 전후 모든 커밋 SHA가 동일해야 한다 (H1a).
    pre-gil만 대상: v3 네이티브(trailer 有 or gilv3 subject)는 건너뛴다 (H1d)."""
    if _has_trailer(repo, commit) or _is_v3_native(repo, commit):
        return False  # 이미 v3 — 소급 대상 아님 (close 포함)
    before = _commit_shas(repo)
    body = "\n".join("%s: %s" % (k, v) for k, v in trailers)
    r = subprocess.run(["git", "-C", repo, "notes", "add", "-f", "-m", body, commit],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.exit("소급각인 실패: %s — %s" % (commit, r.stderr.decode().strip()))
    after = _commit_shas(repo)
    if before != after:
        sys.exit("거부(C018): notes 각인이 커밋 SHA를 바꿨다 — append-only 위반. "
                 "(git notes가 아닌 재작성이 일어남)")
    return True


def main():
    # 사용법: retro_imprint.py <repo> <commit> Key=Val [Key=Val ...]
    if len(sys.argv) < 4:
        sys.exit("사용법: retro_imprint.py <repo> <commit> Key=Val [Key=Val ...]")
    repo, commit = sys.argv[1], sys.argv[2]
    trailers = []
    for kv in sys.argv[3:]:
        k, _, v = kv.partition("=")
        trailers.append((k, v))
    done = retro_imprint(repo, commit, trailers)
    print("소급각인 %s: %s (%s)" % (
        "완료" if done else "건너뜀(이미 v3)", commit[:8],
        ", ".join("%s=%s" % t for t in trailers) if done else "대상 아님"))


if __name__ == "__main__":
    main()
