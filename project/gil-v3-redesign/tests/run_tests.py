#!/usr/bin/env python3
"""테스트를 클래스 단위로 쪼개 프로세스 여럿에서 돌린다.

왜. 단일 프로세스로는 300개가 4분 가까이 걸린다 — 각 테스트가 임시 저장소를 만들고 git 을
수십 번 부르는 I/O 바운드라, 코어를 놀리며 기다리는 시간이 대부분이다. 테스트끼리는 이미
격리돼 있다(각자 tempdir + 자기 git 저장소). 그러니 나눠 돌리면 그대로 빨라진다.

  python3 run_tests.py            # 코어 수만큼
  python3 run_tests.py -j 4       # 4개로
  python3 run_tests.py -k Viewer  # 이름에 Viewer 가 든 클래스만
  GIL_BIN=... python3 run_tests.py

실패가 있으면 그 클래스의 출력을 그대로 보여주고 종료코드 1.
"""
import argparse, json, os, subprocess, sys, time, unittest
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
TIMINGS = os.path.join(HERE, ".test-timings.json")


def load_timings():
    try:
        with open(TIMINGS) as f:
            return json.load(f)
    except Exception:
        return {}


def save_timings(rows):
    """이번 실행의 클래스별 소요를 남긴다 — 다음 실행의 스케줄링 근거."""
    old = load_timings()
    old.update(rows)
    try:
        with open(TIMINGS, "w") as f:
            json.dump(old, f, indent=0, sort_keys=True)
    except OSError:
        pass


def schedule(names):
    """**긴 것부터** 던진다(LPT). 클래스 단위 분할에서 남는 손해는 대부분 꼬리다:
    알파벳 순으로 던지면 51초짜리가 마지막에 시작될 수 있고, 그러면 나머지 7개 워커가
    그 시간 내내 논다. 실측 — 벽시계 172s, CPU 합계 1085s, 이상적 하한(÷8) 136s.
    소요는 지난 실행에서 배운다(.test-timings.json). 처음 보는 클래스는 '길다'고 가정해
    앞에 둔다 — 짧은 걸 앞에 두는 실수보다 손해가 작다."""
    t = load_timings()
    return sorted(names, key=lambda n: -t.get(n, 1e9))


def classes(pattern):
    """test_gil 에서 TestCase 클래스 이름을 모은다(한 번만 임포트)."""
    sys.path.insert(0, HERE)
    import test_gil
    out = []
    for name in dir(test_gil):
        obj = getattr(test_gil, name)
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase) \
           and obj is not unittest.TestCase and name.startswith("Test"):
            if not pattern or pattern.lower() in name.lower():
                out.append(name)
    return sorted(out)


def run_one(name):
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "unittest", f"test_gil.{name}"],
                       cwd=HERE, capture_output=True, text=True)
    # unittest 는 요약을 stderr 로 낸다. "Ran N tests" 에서 개수를 뽑는다.
    n = 0
    for ln in p.stderr.splitlines():
        if ln.startswith("Ran ") and " test" in ln:
            try:
                n = int(ln.split()[1])
            except ValueError:
                pass
    return name, p.returncode, n, p.stdout + p.stderr, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", "--jobs", type=int, default=0, help="병렬 프로세스 수(기본: 코어 수)")
    ap.add_argument("-k", "--filter", default="", help="클래스 이름 부분일치")
    args = ap.parse_args()
    # git 자식이 대부분인 I/O 바운드라 코어 수보다 더 띄우는 편이 빠르다(코어를 놀리며
    # 기다리는 시간이 지배적 — 러너 최상단 주석의 근거 그대로).
    jobs = args.jobs or max(4, int((os.cpu_count() or 4) * 1.5))
    names = schedule(classes(args.filter))
    if not names:
        print("맞는 테스트 클래스가 없다", file=sys.stderr)
        return 2

    t0 = time.time()
    total = failed = 0
    bad = []
    times = {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for name, rc, n, out, dt in ex.map(run_one, names):
            times[name] = round(dt, 2)
            total += n
            mark = "." if rc == 0 else "F"
            if rc != 0:
                failed += 1
                bad.append((name, out))
            sys.stdout.write(mark)
            sys.stdout.flush()
    save_timings(times)
    wall = time.time() - t0
    cpu = sum(times.values())
    print(f"\n\n{len(names)} 클래스 · {total} 테스트 · {wall:.1f}s ({jobs} 병렬)")
    # 병렬이 실제로 먹고 있는지 한 줄로 보여준다 — "느린 것 같은데 병렬 맞나"에 매번
    # 손으로 재지 않도록(상현님). 효율이 낮으면 꼬리(가장 긴 클래스)를 함께 짚는다.
    if cpu > 0:
        eff = cpu / jobs / wall * 100
        line = f"  병렬 효율 {eff:.0f}%  ·  CPU 합계 {cpu:.0f}s  ·  이상적 하한 {cpu / jobs:.0f}s"
        slowest = sorted(times.items(), key=lambda kv: -kv[1])[:3]
        if eff < 85 and slowest:
            line += "\n  꼬리: " + " · ".join(f"{k} {v:.0f}s" for k, v in slowest)
        print(line)
    for name, out in bad:
        print(f"\n{'=' * 70}\n■ {name}\n{'=' * 70}\n{out}")
    if failed:
        print(f"\n실패한 클래스 {failed}개")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
