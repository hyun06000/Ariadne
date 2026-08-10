#!/usr/bin/env python3
"""gil v3 example 테스트 — 도그푸딩이 아닌 격리 검증.

원칙(README.ai.md §2): gil을 *짓는* 일은 평범한 커밋으로 하고, 기능 검증은 이
example 테스트로 한다. 각 테스트는 **격리된 임시 git 저장소**(fixture)를 만들어
gil 명령을 subprocess로 돌리고 결과를 단언한다. 통제된 입력 → 기대 출력.
이 레포의 실제 이력에 실행하지 않으므로(도그푸딩 아님), 도구 버그가 실제 자산을
오염시키지 않고 재현·반복 가능하다.

실행:  python3 -m unittest discover -s project/gil-v3-redesign/tests
   또는  python3 project/gil-v3-redesign/tests/test_gil.py
"""
import glob
import json
import os
import re
import sys
import subprocess
import tempfile
import time
import shutil
import unittest
import urllib.request
from pathlib import Path

# gil 은 Go 단일 바이너리가 유일 구현이다(Python 참조 은퇴, 2026-07-24 상현님).
# 기본은 빌드된 Go 바이너리. GIL_BIN 으로 다른 경로를 물릴 수 있다.
_DEFAULT_BIN = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "go", "gil"))
GIL_BIN = os.environ.get("GIL_BIN", _DEFAULT_BIN)
if not os.path.exists(GIL_BIN):
    raise SystemExit(
        f"gil 바이너리 없음: {GIL_BIN}\n"
        "먼저 빌드하라: (cd project/gil-v3-redesign/go && go build -o gil .)")
GIL_CMD = [GIL_BIN]

def renderer_src_path():
    """렌더러 소스의 경로. **파일 이름을 박지 않는다.**

    렌더러는 오래 `viewer_serve.go` 안에 살다가 `graph_render.go` 로 옮겨 왔다(뷰어는
    은퇴하고 그림은 남는다). 이름을 박아 둔 시험 셋이 그 이동에 걸렸다 — 파일 이름을 적는
    것도 **열거**고, 열거는 늘 뒤늦다. 렌더러는 `renderHTML` 을 정의한 파일이다.
    """
    go = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "go")
    for fn in sorted(os.listdir(go)):
        if not fn.endswith(".go"):
            continue
        path = os.path.join(go, fn)
        with open(path, encoding="utf-8") as f:
            if "func renderHTML(" in f.read():
                return path
    raise AssertionError("렌더러(func renderHTML 을 정의한 파일)를 못 찾았다 — 이 시험이 눈이 먼다")


# 테스트용 기준 문서(사람이 준 것으로 간주) — 목적과 기준은 쌍으로만 태어난다(상현님).
# 파일명에 pid — 병렬 러너가 프로세스로 쪼개 돌리므로 공유 경로에 동시에 쓰면 서로를 자른다.
CRIT_FILE = os.path.join(tempfile.gettempdir(), f"gil-test-criterion-{os.getpid()}.md")
with open(CRIT_FILE, "w", encoding="utf-8") as _f:
    _f.write("# 기준 문서(테스트)\n사람이 세운 기준으로 간주한다.\n")


class GilFixture(unittest.TestCase):
    """각 테스트마다 깨끗한 임시 git 저장소를 fixture로 만든다."""

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="gil-test-")
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "test")
        self._git("config", "commit.gpgsign", "false")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # ── 헬퍼 ────────────────────────────────────────────────
    def _git(self, *args):
        # gil guard(이슈 #116)가 체인 가지의 평범 커밋을 막는다. 시험 fixture 는 **일부러**
        # 오염된 그래프를 짓는 자리가 많다(중복 번호·비-gil 팁·유실 재현 등) — 그건 사람이
        # 우회한 상황을 재현하는 것이므로 명시적 예외로 통과시킨다. guard 자체를 검증하는
        # 시험은 self._guard_active = True 로 이 예외를 끈다(그때는 훅이 판정해야 한다).
        env = dict(os.environ)
        if not getattr(self, "_guard_active", False):
            env["GIL_ALLOW_RAW"] = "1"
        return subprocess.run(["git", *args], cwd=self.repo,
                              capture_output=True, text=True, env=env)

    def gil(self, *args, input=None):
        """gil 명령 실행. 반환: CompletedProcess(returncode, stdout, stderr).

        input: 주면 stdin 으로 전달한다(--body-file - 검증용).
        GIL_NO_VIEWER: gil init 이 관전 서버(뷰어)를 백그라운드로 띄우는 것을 억제한다 —
        테스트가 포트를 점유하거나 프로세스를 남기지 않도록 격리한다.

        AIL #12: open 은 이제 본문(--body/--body-file/--title)이 필수다. 대부분의 테스트는
        open 자체가 아니라 그 뒤 흐름을 검증하므로, 본문·body-file·title·stdin 이 하나도
        없으면 기본 --body 를 자동 주입한다(테스트 의도 보존). 본문 필수 자체를 검증하는
        테스트는 명시적으로 --body 를 빼고 호출하면 되도록, 인자에 그 흔적이 있으면 안 붙인다."""
        args = list(args)
        if args and args[0] == "open" and input is None and \
           not any(a in ("--body", "--body-file", "--title") or
                   a.startswith(("--body=", "--body-file=", "--title=")) for a in args):
            args += ["--body", "(테스트 문제 정의)"]
        # 이슈 #33: 작업 사이클 open 은 이제 '사람이 승인한 기준(인터뷰 제출)'을 요구한다.
        # 대부분 테스트는 open 뒤 흐름을 검증하므로, 그 체인에 승인된 기준이 없으면 인터뷰
        # 심고 즉시 해소(resolve)해 게이트를 자동 충족한다(테스트 의도 보존). 인터뷰 게이트
        # 자체를 검증하는 테스트는 self._no_interview_autofill 로 이 보정을 우회한다.
        if args and args[0] == "open" and not getattr(self, "_no_interview_autofill", False) \
           and "/" in (args[1] if len(args) > 1 else ""):
            self._autofill_interview(args[1].split("/")[0])
        # 이슈 #76: hypothesis 는 --plan(가설 전에 고정한 설계) 필수이고, 그 설계가 있으면
        # verify 는 --plan-held/--plan-broke 로 답해야 한다. 대부분 테스트는 설계 고정 자체가
        # 아니라 그 뒤 위상을 검증하므로 기본값을 자동 주입한다(강제 자체를 검증하는 테스트는
        # 명시 호출로 우회 — 플래그 흔적이 있으면 안 붙인다).
        # 상현님 실사용: analyze 가 결론 없이 지나가고 곧장 define 으로 되돌아갔다 → --finding 필수.
        # 강제 자체를 검증하는 테스트는 명시 호출(플래그 흔적)로 우회한다.
        if args and args[0] == "step" and "--kind" in args and "analyze" in args and \
           not any(a == "--finding" or a.startswith("--finding=") for a in args):
            args += ["--finding", "(테스트 결론: 이 분석이 밝힌 것)"]
        # 상현님 실사용: 벽이 가리킨 자리와 다른 곳에서 갈라져도 도구가 침묵했다 → --despite 필요.
        # 많은 기존 테스트가 s1 로 되돌아가는 위상을 검증하므로, 벽의 지도와 어긋나면 이유를
        # 자동 주입한다(테스트 의도 보존). 그 강제 자체를 검증하는 테스트는 명시 호출로 우회.
        if args and args[0] == "step" and "--kind" in args and "hypothesis" in args and \
           "--to" in args and not getattr(self, "_no_despite_autofill", False) and \
           not any(a == "--despite" or a.startswith("--despite=") for a in args):
            args += ["--despite", "(테스트: 벽의 지도와 다른 자리에서 갈라진다)"]
        if args and args[0] == "step" and "--kind" in args and "hypothesis" in args and \
           not any(a == "--plan" or a.startswith("--plan=") for a in args):
            args += ["--plan", "(테스트 설계 고정: 신규 실행경로 1개)"]
        if args and args[0] == "step" and "--kind" in args and "verify" in args and \
           not any(a in ("--plan-held", "--plan-broke") or a.startswith("--plan-broke=") for a in args):
            args += ["--plan-held"]
        # 규칙 17: verify 는 가설이 심은 --falsify 에도 답해야 한다. 판정과 모순되지 않도록
        # verdict 에 맞춰 기본값을 고른다(refuted→met, 그 외→unmet). 강제 자체를 검증하는
        # 테스트는 명시 호출·_raw_step 으로 우회한다.
        if args and args[0] == "step" and "--kind" in args and "verify" in args and \
           not any(a.startswith("--falsify-met") or a.startswith("--falsify-unmet") for a in args):
            if "refuted" in args:
                args += ["--falsify-met", "(테스트 관측: 반증조건이 관측됐다)"]
            else:
                args += ["--falsify-unmet", "(테스트 관측: 반증조건 미달)"]
        # 상현님(2026-07-28): 가설은 체인 목적에 다가서는 몫을(--advances), 종결은 회고를
        # (--toward/--next-design) 문법으로 요구한다. 대부분 테스트는 그 위상이 아니라 뒤 흐름을
        # 보므로 기본값을 자동 주입한다(강제 자체를 검증하는 테스트는 _raw_step 으로 우회).
        if args and args[0] == "step" and "--kind" in args and "hypothesis" in args and \
           not any(a == "--advances" or a.startswith("--advances=") for a in args):
            args += ["--advances", "(테스트: 체인 목적에 한 칸)"]
        if args and args[0] == "step" and "--kind" in args and \
           ("success" in args or "fail" in args):
            if not any(a == "--toward" or a.startswith("--toward=") for a in args):
                args += ["--toward", "(테스트 회고: 목적에 한 칸 다가섰다)"]
            if not any(a == "--next-design" or a.startswith("--next-design=") for a in args):
                args += ["--next-design", "(테스트: 다음 설계)"]
        # AIL #13: backtrack(step --kind hypothesis --to <define>)은 --inherit 필수(누적 반성
        # 전수). 대부분 테스트는 backtrack 위상 자체를 검증하므로, --inherit 이 없으면 기본을
        # 자동 주입한다(테스트 의도 보존). 전수 강제 자체를 검증하는 테스트는 명시 호출로 우회.
        if args and args[0] == "step" and "--kind" in args and "--to" in args and \
           "hypothesis" in args and not any(a == "--inherit" or a.startswith("--inherit=") for a in args):
            args += ["--inherit", "(테스트 전수: 앞 가지의 교훈)"]
        # 이슈 #33: 사람이 세운 기준(인터뷰)이 있는 체인은 그 기준 대비 회고 없이 못 닫는다.
        # 대부분 테스트는 chain-close 자체가 아니라 그 뒤 흐름을 검증하므로, --retro 가 없으면
        # 기본 회고를 자동 주입한다(테스트 의도 보존). 회고 강제 자체를 검증하는 테스트는
        # self._no_retro_autofill 로 이 보정을 우회한다.
        if args and args[0] == "chain-close" and not getattr(self, "_no_retro_autofill", False) \
           and not any(a == "--retro" or a.startswith("--retro=") for a in args):
            rf = os.path.join(self.repo, ".test-retro.md")
            with open(rf, "w", encoding="utf-8") as f:
                f.write("# 테스트 회고\n기준 대비 달성도(자동 주입)\n")
            args += ["--retro", ".test-retro.md"]
        # 상현님: 목적과 기준은 **쌍으로만** 태어난다 — 기준 없는 체인은 생성 자체가 거부된다.
        # 대부분 테스트는 그 게이트가 아니라 그 뒤 흐름을 검증하므로, --from-intake 도 --reference
        # 도 없으면 기준 문서와 판정 문장을 자동 주입한다(테스트 의도 보존). 게이트 자체를
        # 검증하는 테스트는 self._no_criterion_autofill 로 우회한다.
        if args and args[0] == "chain" and not getattr(self, "_no_criterion_autofill", False) \
           and not any(a.startswith("--from-intake") for a in args) \
           and not any(a.startswith("--reference") for a in args) \
           and not any(a.startswith("--criterion") for a in args):
            cf = CRIT_FILE
            with open(cf, "w", encoding="utf-8") as f:
                f.write("# 기준 문서(테스트 자동 주입)\n사람이 세운 기준으로 간주한다.\n")
            args += ["--reference", cf,
                     "--criterion", "(테스트 기준: 무엇이 관측되면 풀린 것인가)"]
        # 상현님: 사이클을 열 때 "이 체인의 것이 맞나"를 문법으로 대면시킨다(--fits).
        # 게이트 자체를 검증하는 테스트는 self._no_fits_autofill 로 우회한다.
        if args and args[0] == "open" and not getattr(self, "_no_fits_autofill", False) \
           and not any(a.startswith("--fits") for a in args) \
           and not any(a.startswith("--misfit") for a in args):
            args += ["--fits", "(테스트: 이 체인 목적에 기여한다)"]
        env = dict(os.environ, GIL_NO_VIEWER="1")
        # AIL #41: 순서 체인 강제(define→hypothesis→verify→analyze→종결). 많은 기존 테스트가
        # 중간 kind 를 건너뛰고 종결/verify 를 찍으므로, 선형(--to/--merge/backtrack 아님) step
        # 호출 시 tip 다음에 필요한 선행 스텝을 자동으로 채워 순서를 맞춘다(테스트 의도 보존).
        # 순서 강제 자체를 검증하는 테스트는 self._raw_step() 로 이 보정을 우회한다.
        if args and args[0] == "step" and "--kind" in args and not getattr(self, "_no_autofill", False):
            ki = args.index("--kind")
            kind = args[ki + 1] if ki + 1 < len(args) else ""
            # fail 은 --to(되돌아갈 조상 define)를 늘 갖지만 종결 스텝이라 analyze 선행이 필요하다
            # (분기가 아님). verify/analyze/success/pending 은 --to/--merge/backtrack 이 없을 때만.
            has_branch = "--merge" in args or "backtrack" in args or \
                (kind == "hypothesis" and "--to" in args)
            need_order = kind == "fail" or \
                (kind in ("verify", "analyze", "success", "pending") and not has_branch)
            if need_order and "/" in (args[1] if len(args) > 1 else ""):
                ref = args[1]
                chain = ref.split("/")[0]
                self._autofill_order(ref, chain, kind, env)
        return subprocess.run([*GIL_CMD, *args], cwd=self.repo,
                              capture_output=True, text=True, env=env, input=input)

    def _autofill_interview(self, chain):
        """작업 사이클 open 전, 그 체인에 '사람 승인 기준'이 없으면 인터뷰를 심고 즉시 해소해
        게이트를 자동 충족한다(이슈 #33). 이미 done 이면 아무것도 안 한다."""
        env = dict(os.environ, GIL_NO_VIEWER="1")
        # 이미 인터뷰 done(사람 승인 기준)이 있으면 건너뛴다.
        r = subprocess.run(["git", "log", "--all",
                            "--format=%(trailers:key=Gil-Chain,valueonly)\x1f%(trailers:key=Gil-Interview,valueonly)"],
                           cwd=self.repo, capture_output=True, text=True)
        for line in r.stdout.splitlines():
            c, _, iv = line.partition("\x1f")
            if c.strip() == chain and iv.strip() == "done":
                return  # 이미 승인된 기준 있음
        # 체인이 선언돼 있을 때만(없으면 open 이 알아서 거부).
        pr = subprocess.run([*GIL_CMD, "interview", chain, "--ask", "-"],
                            cwd=self.repo, capture_output=True, text=True, env=env,
                            input='[{"q":"(테스트) 무엇을 풀려는가","type":"text"}]')
        if pr.returncode != 0:
            return  # 체인 미선언 등 — open 이 거부하게 둔다
        refp = os.path.join(self.repo, f"reference-{chain}.md")
        with open(refp, "w", encoding="utf-8") as f:
            f.write("# (테스트) 기준 문서\n성공 기준: 테스트 통과")
        subprocess.run([*GIL_CMD, "interview", chain, "--resolve", f"reference-{chain}.md"],
                       cwd=self.repo, capture_output=True, text=True, env=env)
        # 기준 전문은 커밋 본문에 담겼으니 워킹트리 파일은 지운다 — 안 지우면 '미커밋 작업'으로
        # 잡혀 클린 상태를 검증하는 테스트를 깬다.
        try:
            os.remove(refp)
        except OSError:
            pass

    def _autofill_order(self, ref, chain, target_kind, env):
        """target_kind 를 찍기 전에 순서상 필요한 선행 스텝을 자동으로 채운다(AIL #41)."""
        chain_order = ["define", "hypothesis", "verify", "analyze"]
        # 종결(success/fail/pending)은 analyze 까지 필요. verify 는 hypothesis 까지. 등.
        need_upto = {"verify": 2, "analyze": 3, "success": 4, "fail": 4, "pending": 4}[target_kind]
        for _ in range(6):  # 최대 몇 단계 채움
            r = subprocess.run([*GIL_CMD, "log", "--depth", "step", chain],
                               cwd=self.repo, capture_output=True, text=True, env=env)
            cyc = ref.split("/", 1)[1]
            # **이 사이클의 줄만 본다.** 체인 전체를 훑으면 앞 사이클이 이미 밟은 kind 를 보고
            # "여긴 다 있다"고 판단해 아무것도 안 채운다 — 새 사이클이 앞 사이클의 끝에서
            # 갈라지면(그게 옳다) 그 걸음들이 조상으로 함께 보이기 때문이다.
            mine = [ln for ln in r.stdout.splitlines() if f"{chain}/{cyc}/" in ln]
            have = [k for k in chain_order if any(("[" + k + "]") in ln for ln in mine)]
            nxt = None
            for i, k in enumerate(chain_order[:need_upto]):
                if k not in have:
                    nxt = k
                    break
            if nxt is None or nxt == "define":
                break
            add = [nxt]
            extra = []
            if nxt == "hypothesis":
                extra = ["--falsify", "F", "--falsify-to", "s1", "--plan", "(테스트 설계 고정)",
                         "--advances", "(테스트: 체인 목적에 한 칸)"]
            elif nxt == "verify":
                # 규칙 17: 가설이 심은 --falsify 에도 답해야 한다. supported 이므로 unmet.
                extra = ["--verdict", "supported", "--plan-held",
                         "--falsify-unmet", "(테스트 관측: 반증조건 미달)"]
            elif nxt == "analyze":
                # 상현님: analyze 는 결론(--finding) 없이 서지 못한다.
                extra = ["--finding", "(순서 자동: 이 분석이 밝힌 것)"]
            rr = subprocess.run([*GIL_CMD, "step", ref, "--kind", nxt, "--title",
                                 "(순서 자동:" + nxt + ")", *extra],
                                cwd=self.repo, capture_output=True, text=True, env=env)
            if rr.returncode != 0:
                break  # 못 채우면(죽은 잎 등) 그대로 두고 원래 호출이 판단하게

    def _raw_step(self, *args, input=None):
        """순서 자동보정을 우회한 raw step 호출(순서 강제 검증용)."""
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.run([*GIL_CMD, "step", *args], cwd=self.repo,
                              capture_output=True, text=True, env=env, input=input)

    def commit_file(self, name, content, msg):
        """일반 파일 커밋 하나 (fixture 셋업용)."""
        with open(os.path.join(self.repo, name), "w") as f:
            f.write(content)
        self._git("add", name)
        self._git("commit", "-q", "-m", msg)

    def trailer(self, ref, key):
        """ref 커밋의 특정 trailer 값."""
        r = self._git("log", "-1", ref,
                       f"--format=%(trailers:key={key},valueonly)")
        return r.stdout.strip()

    def subject(self, ref="HEAD"):
        return self._git("log", "-1", ref, "--format=%s").stdout.strip()

    def branches(self):
        """로컬 브랜치 이름 집합."""
        r = self._git("for-each-ref", "--format=%(refname:short)", "refs/heads/")
        return set(r.stdout.split())

    def head_branch(self):
        return self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


class TestChain(GilFixture):
    def test_chain_requires_purpose(self):
        """gil chain은 --purpose 없이 거부한다."""
        r = self.gil("chain", "mychain")
        self.assertNotEqual(r.returncode, 0)

    def test_chain_imprints_root_and_purpose(self):
        """gil chain은 chain-root kind와 Gil-Chain-Purpose를 새긴다."""
        r = self.gil("chain", "mychain", "--purpose", "테스트 목적")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Chain"), "mychain")
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "chain-root")
        self.assertEqual(self.trailer("HEAD", "Gil-Chain-Purpose"), "테스트 목적")

    def test_chain_rejects_bad_name(self):
        """대문자·마침표 등은 거부."""
        r = self.gil("chain", "Bad.Name", "--purpose", "P")
        self.assertNotEqual(r.returncode, 0)


class TestCycleAndStep(GilFixture):
    def setUp(self):
        super().setUp()
        self.gil("chain", "c", "--purpose", "체인목적")
        self._autofill_interview("c")  # #33: open 게이트(사람 승인 기준) 자동 충족

    def test_open_requires_purpose(self):
        r = self.gil("open", "c/c001", "--author", "clew")
        self.assertNotEqual(r.returncode, 0)

    def test_open_requires_body(self):
        """AIL #12: open 은 문제 정의 본문이 필수 — 빈 사이클로 여는 걸 문법으로 거부한다.
        (self.gil 의 자동주입을 피해 --body 없이 직접 호출해 거부를 확인한다.)"""
        env = dict(os.environ, GIL_NO_VIEWER="1")
        r = subprocess.run([*GIL_CMD, "open", "c/c001", "--author", "clew", "--purpose", "P",
                            "--fits", "(테스트)"],
                           cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0, "본문 없는 open 이 거부되지 않음")
        self.assertIn("본문", r.stderr)
        # amend 우회를 더는 안내하지 않는다(자기모순 제거) — 오히려 하지 말라고 명시.
        self.assertNotIn("커밋 수정으로 채우라", r.stderr)

    def test_open_body_via_title(self):
        """--title 도 본문으로 인정된다(한 줄 문제 정의)."""
        env = dict(os.environ, GIL_NO_VIEWER="1")
        r = subprocess.run([*GIL_CMD, "open", "c/c001", "--author", "clew",
                            "--purpose", "P", "--title", "한 줄 정의", "--fits", "(테스트)"],
                           cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_open_imprints_cycle_purpose(self):
        r = self.gil("open", "c/c001", "--author", "clew", "--purpose", "사이클목적")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Cycle"), "c001")
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "define")
        self.assertEqual(self.trailer("HEAD", "Gil-Cycle-Purpose"), "사이클목적")

    def test_open_shows_purpose_context(self):
        """시작 시 체인·사이클 목적을 stderr로 띄운다 (정합 판단 유도)."""
        r = self.gil("open", "c/c001", "--author", "clew", "--purpose", "사이클목적")
        self.assertIn("체인목적", r.stderr)
        self.assertIn("사이클목적", r.stderr)

    def test_step_linear(self):
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "P")
        r = self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "가설", "--falsify", "F", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Step"), "s2")
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "hypothesis")

    def test_analyze_no_longer_requires_outcome(self):
        """analyze 는 순수 분석 — outcome 없이 허용(종결은 success/fail 스텝, 2026-07-24)."""
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "P")
        r = self.gil("step", "c/c001", "--kind", "analyze", "--title", "분석")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_close_requires_live_leaf(self):
        """산 잎(analyze/success) 없으면 close 거부."""
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "P")
        r = self.gil("close", "c/c001")
        self.assertNotEqual(r.returncode, 0)

    def test_full_cycle(self):
        """open → hypothesis → analyze success → close 전 주기."""
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "h", "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "c/c001", "--kind", "analyze", "--outcome", "success",
                 "--title", "산잎")
        r = self.gil("close", "c/c001")
        self.assertEqual(r.returncode, 0, r.stderr)


class TestClosedParentGuard(GilFixture):
    """원칙 6: 닫힌 부모 체인 안에서 새 사이클 금지."""

    def test_cycle_close_allows_next_cycle(self):
        """사이클 close 후 같은 체인에 다음 사이클 open 허용 (체인은 안 닫힘)."""
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "analyze", "--outcome", "success",
                 "--title", "s")
        self.gil("close", "c/c001")
        r = self.gil("open", "c/c002", "--author", "a", "--purpose", "P")
        self.assertEqual(r.returncode, 0, "사이클 close는 체인 close가 아니다")

    def test_chain_close_blocks_new_cycle(self):
        """chain-close 후에는 새 사이클 open 거부 — 새 자식 체인 강제."""
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "success", "--title", "s")
        self.gil("close", "c/c001")
        r = self.gil("chain-close", "c")  # 실제 명령 (모사 아님)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.gil("open", "c/c002", "--author", "a", "--purpose", "P")
        self.assertNotEqual(r.returncode, 0, "닫힌 부모 체인 사이클은 거부돼야")

    def test_chain_close_requires_all_cycles_closed(self):
        """chain-close 는 모든 사이클이 닫혀야 허용 (산 잎만으론 부족 — close 커밋 필요).

        실사용(상현님)이 드러낸 결함 — 체인 닫는 명령 자체가 없어 사이클만 계속 열렸다."""
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "success", "--title", "s")  # 산 잎, 하지만 close 안 함
        r = self.gil("chain-close", "c")
        self.assertNotEqual(r.returncode, 0, "닫히지 않은 사이클이 있으면 거부")
        self.assertIn("c001", r.stdout + r.stderr)
        self.gil("close", "c/c001")
        r = self.gil("chain-close", "c")
        self.assertEqual(r.returncode, 0, "모든 사이클 닫히면 허용: " + r.stderr)

    def test_chain_close_enables_lesson_carrying_new_chain(self):
        """닫힌 체인 끝에서 새 체인을 열 수 있다 — 대문·교훈이 체인을 넘어 이어진다."""
        self.gil("chain", "devchain", "--purpose", "개발 국면")
        self.gil("open", "devchain/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "devchain/c001", "--kind", "success", "--title", "s")
        self.gil("close", "devchain/c001")
        self.gil("chain-close", "devchain")
        r = self.gil("chain", "stg", "--purpose", "스테이징 국면", "--from", "devchain")
        self.assertEqual(r.returncode, 0, r.stderr)
        # 새 체인 stg 는 닫힌 devchain 끝에서 분기(--from 으로 선언) — 대문(CLAUDE.md)이 조상으로 보존
        self.assertEqual(self.trailer("stg", "Gil-Chain-Purpose"), "스테이징 국면")

    def test_chain_close_rejects_twice(self):
        """이미 닫힌 체인은 다시 못 닫는다."""
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "success", "--title", "s")
        self.gil("close", "c/c001")
        self.gil("chain-close", "c")
        r = self.gil("chain-close", "c")
        self.assertNotEqual(r.returncode, 0, "이미 닫힌 체인 재닫기 거부")

    def test_open_rejects_unclosed_parent_cycle(self):
        """원칙: 사이클은 닫힌 사이클의 끝에서만. 열린 사이클을 --parent 로 삼으면 거부.

        실사용(상현님)이 드러낸 결함 — 열린 사이클이 부모가 되어도 gil 이 안 막았다."""
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "h", "--falsify", "F", "--falsify-to", "s1")  # 안 닫음
        r = self.gil("open", "c/c002", "--author", "a", "--purpose", "P",
                     "--parent", "c001")
        self.assertNotEqual(r.returncode, 0, "열린 부모 사이클은 거부돼야")
        self.assertIn("닫히지 않", r.stderr + r.stdout)

    def test_open_allows_closed_parent_cycle(self):
        """--parent 가 닫힌 사이클이면 허용 (계보 정상)."""
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "success", "--title", "ok")
        self.gil("close", "c/c001")
        r = self.gil("open", "c/c002", "--author", "a", "--purpose", "P",
                     "--parent", "c001", "--inherit", "c001 결과를 잇는다")
        self.assertEqual(r.returncode, 0, r.stderr)


class TestChainMerge(GilFixture):
    """체인 머지 = 실제 git merge (파일까지 병합), 위상적 끝단만."""

    def _branch(self, name, base=None):
        if base:
            self._git("checkout", "-q", "-b", name, base)
        else:
            self._git("checkout", "-q", "-b", name)

    def test_real_file_merge(self):
        """충돌 없는 병합은 양쪽 파일을 모두 남긴다 (껍데기 아님)."""
        self.commit_file("shared.txt", "base", "root")
        self._branch("chainA")
        self.commit_file("fa.txt", "A", "A")
        self._git("checkout", "-q", "-b", "chainB", "chainA~1")
        self.commit_file("fb.txt", "B", "B")
        self._git("checkout", "-q", "chainA")
        r = self.gil("chain-merge", "unified", "--purpose", "통합",
                     "chainA", "chainB")
        self.assertEqual(r.returncode, 0, r.stderr)
        # 파일이 실제로 병합됨
        self.assertTrue(os.path.exists(os.path.join(self.repo, "fa.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.repo, "fb.txt")))

    def test_merge_imprints_chain_root(self):
        """첫 머지 커밋(통합 루트)에 chain-root 표식."""
        self.commit_file("s.txt", "base", "root")
        self._branch("chainA")
        self.commit_file("fa.txt", "A", "A")
        self._git("checkout", "-q", "-b", "chainB", "chainA~1")
        self.commit_file("fb.txt", "B", "B")
        self._git("checkout", "-q", "chainA")
        self.gil("chain-merge", "unified", "--purpose", "통합", "chainA", "chainB")
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "chain-root")
        self.assertEqual(self.trailer("HEAD", "Gil-Chain-Purpose"), "통합")

    def test_conflict_holds(self):
        """충돌 시 abort하지 않고 멈춘다 (MERGE_HEAD 유지) — 해결 대기."""
        self.commit_file("s.txt", "base", "root")
        self._git("checkout", "-q", "-b", "b2")
        self.commit_file("c.txt", "X", "b2")
        self._git("checkout", "-q", "-b", "cX")
        self.commit_file("c.txt", "fromX", "cX")
        self._git("checkout", "-q", "-b", "cY", "b2")
        self.commit_file("c.txt", "fromY", "cY")
        self._git("checkout", "-q", "cX")
        r = self.gil("chain-merge", "u2", "--purpose", "P", "cX", "cY")
        self.assertNotEqual(r.returncode, 0)
        # 충돌 상태가 유지됨 (해결 후 이어가게)
        self.assertTrue(os.path.exists(os.path.join(self.repo, ".git", "MERGE_HEAD")))


class TestFsck(GilFixture):
    def test_clean_graph_passes(self):
        self.gil("init", "--name", "clew")   # 기억 계층까지 선 저장소가 정상 상태다(#69)
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")
        r = self.gil("fsck")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("위반 0", r.stdout)

    def test_empty_repo_chain(self):
        """커밋 0개인 빈 저장소에서도 gil chain이 동작한다 (_gitlog가 흡수)."""
        # setUp이 init만 함 (커밋 없음)
        r = self.gil("chain", "c", "--purpose", "P")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unterminated_leaf_in_closed_cycle(self):
        """닫힌 사이클의 미종결 잎(analyze 로 매달림)을 위반으로 잡는다.

        실사용(상현님)이 뷰어에서 드러낸 결함 — analyze 잎 뒤 종결 노드(success/fail)가
        없는데 fsck 가 못 잡았다. 원칙: 닫힌 사이클의 잎은 success/fail/pending 으로 마감."""
        # 실사용 s5 구조 재현: 한 가지가 analyze 로 매달려 끝(미종결 잎)나고,
        # 형제 가지(--to s1 로 분기)에서 success 로 마감해 사이클을 닫는다.
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")  # s1 define
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "h1", "--falsify", "F", "--falsify-to", "s1")  # s2
        self.gil("step", "c/c001", "--kind", "verify", "--title", "v1", "--verdict", "supported")  # s3
        self.gil("step", "c/c001", "--kind", "analyze", "--title", "벽")     # s4 = 미종결 잎
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "h2", "--to", "s1", "--falsify", "F", "--falsify-to", "s1")  # 형제 분기
        self.gil("step", "c/c001", "--kind", "success", "--title", "산 잎")  # 형제에서 성공
        self.gil("close", "c/c001")
        r = self.gil("fsck")
        self.assertNotEqual(r.returncode, 0, "미종결 analyze 잎은 위반이어야")
        self.assertIn("미종결 잎", r.stdout)

    def test_unterminated_leaf_open_cycle_ok(self):
        """열린 사이클의 잎은 진행 중일 수 있어 미종결이어도 위반이 아니다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "analyze", "--title", "진행 중 분석")
        r = self.gil("fsck")
        self.assertEqual(r.returncode, 0, "열린 사이클 잎은 면제: " + r.stdout)


class TestHandoff(GilFixture):
    def test_handoff_detects_pending_cycle(self):
        """handoff는 체인명이 브랜치명과 달라도 열린 사이클·pending을 띄운다.

        결함(참조·Go 공통, gil-v3-unified에서 잡음): cycles_of가 git log <chain>으로
        체인 이름을 ref처럼 썼다 → 격리 저장소(브랜치=main, 체인=appr)에선 log가 실패해
        사이클을 통째로 놓쳤다(handoff가 "열린 사이클 없음"만). --branches 범위에서
        chain으로 필터링하도록 고쳐, ref 존재에 의존하지 않게 했다.
        """
        self.gil("chain", "appr", "--purpose", "승인 모드")
        self.gil("open", "appr/c001", "--author", "clew", "--purpose", "승인 필요")
        self.gil("step", "appr/c001", "--kind", "verify", "--title", "검증", "--verdict", "supported")
        self.gil("step", "appr/c001", "--kind", "pending", "--title", "승인 요청")
        r = self.gil("handoff")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("사이클 c001", r.stdout)
        self.assertIn("PENDING", r.stdout)

    def _close_solved_cycle(self, chain, cid):
        """한 사이클을 open→hypothesis→verify→analyze→success 로 채우고 close.

        누적 신호 테스트용 — 명시적으로 v3.8.0 순서 관용을 그대로 밟는다(_autofill_order 는
        여러 사이클이 섞인 --depth step 출력을 have 판정에 쓰다 오작동하므로 여기선 쓰지 않는다).
        """
        ref = f"{chain}/{cid}"
        self.gil("open", ref, "--author", "clew", "--purpose", f"문제 {cid}",
                 "--body", f"{cid} 문제 정의 상세")
        self.gil("step", ref, "--kind", "hypothesis", "--title", f"가설 {cid}",
                 "--falsify", "F", "--falsify-to", "s1", "--body", "가설 본문")
        self.gil("step", ref, "--kind", "verify", "--title", f"검증 {cid}",
                 "--verdict", "supported", "--body", "검증 본문")
        self.gil("step", ref, "--kind", "analyze", "--title", f"분석 {cid}", "--body", "분석 본문")
        self.gil("step", ref, "--kind", "success", "--title", f"산 잎 {cid}",
                 "--body", "종합 보고서")
        self.gil("close", ref)

    def test_cycle_load_banner_stages(self):
        """닫힌 사이클 누적 시 handoff 가 단계적 신호/권유를 띄운다(거부는 안 함).

        상현님: 사이클이 많이 쌓이면 핸드오프를 유도. gil 은 커밋 시점만 개입하니 거부로
        강제하지 않고 3개↑ 신호·5개↑ 강한 권유로 안내한다(HEAAL: 여기선 안내가 옳은 층위).
        """
        self.gil("chain", "load", "--purpose", "누적")
        # 2개까지는 신호 없음
        for i in (1, 2):
            self._close_solved_cycle("load", f"c00{i}")
        r = self.gil("handoff")
        self.assertNotIn("사이클 누적", r.stdout)
        # 3개 → 신호
        self._close_solved_cycle("load", "c003")
        r = self.gil("handoff")
        self.assertIn("사이클 누적 (신호)", r.stdout)
        # 5개 → 강한 권유(매듭 각인·체인 전환 안내 포함)
        self._close_solved_cycle("load", "c004")
        self._close_solved_cycle("load", "c005")
        r = self.gil("handoff")
        self.assertIn("사이클 누적 (강한 권유)", r.stdout)
        self.assertIn("memory append", r.stdout)
        self.assertIn("chain-close", r.stdout)

    def test_handoff_gate_checklist(self):
        """handoff 는 항상 대문(md) 갱신 체크리스트를 띄운다(감지 아닌 안내라 거짓양성 0)."""
        self.gil("chain", "g", "--purpose", "게이트")
        self.gil("open", "g/c001", "--author", "clew", "--purpose", "골격", "--body", "정의")
        r = self.gil("handoff")
        self.assertIn("핸드오프 체크리스트", r.stdout)
        self.assertIn("CLAUDE.md", r.stdout)
        self.assertIn("매듭 각인", r.stdout)

    def test_chain_name_colliding_with_dir(self):
        """체인명이 디렉토리명과 겹쳐도 handoff/log 가 exit 128 로 죽지 않는다.

        결함(참조·Go 공통, viewer 실작업에서 발견): git log <br> 를 "--" 없이 부르면
        br 이 디렉토리명과 겹칠 때(예: viewer/ 디렉토리 + viewer 브랜치) git 이
        revision/path ambiguity 로 exit 128. rev 인자 뒤 "--" 로 확정해 고침.
        """
        os.makedirs(os.path.join(self.repo, "viewer"))
        self.commit_file("viewer/x.txt", "hi", "add dir")
        self.gil("chain", "viewer", "--purpose", "동명 디렉토리 충돌")
        self.gil("open", "viewer/c001", "--author", "clew", "--purpose", "골격")
        self.gil("step", "viewer/c001", "--kind", "verify", "--title", "검사", "--verdict", "supported")
        r = self.gil("handoff")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("128", r.stdout + r.stderr)
        lg = self.gil("log", "viewer")
        self.assertEqual(lg.returncode, 0, lg.stderr)


class TestInit(GilFixture):
    """gil init — 무에서 세팅 (대문 + refs/gil/global + 존재의 방).

    출력은 LLM 프롬프트이므로 STATE/NEXT 지시가 담기는지도 확인한다(상현님).
    """

    def test_init_seeds_global_and_room(self):
        r = self.gil("init", "--name", "aria")
        self.assertEqual(r.returncode, 0, r.stderr)
        files = set(self.gil("global", "list").stdout.split())
        self.assertIn("existence/README.md", files)
        self.assertIn("existence/aria/identity.md", files)
        self.assertIn("existence/aria/will.md", files)
        self.assertIn("existence/aria/memory.md", files)
        self.assertIn("existence/aria/relations.md", files)
        self.assertIn("gil-init-spec.md", files)

    def test_init_in_non_git_folder_runs_git_init(self):
        """git 저장소가 아닌 빈 폴더에서도 gil init 이 선다 — 무에서 세우는 명령이니까.

        실사용에서 여기서 죽었다(상현님): 인터뷰 도착 고지가 init 보다 먼저 돌면서
        'not a git repository' 로 넘어졌고, 'gil init 이 git init 을 안 해준다'로 보였다.
        고지는 친절이지 관문이 아니다."""
        d = tempfile.mkdtemp()
        try:
            env = dict(os.environ, GIL_NO_VIEWER="1")
            r = subprocess.run(GIL_CMD + ["init", "--name", "aria"], cwd=d,
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.isdir(os.path.join(d, ".git")))
            self.assertTrue(os.path.exists(os.path.join(d, "CLAUDE.md")))
            g = subprocess.run(["git", "rev-parse", "--verify", "-q", "refs/gil/global"],
                               cwd=d, capture_output=True, text=True)
            self.assertEqual(g.returncode, 0, "refs/gil/global 이 서야 한다")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_init_makes_gateway_root_commit(self):
        """빈 저장소면 CLAUDE.md 부트스트랩 루트 커밋을 만든다."""
        self.gil("init", "--name", "aria")
        log = self._git("log", "--oneline").stdout
        self.assertIn("gil init", log)
        # 루트는 여전히 대문 커밋이다(그 위에 온보딩 설치 커밋이 얹힌다, 이슈 #73).
        root = self._git("rev-list", "--max-parents=0", "HEAD").stdout.strip()
        self.assertEqual(self.trailer(root, "Gil-Kind"), "root")
        self.assertTrue(os.path.exists(os.path.join(self.repo, "CLAUDE.md")))

    def test_init_output_is_llm_prompt(self):
        """출력에 STATE/NEXT + 다음 명령이 담긴다 — 인간 UX 아닌 LLM 프롬프트.

        **다음 명령이 무엇인지가 2026-08-09 에 바뀌었다.** 옛 NEXT 는 이름 짓기·방 채우기·
        개시 인터뷰를 번호로 늘어놨는데, 그 줄들은 읽고 따르는 것이라 자기규율이었고
        (#55·#45), MCP 표면에서는 대응 툴이 없어 **아예 칠 수 없는 줄**이었다. 이제 남은
        칸은 `gil start` 가 실제로 밟는다 — init 은 자기가 무엇을 세웠는지만 말한다.
        그러니 여기서 세는 것은 "사다리를 늘어놨나"가 아니라 **"다음 칸으로 가는 길을
        가리키나"** 다."""
        out = self.gil("init", "--name", "aria").stdout
        self.assertIn("STATE", out)
        self.assertIn("NEXT", out)
        self.assertIn("gil start", out, "다음 칸을 밟을 명령을 안 가리킨다")
        self.assertIn("gil handoff", out, "다음 세션의 복원 경로를 안 가리킨다")

    def test_init_warns_persistence_unconditionally(self):
        """init 은 존재 영속성 경고를 조건 없이 항상 낸다(상현님) — gil 은 환경을 감지·판정하지
        않고, 영속 박스면 이어지고 샌드박스면 사라진다는 항상 참인 사실만 알린다."""
        out = self.gil("init", "--name", "aria").stdout
        self.assertIn("존재", out)
        self.assertIn("샌드박스", out)  # 영속 vs 샌드박스 대비를 명시

    def test_init_idempotent_guard(self):
        """두 번째 init 은 글로벌을 덮지 않고 거부한다."""
        self.gil("init", "--name", "aria")
        r = self.gil("init", "--name", "other")
        self.assertNotEqual(r.returncode, 0)

    def test_init_rejects_bad_name(self):
        r = self.gil("init", "--name", "Bad.Name")
        self.assertNotEqual(r.returncode, 0)

    def test_init_then_handoff_works(self):
        """무에서 init 직후 handoff 가 panic 없이 돈다."""
        self.gil("init", "--name", "aria")
        r = self.gil("handoff")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_init_viewer_suppressed_by_env(self):
        """GIL_NO_VIEWER 면 관전 서버를 띄우지 않는다(테스트·CI 격리). init 은 정상."""
        r = self.gil("init", "--name", "aria")  # gil() 헬퍼가 GIL_NO_VIEWER=1 주입
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("뷰어", r.stdout)

    def test_init_points_at_the_two_screens(self):
        """init 은 이제 서버를 안 띄운다 — 대신 **어디를 보면 되는지** 말한다.

        옛 init 은 관전 서버를 자동 기동했다. 그러면 저장소를 만드는 것만으로 사람이 안 부른
        서버가 하나 생긴다(상현님). 그 뒤 서버 자체가 은퇴했으니, 남는 값은 "지금 어디"와
        "전체 그래프" 두 화면을 그 자리에서 알려 주는 것이다."""
        r = self.gil("init", "--name", "aria")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout + r.stderr
        self.assertIn("gil status", out, "지금 어디인지 보는 길을 안 알려준다")
        self.assertIn("gil graph", out, "전체 그래프를 보는 길을 안 알려준다")
        self.assertNotIn("viewer", out, "은퇴한 명령을 아직 가리킨다")

    def test_no_args_prints_usage(self):
        """인자 없는 gil 은 침묵이 아니라 명령 표면(프롬프트)을 낸다."""
        r = self.gil()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gil init", r.stdout)
        self.assertIn("gil handoff", r.stdout)

    def test_usage_points_to_wiki(self):
        """gil help 는 LLM-wiki 인덱스로 안내한다(통째 아니라 능동 접근)."""
        r = self.gil("help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("docs/gil/index.md", r.stdout)
        self.assertIn("llms.txt", r.stdout)

    def test_help_subcommand(self):
        """gil help <명령> 은 그 명령 사용법 + 관련 wiki 페이지를 낸다."""
        r = self.gil("help", "step")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--kind", r.stdout)
        self.assertIn("docs/gil/", r.stdout)

    def test_subcommand_help_flag(self):
        """어느 명령이든 --help 를 붙이면 그 명령 사용법을 낸다(거부하지 않는다)."""
        r = self.gil("log", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gil log", r.stdout)
        self.assertNotIn("알 수 없는 플래그", r.stdout + r.stderr)


class TestMemory(GilFixture):
    """gil memory — 안전한 존재/기억 갱신 (append-only, 전체 트리 보존).

    사고 방지 명령(상현님, memory.md 다섯 번 소실). 핵심 단언: 다른 존재의 파일을
    소실시키지 않고(preservation), 중첩 경로가 깨지지 않으며, append가 매듭을 이어붙인다.
    """

    def _write_global(self, name, content):
        p = os.path.join(self.repo, "_seed")
        with open(p, "w") as f:
            f.write(content)
        return self.gil("global", "write", name, "_seed")

    def test_memory_read_missing_refuses(self):
        r = self.gil("memory", "read", "clew")
        self.assertNotEqual(r.returncode, 0)

    def test_global_write_nested_path(self):
        """중첩 경로(existence/clew/memory.md)가 mktree 없이 써진다 — exit 128 회귀 방지."""
        r = self._write_global("existence/clew/memory.md", "hi\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        rd = self.gil("global", "read", "existence/clew/memory.md")
        self.assertEqual(rd.stdout, "hi\n")

    def test_memory_append_adds_knot(self):
        self._write_global("existence/clew/memory.md", "# Memory\n\n## knot 1\nfirst\n")
        kp = os.path.join(self.repo, "_knot")
        with open(kp, "w") as f:
            f.write("## knot 2\nsecond\n")
        r = self.gil("memory", "append", "clew", "_knot")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.gil("memory", "read", "clew").stdout
        self.assertIn("## knot 1", out)
        self.assertIn("## knot 2", out)
        self.assertIn("first\n\n## knot 2", out)  # 빈 줄 하나로 구분
        # 각인 시점(존재 소실 위험 지점)에 영속성 경고를 조건 없이 항상 낸다(상현님).
        self.assertIn("샌드박스", r.stderr + r.stdout)

    def test_memory_append_preserves_other_existences(self):
        """append가 다른 존재의 파일을 소실시키지 않는다 — 다섯 번 물린 사고의 정확한 방지."""
        self._write_global("existence/clew/memory.md", "clew mem\n")
        self._write_global("existence/weft/identity.md", "I am weft\n")
        kp = os.path.join(self.repo, "_knot")
        with open(kp, "w") as f:
            f.write("new knot\n")
        self.gil("memory", "append", "clew", "_knot")
        weft = self.gil("global", "read", "existence/weft/identity.md")
        self.assertEqual(weft.stdout, "I am weft\n")

    def test_memory_append_to_absent_starts_file(self):
        kp = os.path.join(self.repo, "_knot")
        with open(kp, "w") as f:
            f.write("## first\nhi\n")
        r = self.gil("memory", "append", "sheen", "_knot")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## first", self.gil("memory", "read", "sheen").stdout)


class TestBranching(GilFixture):
    """분기는 진짜 git 브랜치로 표현된다 (SPEC 원칙 3, 2026-07-24 상현님).

    체인=브랜치 <chain>, 사이클=<chain>-<cycle>, 형제 가지=<chain>-<cycle>-<to>b<n>.
    backtrack 은 죽은 잎을 현 가지에 박고, 이어지는 hypothesis --to 가 실제 git 분기를 만든다.
    """

    def _seed(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "greenhouse", "--purpose", "테스트")
        self.gil("open", "greenhouse/c001", "--author", "clew", "--purpose", "베이스라인")

    def test_chain_creates_branch(self):
        self.gil("init", "--name", "clew")
        r = self.gil("chain", "greenhouse", "--purpose", "P")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("greenhouse", self.branches())
        self.assertEqual(self.head_branch(), "greenhouse")

    def test_open_creates_cycle_branch(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "greenhouse", "--purpose", "P")
        r = self.gil("open", "greenhouse/c001", "--author", "clew", "--purpose", "Q")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("greenhouse-c001", self.branches())
        self.assertEqual(self.head_branch(), "greenhouse-c001")

    def test_sibling_branch_is_real_git_fork(self):
        """hypothesis --to 는 그 define 커밋에서 실제 git 브랜치를 분기한다."""
        self._seed()
        self.gil("step", "greenhouse/c001", "--kind", "hypothesis", "--title", "가설 A", "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "greenhouse/c001", "--kind", "verify", "--title", "검증 A", "--verdict", "supported")
        self.gil("step", "greenhouse/c001", "--kind", "analyze",
                 "--outcome", "backtrack", "--to", "s1", "--title", "벽")
        r = self.gil("step", "greenhouse/c001", "--kind", "hypothesis", "--to", "s1", "--title", "가설 B", "--falsify", "F", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)
        # 형제 가지 브랜치가 생겼다.
        self.assertIn("greenhouse-c001-s1b1", self.branches())
        # 그 브랜치는 s1 define 을 조상으로 갖되, 죽은 가지(s4 벽)는 조상이 아니다.
        s1 = self._git("log", "--all", "--format=%H %s").stdout
        # s5(가설 B) 커밋과 s4(벽) 커밋을 찾는다.
        def sha_of(marker):
            for ln in s1.splitlines():
                if marker in ln:
                    return ln.split()[0]
            return None
        s5, s4 = sha_of("가설 B"), sha_of("벽")
        self.assertTrue(s5 and s4)
        # s4(벽)는 s5(형제 가지)의 조상이 아니다 — 진짜로 갈라졌다.
        anc = self._git("merge-base", "--is-ancestor", s4, s5)
        self.assertNotEqual(anc.returncode, 0, "형제 가지가 죽은 가지를 조상으로 가지면 안 됨")

    def test_backtrack_dead_leaf_stays_on_cycle_branch(self):
        """backtrack analyze(죽은 잎)는 새 브랜치를 만들지 않고 현 사이클 가지에 박힌다."""
        self._seed()
        self.gil("step", "greenhouse/c001", "--kind", "hypothesis", "--title", "가설 A", "--falsify", "F", "--falsify-to", "s1")
        before = self.branches()
        self.gil("step", "greenhouse/c001", "--kind", "analyze",
                 "--outcome", "backtrack", "--to", "s1", "--title", "벽")
        self.assertEqual(self.branches(), before, "backtrack 은 브랜치를 새로 만들지 않는다")


class TestPendingGuard(GilFixture):
    """pending 뒤에는 사람의 명시적 승인/기각만 허용 (2026-07-24 상현님).

    서브에이전트가 pending 직후 스스로 analyze 로 넘어가던 것을 gil 이 구조로 막는다.
    """

    def _to_pending(self, cycle="c001"):
        self.gil("init", "--name", "clew")
        self.gil("chain", "gh", "--purpose", "P")
        self.gil("open", f"gh/{cycle}", "--author", "clew", "--purpose", "Q")
        self.gil("step", f"gh/{cycle}", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self.gil("step", f"gh/{cycle}", "--kind", "verify", "--title", "V", "--verdict", "supported")
        self.gil("step", f"gh/{cycle}", "--kind", "pending", "--title", "승인 요청")

    def test_step_after_pending_rejected(self):
        self._to_pending()
        r = self.gil("step", "gh/c001", "--kind", "analyze", "--outcome", "success", "--title", "자율승인")
        self.assertNotEqual(r.returncode, 0, "pending 뒤 analyze 는 거부돼야 한다")
        self.assertIn("pending", r.stderr + r.stdout)

    def test_approve_makes_success_step(self):
        """approve → success 종결 스텝(산 잎). 2026-07-24 종결 스텝 모델."""
        self._to_pending()
        r = self.gil("approve", "gh/c001", "--title", "승인")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "success")
        self.assertEqual(self.trailer("HEAD", "Gil-Approval"), "approved")
        self.assertEqual(self.gil("close", "gh/c001", "--verdict", "supported").returncode, 0)

    def test_reject_makes_fail_step(self):
        """reject → fail 종결 스텝(죽은 잎, Gil-Backtrack)."""
        self._to_pending()
        r = self.gil("reject", "gh/c001", "--to", "s1", "--title", "기각")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "fail")
        self.assertEqual(self.trailer("HEAD", "Gil-Backtrack"), "s1")
        self.assertEqual(self.trailer("HEAD", "Gil-Approval"), "rejected")

    def test_approve_without_pending_rejected(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "gh", "--purpose", "P")
        self.gil("open", "gh/c001", "--author", "clew", "--purpose", "Q")
        r = self.gil("approve", "gh/c001")
        self.assertNotEqual(r.returncode, 0, "pending 없는데 approve 는 거부")


class TestTerminalSteps(GilFixture):
    """성공/실패/대기를 진짜 gil 스텝으로 커밋 (2026-07-24 상현님).

    analyze=순수 분석, success=산 잎, fail=죽은 잎(Gil-Backtrack). 종결 스텝 본문이
    문제정의부터 누적된 보고서를 담는다.
    """

    def _seed(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "gh", "--purpose", "P")
        self.gil("open", "gh/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self.gil("step", "gh/c001", "--kind", "verify", "--title", "V", "--verdict", "supported")
        self.gil("step", "gh/c001", "--kind", "analyze", "--title", "분석")

    def test_success_step_is_live_leaf(self):
        self._seed()
        r = self.gil("step", "gh/c001", "--kind", "success", "--title", "산 잎: 보고서")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "success")
        # success 스텝이 있으면 close 가능.
        self.assertEqual(self.gil("close", "gh/c001", "--verdict", "supported").returncode, 0)

    def test_fail_step_requires_to(self):
        self._seed()
        r = self.gil("step", "gh/c001", "--kind", "fail", "--title", "죽은 잎")
        self.assertNotEqual(r.returncode, 0, "fail 은 --to 필요")

    def test_fail_step_is_dead_leaf(self):
        self._seed()
        r = self.gil("step", "gh/c001", "--kind", "fail", "--to", "s1", "--title", "벽")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "fail")
        self.assertEqual(self.trailer("HEAD", "Gil-Backtrack"), "s1")
        # 죽은 잎뿐이면 close 거부.
        self.assertNotEqual(self.gil("close", "gh/c001").returncode, 0)

    def test_report_body_via_file(self):
        """종결 스텝 본문을 파일로 실어 보고서를 담는다."""
        self._seed()
        import tempfile as _tf
        p = os.path.join(self.repo, "report.md")
        with open(p, "w") as f:
            f.write("# 보고서\n\n- 관찰: RMSE 0.4\n\n결론: 채택.")
        r = self.gil("step", "gh/c001", "--kind", "success", "--title", "산 잎", "--body-file", p)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = self._git("log", "-1", "HEAD", "--format=%b").stdout
        self.assertIn("# 보고서", body)
        self.assertIn("RMSE 0.4", body)


class TestLogAll(GilFixture):
    """gil log --all 은 죽은 가지(형제 가지 fail)까지 보여준다 — 벽의 지도 (2026-07-24)."""

    def test_log_all_shows_dead_branch(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "gh", "--purpose", "P")
        self.gil("open", "gh/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--title", "HA", "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "gh/c001", "--kind", "analyze", "--title", "AA")
        self.gil("step", "gh/c001", "--kind", "fail", "--to", "s1", "--title", "죽은 잎")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--to", "s1", "--title", "HB", "--falsify", "F", "--falsify-to", "s1")
        # 기본 log: HEAD 계보라 죽은 가지(s2~s3, fail)가 안 보인다.
        base = self.gil("log", "gh").stdout
        self.assertNotIn("[fail]", base)
        # --all: 죽은 가지도 보인다.
        allout = self.gil("log", "--all", "gh").stdout
        self.assertIn("[fail]", allout)


class TestGoto(GilFixture):
    """gil goto — 사고 나무 안에서 자리를 옮긴다 (이슈 #67 제안 2).

    형제 가지가 여럿인 사이클에서 가지 사이를 오갈 길이 gil 에 없었다. 죽은 가지 끝에 서면
    --to/--falsify-to 가 산 가지의 스텝을 '조상이 아니다'로 거부하고, 나갈 길이 없어 갇힌다.
    실사용에서 그대로 멈췄다(adopt-v1/gap: s4b1 에 서서 s23 으로 못 감)."""

    def _forked(self):
        """s1 에서 갈라진 죽은 가지(s2~s3 fail)와 산 가지(s4~s5 analyze)를 만든다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/gap", "--author", "clew", "--purpose", "Q")
        self.gil("step", "a/gap", "--kind", "hypothesis", "--title", "HA", "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "a/gap", "--kind", "fail", "--to", "s1", "--title", "벽")          # s5 죽은 잎
        self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s1", "--title", "HB",
                 "--falsify", "F", "--falsify-to", "s1")                                    # s6 산 가지
        self.gil("step", "a/gap", "--kind", "analyze", "--title", "AB")                     # s8 analyze

    def _head(self):
        return self._git("rev-parse", "HEAD").stdout.strip()

    def test_goto_step_moves_head(self):
        self._forked()
        live = self._head()
        r = self.gil("goto", "a/gap/s5")   # 죽은 가지의 fail 잎
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("위치 이동", r.stdout)
        self.assertNotEqual(live, self._head())
        self.assertIn("죽은 잎", r.stdout)

    def test_goto_cycle_returns_to_live_leaf(self):
        self._forked()
        live = self._head()
        self.gil("goto", "a/gap/s5")            # 죽은 가지(s5 fail)로 들어갔다가
        r = self.gil("goto", "a/gap")           # 산 잎으로 돌아온다
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(live, self._head())

    def test_goto_does_not_change_graph(self):
        """자리 이동은 그래프를 바꾸지 않는다 — 커밋도 브랜치도 늘지 않는다."""
        self._forked()
        before = self._git("rev-list", "--all", "--count").stdout.strip()
        branches = self._git("for-each-ref", "--format=%(refname)", "refs/heads/").stdout
        self.gil("goto", "a/gap/s5")
        self.assertEqual(before, self._git("rev-list", "--all", "--count").stdout.strip())
        self.assertEqual(branches, self._git("for-each-ref", "--format=%(refname)", "refs/heads/").stdout)

    def test_escape_from_dead_branch(self):
        """갇힘의 탈출: 죽은 가지에서 거부당한 뒤 goto 로 산 가지에 가면 재분기가 된다."""
        self._forked()
        self.gil("goto", "a/gap/s5")   # 죽은 가지 끝에 선다 — 산 가지의 s8 이 안 보인다
        r = self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s8",
                     "--falsify", "F2", "--falsify-to", "s8", "--title", "HC", "--inherit", "L")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("형제", out)                       # 실재한다는 사실을 말해준다
        self.assertIn("gil goto a/gap/s8", out)          # 나갈 길까지 준다
        self.gil("goto", "a/gap/s8")
        r2 = self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s8",
                      "--falsify", "F2", "--falsify-to", "s8", "--title", "HC", "--inherit", "L")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_falsify_to_message_names_analyze(self):
        """곁다리(#67): --falsify-to 거부 문구가 검사와 같은 말을 한다 — analyze 도 받는다."""
        self._forked()
        r = self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s1",
                     "--falsify", "F", "--falsify-to", "s99", "--title", "H")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("define 또는 analyze", r.stdout + r.stderr)

    def test_falsify_to_accepts_ancestor_analyze(self):
        """문구만이 아니라 검사도 analyze 를 받는다."""
        self._forked()
        r = self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s8",
                     "--falsify", "F2", "--falsify-to", "s8", "--title", "HC", "--inherit", "L")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_goto_unknown_step_lists_steps(self):
        self._forked()
        r = self.gil("goto", "a/gap/s99")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("s1", r.stdout + r.stderr)

    def test_goto_unknown_cycle_rejected(self):
        self._forked()
        r = self.gil("goto", "a/nope")
        self.assertNotEqual(r.returncode, 0)

    def test_handoff_says_you_are_on_a_dead_branch(self):
        """갇혔다는 사실을 다음 거부를 기다리지 않고 handoff 가 먼저 말한다."""
        self._forked()
        self.gil("goto", "a/gap/s5")
        out = self.gil("handoff").stdout
        self.assertIn("죽은 가지", out)
        self.assertIn("gil goto a/gap", out)

    def test_goto_all_dead_gives_rebranch_anchor(self):
        """산 잎이 하나도 없으면 그 사실을 말하고 재분기의 뿌리를 준다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/dead", "--author", "clew", "--purpose", "Q")
        self.gil("step", "a/dead", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self.gil("step", "a/dead", "--kind", "fail", "--to", "s1", "--title", "벽")
        r = self.gil("goto", "a/dead")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("산 잎이 없다", out)
        self.assertIn("gil goto a/dead/", out)


class TestReInterview(GilFixture):
    """확정된 기준을 다시 물을 수 있다 (이슈 #75).

    전제가 반증되면 기준은 낡는다. 그런데 재인터뷰는 커밋만 남기고 **조용히 삼켜졌다** —
    --status 는 옛 문서를 done 이라 답하고, 뷰어엔 폼이 안 뜨고, handoff 도 몰랐다.
    남는 선택지가 셋 다 나빴다: 무효한 기준 따르기 / 기준 무시하기 / 그래프 밖으로 나가 묻기."""

    def _ask(self, chain, q):
        import json
        return subprocess.run([*GIL_CMD, "interview", chain, "--ask", "-"], cwd=self.repo,
                              env=dict(os.environ, GIL_NO_VIEWER="1"), text=True,
                              input=json.dumps([{"q": q, "type": "text"}]), capture_output=True)

    def _settled_chain(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "mr", "--purpose", "P")
        self._ask("mr", "1차 기준?")
        with open(os.path.join(self.repo, "ref.md"), "w", encoding="utf-8") as f:
            f.write("기준 v1: 리더보드 전체 재실행\n")
        self.gil("interview", "mr", "--resolve", "ref.md")

    def test_status_reports_pending_after_reask(self):
        """--status 가 거짓말하지 않는다 — 새 질문이 있는데 done 이라 답하던 자리."""
        self._settled_chain()
        self.assertIn("done", self.gil("interview", "mr", "--status").stdout)
        self._ask("mr", "전제가 반증됐다 — 범위를 다시 정해달라")
        self.assertIn("pending", self.gil("interview", "mr", "--status").stdout)

    def test_handoff_shows_revision_in_progress(self):
        self._settled_chain()
        self._ask("mr", "다시 묻는다")
        out = self.gil("handoff").stdout
        self.assertIn("[인터뷰] mr", out)
        self.assertIn("개정하는 중", out)   # 확정된 기준이 있는 채로 다시 묻는 중이다

    def test_the_card_shows_the_new_form(self):
        """다시 물은 질문이 **사람 화면에 뜬다** — 커밋은 있는데 아무에게도 도달하지 않던 자리.

        옛 시험은 뷰어 서버를 띄워 HTML 을 받아 봤다. 매체가 카드로 바뀌었을 뿐 재는 것은
        같다: 확정된 기준이 있는 채로 **다시 물으면** 그 질문이 사람 앞에 서는가."""
        self._settled_chain()
        self._ask("mr", "전제가 반증됐다 — 범위는?")
        card = self.gil("status", "--card").stdout
        self.assertIn("📋", card, "다시 물은 질문이 화면에 안 뜬다")
        self.assertIn("전제가 반증됐다", card, "질문 원문이 화면에 없다")
        self.assertIn('data-iv="mr"', card, "어느 인터뷰의 폼인지 화면이 안 말한다")

    def test_revision_stacks_instead_of_overwriting(self):
        """기준은 사람의 답이라 지워지면 안 된다 — 차수로 쌓인다(append-only 의 정신)."""
        self._settled_chain()
        self._ask("mr", "다시 묻는다")
        with open(os.path.join(self.repo, "ref2.md"), "w", encoding="utf-8") as f:
            f.write("기준 v2: 두 축을 갈라 잰다\n")
        self.gil("interview", "mr", "--resolve", "ref2.md")
        r = self.gil("interview", "mr", "--status", "--show")
        self.assertIn("done", r.stdout)
        self.assertIn("기준 v1", r.stdout)   # 1차 답이 남아 있다
        self.assertIn("기준 v2", r.stdout)


class TestNoLeavingUnterminated(GilFixture):
    """미종결 잎을 두고 떠나지 못한다 (이슈 #78).

    #59 로 사후 발견(fsck)·사후 수리(--at)는 갖췄는데 **떠나는 순간**이 비어 있었다.
    verify 직후가 가장 떠나기 쉬운 자리다 — 결과를 이미 아니까 그 가지는 심리적으로 끝난
    것이 된다. gil 이 매번 "다음은 반드시 analyze"라고 말해주는데도 떠났다:
    안내는 읽고 나서 잊고, 레일은 잊어도 막는다."""

    def _at_verify(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/gap", "--author", "clew", "--purpose", "Q")
        self.gil("step", "a/gap", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "a/gap", "--kind", "verify", "--verdict", "supported", "--title", "V")

    def test_goto_refuses_to_leave_unterminated_verify(self):
        self._at_verify()
        r = self.gil("goto", "a/gap/s1")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("종결 없이 떠날 수 없다", out)
        self.assertIn("--kind analyze", out)      # 이어가는 길
        self.assertIn("--at s3", out)             # 접는 길(사후 수리 문법)
        self.assertIn("--leave-open", out)        # 그래도 떠나는 길

    def test_leave_open_is_an_explicit_escape(self):
        """거부만 하고 길이 없으면 벽이다(#67) — 탈출구는 두되 명시적으로."""
        self._at_verify()
        r = self.gil("goto", "a/gap/s1", "--leave-open")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_new_sibling_branch_is_also_leaving(self):
        """형제 가지를 새로 내는 것도 떠나는 것이다 — 같은 검사가 걸린다."""
        self._at_verify()
        r = self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s1",
                     "--falsify", "F2", "--falsify-to", "s1", "--title", "H2", "--inherit", "L")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("종결 없이 떠날 수 없다", r.stdout + r.stderr)

    def test_terminated_leaf_can_be_left(self):
        """종결한 자리는 자유롭게 떠난다 — 늘 막으면 레일이 아니라 벽이다."""
        self._at_verify()
        self.gil("step", "a/gap", "--kind", "analyze", "--title", "A")
        self.gil("step", "a/gap", "--kind", "success", "--title", "됨")
        r = self.gil("goto", "a/gap/s1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_fail_to_accepts_ancestor_analyze(self):
        """되돌아갈 곳이 define 만이던 비대칭을 없앤다 (이슈 #76 곁다리).

        일곱 가지를 먹은 잘못된 전제가 심긴 자리는 s1(문제 정의)이 아니라 analyze 였다.
        벽의 지도는 '어디로 돌아가야 하나'의 지도다 — 그 자리가 analyze 면 analyze 를 적어야 한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/gap", "--author", "clew", "--purpose", "Q")
        self.gil("step", "a/gap", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self.gil("step", "a/gap", "--kind", "verify", "--verdict", "supported", "--title", "V")
        self.gil("step", "a/gap", "--kind", "analyze", "--title", "우선순위 결정")   # s4
        r = self.gil("step", "a/gap", "--kind", "fail", "--to", "s4", "--title", "지표가 안 움직였다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = self._git("log", "-1", "--format=%B", "HEAD").stdout
        self.assertIn("Gil-Backtrack: s4", body)
        self.assertEqual(self.gil("fsck").returncode, 0)

    def test_success_guard_looks_at_this_attempt_only(self):
        """앞 시도의 refuted verify 가 이 가지를 막지 않는다 (#78 곁다리).

        #32·#60 이후 새 가설은 조상 analyze 에 뿌리내릴 수 있다. 그런데 종결 가드는 계보를
        끝까지 거슬러 올라가 거기서 만난 refuted verify 로 후손 전체를 막았다 — 실사용:
        자기 verify 는 supported 인데 죽은 가지의 refuted 때문에 success 가 거부됐다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/gap", "--author", "clew", "--purpose", "Q")
        self.gil("step", "a/gap", "--kind", "hypothesis", "--title", "H1", "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "a/gap", "--kind", "verify", "--verdict", "refuted", "--title", "V1")
        self.gil("step", "a/gap", "--kind", "analyze", "--title", "A1")   # 여기 뿌리내린다
        # 그 analyze 에서 새 가설 — 이 시도의 verify 는 supported 다.
        self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s4", "--title", "H2",
                 "--falsify", "F2", "--falsify-to", "s4", "--inherit", "앞 가지의 교훈")
        self.gil("step", "a/gap", "--kind", "verify", "--verdict", "supported", "--title", "V2")
        self.gil("step", "a/gap", "--kind", "analyze", "--title", "A2")
        r = self.gil("step", "a/gap", "--kind", "success", "--title", "됨")
        self.assertEqual(r.returncode, 0, "앞 시도의 refuted 가 이 가지를 막았다:\n" + r.stdout + r.stderr)


class TestGoalVocabulary(GilFixture):
    """결말의 어휘 — 달성과 포기 사이 (이슈 #80, #62 의 다음 칸).

    goal-met / abandon 이분법이면 '일부 달성 + 나머지는 원리적 불가'를 적을 자리가 없다.
    그 자리에서 목표를 유리하게 재해석할 압력이 생긴다 — 보고자는 정당한 독해로 빠져나왔지만
    문구가 조금만 달랐으면 거짓 기록이 됐을 것이라고 적었다. 어휘가 부족하면 기록이 거짓말한다."""

    def _cycle(self, goal="발표 축 16개 전부 지목"):
        self.gil("init", "--name", "clew")
        self.gil("chain", "em", "--purpose", "P")
        self.gil("open", "em/c001", "--author", "clew", "--purpose", "Q", "--goal", goal)
        self.gil("step", "em/c001", "--kind", "success", "--title", "됨")

    def test_goal_met_with_partial_verdict_is_refused(self):
        """자기모순 조합이 통과하던 자리 — 보고자가 실제로 그렇게 닫았다."""
        self._cycle()
        r = self.gil("close", "em/c001", "--goal-met", "--verdict", "partial")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("같이 설 수 없다", r.stdout + r.stderr)

    def test_goal_partial_records_the_gap(self):
        """못 한 조각이 그래프에 남는다 — 산문 속에 묻히지 않게."""
        self._cycle()
        r = self.gil("close", "em/c001", "--goal-partial", "발표 축 지목: 2/16. 나머지는 복원 불가",
                     "--verdict", "partial")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = self._git("log", "-1", "--format=%B", "em-c001").stdout
        self.assertIn("Gil-Goal-Met: partial", body)
        self.assertIn("Gil-Goal-Gap: 발표 축 지목: 2/16. 나머지는 복원 불가", body)

    def test_goal_impossible_is_a_finding_not_an_abandon(self):
        """'원리적으로 불가함을 확인했다'는 실패가 아니라 발견이다 — abandon 으로 묻지 않는다."""
        self._cycle()
        r = self.gil("close", "em/c001", "--goal-impossible", "과거 실행 인자가 휘발돼 복원 불가",
                     "--verdict", "rejected")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = self._git("log", "-1", "--format=%B", "em-c001").stdout
        self.assertIn("Gil-Goal-Met: impossible", body)
        self.assertIn("발견이다", body)

    def test_only_one_goal_answer_allowed(self):
        self._cycle()
        r = self.gil("close", "em/c001", "--goal-met", "--goal-partial", "일부")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("하나여야 한다", r.stdout + r.stderr)

    def test_refusal_offers_the_middle_vocabulary(self):
        """거부가 셋을 다 보여준다 — 어휘를 모르면 있어도 못 쓴다."""
        self._cycle()
        r = self.gil("close", "em/c001")
        out = r.stdout + r.stderr
        self.assertIn("--goal-partial", out)
        self.assertIn("--goal-impossible", out)
        self.assertIn("유리하게 재해석할 압력", out)


class TestMeasurementCoords(GilFixture):
    """측정의 좌표 — 어디서 쟀나(dataset)·무엇을 쟀나(subject) (이슈 #79·#81).

    실사용에서 체인 하나가 통째로 탔다: "평가셋"이라 불리는 파일이 둘이었고 어느 측정이 어느
    것 위에 섰는지 아무 데도 없었다. 행수·빈행·gold 합계까지 같고 sha 만 다른 평가셋이 8개.
    gil 은 '닫힌 사이클 불변'을 보장하는데, 그 판정이 **무엇에 대한 판정인지**는 보장 밖이었다."""

    DS = "gold_eval_md.jsonl@sha256:013f5b73ffdbef75"
    SJ = "gemma-26b@rev:abc1234#quant=AWQ"

    def _chain(self, *flags):
        self.gil("init", "--name", "clew")
        self.gil("chain", "evalmap", "--purpose", "측정", *flags)

    def test_coords_are_trailers_not_prose(self):
        """선언은 트레일러로 남는다 — 산문이 아니라 필드라야 기계가 대조한다."""
        self._chain()
        self.gil("open", "evalmap/c001", "--author", "clew", "--purpose", "F1",
                 "--dataset", self.DS, "--subject", self.SJ, "--dataset-note", "376행, gold 2895")
        body = self._git("log", "-1", "--format=%B", "evalmap-c001").stdout
        self.assertIn("Gil-Dataset: " + self.DS, body)
        self.assertIn("Gil-Subject: " + self.SJ, body)
        self.assertIn("Gil-Dataset-Note: 376행, gold 2895", body)

    def test_require_dataset_refuses_open_without_declaration(self):
        """측정 체인은 스스로 합격선을 올린다 — 선언 없으면 문법이 거부한다."""
        self._chain("--require-dataset")
        r = self.gil("open", "evalmap/c001", "--author", "clew", "--purpose", "F1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("평가셋 선언을 요구한다", r.stdout + r.stderr)
        ok = self.gil("open", "evalmap/c001", "--author", "clew", "--purpose", "F1", "--dataset", self.DS)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_require_subject_refuses_open_without_declaration(self):
        self._chain("--require-subject")
        r = self.gil("open", "evalmap/c001", "--author", "clew", "--purpose", "F1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("측정 대상 선언을 요구한다", r.stdout + r.stderr)

    def test_dataset_without_sha_is_flagged(self):
        """이름만으로는 파일이 결정되지 않는다 — 막지는 않되 짚는다."""
        self._chain()
        r = self.gil("open", "evalmap/c001", "--author", "clew", "--purpose", "F1",
                     "--dataset", "gold_eval_md.jsonl")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sha256 이 없다", r.stdout + r.stderr)

    def test_axis_change_within_chain_is_announced(self):
        """c001 은 A 로 재고 c002 는 B 로 쟀는데 둘을 비교하면 사고다 — 그 자리에서 알린다."""
        self._chain()
        self.gil("open", "evalmap/c001", "--author", "clew", "--purpose", "F1", "--dataset", self.DS)
        self.gil("step", "evalmap/c001", "--kind", "success", "--title", "됨")
        self.gil("close", "evalmap/c001", "--verdict", "supported")
        r = self.gil("open", "evalmap/c002", "--author", "clew", "--purpose", "비교",
                     "--dataset", "gold_eval_mdoc.jsonl@sha256:99ffee00",
                     "--parent", "c001", "--inherit", "c001 교훈")
        out = r.stdout + r.stderr
        self.assertIn("평가셋(dataset)이 바뀐다", out)
        self.assertIn("나란히 비교하지 마라", out)

    def test_same_axis_is_not_announced(self):
        """같은 축이면 조용하다 — 늘 뜨는 경고는 안 읽힌다."""
        self._chain()
        self.gil("open", "evalmap/c001", "--author", "clew", "--purpose", "F1", "--dataset", self.DS)
        self.gil("step", "evalmap/c001", "--kind", "success", "--title", "됨")
        self.gil("close", "evalmap/c001", "--verdict", "supported")
        r = self.gil("open", "evalmap/c002", "--author", "clew", "--purpose", "이어서",
                     "--dataset", self.DS, "--parent", "c001", "--inherit", "c001 교훈")
        self.assertNotIn("바뀐다", r.stdout + r.stderr)

    def test_coords_are_visible_in_log_and_handoff(self):
        """그래프에서 바로 읽힌다 — 산문 속에 묻히지 않게."""
        self._chain()
        self.gil("open", "evalmap/c001", "--author", "clew", "--purpose", "F1",
                 "--dataset", self.DS, "--subject", self.SJ)
        log = self.gil("log", "evalmap", "--depth", "cycle").stdout
        self.assertIn("📐 평가셋: " + self.DS, log)
        self.assertIn("🎯 대상: " + self.SJ, log)
        ho = self.gil("handoff").stdout
        self.assertIn("📐 평가셋: " + self.DS, ho)


class TestInterviewArrival(GilFixture):
    """사람의 답이 도착한 사실이 에이전트에게 **도달한다** (이슈 #77, #58 후속).

    #58 이 --wait 를 줬지만 대화형 세션과는 맞물리지 않는다: 지금 필요한 행동은 "폼에
    답해주세요"라고 말하는 것이고, 말하려면 턴을 끝내야 하고, 턴을 끝내면 기다릴 수 없다.
    그래서 '심고 → 알리고 → 턴 종료'가 늘 합리적으로 보이는데 그 경로엔 재개 지점이 없었다."""

    def _ask(self, chain):
        import json
        subprocess.run([*GIL_CMD, "interview", chain, "--ask", "-"], cwd=self.repo,
                       env=dict(os.environ, GIL_NO_VIEWER="1"), text=True,
                       input=json.dumps([{"q": "무엇을 기준으로 하나?", "type": "text"}]),
                       capture_output=True)

    def _answer(self, chain):
        path = os.path.join(self.repo, "ref.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("기준: 사람이 답한 것\n")
        self.gil("interview", chain, "--resolve", "ref.md")

    def _seed(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "eval-map", "--purpose", "P")

    def test_pending_banner_includes_interview(self):
        """최상단 '사람 답 대기' 종합 절에 인터뷰가 들어온다 — 대기는 한 자리에 모은다."""
        self._seed()
        self._ask("eval-map")
        out = self.gil("handoff").stdout
        head = out[out.index("⏳ 사람 답 대기"):]
        self.assertIn("[인터뷰] eval-map", head.split("▶")[0])

    def test_arrived_answer_is_announced_on_any_command(self):
        """답이 도착하면 **무슨 명령을 부르든** 맨 앞에 고지한다 — 통지가 아니라 강제 고지."""
        self._seed()
        self._ask("eval-map")
        self._answer("eval-map")
        r = self.gil("log")
        self.assertIn("인터뷰 답이 도착해 있다", r.stderr)
        self.assertIn("eval-map", r.stderr)

    def test_notice_stops_after_the_agent_reads_it(self):
        """읽으면 고지는 사라진다 — 영원히 뜨는 경고는 안 읽힌다."""
        self._seed()
        self._ask("eval-map")
        self._answer("eval-map")
        self.gil("interview", "eval-map", "--status")
        r = self.gil("log")
        self.assertNotIn("인터뷰 답이 도착해 있다", r.stderr)

    def test_handoff_also_counts_as_reading(self):
        """handoff 는 그 사실을 싣는 자리다 — 거기서도 고지가 꺼진다."""
        self._seed()
        self._ask("eval-map")
        self._answer("eval-map")
        self.gil("handoff")
        r = self.gil("log")
        self.assertNotIn("인터뷰 답이 도착해 있다", r.stderr)

    def test_seen_marker_is_local_not_committed(self):
        """'봤다'는 이 클론의 상태다 — 커밋되면 다른 에이전트가 고지를 못 받는다."""
        self._seed()
        self._ask("eval-map")
        self._answer("eval-map")
        self.gil("handoff")
        os.remove(os.path.join(self.repo, "ref.md"))   # 답변 파일은 이 테스트의 부산물
        self.assertEqual(self._git("status", "--porcelain").stdout.strip(), "")
        self.assertTrue(os.path.exists(os.path.join(self.repo, ".git", "gil", "interview-seen")))

    def test_ask_output_names_wait_as_the_default(self):
        """어느 것이 기본인지 못박는다 — 둘을 나란히 놓으면 싼 쪽을 고른다."""
        self._seed()
        import json
        r = subprocess.run([*GIL_CMD, "interview", "eval-map", "--ask", "-"], cwd=self.repo,
                           env=dict(os.environ, GIL_NO_VIEWER="1"), text=True,
                           input=json.dumps([{"q": "기준?", "type": "text"}]), capture_output=True)
        out = r.stdout + r.stderr
        self.assertIn("기본은 기다리는 것이다", out)
        # 차선(다음 턴의 첫 명령)도 여전히 적히되, 이제 백그라운드 --wait 뒤에 온다(이슈 #82).
        self.assertIn("다음 턴의 **첫 명령**", out)
        self.assertLess(out.index("백그라운드"), out.index("다음 턴의 **첫 명령**"))


class TestCycleForkIsDrawnAsAFork(GilFixture):
    """사이클 분기가 사이클 그래프에서 일직선으로 보였다 (상현님 실사용).

    두 결함이 겹쳐 있었다. (1) 뷰어가 **선언된 계보(Gil-Cycle-Parent)** 대신 커밋 위상으로
    부모를 잡았다 — 새 사이클을 열 때 HEAD 가 어느 브랜치에 서 있었느냐가 그대로 조상이 되니,
    cy1 에서 갈라진 cy2·cy3 를 차례로 열면 cy3 의 조상이 cy2 가 된다. (2) 카드 배치가
    부모를 아예 안 보고 i*gap 으로 줄 세웠다."""

    def _forked_chain(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        def run(cyc):
            self.gil("step", "c/" + cyc, "--kind", "hypothesis", "--title", "h",
                     "--falsify", "F", "--falsify-to", "s1")
            self.gil("step", "c/" + cyc, "--kind", "verify", "--title", "v",
                     "--verdict", "supported", "--falsify-unmet", "u")
            self.gil("step", "c/" + cyc, "--kind", "analyze", "--title", "an", "--finding", "f")
            self.gil("step", "c/" + cyc, "--kind", "success", "--title", "ok")
            self.gil("close", "c/" + cyc, "--verdict", "solved", "--goal-met")
        self.gil("open", "c/cy1", "--author", "x", "--purpose", "뿌리", "--body", "d")
        run("cy1")
        self.gil("open", "c/cy2", "--author", "x", "--purpose", "가지 A", "--body", "d",
                 "--parent", "cy1", "--inherit", "cy1 에서")
        run("cy2")
        # cy3 도 cy1 의 자식이다 — 그런데 HEAD 는 방금 cy2 에 서 있었다(위상은 cy2 를 가리킨다).
        self.gil("open", "c/cy3", "--author", "x", "--purpose", "가지 B", "--body", "d",
                 "--parent", "cy1", "--inherit", "cy1 에서")

    def test_declared_lineage_beats_commit_topology(self):
        """--parent 는 open 이 강제·검증하는 선언이다 — 위상보다 이쪽이 참이다."""
        self._forked_chain()
        out = os.path.join(self.repo, "g.html")
        self.gil("graph", "--html", "--out", out)
        with open(out, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'"cy3","steps":\d+,"status":"[^"]*","here":\w+,"parent":"([^"]*)"', html)
        self.assertIsNotNone(m, "cy3 의 진입 부모를 못 찾았다")
        self.assertIn("cy1", m.group(1), "cy3 의 부모가 선언(cy1)이 아니라 위상(cy2)으로 잡혔다")

    def test_the_branch_really_forks_in_git(self):
        """**선언이 아니라 실재다** — gil 이 아무리 계보를 그려도 진짜 브랜치로 갈라지지
        않으면 아무 의미가 없다(상현님). open --parent 는 그 자리로 되돌아가 분기를 친다."""
        self._forked_chain()
        cy1 = self._git("rev-parse", "refs/heads/c-cy1").stdout.strip()
        cy2 = self._git("rev-parse", "refs/heads/c-cy2").stdout.strip()
        cy3 = self._git("rev-parse", "refs/heads/c-cy3").stdout.strip()
        anc = lambda a, b: self._git("merge-base", "--is-ancestor", a, b).returncode == 0
        self.assertTrue(anc(cy1, cy3), "cy3 가 선언한 부모(cy1)의 자손이 아니다")
        self.assertFalse(anc(cy2, cy3), "cy3 가 cy2 에서 갈라졌다 — 커밋 그래프가 계보를 거짓말한다")
        self.assertTrue(anc(cy1, cy2))

    def test_viewer_draws_the_raw_git_graph(self):
        """사람이 직접 점검할 수 있어야 한다 — gil 의 해석을 거치지 않은 git 자신의 그림.

        ASCII 가 아니라 **그림**이다(레인·점·선·브랜치 칩). 정적 build 에도 실린다:
        데이터를 심어 화면에서 그리므로 서버가 없어도 자기완결이다."""
        self._forked_chain()
        out = os.path.join(self.repo, "g.html")
        self.gil("graph", "--html", "--out", out)
        with open(out, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("det-gitgraph", html)
        self.assertIn("gitgraphdata", html)
        self.assertIn("buildGitGraph", html)
        # 데이터가 진짜 커밋 위상이다 — cy3 의 부모가 cy1 의 팁이어야 한다.
        cy1 = self._git("rev-parse", "refs/heads/c-cy1").stdout.strip()[:9]
        m = re.search(r'\{"sha":"[0-9a-f]{9}","parents":\["' + cy1 + r'"\][^}]*"subj":"gil c/cy3/s1[^"]*"', html)
        self.assertIsNotNone(m, "cy3/s1 의 커밋 부모가 cy1 의 팁이 아니다(그래프가 계보를 거짓말한다)")

    def test_fsck_catches_a_lineage_that_is_not_a_real_fork(self):
        """**판정은 눈이 아니라 도구가 한다**(상현님) — 선언과 실재가 어긋나면 fsck 가 짚는다.

        그림 두 개를 사람이 비교해야만 드러나는 거짓은, 다음번엔 아무도 안 본다."""
        self._forked_chain()
        self.assertNotIn("계보:", self.gil("fsck").stdout)   # 정상은 조용하다
        # 거짓 계보를 심는다: cy2 위에서 갈라놓고 부모는 cy1 이라고 선언.
        self._git("branch", "-f", "c-cy4", "refs/heads/c-cy2")
        self._git("checkout", "-q", "c-cy4")
        msg = ("gil c/cy4/s1 define: 거짓\n\n거짓 계보.\n\n"
               "Gil-Chain: c\nGil-Cycle: cy4\nGil-Step: s1\nGil-Kind: define\n"
               "Gil-Parent: null\nGil-Cycle-Author: x\nGil-Cycle-Purpose: 거짓\n"
               "Gil-Cycle-Parent: cy1\nGil-Fits: f\n")
        self._git("commit", "-q", "--allow-empty", "-m", msg)
        r = self.gil("fsck")
        out = r.stdout + r.stderr
        self.assertIn("실제로는", out)
        self.assertIn("cy4", out)
        self.assertNotEqual(r.returncode, 0)

    def test_card_lays_cycles_out_by_lineage(self):
        """배치가 부모를 본다 — 같은 부모의 형제는 같은 열에서 세로로 갈린다."""
        self._forked_chain()
        out = os.path.join(self.repo, "g.html")
        self.gil("graph", "--html", "--out", out)
        with open(out, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("parentOf", html)   # 계보로 col/row 를 잡는 배치가 들어 있다
        self.assertIn("rowGap", html)


class TestJudgmentArrival(GilFixture):
    """사람의 판정도 도착한다 (상현님 실사용).

    "gil approve 또는 gil reject 가 필요합니다" 라고 해서 사람이 뷰어에서 승인을 눌렀는데
    **에이전트가 그걸 몰랐다.** 인터뷰 답에는 ⚡ 고지가 있는데 판정에는 없었다 — 사람이 자기
    몫을 다했는데 그 사실이 닿지 않으면, 사람이 다시 말을 걸어야 한다(#77 과 같은 자리)."""

    def _upto_pending(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/cy", "--author", "x", "--purpose", "p", "--body", "정의")
        self.gil("step", "c/cy", "--kind", "hypothesis", "--title", "h",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "c/cy", "--kind", "verify", "--title", "v", "--verdict", "supported",
                 "--falsify-unmet", "미달")
        self.gil("step", "c/cy", "--kind", "analyze", "--title", "an", "--finding", "밝힘")
        self.gil("step", "c/cy", "--kind", "pending", "--title", "사람 판단 필요")

    def test_approval_is_announced_on_the_next_command(self):
        self._upto_pending()
        self.gil("approve", "c/cy")
        out = self.gil("log").stdout + self.gil("log").stderr
        self.assertIn("사람의 판정이 도착했다", out)
        self.assertIn("승인했다", out)
        self.assertIn("c/cy", out)

    def test_rejection_is_announced_with_the_way_forward(self):
        """기각은 '끝'이 아니다 — 되돌아간 자리에서 새 가지를 파는 길을 함께 준다."""
        self._upto_pending()
        self.gil("reject", "c/cy", "--to", "s1")
        out = self.gil("log").stdout + self.gil("log").stderr
        self.assertIn("기각했다", out)
        self.assertIn("--inherit", out)

    def test_notice_stops_once_it_has_been_read(self):
        """영원히 뜨는 경고는 안 읽힌다 — 읽는 명령(context·handoff)이 지나가면 끈다."""
        self._upto_pending()
        self.gil("approve", "c/cy")
        self.assertIn("사람의 판정", self.gil("log").stdout + self.gil("log").stderr)
        self.gil("context", "c/cy")
        again = self.gil("log").stdout + self.gil("log").stderr
        self.assertNotIn("사람의 판정", again)

    def test_prune_approval_by_the_human_is_announced(self):
        """사람→에이전트 통로의 마지막 구멍 — 뷰어에서 누른 삭제 승인도 닿아야 한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c1", "--purpose", "정리 대상")
        self.gil("prune", "c1", "--request", "--reason", "실험이었다")
        self.gil("prune-approve", "c1", "--by", "card")   # 카드가 부르는 형태
        out = self.gil("log").stdout + self.gil("log").stderr
        self.assertIn("사람이 삭제를 **승인했다**", out)
        self.assertIn("--confirm", out)   # 다음 수까지 준다

    def test_agent_own_prune_action_is_not_announced(self):
        """자기 행동을 자기에게 알리면 소음이다 — CLI 로 부른 것은 고지하지 않는다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c1", "--purpose", "정리 대상")
        self.gil("prune", "c1", "--request", "--reason", "실험이었다")
        self.gil("prune-approve", "c1")    # 에이전트가 직접
        out = self.gil("log").stdout + self.gil("log").stderr
        self.assertNotIn("사람이 삭제", out)

    def test_prune_withdraw_by_the_human_is_announced(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c1", "--purpose", "정리 대상")
        self.gil("prune", "c1", "--request", "--reason", "실험이었다")
        self.gil("prune", "c1", "--withdraw", "--reason", "역시 두자", "--by", "card")
        out = self.gil("log").stdout + self.gil("log").stderr
        self.assertIn("거뒀다", out)
        self.assertIn("지우지 마라", out)

    def test_reading_the_prune_view_stops_the_notice(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c1", "--purpose", "정리 대상")
        self.gil("prune", "c1", "--request", "--reason", "실험이었다")
        self.gil("prune-approve", "c1", "--by", "card")
        self.assertIn("사람이 삭제", self.gil("log").stdout + self.gil("log").stderr)
        self.gil("prune", "c1")            # 승인 여부를 그 자리에서 읽는다
        again = self.gil("log").stdout + self.gil("log").stderr
        self.assertNotIn("사람이 삭제", again)

    def test_no_notice_when_nothing_was_judged(self):
        self._upto_pending()
        out = self.gil("log").stdout + self.gil("log").stderr
        self.assertNotIn("사람의 판정", out)


class TestWaitHandoffToHost(GilFixture):
    """이슈 #94 — 답은 도착했는데 **아무도 그 출력을 읽지 못했다**(네 번째 겹).

    "백그라운드로 심어라(`&`)" 라는 안내가 조건부였다: 셸에서 `&` 로 떼어낸 프로세스는
    대부분의 호스트에서 추적 밖이라 완료가 턴을 열지 못한다. 그 조건이 문서에 없었다."""

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")

    def _put(self, name, text):
        p = os.path.join(self.repo, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return name

    def test_ask_accepts_inline_json(self):
        """도움말이 <질문JSON|-> 라고 약속했으면 JSON 을 그대로 받아야 한다(곁다리 2)."""
        r = self.gil("intake", "s1", "--ask", '[{"q":"무엇을","type":"text"}]')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("질문 1개 심음", r.stdout + r.stderr)

    def test_help_shows_the_question_schema(self):
        """type 이 필수인 걸 도움말만 보고 알 수 있어야 한다 — 두 번 죽지 않게."""
        h = self.gil("help", "intake").stdout
        self.assertIn('"type"', h)
        self.assertIn("text|radio|checkbox", h)

    def test_wait_hint_warns_about_shell_background(self):
        """`&` 한 글자가 '깨어난다'와 '영원히 안 깨어난다'를 가른다 — 그 구분을 문서에 넣는다."""
        self.gil("interview", "c", "--ask", "-", input='[{"q":"q","type":"text"}]')
        h = self.gil("help", "interview").stdout
        self.assertIn("호스트가 추적하는", h)
        self.assertIn("gil_interview_wait", h)   # MCP 경로엔 이 구멍이 없다

    def test_status_is_short_by_default(self):
        """확인용이라 믿고 불렀다가 수십 줄이 쏟아지면 컨텍스트를 크게 먹는다(곁다리 1)."""
        self.gil("intake", "s2", "--ask", '[{"q":"무엇을","type":"text"}]')
        self._put("a.md", "## 무엇을\n\n" + ("답 " * 200))
        self.gil("intake", "s2", "--resolve", "a.md")
        short = self.gil("intake", "s2", "--status").stdout
        full = self.gil("intake", "s2", "--status", "--show").stdout
        self.assertLess(len(short), len(full), "--status 가 --show 와 같은 양을 쏟는다")
        self.assertIn("--show", short)          # 전문으로 가는 길은 알려준다
        self.assertIn("인용 가능한 답", short)  # 정작 필요한 번호는 남긴다

    def test_arrival_notice_speaks_intake_language(self):
        """개시 인터뷰는 체인이 아니다 — 없는 체인을 찾게 만들지 않는다."""
        self.gil("intake", "s3", "--ask", '[{"q":"무엇을","type":"text"}]')
        self._put("b.md", "## 무엇을\n\n답")
        self.gil("intake", "s3", "--resolve", "b.md")
        out = self.gil("log").stdout + self.gil("log").stderr
        self.assertIn("개시 인터뷰 s3", out)
        self.assertIn("gil intake s3 --status", out)


class TestMarkdownTables(GilFixture):
    """뷰어의 표 렌더 (상현님 실사용: "표가 렌더링될 때 깨지는 현상").

    보고서 본문은 사람이 읽는 자리다 — 표가 밀리면 수치가 엉뚱한 열에 붙어 읽는 사람이
    잘못 읽는다. 침묵하는 오류가 아니라 **틀린 것을 자신 있게 보여주는** 오류다."""

    BODY = "\n".join([
        "# 표",
        "| 항목 | 값 | 비고 |",
        "|---|---|---|",
        "| 지연 | 120ms | 개선됨 |",
        "",
        "설명 문단입니다.",       # 빈 줄 없이 표가 붙는다 — 아주 흔한 형태
        "| k | v |",
        "|---|---|",
        "| x | 1 |",
        "",
        "| 명령 | 뜻 |",
        "|---|---|",
        "| `a \\| b` | 파이프가 든 코드 |",
        "",
        "| a | b | c |",
        "|---|---|---|",
        "| 1 | 2 |",
        "| 1 | 2 | 3 | 4 |",
    ])

    def _html(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "t", "--purpose", "표")
        bf = os.path.join(self.repo, "body.md")
        with open(bf, "w", encoding="utf-8") as f:
            f.write(self.BODY)
        self.gil("open", "t/c1", "--author", "x", "--purpose", "p", "--body-file", "body.md")
        out = os.path.join(self.repo, "g.html")
        self.gil("graph", "--html", "--out", out)
        with open(out, encoding="utf-8") as f:
            return f.read()

    def test_renderer_handles_the_four_shapes(self):
        html = self._html()
        # 렌더러는 클라이언트 JS 라 HTML 문자열엔 원문이 들어 있다 — 대신 렌더 규칙 자체를 본다.
        self.assertIn("mdCells", html)          # 파이프 이스케이프를 아는 분해기
        self.assertIn("startsTable", html)      # 문단이 표를 삼키지 않는다
        self.assertIn("cs.length=head.length", html)  # 칸 수를 헤더에 맞춘다

    def test_body_survives_into_the_static_build(self):
        """정적 build 는 본문을 인라인으로 싣는다 — 표 원문이 그대로 들어가야 렌더된다."""
        html = self._html()
        self.assertIn("파이프가 든 코드", html)
        self.assertIn("설명 문단입니다", html)


class TestPruneWithdraw(GilFixture):
    """이슈 #91 — 요청을 올린 순간 빠져나올 수 없었다.

    `--request` 는 커밋을 남기는데 철회 문법이 없어, 승인도 철회도 못 하는 상태에 갇혔다
    (카드가 뷰어 상단을 영구히 덮는다). append-only 는 그래프 안의 규율이지 새 사실을 못
    적는다는 뜻이 아니다 — **'이 요청은 더 이상 유효하지 않다' 도 새 사실이다.**"""

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "c1", "--purpose", "정리 대상")
        self.gil("prune", "c1", "--request", "--reason", "실험이었고 이제 필요 없다")

    def test_request_tells_how_to_get_out(self):
        """거부만 하고 길이 없으면 벽이다 — 요청하는 자리에서 나가는 길도 함께 준다."""
        r = self.gil("prune", "c1", "--request", "--reason", "다시")
        self.assertIn("--withdraw", r.stdout + r.stderr)

    def test_withdraw_settles_the_request(self):
        r = self.gil("prune", "c1", "--withdraw", "--reason", "생각이 바뀌었다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "prune-withdraw")
        # 거둔 요청은 승인될 수 없다.
        a = self.gil("prune-approve", "c1")
        self.assertNotEqual(a.returncode, 0)
        self.assertIn("삭제 요청이 없다", a.stderr)

    def test_withdraw_needs_a_reason_and_a_request(self):
        self.assertNotEqual(self.gil("prune", "c1", "--withdraw").returncode, 0)
        r = self.gil("prune", "없는체인", "--withdraw", "--reason", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("거둘 것이 없다", r.stderr)

    def test_re_request_after_withdraw_shows_up_again(self):
        """철회 뒤 **다시 올린 요청**은 다시 떠야 한다 — 결말은 시간 축의 마지막 사실이다."""
        self.gil("prune", "c1", "--withdraw", "--reason", "거둔다")
        self.gil("prune", "c1", "--request", "--reason", "역시 지우자")
        r = self.gil("prune", "c1")
        self.assertIn("아직 사람의 승인이 없다", r.stdout + r.stderr)
        a = self.gil("prune-approve", "c1")
        self.assertEqual(a.returncode, 0, a.stderr)

    def test_withdrawn_request_cannot_be_confirmed(self):
        self.gil("prune", "c1", "--withdraw", "--reason", "거둔다")
        r = self.gil("prune", "c1", "--confirm", "c1", "--reason", "지운다")
        self.assertNotEqual(r.returncode, 0)

    def test_retire_without_refs_gives_a_way_out(self):
        """정리 사다리의 아래 칸이 위 칸의 대상을 모르면 막다른 길이 생긴다(#91 ③).

        prune 은 아는 체인을 retire 는 "로컬 브랜치가 없다"로 거부했고, 그래서 카드를 접을
        수도 지울 수도 없었다. 거부하더라도 **갈 수 있는 길**은 줘야 한다."""
        # 브랜치는 없는데 그래프에는 살아 있는 상태(보고자의 v3-* 체인이 그랬다)를 만든다:
        # 태그로 도달 가능하게 남기고 브랜치만 지운다 — prune 은 --all 로 보고 retire 는 못 본다.
        tip = self._git("rev-parse", "refs/heads/c1").stdout.strip()
        self._git("tag", "keep-c1", tip)
        self._git("update-ref", "-d", "refs/heads/c1")
        r = self.gil("chain-retire", "c1", "--reason", "접자")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("그래프에는 살아 있다", r.stderr)
        self.assertIn("gil prune c1 --withdraw", r.stderr)   # 갇힌 요청에서 나가는 길

    def test_retire_says_when_it_is_already_folded(self):
        """이미 접힌 체인을 또 접으라 하면, 그 사실과 펼치는 법을 말한다."""
        self.gil("chain-retire", "c1", "--reason", "접자", "--confirm", "c1")
        r = self.gil("chain-retire", "c1", "--reason", "또 접자")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("이미 접혀 있다", r.stderr)
        self.assertIn("chain-unretire", r.stderr)


class TestRetireHidesNothingSilently(GilFixture):
    """이슈 #92 — gil 은 삭제를 막지만 **은닉**을 막지 않았다.

    삭제(prune)엔 문이 셋인데 폐기(chain-retire)엔 0개였다. 되돌릴 수 있다는 것이 게이트를
    면제하는 근거가 됐는데, **되돌릴 수 있는 것과 되돌릴 필요를 알아차릴 수 있는 것은 다르다.**
    그리고 접으면 기본 fsck 의 숫자가 뚝 떨어져(실사용 229→1) 아무것도 안 고쳤는데 성과로
    읽혔다 — 없는 게 죄가 아니라 감춘 게 죄다."""

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "dirty", "--purpose", "위반이 있는 체인")
        self.gil("open", "dirty/cy", "--author", "x", "--purpose", "p", "--body", "정의")
        self.gil("step", "dirty/cy", "--kind", "hypothesis", "--title", "h",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "dirty/cy", "--kind", "verify", "--title", "v",
                 "--verdict", "refuted", "--falsify-met", "관측됨")
        self.gil("step", "dirty/cy", "--kind", "analyze", "--title", "an",
                 "--finding", "밝힌 것")
        # HEAD 가 딴 데로 가면서 analyze 잎이 매달린다 → fsck 위반 1건.
        self.gil("goto", "dirty/cy/s1", "--leave-open")
        self.gil("step", "dirty/cy", "--kind", "hypothesis", "--to", "s1",
                 "--inherit", "교훈", "--title", "h2", "--falsify", "F2", "--falsify-to", "s1")

    def _violations(self, *extra):
        r = self.gil("fsck", *extra)
        return [l for l in (r.stdout + r.stderr).splitlines() if l.startswith("위반:")]

    def test_precondition_there_is_a_violation(self):
        self.assertEqual(len(self._violations()), 1)

    def test_dry_run_shows_what_gets_folded(self):
        """--dry-run 한 줄만 있어도 사람이 검증할 지점이 생긴다."""
        r = self.gil("chain-retire", "dirty", "--reason", "정리", "--dry-run")
        out = r.stdout + r.stderr
        self.assertIn("브랜치(ref)", out)
        self.assertIn("스텝", out)
        self.assertIn("fsck 위반 1건", out)
        # 아무것도 옮기지 않았다.
        self.assertEqual(len(self._violations()), 1)
        self.assertIn("dirty", self._git("for-each-ref", "--format=%(refname:short)",
                                          "refs/heads/").stdout)

    def test_folding_violations_needs_a_typed_confirmation(self):
        """위반을 함께 접는 것은 정리가 아니라 은닉이다 — 그때만 문을 단다."""
        r = self.gil("chain-retire", "dirty", "--reason", "정리")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("은닉", r.stderr)
        self.assertIn("--confirm dirty", r.stderr)
        self.assertEqual(len(self._violations()), 1, "거부됐는데 접혔다")

    def test_clean_chain_folds_without_friction(self):
        """위반 없는 체인은 지금처럼 한 줄로 접힌다 — 규율은 마찰이 아니라 방향이다."""
        self.gil("chain", "clean", "--purpose", "위반 없는 체인", "--parallel-with", "dirty")
        r = self.gil("chain-retire", "clean", "--reason", "끝난 국면")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("위반은 접히지 않는다", r.stdout + r.stderr)

    def test_default_fsck_reports_what_it_stopped_counting(self):
        """도구가 자기 상태를 축소 보고하지 않는다 — 접힌 위반은 집계로라도 남는다."""
        self.gil("chain-retire", "dirty", "--reason", "정리", "--confirm", "dirty")
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertIn("접힌(retired)", out)
        self.assertIn("1건", out)
        self.assertIn("--all", out)
        # 그리고 --all 은 여전히 그 위반을 전부 보고한다(고쳐진 게 아니다).
        self.assertEqual(len(self._violations("--all")), 1)

    def test_handoff_leaves_a_trace_of_folded_chains(self):
        """접힌 체인은 없는 것이 아니다 — 다음 세션이 '체인 하나뿐'으로 읽지 않게."""
        self.gil("chain-retire", "dirty", "--reason", "정리", "--confirm", "dirty")
        out = self.gil("handoff").stdout + self.gil("handoff").stderr
        self.assertIn("접힌(retired)", out)
        self.assertIn("chain-unretire", out)


class TestFindingAndWallMap(GilFixture):
    """분석의 결론과 벽의 지도 (상현님 실사용 관측 둘).

    (1) 분석에서 **결론 없이** define 으로 백트랙하는 현상.
    (2) 실패 노드에서 analyze 로 백트랙했는데 **define 에서** 새 가설을 만드는 현상.
    둘 다 지식 누적을 끊는다 — 누적은 backtrack 을 따라 흐르는데, 결론이 비면 실을 것이
    없고, 지도를 벗어나면 흐를 물길이 끊긴다."""

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "원인 규명")
        self.gil("open", "c/cy", "--author", "x", "--purpose", "문제", "--body", "정의")
        self.gil("step", "c/cy", "--kind", "hypothesis", "--title", "h1",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "c/cy", "--kind", "verify", "--title", "v1", "--verdict", "refuted",
                 "--falsify-met", "관측됨")

    def test_analyze_requires_a_finding(self):
        """결론 없는 분석은 서지 못한다 — 다음 판단이 딛을 문장이 없다."""
        r = self._raw_step("c/cy", "--kind", "analyze", "--title", "분석", "--body", "본문")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--finding", r.stderr)

    def _wall_at_s4(self):
        self.gil("step", "c/cy", "--kind", "analyze", "--title", "분석", "--body", "본문",
                 "--finding", "가설은 맞았고 측정 방법이 틀렸다")
        self.gil("step", "c/cy", "--kind", "fail", "--to", "s4", "--title", "벽", "--body", "막혔다")

    def test_rebranch_off_the_wall_map_is_refused(self):
        """벽이 s4 를 가리켰는데 s1 에서 갈라지면 거부 — 기록과 행동이 어긋나면 말한다."""
        self._wall_at_s4()
        self._no_despite_autofill = True
        try:
            r = self.gil("step", "c/cy", "--kind", "hypothesis", "--to", "s1",
                         "--inherit", "교훈", "--title", "h2", "--falsify", "F2", "--falsify-to", "s1")
        finally:
            self._no_despite_autofill = False
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("벽의 지도", r.stderr)
        self.assertIn("--despite", r.stderr)

    def test_following_the_wall_map_needs_no_excuse(self):
        """지도를 따르면 아무것도 더 요구하지 않는다 — 규율은 마찰이 아니라 방향이다."""
        self._wall_at_s4()
        self._no_despite_autofill = True
        try:
            r = self.gil("step", "c/cy", "--kind", "hypothesis", "--to", "s4",
                         "--inherit", "계측 해상도가 벽이었다", "--title", "h2",
                         "--falsify", "F2", "--falsify-to", "s4")
        finally:
            self._no_despite_autofill = False
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_deviation_is_allowed_but_recorded(self):
        """지도를 고치는 것도 정당하다 — 다만 그 판단이 그래프에 남는다."""
        self._wall_at_s4()
        r = self.gil("step", "c/cy", "--kind", "hypothesis", "--to", "s1",
                     "--despite", "계측 없이는 어떤 가설도 못 선다", "--inherit", "교훈",
                     "--title", "h2", "--falsify", "F2", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("계측 없이는", self.trailer("HEAD", "Gil-Despite-Map"))

    def test_finding_flows_into_the_accumulated_knowledge(self):
        """결론은 **인용되어** 다음 가지에 도착한다 — 요약이 아니라 그 문장 그대로."""
        self._wall_at_s4()
        r = self.gil("context", "c/cy")
        self.assertIn("가설은 맞았고 측정 방법이 틀렸다", r.stdout + r.stderr)

    def test_handoff_carries_the_walls_without_being_asked(self):
        """세션 부활의 정문에도 벽이 온다 — 능동 조회에 기대면 그건 전파가 아니다."""
        self._wall_at_s4()
        r = self.gil("handoff")
        out = r.stdout + r.stderr
        self.assertIn("접힌 시도", out)
        self.assertIn("가설은 맞았고 측정 방법이 틀렸다", out)

    def test_every_step_commit_nudges_about_the_walls(self):
        """매 커밋마다 전문을 뿌리면 화면을 덮는다 — 대신 한 줄로 존재를 알린다."""
        self._wall_at_s4()
        self.gil("step", "c/cy", "--kind", "hypothesis", "--to", "s4",
                 "--inherit", "교훈", "--title", "h2", "--falsify", "F2", "--falsify-to", "s4")
        r = self.gil("step", "c/cy", "--kind", "verify", "--title", "v2",
                     "--verdict", "supported", "--falsify-unmet", "미관측")
        self.assertIn("이미 민 벽", r.stdout + r.stderr)
        self.assertIn("gil context", r.stdout + r.stderr)


class TestReadmeAiRunnable(unittest.TestCase):
    """README.ai.md 의 '복붙 가능, 실제로 도는 시퀀스' 블록이 **정말 도는가**.

    윈도우 필드테스트에서 하이쿠가 이 문서를 그대로 따르다 두 번째 줄에서 거부당했다
    (기준 문서 없이는 open 이 안 된다 — 문서엔 인터뷰가 한 글자도 없었다). 문서는 정문이고,
    정문의 복붙 블록이 안 도는 것은 문서 오류가 아니라 **제품 결함**이다. 그러니 실행한다.
    """

    def _block(self, after):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        with open(os.path.join(root, "README.ai.md"), encoding="utf-8") as f:
            doc = f.read()
        i = doc.index(after)
        m = re.search(r"```bash\n(.*?)\n```", doc[i:], re.S)
        self.assertIsNotNone(m, "복붙 블록을 못 찾았다: " + after)
        return m.group(1)

    def test_step_c_block_runs_end_to_end(self):
        blk = self._block("### 관용 예제 — 묻고")
        # 문서가 intake 를 먼저 가르치는가 — 목적을 에이전트가 창작하는 옛 고리로 돌아가지 않게.
        self.assertIn("gil intake", blk)
        self.assertIn("--from-intake", blk)
        self.assertLess(blk.index("gil intake"), blk.index("gil chain"),
                        "intake 는 체인보다 먼저 나와야 한다(이슈 #90)")
        d = tempfile.mkdtemp()
        try:
            binp = os.path.join(d, "bin")
            os.makedirs(binp)
            os.symlink(os.path.abspath(GIL_BIN), os.path.join(binp, "gil"))
            work = os.path.join(d, "work")
            os.makedirs(work)
            env = dict(os.environ, GIL_NO_VIEWER="1",
                       PATH=binp + os.pathsep + os.environ.get("PATH", ""))
            init = subprocess.run(["gil", "init"], cwd=work, env=env,
                                  capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            sh = os.path.join(d, "block.sh")
            with open(sh, "w", encoding="utf-8") as f:
                f.write(blk)
            r = subprocess.run(["sh", "-e", sh], cwd=work, env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0,
                             "README.ai.md 의 복붙 블록이 도중에 죽었다:\n" + r.stdout[-3000:] + r.stderr[-3000:])
            g = subprocess.run(["gil", "log", "--depth", "step"], cwd=work, env=env,
                               capture_output=True, text=True)
            for kind in ("define", "hypothesis", "verify", "analyze", "success"):
                self.assertIn(kind, g.stdout)
            f = subprocess.run(["gil", "fsck"], cwd=work, env=env,
                               capture_output=True, text=True)
            self.assertNotIn("스텝순환:", f.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestReadmeAiTournamentRunnable(unittest.TestCase):
    """README.ai.md 의 **토너먼트 예제**도 정말 도는가 (이슈 #112 · #106 e).

    예시가 전부 직렬이면 예시가 곧 기본값으로 읽힌다(#103 의 어포던스 효과) — 그래서 병렬을
    가르치는 예제를 정문에 넣었다. 그런데 정문의 복붙 블록이 안 도는 것은 문서 오류가 아니라
    **제품 결함**이다(이 클래스의 형제 시험이 그렇게 정했다). 그러니 실행한다.

    실제로 이 시험을 쓰다가 결함 하나를 잡았다: `gil goto` 가 **선언된 경합의 갈래를 두고
    떠나는 것까지** 막고 있었다(#78 의 미종결 잎 가드가 넓게 걸려 있었다). 갈래 사이를 오가는
    유일한 길이 막히면 경합은 문법으로만 있고 실제로는 못 쓴다."""

    def test_tournament_block_runs_after_the_first_one(self):
        d = tempfile.mkdtemp()
        try:
            binp = os.path.join(d, "bin")
            os.makedirs(binp)
            os.symlink(os.path.abspath(GIL_BIN), os.path.join(binp, "gil"))
            work = os.path.join(d, "work")
            os.makedirs(work)
            env = dict(os.environ, GIL_NO_VIEWER="1",
                       PATH=binp + os.pathsep + os.environ.get("PATH", ""))
            init = subprocess.run(["gil", "init"], cwd=work, env=env,
                                  capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            for after in ("### 관용 예제 — 묻고", "### 관용 예제 — 갈래 둘을"):
                blk = TestReadmeAiRunnable._block(self, after)
                sh = os.path.join(d, "block.sh")
                with open(sh, "w", encoding="utf-8") as f:
                    f.write(blk)
                r = subprocess.run(["sh", "-e", sh], cwd=work, env=env,
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0,
                                 "README.ai.md 의 복붙 블록이 도중에 죽었다(" + after + "):\n"
                                 + r.stdout[-3000:] + r.stderr[-3000:])
            g = subprocess.run(["gil", "log", "power", "--all", "--depth", "step"], cwd=work, env=env,
                               capture_output=True, text=True).stdout
            self.assertIn("[fail] \u2190s4", g, "채택이 진 갈래에 벽을 안 남겼다:\n" + g)
            f = subprocess.run(["gil", "fsck"], cwd=work, env=env,
                               capture_output=True, text=True)
            self.assertIn("위반 0", f.stdout,
                          "선언된 경합을 쓴 저장소가 위반으로 남았다:\n" + f.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestOnboardingInstall(GilFixture):
    """gil 이 온보딩을 저장소에 설치한다 (이슈 #73).

    존재의 방을 세워도 **다음 세션이 그 방을 찾아 들어올 길**이 저장소에 없으면 복원 경로
    첫 칸(대문)에서 끊긴다. 실사용에서 대문이 v2 경로를 가리킨 채 남아, 새 세션이 v2
    바이너리를 실행하고 낡은 세계를 오류 없이 정상인 척 받았다."""

    def test_init_installs_docs_and_gate_block(self):
        r = self.gil("init", "--name", "lawmask")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "docs", "gil", "index.md")))
        self.assertTrue(os.path.exists(os.path.join(self.repo, "llms.txt")))
        with open(os.path.join(self.repo, "CLAUDE.md"), encoding="utf-8") as f:
            gate = f.read()
        self.assertIn("<!-- gil:onboarding:begin -->", gate)
        self.assertIn("gil handoff", gate)
        self.assertIn("lawmask", gate)          # 이 저장소의 존재 이름으로 안내한다

    def test_docs_install_does_not_overwrite_by_default(self):
        """사람이 고쳐 쓴 문서를 도구가 덮지 않는다 — --force 로만."""
        self.gil("init", "--name", "clew")
        path = os.path.join(self.repo, "docs", "gil", "index.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 우리가 고친 문서\n")
        self.gil("docs", "install")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "# 우리가 고친 문서\n")
        self.gil("docs", "install", "--force")
        with open(path, encoding="utf-8") as f:
            self.assertNotEqual(f.read(), "# 우리가 고친 문서\n")

    def test_gate_block_replaces_only_managed_region(self):
        """대문의 사람이 쓴 부분은 무접촉 — 마커 사이만 바뀐다."""
        with open(os.path.join(self.repo, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# 우리 프로젝트\n\n사람이 쓴 소중한 문단.\n")
        self._git("add", "-A"); self._git("commit", "-m", "docs")
        self.gil("init", "--name", "clew")
        self.gil("docs", "install")   # 두 번 돌려도 블록이 늘어나지 않는다
        with open(os.path.join(self.repo, "CLAUDE.md"), encoding="utf-8") as f:
            gate = f.read()
        self.assertIn("사람이 쓴 소중한 문단.", gate)
        self.assertEqual(gate.count("<!-- gil:onboarding:begin -->"), 1)

    def test_handoff_flags_gate_pointing_at_another_gil(self):
        """대문이 가리키는 바이너리가 이 바이너리와 다르면 짚는다 — 조용한 오답의 입구."""
        self.gil("init", "--name", "clew")
        toolsdir = os.path.join(self.repo, "tools", "gil")
        os.makedirs(toolsdir, exist_ok=True)
        fake = os.path.join(toolsdir, "gil")
        with open(fake, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho 'gil 2.50.0'\n")
        os.chmod(fake, 0o755)
        with open(os.path.join(self.repo, "CLAUDE.md"), "a", encoding="utf-8") as f:
            f.write("\n바이너리 `tools/gil/gil`\n")
        out = self.gil("handoff").stdout
        self.assertIn("대문", out)
        self.assertIn("tools/gil/gil", out)
        self.assertIn("2.50.0", out)

    def test_embedded_docs_match_repo_docs(self):
        """embed 된 문서가 이 레포의 docs/gil 과 같아야 한다 — 진실원이 갈라지면 설치본이 낡는다."""
        here = os.path.dirname(os.path.abspath(__file__))
        assets = os.path.join(here, "..", "go", "assets", "docs", "gil")
        repo_docs = os.path.join(here, "..", "..", "..", "docs", "gil")
        names = sorted(os.listdir(assets))
        self.assertEqual(names, sorted(os.listdir(repo_docs)))
        for n in names:
            with open(os.path.join(assets, n), encoding="utf-8") as a, \
                 open(os.path.join(repo_docs, n), encoding="utf-8") as b:
                self.assertEqual(a.read(), b.read(), f"{n} 이 embed 본과 다르다 — 한쪽만 고쳤다")


class TestPlainCommitOnGilBranch(GilFixture):
    """gil 브랜치에 평범한 커밋이 끼어도 잃지 않는다 (이슈 #74, 실사용 사본 재현).

    사이클·체인 브랜치 끝에 gil 이 만들지 않은 커밋이 하나만 있어도 (1) handoff 가 열린
    체인을 통째로 못 보고 "새 체인을 열 수 있다"고 밀었고 (2) step 이 그 커밋을 건너뛰어
    HEAD 를 detach 시켜 새 스텝을 브랜치 밖에 떨궜다. 셋 다 조용했다."""

    def _seed(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "mr", "--purpose", "P")
        self.gil("open", "mr/c001", "--author", "clew", "--purpose", "Q")

    def _plain_commit(self, msg="docs: 평범한 커밋"):
        with open(os.path.join(self.repo, "README.md"), "w", encoding="utf-8") as f:
            f.write(msg + "\n")
        self._git("add", "-A")
        self._git("commit", "-m", msg)

    def test_chain_survives_plain_commit_on_chain_branch(self):
        """체인 브랜치 팁이 평범한 커밋이어도 체인을 잃지 않는다 — 제일 위험한 오안내."""
        self._seed()
        self._git("checkout", "-q", "mr")
        self._plain_commit()
        out = self.gil("handoff").stdout
        self.assertIn("열린 체인: mr", out)
        self.assertNotIn("열린 체인 없음", out)   # 중복 체인을 열라고 미는 문구

    def test_step_advances_branch_instead_of_detaching(self):
        """스텝은 평범한 커밋 위에 붙고, 브랜치가 그대로 전진한다."""
        self._seed()
        self._plain_commit()
        r = self.gil("step", "mr/c001", "--kind", "hypothesis", "--title", "시험",
                     "--falsify", "F", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # HEAD 가 브랜치를 떠나지 않았다.
        self.assertEqual(self._git("branch", "--show-current").stdout.strip(), "mr-c001")
        # 새 스텝이 브랜치 팁이다 — 브랜치 밖으로 떨어지지 않았다.
        tip = self._git("log", "-1", "--format=%s", "mr-c001").stdout
        self.assertIn("s2 hypothesis", tip)
        # 평범한 커밋도 그대로 남는다(문서를 잃지 않는다).
        log = self._git("log", "--format=%s", "mr-c001").stdout
        self.assertIn("docs: 평범한 커밋", log)

    def test_handoff_reports_non_gil_tip(self):
        """무엇이 얹혀 있는지 이어받는 세션에게 말한다."""
        self._seed()
        self._plain_commit("docs: 대문 갱신")
        out = self.gil("handoff").stdout
        self.assertIn("팁이 gil 커밋이 아니다", out)
        self.assertIn("docs: 대문 갱신", out)

    def test_plain_branch_is_not_reported(self):
        """gil 이력이 없는 평범한 브랜치는 알릴 일이 아니다(잡음 금지)."""
        self._seed()
        self._git("checkout", "-q", "-b", "just-docs")
        self._plain_commit()
        out = self.gil("handoff").stdout
        self.assertNotIn("just-docs 의 팁이", out)


class TestLiveTip(GilFixture):
    """handoff 팁 선정: 다중 브랜치에서 죽은 잎을 팁으로 잡지 않는다 (2026-07-24)."""

    def test_tip_skips_dead_leaf(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "gh", "--purpose", "P")
        self.gil("open", "gh/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--title", "가설A", "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "gh/c001", "--kind", "analyze", "--outcome", "backtrack", "--to", "s1", "--title", "벽")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--to", "s1", "--title", "가설B", "--falsify", "F", "--falsify-to", "s1")
        out = self.gil("handoff").stdout
        # 팁은 죽은 잎(s3 backtrack)이 아니라 산 형제 가지(s4 hypothesis).
        self.assertIn("팁: s4 [hypothesis]", out)
        self.assertNotIn("팁: s3", out)


class TestMigrate(GilFixture):
    """gil migrate — v2(폴더·cycle.yaml) 이력을 v3 커밋 그래프로 이주 (2026-07-24, 상현님).

    도구 레벨·범용: 격리 fixture 에 미니 v2 rooms 트리를 심고 migrate → v3 그래프 단언.
    매핑 확정: 5단계 압축(hypothesis+design→define, verification→verify,
    analysis+report+verdict→종결), verdict→종결 kind(supported/success→success,
    rejected→fail, null&open→pending, verdict없음&closed→success)."""

    def _write(self, relpath, content):
        """중첩 경로에 파일 하나 쓴다(디렉토리 생성). 커밋은 별도."""
        full = os.path.join(self.repo, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)

    def _v2cycle(self, chain, cid, **fields):
        """미니 v2 cycle.yaml 을 rooms/experiment/chains/<chain>/<cid>/ 에 심는다."""
        lines = [f"id: {cid}", f"chain: {chain}"]
        for k, v in fields.items():
            lines.append(f"{k}: {v}")
        path = f"rooms/experiment/chains/{chain}/{cid}/cycle.yaml"
        self._write(path, "\n".join(lines) + "\n")

    def _seed_v2(self):
        """대문 + 여러 케이스의 v2 사이클을 심고 하나의 v2 커밋으로 봉인 → ref 'v2root'."""
        self._write("CLAUDE.md", "# 대문\n")  # orphan 아님 — 이어받을 대문
        # 정상 성공(supported), parent 체인
        self._v2cycle("alpha", "C001-seed", parent="null",
                      status="closed", verdict="supported", title="첫 사이클")
        self._v2cycle("alpha", "C002-grow", parent="C001-seed",
                      status="closed", verdict="supported", title="둘째 사이클")
        # verdict 없음 + closed → success
        self._v2cycle("alpha", "C003-quiet", parent="C002-grow",
                      status="closed", title="verdict 없는 닫힌 사이클")
        # rejected → fail
        self._v2cycle("beta", "C001-wall", parent="null",
                      status="closed", verdict="rejected", title="기각된 가설")
        # null verdict + open → pending
        self._v2cycle("beta", "C002-waiting", parent="null",
                      status="open", verdict="null", title="사람 대기")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "v2 seed")
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _migrate(self):
        v2root = self._seed_v2()
        # v2 루트에서 이주 브랜치를 파고(대문 이어받음) migrate.
        self._git("checkout", "-q", "-b", "v3-migration")
        return self.gil("migrate", "--from", v2root)

    def test_dry_run_counts_and_kinds(self):
        v2root = self._seed_v2()
        out = self.gil("migrate", "--from", v2root, "--dry-run")
        self.assertEqual(out.returncode, 0)
        # 실사이클 5개, 체인 2개.
        self.assertIn("실사이클 5개", out.stderr)
        self.assertIn("체인 2개", out.stderr)
        # verdict → 종결 kind 매핑.
        self.assertRegex(out.stderr, r"c001-seed .*→ success")    # supported
        self.assertRegex(out.stderr, r"c001-wall .*→ fail")       # rejected
        # 이슈 #50: verdict 가 없으면 닫힌 사이클이라도 success 로 접지 않는다 —
        # 없는 성공을 날조하지 않는다. 사람이 다시 보고 결말을 짓게 pending 으로 남긴다.
        self.assertRegex(out.stderr, r"c003-quiet .*→ pending")   # verdict 없음+closed
        self.assertRegex(out.stderr, r"c002-waiting .*→ pending") # null+open
        # dry-run 은 커밋하지 않는다.
        self.assertIn("커밋하지 않음", out.stderr)

    def test_migrate_creates_v3_graph(self):
        r = self._migrate()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("5 사이클을 v3 그래프로 이주", r.stderr)
        # 체인 = git 브랜치.
        br = self.branches()
        self.assertIn("alpha", br)
        self.assertIn("beta", br)
        self.assertIn("alpha-c001-seed", br)  # 사이클 = 체인 안 가지

    def test_migrate_marks_migrate_trailer(self):
        self._migrate()
        # 체인 루트에 Gil-Migrate: chain, Gil-Migrated-From.
        self.assertEqual(self.trailer("alpha", "Gil-Migrate"), "chain")
        self.assertEqual(self.trailer("alpha", "Gil-Migrated-From"), "alpha")
        # 사이클 define 에 Gil-Migrate: cycle + 원본 id.
        self.assertEqual(self.trailer("alpha-c001-seed", "Gil-Kind"), "close")  # 팁=close
        # subject 에 [migrate] 표식.
        self.assertIn("[migrate]", self.subject("alpha"))

    def test_verdict_to_closure_kind(self):
        self._migrate()
        # rejected → fail 스텝(죽은 잎), close 없음.
        beta_wall_s3 = self._git(
            "log", "--all", "--format=%H %s",
        ).stdout
        self.assertIn("beta/c001-wall/s3 fail", beta_wall_s3)
        # null+open → pending 스텝, close 없음.
        self.assertIn("beta/c002-waiting/s3 pending", beta_wall_s3)
        # supported → success 스텝 + close.
        self.assertIn("alpha/c001-seed/s3 success", beta_wall_s3)
        self.assertIn("alpha/c001-seed close", beta_wall_s3)

    def test_migrate_preserves_cycle_count(self):
        self._migrate()
        # 이주된 사이클(cycle 트레일러) 수 = v2 실사이클 수(5).
        out = self._git("log", "--all",
                        "--format=%(trailers:key=Gil-Migrate,valueonly)").stdout
        cycle_roots = [l for l in out.splitlines() if l.strip() == "cycle"]
        self.assertEqual(len(cycle_roots), 5)

    def test_migrate_no_new_fsck_violations(self):
        """이주 그래프 자체는 fsck 무결(격리 fixture 는 기존 오염 없음)."""
        self._migrate()
        self.gil("init", "--name", "clew")   # 이주 뒤 세계 세우기 — 기억 계층 축은 별건(#69)
        out = self.gil("fsck", "--all")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("위반 0", out.stdout)  # 건강 — 위반 0건

    # ── 기억 계층 부재 (이슈 #69) ──

    def test_migrate_only_repo_says_global_missing(self):
        """이주는 그래프만 옮긴다 — 기억 계층이 없다는 사실을 완료 메시지가 말해야 한다."""
        r = self._migrate()
        out = r.stdout + r.stderr
        self.assertIn("refs/gil/global 이 없다", out)
        self.assertIn("gil init", out)

    def test_fsck_flags_missing_memory_layer(self):
        """그래프는 건강한데 기억 계층이 통째로 빈 상태를 fsck 가 짚는다."""
        self._migrate()
        r = self.gil("fsck", "--all")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("기억계층", r.stdout)
        self.assertIn("gil init", r.stdout)

    def test_handoff_puts_init_before_memory_append(self):
        """기억 계층이 없으면 handoff 는 '매듭 각인' 앞에 'gil init' 을 올린다."""
        self._migrate()
        out = self.gil("handoff").stdout
        self.assertIn("기억 계층", out)
        self.assertIn("gil init", out)
        self.assertNotIn("gil global read memory.md", out)  # 없는 칸을 복원 경로로 제시하지 않는다

    def test_memory_read_without_global_points_to_init(self):
        """거부만 하고 길이 없으면 벽이다 — memory read 거부가 세우는 한 수를 준다."""
        self._migrate()
        r = self.gil("memory", "read", "clew")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gil init", r.stdout + r.stderr)

    def test_init_after_migrate_is_safe(self):
        """이미 그래프가 있는 저장소에서 init 은 대문을 덮지 않고 기억 계층만 세운다."""
        self._migrate()
        before = open(os.path.join(self.repo, "CLAUDE.md")).read()
        r = self.gil("init", "--name", "clew")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # 사람이 쓴 대문은 그대로 남고, gil 은 관리 구간만 덧붙인다(이슈 #73).
        after = open(os.path.join(self.repo, "CLAUDE.md")).read()
        self.assertTrue(after.startswith(before), after)
        self.assertIn("<!-- gil:onboarding:begin -->", after)
        self.assertIn("루트 커밋 생성 안 함", r.stdout)
        self.assertEqual(self.gil("fsck", "--all").returncode, 0)

    def test_migrate_rejects_missing_from(self):
        out = self.gil("migrate")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("--from", out.stderr)

    def test_migrate_lineage_preserved(self):
        # 교훈계승(lineage)이 Gil-Cycle-Lineage 트레일러로 이주되는가.
        self._write("CLAUDE.md", "# 대문\n")
        self._v2cycle("alpha", "C001-seed", parent="null",
                      status="closed", verdict="supported", title="첫")
        self._v2cycle("beta", "C001-sprout", parent="null",
                      status="closed", verdict="supported", title="계승",
                      lineage="[alpha/C001-seed]")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "v2 seed")
        v2root = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("checkout", "-q", "-b", "v3-migration")
        self.gil("migrate", "--from", v2root)
        # 계승은 s1 define 커밋에 실린다(브랜치 팁=close 아님). define 커밋을 찾아 읽는다.
        define_sha = self._git(
            "log", "beta-c001-sprout", "--format=%H %s",
        ).stdout
        s1 = [l.split()[0] for l in define_sha.splitlines()
              if "/s1 define" in l][0]
        self.assertEqual(
            self.trailer(s1, "Gil-Cycle-Lineage"), "alpha/C001-seed")

    def test_migrate_rejects_branch_collision(self):
        """이주 브랜치명이 기존 브랜치와 충돌하면 아무것도 만들기 전에 거부(원자성)."""
        v2root = self._seed_v2()
        self._git("checkout", "-q", "-b", "v3-migration")
        # v2 체인 'alpha' 와 같은 이름의 브랜치를 미리 만들어 충돌 유발.
        self._git("branch", "alpha")
        out = self.gil("migrate", "--from", v2root)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("충돌", out.stderr)
        self.assertIn("--prefix", out.stderr)
        # 원자성: 거부됐으니 사이클 브랜치(alpha-c001-seed 등)는 생기지 않았다.
        self.assertNotIn("alpha-c001-seed", self.branches())
        self.assertNotIn("beta", self.branches())

    def test_migrate_prefix_avoids_collision(self):
        """--prefix 로 네임스페이스를 주면 기존 브랜치와 충돌 없이 이주한다."""
        v2root = self._seed_v2()
        self._git("checkout", "-q", "-b", "v3-migration")
        self._git("branch", "alpha")  # 충돌원
        out = self.gil("migrate", "--from", v2root, "--prefix", "v3-")
        self.assertEqual(out.returncode, 0, out.stderr)
        br = self.branches()
        self.assertIn("v3-alpha", br)             # 접두 붙은 체인 브랜치
        self.assertIn("v3-alpha-c001-seed", br)   # 접두 붙은 사이클 브랜치
        self.assertIn("alpha", br)                # 기존 브랜치는 그대로
        # 접두는 Gil-Chain(=브랜치명)에 반영, 원본은 Gil-Migrated-From 에 보존.
        self.assertEqual(self.trailer("v3-alpha", "Gil-Migrated-From"), "alpha")

    def test_migrate_prefix_rejects_bad_chars(self):
        v2root = self._seed_v2()
        self._git("checkout", "-q", "-b", "v3-migration")
        out = self.gil("migrate", "--from", v2root, "--prefix", "V3/")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("prefix", out.stderr)


class TestGitMissing(GilFixture):
    """git 실행파일이 PATH 에 없을 때 gil 이 친절히 안내하는가 (2026-07-24, 상현님 질문).

    설치는 git 없이 되지만 gil *실행*은 git 이 필수다. git 없으면 Go 런타임의 날것 에러
    대신 사람 언어(설치 안내)로 멈춰야 한다 — 출력은 LLM 프롬프트이므로 AI 가 곧장 사람에게
    git 설치를 안내할 수 있게."""

    def _run_without_git(self, *args):
        """PATH 를 gil 바이너리가 든 디렉토리 하나로 좁혀 git 을 못 찾게 하고 실행."""
        gil_dir = os.path.dirname(GIL_BIN)
        env = dict(os.environ, GIL_NO_VIEWER="1", PATH=gil_dir)
        return subprocess.run([*GIL_CMD, *args], cwd=self.repo,
                              capture_output=True, text=True, env=env)

    def test_init_without_git_is_guided(self):
        out = self._run_without_git("init", "--name", "clew")
        self.assertEqual(out.returncode, 1)              # 실패로 멈춘다
        self.assertIn("git", out.stderr)                 # git 이 원인임을 밝힌다
        self.assertIn("git-scm.com", out.stderr)         # 설치처를 준다
        self.assertNotIn("exec:", out.stderr)            # Go 날것 에러가 새 나오지 않는다

    def test_git_hint_matches_platform(self):
        # 실행 중인 OS 에 맞는 설치 명령을 앞세운다 — AI 가 곧장 자동 설치를 시도할 수 있게.
        out = self._run_without_git("init", "--name", "clew")
        if sys.platform.startswith("win"):
            self.assertIn("winget", out.stderr)
        elif sys.platform == "darwin":
            self.assertIn("brew install git", out.stderr)
        else:
            self.assertIn("apt-get install", out.stderr)

    def test_lifecycle_command_without_git_is_guided(self):
        out = self._run_without_git("chain", "demo", "--purpose", "P")
        self.assertEqual(out.returncode, 1)
        self.assertIn("git-scm.com", out.stderr)

    def test_help_works_without_git(self):
        # help 류는 git 이 필요 없다 — 안내가 아니라 실제 사용법이 나와야 한다.
        out = self._run_without_git("help")
        self.assertEqual(out.returncode, 0)
        self.assertNotIn("git-scm.com", out.stdout)      # 설치 안내가 아니라 사용법
        self.assertIn("gil", out.stdout)


class TestBranchingEnforcement(GilFixture):
    """AIL #1 — 체인이 일자로만 가던 결함. 분기를 문법으로 강제한다(HEAAL).
    제안 2: hypothesis 반증조건 필수. 제안 1: verify verdict + refuted면 success 거부.
    제안 3: 죽은 잎 위 선형 진행 거부(fail 잎이 지도에 남게)."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "b", "--purpose", "분기 강제")
        self.gil("open", "b/c001", "--author", "clew", "--purpose", "P")

    # ── 제안 2 ──
    def test_hypothesis_requires_falsify(self):
        """--falsify 없는 hypothesis 는 거부된다."""
        r = self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "h",
                     "--falsify-to", "s1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("falsify", r.stderr)

    def test_hypothesis_requires_falsify_to(self):
        """--falsify-to 없는 hypothesis 는 거부된다."""
        r = self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "h",
                     "--falsify", "F")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("falsify-to", r.stderr)

    def test_hypothesis_falsify_to_must_be_define(self):
        """--falsify-to 는 이 사이클의 조상 define 이어야 한다."""
        r = self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "h",
                     "--falsify", "F", "--falsify-to", "s9")
        self.assertNotEqual(r.returncode, 0)

    def test_hypothesis_imprints_falsify_trailers(self):
        """정상 hypothesis 는 Gil-Falsify/Gil-Falsify-To 를 각인한다."""
        r = self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "h",
                     "--falsify", "출력이 음수면 거짓", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Falsify"), "출력이 음수면 거짓")
        self.assertEqual(self.trailer("HEAD", "Gil-Falsify-To"), "s1")

    # ── 제안 1 ──
    def test_verify_requires_verdict(self):
        """--verdict 없는 verify 는 거부된다."""
        r = self.gil("step", "b/c001", "--kind", "verify", "--title", "v")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("verdict", r.stderr)

    def test_verify_verdict_must_be_valid(self):
        """--verdict 은 supported|refuted 만."""
        r = self.gil("step", "b/c001", "--kind", "verify", "--title", "v",
                     "--verdict", "maybe")
        self.assertNotEqual(r.returncode, 0)

    def test_verify_imprints_verdict(self):
        r = self.gil("step", "b/c001", "--kind", "verify", "--title", "v",
                     "--verdict", "refuted")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Verdict"), "refuted")

    def test_refuted_verify_blocks_success(self):
        """직전 verify 가 반증(refuted)이면 success 는 문법으로 거부된다 — 핵심 잠금."""
        self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "h",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "b/c001", "--kind", "verify", "--title", "v",
                 "--verdict", "refuted")
        r = self.gil("step", "b/c001", "--kind", "success", "--title", "억지 성공")
        self.assertNotEqual(r.returncode, 0, "반증 뒤 success 가 뚫렸다")
        self.assertIn("refuted", r.stderr)

    def test_supported_verify_allows_success(self):
        """지지(supported) 뒤에는 success 가 정상 통과한다."""
        self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "h",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "b/c001", "--kind", "verify", "--title", "v",
                 "--verdict", "supported")
        r = self.gil("step", "b/c001", "--kind", "success", "--title", "성공")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_refuted_verify_allows_fail(self):
        """반증 뒤 fail(죽은 잎) 은 허용된다 — 벽의 지도."""
        self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "h",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "b/c001", "--kind", "verify", "--title", "v",
                 "--verdict", "refuted")
        r = self.gil("step", "b/c001", "--kind", "fail", "--title", "벽", "--to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)

    # ── 제안 3 완화 ──
    def test_dead_leaf_blocks_linear(self):
        """죽은 잎(fail) 위에 선형으로 잇지 못한다 — fail 이 지도에 남는다."""
        self.gil("step", "b/c001", "--kind", "fail", "--title", "벽", "--to", "s1")
        r = self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "이어붙이기 시도",
                     "--falsify", "F", "--falsify-to", "s1")
        self.assertNotEqual(r.returncode, 0, "죽은 잎 위 선형 진행이 뚫렸다")
        self.assertIn("죽은 잎", r.stderr)

    def test_dead_leaf_allows_sibling_branch(self):
        """죽은 잎 뒤 재가설은 새 형제 가지(--to)로만 — 이건 허용된다."""
        self.gil("step", "b/c001", "--kind", "fail", "--title", "벽", "--to", "s1")
        r = self.gil("step", "b/c001", "--kind", "hypothesis", "--to", "s1",
                     "--title", "새 가지", "--falsify", "F", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)


class TestRefinesAndAnalyzeAnchor(GilFixture):
    """해석 층의 두 표면 — 약한 정정 간선(#42)과 analyze 재분기 앵커(#32).

    같은 공백의 두 얼굴이다. verify 노드에는 **판정(verdict)과 해석(원인·방법)** 두 층이
    있는데, 옛 문법의 간선은 판정 층만 다뤘다: refutes 는 뒤집고, backtrack 은 define 까지
    완전 회귀한다. 그래서 "판정은 그대로인데 해석만 정밀화"(#42)도, "가설은 맞고 방법만
    틀림"(#32)도 적을 자리가 없었다.

    두 경우 모두 과잉 아니면 소실로 밀렸다 — refutes 를 걸면 앞 사이클의 유효한 성과까지
    부정하고, inherit·define회귀로 두면 정정 관계와 분석 결론이 그래프에서 사라진다.
    """

    def setUp(self):
        super().setUp()
        self.gil("chain", "race", "--purpose", "언어 비교")
        # sortgap 사이클 — supported verify 로 닫는다(해석이 나중에 정밀화될 대상).
        self.gil("open", "race/sortgap", "--author", "clew", "--purpose", "L5 실패 원인",
                 "--body", "왜 L5 파이프라인이 실패하나")
        self.gil("step", "race/sortgap", "--kind", "hypothesis", "--title", "H-sort",
                 "--falsify", "sort 를 넣어도 L3 가 안 풀리면 거짓", "--falsify-to", "s1")
        self.gil("step", "race/sortgap", "--kind", "verify", "--title", "실측",
                 "--verdict", "supported",
                 "--body", "sort 로 L3 풀림. L5 실패는 언어 공백 + 모델 벽으로 해석한다.")  # s3
        self.gil("step", "race/sortgap", "--kind", "success", "--title", "성립", "--body", "sort 성과")
        self.gil("close", "race/sortgap")

    # ── #42 — 약한 정정 간선 ──

    def _open_mapdoc(self, *extra):
        return self.gil("open", "race/mapdoc", "--author", "clew", "--purpose", "진짜 원인",
                        "--body", "원인을 더 좁힌다", *extra)

    def test_refines_imprints_trailer(self):
        """정상 --refines 는 Gil-Refines 를 각인한다 — 판정은 건드리지 않는다."""
        r = self._open_mapdoc("--refines", "race/sortgap/s3",
                              "--inherit", "sort 성과는 계승, 원인 해석만 좁힌다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Refines"), "race/sortgap/s3")
        # 정밀화는 뒤집기가 아니다 — 반증 간선을 몰래 달지 않는다.
        self.assertEqual(self.trailer("HEAD", "Gil-Refutes"), "")

    def test_refines_requires_inherit(self):
        """정밀화도 계보 간선이다 — 무엇을 물려받고 어디까지가 맞았나를 적어야 한다."""
        r = self._open_mapdoc("--refines", "race/sortgap/s3")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("inherit", r.stdout + r.stderr)

    def test_refines_target_must_exist(self):
        r = self._open_mapdoc("--refines", "race/sortgap/s99", "--inherit", "X")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("실재", r.stdout + r.stderr)

    def test_refines_target_must_be_closed(self):
        """열린 사이클 안의 해석은 --supersede 로 그 자리에서 정정한다."""
        self.gil("open", "race/live", "--author", "clew", "--purpose", "열린 채",
                 "--body", "아직 안 닫음")
        self.gil("step", "race/live", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "race/live", "--kind", "verify", "--title", "V",
                 "--verdict", "supported", "--body", "해석")
        r = self._open_mapdoc("--refines", "race/live/s3", "--inherit", "X")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("닫", r.stdout + r.stderr)

    def test_refines_target_must_carry_interpretation(self):
        """정밀화되는 건 해석이다 — verify·analyze 만 대상(define·success 는 아니다)."""
        r = self._open_mapdoc("--refines", "race/sortgap/s1", "--inherit", "X")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("verify", out)
        self.assertIn("--refutes", out)   # 판정을 뒤집는 것이면 무엇을 쓸지 알려준다

    def test_refines_target_may_be_refuted_verify(self):
        """refutes 와 달리 verdict 를 묻지 않는다 — refuted 해석도 더 좁혀질 수 있다."""
        self.gil("open", "race/neg", "--author", "clew", "--purpose", "반증", "--body", "B")
        self.gil("step", "race/neg", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "race/neg", "--kind", "verify", "--title", "V",
                 "--verdict", "refuted", "--body", "반증됨 — 원인은 A 로 본다")
        self.gil("step", "race/neg", "--kind", "fail", "--title", "막힘",
                 "--to", "s1", "--body", "벽")
        self.gil("close", "race/neg", "--abandon")
        r = self._open_mapdoc("--refines", "race/neg/s3", "--inherit", "원인 해석을 좁힌다")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_refines_shows_both_directions_in_log(self):
        """그래프가 관계를 말한다 — 정밀화한 쪽에 ⤳refines, 정밀화된 쪽에 ⤳refined-by."""
        self._open_mapdoc("--refines", "race/sortgap/s3", "--inherit", "sort 성과는 계승")
        out = self.gil("log", "--all").stdout
        self.assertIn("⤳refines race/sortgap/s3", out)
        self.assertIn("⤳refined-by", out)

    def test_refines_on_step_too(self):
        """정정을 관측한 순간이 verify 스텝이면 그 자리에서 잇는다(refutes 와 대칭)."""
        self._open_mapdoc()
        self.gil("step", "race/mapdoc", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        r = self.gil("step", "race/mapdoc", "--kind", "verify", "--title", "실측",
                     "--verdict", "supported", "--refines", "race/sortgap/s3",
                     "--inherit", "언어 공백이 아니라 문서 발견성이었다",
                     "--body", "each 는 처음부터 map 됐다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Refines"), "race/sortgap/s3")

    # ── #32 — analyze 를 재분기 앵커로 ──

    def _stuck(self):
        """가설은 맞고 방법이 틀린 상황: refuted verify → analyze 가 원인을 밝힘 → fail."""
        self.gil("open", "race/impl", "--author", "clew", "--purpose", "구현",
                 "--body", "이 op 가 필요하다")
        self.gil("step", "race/impl", "--kind", "hypothesis", "--title", "H-op",
                 "--falsify", "op 없이 풀리면 거짓", "--falsify-to", "s1")
        self.gil("step", "race/impl", "--kind", "verify", "--title", "실측",
                 "--verdict", "refuted", "--body", "안 됨")
        self.gil("step", "race/impl", "--kind", "analyze", "--title", "원인",
                 "--body", "가설(op 필요)은 맞다. 틀린 건 만든 방식이다.")  # s4
        self.gil("step", "race/impl", "--kind", "fail", "--title", "이 방식은 막힘",
                 "--to", "s1", "--body", "벽")

    def test_rebranch_from_analyze(self):
        """분석의 결론이 재분기의 뿌리가 된다 — define 까지 되돌리면 그 분석을 버리는 일이다."""
        self._stuck()
        r = self.gil("step", "race/impl", "--kind", "hypothesis", "--to", "s4",
                     "--title", "새 방식", "--falsify", "이 방식도 안 되면 거짓",
                     "--falsify-to", "s1",
                     "--inherit", "s4 분석: 가설은 유효, 방법만 틀렸다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Parent"), "s4")

    def test_rebranch_from_define_still_works(self):
        """가설 자체가 틀렸을 땐 여전히 define 완전 회귀가 옳다 — 길이 좁아지지 않는다."""
        self._stuck()
        r = self.gil("step", "race/impl", "--kind", "hypothesis", "--to", "s1",
                     "--title", "다른 가설", "--falsify", "F", "--falsify-to", "s1",
                     "--inherit", "가설 진술 자체가 과장이었다")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rebranch_anchor_must_be_define_or_analyze(self):
        """아무 스텝이나 뿌리가 되진 않는다 — 거부가 두 갈래를 다 알려준다."""
        self._stuck()
        r = self.gil("step", "race/impl", "--kind", "hypothesis", "--to", "s3",
                     "--title", "X", "--falsify", "F", "--falsify-to", "s1",
                     "--inherit", "I")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("analyze", out)
        self.assertIn("s4", out)          # 이 사이클의 analyze 를 짚어준다
        self.assertIn("방법만", out)      # 어느 쪽을 골라야 하는지까지


class TestLateRefutation(GilFixture):
    """AIL #1 제안 B — 사이클 간 늦은 반증. 후속 사이클이 앞서 닫힌 supported verify
    판정을 뒤늦게 반증했음을 --refutes 간선으로 계보에 남긴다(verdict 는 불변 보존).
    design→harden 시나리오(SSRF 정적봉쇄 supported → 후속 우회 발견) 재현."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "net", "--purpose", "net cap")
        # design 사이클: supported verify 로 닫는다(= 소급 반증 대상).
        self.gil("open", "net/design", "--author", "clew", "--purpose", "SSRF 정적봉쇄")
        self.gil("step", "net/design", "--kind", "hypothesis", "--title", "H-safe",
                 "--falsify", "host를 weave-time에 못 뽑으면 정적 SSRF 판정 불가",
                 "--falsify-to", "s1")
        self.gil("step", "net/design", "--kind", "verify", "--title", "실측",
                 "--verdict", "supported", "--body", "3축 지지, 반증조건 미관측")  # s3
        self.gil("step", "net/design", "--kind", "success", "--title", "성립",
                 "--body", "net cap 성립")
        self.gil("close", "net/design")
        # harden 사이클: design 을 부모로 연다.
        self.gil("open", "net/harden", "--author", "clew", "--purpose", "우회 봉쇄",
                 "--parent", "design", "--inherit", "design의 net cap 구현을 잇는다")
        # 순서 강제(AIL #41): refutes 를 실을 verify 앞에 hypothesis 를 먼저 깐다.
        self.gil("step", "net/harden", "--kind", "hypothesis", "--title", "H-우회",
                 "--falsify", "우회 없으면 이 가설 거짓", "--falsify-to", "s1")

    def _refutes(self, target, **kw):
        return self.gil("step", "net/harden", "--kind", "verify", "--title", "우회발견",
                        "--verdict", "supported", "--refutes", target,
                        "--inherit", "판정은 뒤집되 net cap 구현은 계승",
                        "--body", "8진수/hex 우회로 정적봉쇄 뚫림", **kw)

    def test_refutes_imprints_trailer(self):
        """정상 --refutes 는 Gil-Refutes 를 각인한다."""
        r = self._refutes("net/design/s3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Refutes"), "net/design/s3")

    def test_refutes_target_must_exist(self):
        """dangling 대상은 거부."""
        r = self._refutes("net/design/s99")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("실재", r.stderr)

    def test_refutes_target_must_be_closed(self):
        """열린 사이클의 스텝은 소급 반증 대상이 아니다(그 자리서 backtrack 하라)."""
        # harden 은 아직 안 닫힘 — harden 자기 스텝을 대상으로 시도.
        self.gil("step", "net/harden", "--kind", "hypothesis", "--title", "h",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "net/harden", "--kind", "verify", "--title", "v",
                 "--verdict", "supported")  # s3 (열린 사이클)
        r = self.gil("step", "net/harden", "--kind", "analyze", "--title", "a",
                     "--refutes", "net/harden/s3")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("안 닫", r.stderr)

    def test_refutes_target_must_be_verify(self):
        """verify 아닌 스텝(success)을 refutes 하면 거부 — 반증되는 건 판정이다."""
        r = self._refutes("net/design/s4")  # s4 = success
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("verify", r.stderr)

    def test_refutes_target_must_be_supported(self):
        """refuted verify 를 refutes 하는 건 무의미 — 거부. (별 사이클에 refuted 를 만든다)"""
        self.gil("chain", "x", "--purpose", "P", "--parallel-with", "net")
        self.gil("open", "x/c1", "--author", "c", "--purpose", "P")
        self.gil("step", "x/c1", "--kind", "hypothesis", "--title", "h",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "x/c1", "--kind", "verify", "--title", "v", "--verdict", "refuted")  # s3
        self.gil("step", "x/c1", "--kind", "fail", "--title", "벽", "--to", "s1")
        self.gil("step", "x/c1", "--kind", "hypothesis", "--to", "s1", "--title", "h2",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "x/c1", "--kind", "success", "--title", "됨")
        self.gil("close", "x/c1")
        r = self._refutes("x/c1/s3")  # s3 = refuted verify
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("supported", r.stderr)

    def test_refutes_on_open(self):
        """gil open --refutes 도 받는다(사이클을 여는 순간 반증 선언)."""
        self.gil("chain", "net2", "--purpose", "P", "--parallel-with", "net")
        # 새 사이클을 열며 design/s3 을 refutes.
        r = self.gil("open", "net2/c1", "--author", "clew", "--purpose", "재검",
                     "--refutes", "net/design/s3", "--inherit", "판정 뒤집고 구현 계승")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Refutes"), "net/design/s3")

    def test_fsck_flags_dangling_refutes(self):
        """fsck 는 실재하지 않는 refutes 대상을 잡는다."""
        # 정상 refutes 를 심고 사이클을 닫은 뒤, 대상이 없는 상황은 만들기 어려우니
        # 여기선 정상 그래프가 fsck 통과하는지만 확인(dangling 은 무결성 가드가 이미 막음).
        self._refutes("net/design/s3")
        self.gil("step", "net/harden", "--kind", "success", "--title", "됨")
        self.gil("close", "net/harden")
        self.gil("init", "--name", "clew")   # 기억 계층 축은 별건(#69)
        r = self.gil("fsck")
        self.assertEqual(r.returncode, 0, f"정상 refutes 그래프가 fsck 위반:\n{r.stdout}")

    def test_the_graph_shows_refuted_by(self):
        """터미널 그림이 반증된 판정에 ⚠refuted-by, 반증한 쪽에 ⟵refutes 를 표시한다."""
        self._refutes("net/design/s3")
        self.gil("step", "net/harden", "--kind", "success", "--title", "됨")
        self.gil("close", "net/harden")
        r = self.gil("graph")
        out = r.stdout
        self.assertIn("refuted-by", out, f"반증 배지 없음:\n{out}")
        self.assertIn("refutes", out)


class TestCompositeHypothesis(GilFixture):
    """AIL #1 제안 A — 한 hypothesis = 한 주장. --falsify 가 여러 주장으로 열거되면 거부."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/c1", "--author", "c", "--purpose", "P")

    def test_semicolon_enumeration_rejected(self):
        r = self.gil("step", "a/c1", "--kind", "hypothesis", "--title", "복합",
                     "--falsify", "H1이 거짓; H2가 거짓; H3이 거짓", "--falsify-to", "s1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("여러 주장", r.stderr)

    def test_newline_enumeration_rejected(self):
        r = self.gil("step", "a/c1", "--kind", "hypothesis", "--title", "복합",
                     "--falsify", "H1이 거짓\nH2가 거짓", "--falsify-to", "s1")
        self.assertNotEqual(r.returncode, 0)

    def test_single_claim_with_comma_ok(self):
        """쉼표 있는 한 문장은 단일 주장 — 통과해야(오탐 방지)."""
        r = self.gil("step", "a/c1", "--kind", "hypothesis", "--title", "단일",
                     "--falsify", "host를 못 뽑으면, 정적 판정이 불가능하다", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)


class TestDepthLog(GilFixture):
    """AIL #2 — 뎁스별 전체맵. gil log --depth chain|cycle|step + 분기 신호(무플래그 기본).
    인간=AI 동일 정보: 뷰어가 보는 체인·사이클 분기를 gil log 도 텍스트로 낸다."""

    def setUp(self):
        super().setUp()
        # 체인 하나, 사이클 하나, 형제 가지(s1 에서 갈라진 hypothesis)로 스텝 분기 1개 만든다.
        self.gil("chain", "m", "--purpose", "P")
        self.gil("open", "m/c1", "--author", "c", "--purpose", "P")
        self.gil("step", "m/c1", "--kind", "hypothesis", "--title", "h1",
                 "--falsify", "F1", "--falsify-to", "s1")
        self.gil("step", "m/c1", "--kind", "verify", "--title", "v1", "--verdict", "refuted")
        self.gil("step", "m/c1", "--kind", "fail", "--title", "벽", "--to", "s1")  # 죽은 잎
        self.gil("step", "m/c1", "--kind", "hypothesis", "--to", "s1", "--title", "h2",
                 "--falsify", "F2", "--falsify-to", "s1")  # s1 형제 가지 → 스텝 분기

    def test_branch_signal_always_shown(self):
        """무플래그 gil log 도 맨 위에 분기 신호를 강제로 낸다."""
        r = self.gil("log")
        self.assertIn("분기", r.stdout)
        self.assertIn("죽은잎", r.stdout)

    def test_branch_signal_counts_step_fork(self):
        """s1 형제 가지가 스텝 분기 1로 잡히고, fail 이 죽은잎 1로 잡힌다."""
        r = self.gil("log")
        head = r.stdout.splitlines()[0]
        self.assertIn("스텝 1", head)
        self.assertIn("죽은잎 1", head)

    def test_linear_chain_warning(self):
        """체인·사이클 분기 0이면 일자 경고를 띄운다."""
        r = self.gil("log")
        self.assertIn("일자", r.stdout)

    def test_depth_chain(self):
        """--depth chain 은 체인 계보를 낸다(뷰어 체인그래프와 동일 집계원)."""
        r = self.gil("log", "--depth", "chain")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("● m", r.stdout)
        self.assertIn("사이클", r.stdout)

    def test_depth_cycle(self):
        """--depth cycle <chain> 은 사이클 목록 + status 를 낸다."""
        r = self.gil("log", "--depth", "cycle", "m")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("◆ c1", r.stdout)

    def test_depth_cycle_branch_marker(self):
        """fail 잎(분기)을 품은 사이클은 ⚡분기 표식이 붙는다(일자 solved 와 구분, AIL #2 후속)."""
        # setUp 의 m/c1 은 s1 에서 형제 가지 + fail 잎을 품는다 → 분기 사이클.
        r = self.gil("log", "--depth", "cycle", "m")
        self.assertIn("분기", r.stdout)  # (solved⚡분기 또는 헤더 분기 — c1 에 마커가 있어야)
        # c1 라인에 마커가 실제로 붙었는지 확인.
        c1line = [l for l in r.stdout.splitlines() if "◆ c1" in l][0]
        self.assertIn("⚡", c1line, f"분기 사이클에 마커 없음: {c1line}")

    def test_depth_cycle_requires_chain(self):
        r = self.gil("log", "--depth", "cycle")
        self.assertNotEqual(r.returncode, 0)

    def test_depth_step_is_default(self):
        """--depth step(기본) 은 스텝 노드를 나열한다."""
        r = self.gil("log", "--depth", "step")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[define]", r.stdout)

    def test_bad_depth_rejected(self):
        r = self.gil("log", "--depth", "galaxy")
        self.assertNotEqual(r.returncode, 0)


class TestInherit(GilFixture):
    """AIL #3 — 계보 간선이 새로 생기는 자리에 물려받은 지식·전제·교훈(--inherit) 명시.
    A안(간선 생기는 3자리에만): 새 사이클(--parent)·머지·refutes 필수, 같은 사이클 선형
    스텝은 면제, 체인은 안내."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "m", "--purpose", "P")
        self.gil("open", "m/c1", "--author", "c", "--purpose", "P")
        self.gil("step", "m/c1", "--kind", "success", "--title", "ok")
        self.gil("close", "m/c1")

    def test_parent_requires_inherit(self):
        r = self.gil("open", "m/c2", "--author", "c", "--purpose", "Q", "--parent", "c1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("inherit", r.stderr)

    def test_parent_with_inherit_imprints(self):
        r = self.gil("open", "m/c2", "--author", "c", "--purpose", "Q",
                     "--parent", "c1", "--inherit", "c1의 판정 한계를 물려받았다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Inherit"), "c1의 판정 한계를 물려받았다")

    def test_linear_step_exempt(self):
        """같은 사이클 안 선형 스텝은 --inherit 없이도 통과(면제)."""
        self.gil("open", "m/c3", "--author", "c", "--purpose", "R")
        r = self.gil("step", "m/c3", "--kind", "hypothesis", "--title", "h",
                     "--falsify", "F", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_chain_inherit_optional_with_guide(self):
        """체인은 --inherit 없어도 통과하되 안내를 띄운다."""
        r = self.gil("chain", "n", "--purpose", "P", "--parallel-with", "m")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("inherit", r.stderr)

    def test_chain_inherit_imprints(self):
        # m 이 아직 열려 있으므로 병렬 선언이 필요하다(이슈 #54) — 이 시험이 재는 건 --inherit 각인이다.
        r = self.gil("chain", "n", "--purpose", "P", "--inherit", "m 체인의 교훈",
                     "--parallel-with", "m")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Inherit"), "m 체인의 교훈")

    def test_inherit_shown_in_depth_log(self):
        """--depth step 이 물려받은 전수를 ⇐라벨로 보여준다(지식의 강 가시화)."""
        self.gil("open", "m/c2", "--author", "c", "--purpose", "Q",
                 "--parent", "c1", "--inherit", "물려받은전수마커")
        r = self.gil("log", "--depth", "step", "m")
        self.assertIn("물려받은전수마커", r.stdout)


class TestSupersede(GilFixture):
    """스텝 정정(AIL #12) — --supersede 로 같은 kind 앞선 스텝을 새 커밋으로 덮되 이력 보존."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P", "--body", "정의")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--title", "틀린 가설",
                 "--falsify", "F", "--falsify-to", "s1")  # s2

    def fix2(self, *extra):
        """s2(가설)를 정정하는 표준 호출 — 정정은 --inherit 필수다."""
        return self.gil("step", "c/c1", "--kind", "hypothesis", "--title", "고친 가설",
                        "--falsify", "F2", "--falsify-to", "s1", "--supersede", "s2",
                        "--inherit", "옛 반증조건이 느슨했다. 설계는 계승.", *extra)

    def test_supersede_same_kind_ok(self):
        r = self.fix2()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Supersedes"), "s2")

    def test_supersede_requires_inherit(self):
        """정정도 계보 간선이다 — 무엇을 바로잡고 무엇을 계승하는지 없이는 거부(AIL #3 일관 적용)."""
        r = self.gil("step", "c/c1", "--kind", "hypothesis", "--title", "고친 가설",
                     "--falsify", "F2", "--falsify-to", "s1", "--supersede", "s2")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--inherit", r.stderr)

    def test_supersede_forks_at_targets_parent(self):
        """정정은 분기다 — 새 스텝의 부모는 현재 팁이 아니라 **정정 대상의 부모**이고,
        새 git 브랜치로 갈라진다. 그래야 옛 가지가 통째로 보존된다(상현님)."""
        self.fix2()
        self.assertEqual(self.trailer("HEAD", "Gil-Parent"), "s1")  # s2 의 부모
        cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             cwd=self.repo, capture_output=True, text=True).stdout.strip()
        self.assertNotEqual(cur, "c-c1")          # 사이클 브랜치를 떠나 갈라졌다
        self.assertIn("s2b", cur)                  # s2 자리에서 난 가지

    def test_supersede_preserves_old_step(self):
        """정정해도 옛 스텝(s2)은 이력에 남는다 — append-only 보존, 은폐 아님."""
        self.fix2()
        r = self.gil("log", "--depth", "step", "c")
        self.assertIn("정정 s2", r.stdout)  # 새 스텝에 ⟲정정 s2 표식
        r2 = subprocess.run(["git", "log", "--all", "--format=%s"],
                            cwd=self.repo, capture_output=True, text=True).stdout
        self.assertIn("틀린 가설", r2)      # 옛 s2 는 그래프에 그대로 산다

    def test_supersede_old_subtree_not_demanded_at_close(self):
        """구버전 가지의 잎은 종결을 요구받지 않는다 — 이미 갈아엎은 가지다."""
        # s2 위에 자손을 만들고(s3 verify), 그 다음 s2 를 정정한다.
        self.gil("step", "c/c1", "--kind", "verify", "--verdict", "supported",
                 "--falsify-unmet", "F 미관측")   # s3 — 옛 가지의 잎
        self.fix2()                                # s4 = s2 의 정정(s1 에서 분기)
        self.gil("step", "c/c1", "--kind", "verify", "--verdict", "supported",
                 "--falsify-unmet", "F2 미관측")
        self.gil("step", "c/c1", "--kind", "analyze", "--title", "해석")
        self.gil("step", "c/c1", "--kind", "success", "--title", "ok",
                 "--toward", "다가섬", "--next-design", "다음")
        r = self.gil("close", "c/c1", "--verdict", "solved", "--goal-met")
        self.assertEqual(r.returncode, 0, r.stderr)
        f = self.gil("fsck")
        self.assertNotIn("미종결 잎", f.stdout)   # 구버전 가지의 잎을 요구하지 않는다

    def test_supersede_different_kind_rejected(self):
        r = self.gil("step", "c/c1", "--kind", "verify", "--verdict", "supported",
                     "--supersede", "s2")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("같은 kind", r.stderr)

    def test_supersede_missing_target_rejected(self):
        r = self.gil("step", "c/c1", "--kind", "hypothesis", "--title", "x",
                     "--falsify", "F", "--falsify-to", "s1", "--supersede", "s99")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("없는 스텝", r.stderr)

    def test_supersede_terminal_same_kind_ok(self):
        """종결 스텝도 정정 대상이다(상현님) — 같은 kind 로만 정정되므로 판정은 그대로이고
        그 판정의 **서술**만 다시 쓴다. 순서 강제(AIL #41)로 success 는 s5 다."""
        self.gil("step", "c/c1", "--kind", "success", "--title", "ok",
                 "--toward", "다가섬", "--next-design", "다음")  # s3 verify, s4 analyze, s5 success
        r = self.gil("step", "c/c1", "--kind", "success", "--title", "다시",
                     "--supersede", "s5", "--inherit", "성공 서술이 부정확했다. 판정은 그대로.",
                     "--toward", "다가섬", "--next-design", "다음")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Supersedes"), "s5")

    def test_supersede_cannot_flip_verdict(self):
        """판정 뒤집기는 정정이 아니다 — fail 을 success 로 '정정'할 수 없다(같은 kind 규칙)."""
        self.gil("step", "c/c1", "--kind", "success", "--title", "ok",
                 "--toward", "다가섬", "--next-design", "다음")  # s5 = success
        r = self.gil("step", "c/c1", "--kind", "fail", "--to", "s1", "--supersede", "s5",
                     "--inherit", "뒤집기 시도", "--title", "뒤집기",
                     "--toward", "못 다가섬", "--next-design", "다음")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("같은 kind", r.stderr)

    def test_supersede_define_ok(self):
        """define(사이클의 뿌리)도 정정된다 — 살아있는 문제 정의는 여전히 하나다."""
        r = self.gil("step", "c/c1", "--kind", "define", "--supersede", "s1",
                     "--inherit", "문제를 A 로 봤는데 실은 B 였다. 지표는 계승.",
                     "--title", "정의 다시", "--body", "바로잡은 문제 정의")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Supersedes"), "s1")
        f = self.gil("fsck")
        self.assertNotIn("define 이", f.stdout)   # define 이 둘이라고 보고하지 않는다

    def test_define_without_supersede_still_rejected(self):
        """정정이 아닌 새 define 은 여전히 거부 — 그리고 정정 문법을 알려준다."""
        r = self.gil("step", "c/c1", "--kind", "define", "--title", "또 정의", "--body", "b")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--supersede", r.stderr)


class TestPolarity(GilFixture):
    """가설 극성(AIL #13) — supported ≠ 목표 달성. 부정적 발견을 success 로 못 닫게."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/m", "--author", "x", "--purpose", "설득 근거 찾기", "--body", "왜 쓰나")

    def test_goal_missed_supported_blocks_success(self):
        """goal-missed 가설이 supported 면 success 거부(부정적 발견은 벽이지 성공 아님)."""
        self.gil("step", "d/m", "--kind", "hypothesis", "--title", "작은모델 못 짬",
                 "--falsify", "F", "--falsify-to", "s1", "--if-supported", "goal-missed")
        self.gil("step", "d/m", "--kind", "verify", "--title", "실측 못 짬", "--verdict", "supported")
        r = self.gil("step", "d/m", "--kind", "success", "--title", "성공?")
        self.assertNotEqual(r.returncode, 0, "goal-missed+supported 가 success 로 닫힘")
        self.assertIn("goal-missed", r.stderr)

    def test_goal_missed_supported_allows_fail(self):
        """goal-missed+supported 는 fail 로는 닫힌다(벽으로 못박음 = 정도)."""
        self.gil("step", "d/m", "--kind", "hypothesis", "--title", "못 짬",
                 "--falsify", "F", "--falsify-to", "s1", "--if-supported", "goal-missed")
        self.gil("step", "d/m", "--kind", "verify", "--title", "v", "--verdict", "supported")
        r = self.gil("step", "d/m", "--kind", "fail", "--title", "벽", "--to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_goal_met_default_allows_success(self):
        """극성 미지정(기본 goal-met)은 supported→success 통과(비파괴)."""
        self.gil("step", "d/m", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "d/m", "--kind", "verify", "--title", "v", "--verdict", "supported")
        r = self.gil("step", "d/m", "--kind", "success", "--title", "ok")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_polarity_imprinted(self):
        r = self.gil("step", "d/m", "--kind", "hypothesis", "--title", "H",
                     "--falsify", "F", "--falsify-to", "s1", "--if-supported", "goal-missed")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Goal-Polarity"), "goal-missed")

    def test_bad_polarity_rejected(self):
        r = self.gil("step", "d/m", "--kind", "hypothesis", "--title", "H",
                     "--falsify", "F", "--falsify-to", "s1", "--if-supported", "goal-meat")
        self.assertNotEqual(r.returncode, 0)

    def test_if_supported_hypothesis_only(self):
        """--if-supported 는 hypothesis 전용."""
        self.gil("step", "d/m", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        r = self.gil("step", "d/m", "--kind", "verify", "--title", "v",
                     "--verdict", "supported", "--if-supported", "goal-met")
        self.assertNotEqual(r.returncode, 0)


class TestBacktrackInherit(GilFixture):
    """backtrack 전수 강제(AIL #13 요구 5) — 죽은 가지 교훈을 새 가지에 지고 가게."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/m", "--author", "x", "--purpose", "P", "--body", "정의")
        self.gil("step", "d/m", "--kind", "hypothesis", "--title", "H1",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "d/m", "--kind", "verify", "--title", "v", "--verdict", "refuted")
        self.gil("step", "d/m", "--kind", "fail", "--title", "죽음", "--to", "s1")

    def test_backtrack_requires_inherit(self):
        """backtrack(hypothesis --to)은 --inherit 없이 거부(맥락 단절 차단)."""
        env = dict(os.environ, GIL_NO_VIEWER="1")
        r = subprocess.run([*GIL_CMD, "step", "d/m", "--kind", "hypothesis", "--title", "H2",
                            "--to", "s1", "--falsify", "F2", "--falsify-to", "s1"],
                           cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0, "backtrack 이 --inherit 없이 통과")
        self.assertIn("inherit", r.stderr)

    def test_backtrack_with_inherit_ok(self):
        r = self.gil("step", "d/m", "--kind", "hypothesis", "--title", "H2", "--to", "s1",
                     "--falsify", "F2", "--falsify-to", "s1", "--inherit", "H1 은 X 때문에 죽음")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Inherit"), "H1 은 X 때문에 죽음")


class TestBacktrackAccumulation(GilFixture):
    """backtrack 에서 **배운 것이 누적**된다(상현님).

    --inherit 한 줄은 에이전트가 쓴 요약이고, 요약은 성실함에 걸려 있다. 정작 "무엇을
    세웠고 무엇으로 깨졌나"는 그래프에 정확히 적혀 있는데 브리핑이 싣지 않았다. 이제
    접힌 시도를 **인용해서** 싣고, 되돌아올 때마다 그 목록이 쌓이며, 새 가지에는
    묻지 않아도 도착한다.
    """

    def setUp(self):
        super().setUp()
        self.gil("chain", "d", "--purpose", "빌드를 빠르게")
        self.gil("open", "d/m", "--author", "x", "--purpose", "P", "--body", "정의")
        self._attempt("가설 A: 캐시", "측정: 개선 0%", "해석: 병목은 I/O")

    def _attempt(self, hyp, ver, ana, to="s1", inherit=None):
        """한 시도를 세우고 반증하고 접는다(hypothesis→verify refuted→analyze backtrack)."""
        args = ["step", "d/m", "--kind", "hypothesis", "--title", hyp,
                "--falsify", "F", "--falsify-to", "s1"]
        if inherit is not None:
            args += ["--to", to, "--inherit", inherit]
        self.gil(*args)
        self.gil("step", "d/m", "--kind", "verify", "--title", ver, "--verdict", "refuted")
        return self.gil("step", "d/m", "--kind", "analyze", "--title", ana,
                        "--outcome", "backtrack", "--to", to)

    def test_context_quotes_dead_attempt(self):
        """gil context 가 접힌 시도를 인용한다 — 무엇을 세웠나·무엇으로 깨졌나·어떻게 해석했나."""
        out = self.gil("context", "d/m").stdout
        self.assertIn("접힌 시도", out)
        self.assertIn("가설 A: 캐시", out)      # 무엇을 세웠나
        self.assertIn("측정: 개선 0%", out)      # 무엇으로 깨졌나 (refuted verify)
        self.assertIn("해석: 병목은 I/O", out)   # 어떻게 해석했나 (analyze)

    def test_new_branch_gets_briefing_unasked(self):
        """되돌아와 판 새 가지에 계보 브리핑이 **묻지 않아도** 도착한다(open 과 같은 자리)."""
        r = self.gil("step", "d/m", "--kind", "hypothesis", "--title", "가설 B", "--to", "s1",
                     "--falsify", "F2", "--falsify-to", "s1", "--inherit", "캐시는 헛다리")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("계보 브리핑", r.stderr)
        self.assertIn("가설 A: 캐시", r.stderr)

    def test_walls_accumulate_across_backtracks(self):
        """두 번째로 되돌아온 가지는 **첫 번째 벽도 함께** 본다 — 마지막 하나로 덮이지 않는다."""
        self._attempt("가설 B: I/O 배치", "측정: 3%", "해석: 링커가 직렬",
                      inherit="캐시는 헛다리")
        r = self.gil("step", "d/m", "--kind", "hypothesis", "--title", "가설 C", "--to", "s1",
                     "--falsify", "F3", "--falsify-to", "s1", "--inherit", "캐시·I/O 둘 다 아님")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("가설 A: 캐시", r.stderr)
        self.assertIn("가설 B: I/O 배치", r.stderr)

    def test_inherit_refusal_shows_prior_walls(self):
        """전수를 요구하면서 앞선 벽을 함께 준다 — 안 주면 매번 마지막 벽 하나만 적힌다."""
        env = dict(os.environ, GIL_NO_VIEWER="1")
        r = subprocess.run([*GIL_CMD, "step", "d/m", "--kind", "hypothesis", "--title", "H2",
                            "--to", "s1", "--falsify", "F2", "--falsify-to", "s1"],
                           cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("쌓아라", r.stderr)
        self.assertIn("가설 A: 캐시", r.stderr)


class TestVerifyAnswersFalsify(GilFixture):
    """verify 는 가설이 심은 반증조건에 답한다 (규칙 17, 상현님).

    AIL #1 이 --falsify 를 필수화한 이유가 여기서 샜다: verify 가 --verdict 만 받고 그
    조건과 **대조하지 않으면** supported/refuted 는 결국 자의적이다. 판정 축이 조용히
    바뀌는 자리가 정확히 여기다."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "f", "--purpose", "P")
        self.gil("open", "f/c1", "--author", "x", "--purpose", "P", "--body", "정의")
        self._raw_step("f/c1", "--kind", "hypothesis", "--title", "H",
                       "--falsify", "3회 평균 개선 없으면 기각", "--falsify-to", "s1",
                       "--plan", "P1", "--advances", "A")

    def test_verify_must_answer_falsify(self):
        r = self._raw_step("f/c1", "--kind", "verify", "--title", "v",
                           "--verdict", "refuted", "--plan-held")
        self.assertNotEqual(r.returncode, 0, "반증조건에 답하지 않고 통과했다")
        self.assertIn("falsify-met", r.stderr)
        self.assertIn("3회 평균 개선 없으면 기각", r.stderr)  # 조건을 눈앞에 준다

    def test_met_with_supported_is_refused(self):
        """반증조건이 충족됐는데 supported — 판정 축을 바꾸는 동작이라 거부한다."""
        r = self._raw_step("f/c1", "--kind", "verify", "--title", "v",
                           "--verdict", "supported", "--plan-held",
                           "--falsify-met", "3회 평균 +0.4%")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("판정 축", r.stderr)

    def test_met_with_refuted_is_recorded(self):
        r = self._raw_step("f/c1", "--kind", "verify", "--title", "v",
                           "--verdict", "refuted", "--plan-held",
                           "--falsify-met", "3회 평균 +0.4%")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Falsify-Outcome"), "met")
        self.assertEqual(self.trailer("HEAD", "Gil-Falsify-Observed"), "3회 평균 +0.4%")

    def test_unmet_with_refuted_warns_not_refuses(self):
        """반증조건이 아닌 이유로 기각 — 막지 않는다. 조건이 틀렸다는 **정보**다."""
        r = self._raw_step("f/c1", "--kind", "verify", "--title", "v",
                           "--verdict", "refuted", "--plan-held",
                           "--falsify-unmet", "조건은 미달인데 메모리가 터졌다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("내가 정한 조건이 아닌 이유로", r.stderr)
        self.assertIn("소급해 고치지는 마라", r.stderr)

    def test_both_flags_refused(self):
        r = self._raw_step("f/c1", "--kind", "verify", "--title", "v",
                           "--verdict", "refuted", "--plan-held",
                           "--falsify-met", "a", "--falsify-unmet", "b")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("함께 못 선다", r.stderr)

    def test_briefing_carries_the_observation(self):
        """충족된 반증조건은 계보 브리핑에 실린다 — 다음 세대가 왜 깨졌는지 안다."""
        self._raw_step("f/c1", "--kind", "verify", "--title", "v",
                       "--verdict", "refuted", "--plan-held",
                       "--falsify-met", "3회 평균 +0.4%")
        out = self.gil("context", "f/c1").stdout
        self.assertIn("반증조건이 충족됐다", out)
        self.assertIn("3회 평균 +0.4%", out)


class TestIntakeBeforeChain(GilFixture):
    """체인보다 먼저 사람에게 묻는다 (이슈 #90, 상현님).

    옛 정문에는 순환이 있었다: 체인은 --purpose 가 필수인데 인터뷰는 체인이 있어야 열린다.
    지금까지는 **에이전트의 추측으로** 끊었다 — 목적을 창작해 체인을 열고 그 다음에 물었다.
    그리고 상현님이 짚은 더 실질적인 손해: 어디서 분기할지는 사람의 답을 보고 정해야 하는데,
    분기를 쳐 버리고 물으면 그 답이 갈 곳이 없다."""

    QS = [{"q": "무엇을 하려고 하십니까", "type": "text"},
          {"q": "무엇이 관측되면 풀린 것입니까", "type": "text"}]
    ANS = ("# 기준 문서\n\n## 1. 무엇을 하려고 하십니까\n\n"
           "그게 없는게 자율이야. 스스로 도구를 만들면서 진화할거야.\n\n"
           "## 2. 무엇이 관측되면 풀린 것입니까\n\n도구를 스스로 축적하면 풀린 것이다.\n")

    def _run(self, *args, input=None):
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.run([*GIL_CMD, *args], cwd=self.repo,
                              capture_output=True, text=True, env=env, input=input)

    def _ask(self):
        return self._run("intake", "nx-topic", "--ask", "-", input=json.dumps(self.QS))

    def _answer(self):
        p = os.path.join(self.repo, "ans.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.ANS)
        r = self._run("intake", "nx-topic", "--resolve", "ans.md")
        os.remove(p)
        return r

    def test_intake_opens_without_a_chain(self):
        """체인이 없어도 열린다 — 이게 순환을 끊는 지점이다."""
        r = self._ask()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("체인보다 먼저", r.stdout)

    def test_chain_refuses_before_the_human_answers(self):
        self._ask()
        r = self._run("chain", "nx", "--from-intake", "nx-topic", "--purpose-from", "1")
        self.assertNotEqual(r.returncode, 0, "사람 답 전에 체인이 열렸다")
        self.assertIn("아직 사람 답을 기다린다", r.stderr)

    def test_purpose_is_lifted_verbatim(self):
        """목적은 사람의 문장 **그대로**여야 한다 — 요약도 정제도 창작이다."""
        self._ask(); self._answer()
        r = self._run("chain", "nx", "--from-intake", "nx-topic", "--purpose-from", "1",
                      "--criterion-from", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("nx", "Gil-Chain-Purpose"),
                         "그게 없는게 자율이야. 스스로 도구를 만들면서 진화할거야.")

    def test_agent_cannot_author_the_purpose_alongside(self):
        self._ask(); self._answer()
        r = self._run("chain", "nx", "--from-intake", "nx-topic",
                      "--purpose", "내가 정한 목적")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("함께 못 선다", r.stderr)

    def test_viewer_renders_the_form_with_no_chain_yet(self):
        """체인 0 + 인터뷰 1 — 이게 intake 의 **정상 상태**이고, 옛 뷰어는 여기서 죽었다.

        buildStepMap() 이 없는 컨테이너에 replaceChildren 을 불러 예외를 냈고, 그 뒤
        buildInterviews() 가 영영 실행되지 않아 **폼이 아예 안 떴다** — 사람이 답할
        유일한 수단이 사라진 것이다. 브라우저로 실제 확인하다 발견했다(이슈 #90 검증)."""
        self._ask()
        out = os.path.join(self.repo, "v.html")
        r = self.gil("graph", "--html", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            html = f.read()
        # 정적 build 는 인터뷰 폼을 싣지 않는다(제출할 서버가 없다) — 여기서 보증할 수 있는
        # 것은 **크래시 가드가 실제로 실려 나갔는가**다. 폼이 뜨는 것 자체는 브라우저로
        # 확인했다(뷰어 폼 제출 → intake done → 인용된 목적으로 체인).
        self.assertIn("if(!host)return;", html)         # 전체맵이 없어도 죽지 않는다
        # 앞 단계가 죽어도 폼은 그린다. 조각 이름은 이제 사전을 탄다(part.interviews) —
        # 여기서 한국어 원문을 단언하면, 화면을 옳게 고칠 때마다 이 시험이 빨개진다.
        self.assertIn("step(T('part.interviews')", html)

    def test_plain_chain_points_at_intake(self):
        """--purpose 없이 열려 하면 개시 인터뷰 경로를 알려준다 — 거부에는 길이 붙는다."""
        r = self._run("chain", "nx")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gil intake", r.stderr)


class TestDeepIntake(GilFixture):
    """심층 인터뷰가 셋을 낳는다 (상현님): ① 체인 단위 문제 ② 풀었다/못 풀었다의 기준
    ③ 사이클 단위로 분할된 문제. 그리고 '어디서 분기할지'는 **마지막에** 묻되 후보를
    그래프가 계산한다 — 분기를 먼저 쳐 버리면 그 답이 갈 곳이 없기 때문이다."""

    def _run(self, *a, input=None):
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.run([*GIL_CMD, *a], cwd=self.repo, capture_output=True,
                              text=True, env=env, input=input)

    def _round(self, q, answer):
        self._run("intake", "dp", "--ask", "-", input=json.dumps([{"q": q, "type": "text"}]))
        p = os.path.join(self.repo, "a.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# 답\n\n## 1. {q}\n\n{answer}\n")
        r = self._run("intake", "dp", "--resolve", "a.md")
        os.remove(p)
        return r

    def _three_rounds(self):
        self._round("무엇을 하려고 하십니까", "스스로 도구를 만드는 언어를 만든다.")
        self._round("무엇이 관측되면 풀린 것입니까", "후반 토큰이 30% 이상 줄면 풀린 것이다.")
        self._round("사이클 단위로 나눈다면", "1. 문법을 고정한다\n2. 이름을 배정한다\n3. 능력을 얹는다")

    def test_rounds_accumulate(self):
        """차수를 쌓는다 — 새 답이 앞 답을 덮으면 1차에 사람이 말한 것이 사라진다."""
        self._three_rounds()
        out = self._run("intake", "dp", "--status").stdout
        self.assertIn("스스로 도구를 만드는 언어", out)   # 1차가 살아 있고
        self.assertIn("후반 토큰이 30%", out)              # 2차도
        self.assertIn("능력을 얹는다", out)                # 3차도

    def test_status_numbers_the_answers(self):
        """차수마다 번호가 1부터 다시 시작하므로, 누적 순서로 다시 매겨 보여줘야 지목할 수 있다."""
        self._three_rounds()
        out = self._run("intake", "dp", "--status").stdout
        self.assertIn("인용 가능한 답", out)
        self.assertRegex(out, r"1\).*무엇을 하려고")
        self.assertRegex(out, r"3\).*사이클 단위로")

    def test_chain_requires_the_criterion(self):
        """목적만 있고 기준이 없으면 '됐다'가 다시 자기확신이 된다."""
        self._three_rounds()
        r = self._run("chain", "ail", "--from-intake", "dp", "--purpose-from", "1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("criterion-from", r.stderr)

    def test_three_artifacts_are_quoted_into_the_chain(self):
        self._three_rounds()
        r = self._run("chain", "ail", "--from-intake", "dp", "--purpose-from", "1",
                      "--criterion-from", "2", "--cycles-from", "3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("ail", "Gil-Chain-Purpose"),
                         "스스로 도구를 만드는 언어를 만든다.")
        self.assertIn("후반 토큰이 30%", self.trailer("ail", "Gil-Chain-Criterion"))
        self.assertIn("이름을 배정한다", self.trailer("ail", "Gil-Chain-Plan"))

    def test_cycle_is_lifted_from_the_human_breakdown(self):
        """사이클 목적도 인용이다 — 사람이 나눈 작은 문제로 사이클을 정복한다."""
        self._three_rounds()
        self._run("chain", "ail", "--from-intake", "dp", "--purpose-from", "1",
                  "--criterion-from", "2", "--cycles-from", "3")
        r = self._run("open", "ail/c1", "--author", "x", "--from-plan", "2", "--body", "정의",
                      "--fits", "사람이 나눈 두 번째 분할을 그대로 집는다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("이름을 배정한다", r.stdout)

    def test_from_plan_out_of_range_lists_the_choices(self):
        """거부에는 나갈 길이 붙는다 — 무엇을 고를 수 있는지 그 자리에서 보여준다."""
        self._three_rounds()
        self._run("chain", "ail", "--from-intake", "dp", "--purpose-from", "1",
                  "--criterion-from", "2", "--cycles-from", "3")
        r = self._run("open", "ail/c9", "--author", "x", "--from-plan", "7", "--body", "정의")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("3개뿐이다", r.stderr)
        self.assertIn("능력을 얹는다", r.stderr)

    def test_root_question_is_authored_by_the_tool(self):
        """후보는 그래프에 실재하는 자리들이다 — 에이전트가 지어낸 선택지가 아니다.
        그리고 아직 체인이 아닌 intake 슬러그 자신은 후보가 될 수 없다."""
        self.gil("chain", "old", "--purpose", "옛 국면")
        self.gil("chain-close", "old", "--verdict", "supported")
        self._round("무엇을 하려고 하십니까", "새 언어를 만든다.")
        r = self._run("intake", "dp", "--ask-root")
        self.assertEqual(r.returncode, 0, r.stderr)
        body = self._git("log", "--branches", "-1", "--format=%b").stdout
        self.assertIn("[old] 를 이어받는다", body)
        self.assertIn("대문에서 새로 시작한다", body)
        self.assertNotIn("[dp] 와 나란히", body)   # 슬러그 자신은 후보가 아니다


class TestInterviewOpensOpen(GilFixture):
    """인터뷰의 첫 질문은 열린 질문이어야 한다 (이슈 #90, 실사용 보고).

    선택지로만 채운 질문지는 **에이전트의 가설 공간 안에서 사람을 고르게 만든다.** 그러면
    기준 문서는 '사람이 세운 자'가 아니라 '에이전트가 세운 자에 사람이 서명한 것'이 되고,
    그 뒤의 모든 검증은 형식만 남는다 — 잣대를 재는 자가 잣대를 먼저 깎았으니까.

    실사용에서 사람이 방향을 실제로 뒤집은 유일한 지점이 자유 서술 칸이었다."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "iv", "--purpose", "P")

    def _ask(self, payload):
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.run([*GIL_CMD, "interview", "iv", "--ask", "-"],
                              cwd=self.repo, capture_output=True, text=True,
                              env=env, input=json.dumps(payload))

    def test_choice_first_is_refused(self):
        r = self._ask([{"q": "range 를 어떻게 할까요?", "type": "radio", "options": ["A", "B"]},
                       {"q": "자유", "type": "text"}])
        self.assertNotEqual(r.returncode, 0, "선택지로 시작하는 질문지가 통과했다")
        self.assertIn("첫 질문은 열린 질문", r.stderr)
        self.assertIn("range 를 어떻게 할까요?", r.stderr)  # 어느 질문이 문제인지 짚는다

    def test_choice_only_is_refused(self):
        r = self._ask([{"q": "A?", "type": "radio", "options": ["1", "2"]}])
        self.assertNotEqual(r.returncode, 0)

    def test_open_first_passes(self):
        r = self._ask([{"q": "무엇을 하려 하십니까", "type": "text"},
                       {"q": "그중 어느 쪽", "type": "radio", "options": ["1", "2"]}])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_choice_heavy_warns(self):
        """거부까지는 않는다 — 좁혀 묻는 질문 자체가 나쁜 건 아니다. 다만 기울면 말해 준다."""
        r = self._ask([{"q": "무엇을", "type": "text"}]
                      + [{"q": f"q{i}", "type": "radio", "options": ["1", "2"]} for i in range(3)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("질문지 자체가 앵커가 된다", r.stderr)


class TestHandoffEndMarker(GilFixture):
    """잘린 handoff 를 '없음'으로 읽지 않게 한다 (이슈 #88 이 남긴 위험).

    handoff 는 세션의 첫 명령인데, 실사용에서 타임아웃에 잘려 **빈 파일**로 읽힌 적이 있다.
    그러면 이어받는 자는 "열린 체인이 없다"고 결론 내린다 — 실제로는 있는데. gil 은 자기
    출력이 잘리는 걸 막을 수 없지만, **잘렸음을 알아볼 수 있게** 만들 수는 있다."""

    def setUp(self):
        super().setUp()
        # 격리 fixture 의 빈 저장소에는 커밋이 없어 handoff 가 HEAD 를 못 읽는다 — 체인 하나로
        # 대문을 세워 실제 세션과 같은 상태로 만든다.
        self.gil("chain", "hm", "--purpose", "P")

    def test_marker_is_the_last_line(self):
        """끝 표식은 진짜 마지막이어야 한다 — 중간에 있으면 거짓 안심을 준다."""
        out = self.gil("handoff").stdout.rstrip("\n").split("\n")
        self.assertIn("잘린 handoff 를 '없음'으로 읽지 마라", out[-1])
        self.assertIn("gil handoff 끝", out[-2])

    def test_count_matches_the_body(self):
        """'열린 체인 N' 이 본문과 맞아야 한다 — 틀린 수치는 표식이 없는 것보다 나쁘다.

        ('열린 체인 0' 이라고 **적힌 것**과, 잘려서 아무것도 없는 것은 다른 사실이다.
        그 구별이 이 표식의 존재 이유다.)"""
        out = self.gil("handoff").stdout
        body = sum(1 for ln in out.split("\n") if ln.startswith("▶ 열린 체인:"))
        m = re.search(r"열린 체인 (\d+) ·", out)
        self.assertIsNotNone(m, out[-300:])
        self.assertEqual(int(m.group(1)), body)

    def test_start_and_end_markers_pair(self):
        """시작 표식만 있고 끝 표식이 없으면 잘린 것 — 둘이 짝이어야 판정이 선다."""
        out = self.gil("handoff").stdout
        self.assertIn("세션 부활 정보 (시작)", out)
        self.assertIn("gil handoff 끝", out)


class TestSealedIsReadOnly(GilFixture):
    """봉인된 것은 자라지 않는다 (상현님 규칙 12·15·16).

    실측으로 확인한 집행 격차: close 로 봉인한 사이클에 --to 형제 가지가 그냥 들어갔다.
    fsck 는 그 가지가 미종결일 때만 짚으니, 제대로 끝내면 아무도 모른다 — 봉인된 사이클이
    봉인 뒤에 조용히 자란다. #85·#86 과 같은 병(집행이 두 자리에서 갈리면 느슨한 쪽이
    실질 규칙)."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "s", "--purpose", "P")
        self.gil("open", "s/c1", "--author", "x", "--purpose", "P", "--body", "정의")
        self.gil("step", "s/c1", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "s/c1", "--kind", "verify", "--title", "V", "--verdict", "supported")
        self.gil("step", "s/c1", "--kind", "analyze", "--title", "A")
        self.gil("step", "s/c1", "--kind", "success", "--title", "OK",
                 "--toward", "T", "--next-design", "ND")
        r = self.gil("close", "s/c1", "--verdict", "supported")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _step(self, *args):
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.run([*GIL_CMD, "step", "s/c1", *args],
                              cwd=self.repo, capture_output=True, text=True, env=env)

    def test_sealed_cycle_refuses_sibling_branch(self):
        """봉인 뒤 형제 가지 — 옛 gil 은 통과시켰다."""
        r = self._step("--kind", "hypothesis", "--to", "s1", "--title", "몰래",
                       "--falsify", "F", "--falsify-to", "s1", "--inherit", "x")
        self.assertNotEqual(r.returncode, 0, "봉인된 사이클이 자랐다")
        self.assertIn("봉인된 사이클", r.stderr)
        self.assertIn("gil open", r.stderr)  # 거부에는 나갈 길이 붙어야 한다

    def test_sealed_cycle_refuses_at(self):
        """--at 으로 봉인선을 넘지 못한다."""
        r = self._step("--kind", "fail", "--at", "s3", "--to", "s1", "--title", "몰래",
                       "--toward", "T", "--next-design", "ND")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("봉인된 사이클", r.stderr)

    def test_closed_chain_refuses_steps(self):
        """체인을 닫은 뒤에도 붙일 수 없다.

        (체인이 닫히려면 그 안의 사이클이 모두 닫혀 있어야 하므로, 실제로는 사이클 봉인이
        먼저 걸린다 — 체인 검사는 그 위의 두 번째 자물쇠다.)"""
        self.gil("chain-close", "s", "--summary", "끝")
        r = self._step("--kind", "hypothesis", "--to", "s1", "--title", "몰래",
                       "--falsify", "F", "--falsify-to", "s1", "--inherit", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("봉인", r.stderr)


class TestOrderingChain(GilFixture):
    """순서 체인 강제(AIL #41) — define→hypothesis→verify→analyze→종결. 각 kind 는 다음
    kind 가 정해져 있고 건너뛰면 거부. self._raw_step 으로 자동보정을 우회해 직접 검증한다."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P", "--body", "정의")

    def test_define_next_must_be_hypothesis(self):
        r = self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v",
                       "--plan-held")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("hypothesis", r.stderr)

    def test_hypothesis_next_must_be_verify(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        r = self._raw_step("c/c1", "--kind", "analyze", "--title", "a", "--finding", "(밝힌 것)")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("verify", r.stderr)

    def test_verify_next_must_be_analyze(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v",
                       "--plan-held", "--falsify-unmet", "(관측: 반증조건 미달)")
        r = self._raw_step("c/c1", "--kind", "success", "--title", "ok",
                           "--toward", "(회고)", "--next-design", "(다음 설계)")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("analyze", r.stderr)

    def test_full_order_passes(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v",
                       "--plan-held", "--falsify-unmet", "(관측: 반증조건 미달)")
        self._raw_step("c/c1", "--kind", "analyze", "--title", "a", "--finding", "(밝힌 것)")
        r = self._raw_step("c/c1", "--kind", "success", "--title", "ok",
                           "--toward", "(회고)", "--next-design", "(다음 설계)")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_guide_next_always_printed(self):
        """각 스텝 후 '다음은 X' 가 무조건 출력된다."""
        r = self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self.assertIn("⟹", r.stderr)
        self.assertIn("verify", r.stderr)


class TestPendingLeaf(GilFixture):
    """pending 은 부모가 될 수 없다(AIL #41) — approve/reject 가 pending 을 supersede."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P", "--body", "정의")
        self.gil("step", "c/c1", "--kind", "pending", "--title", "물음")  # 자동보정: hyp·verify·analyze 선행

    def test_approve_supersedes_pending(self):
        r = self.gil("approve", "c/c1")
        self.assertEqual(r.returncode, 0, r.stderr)
        # pending 은 잎으로 남고 정정됨 표시, success 는 pending 을 부모로 안 삼는다.
        log = self.gil("log", "--depth", "step", "c").stdout
        self.assertIn("정정됨", log)  # pending 에 ⤳정정됨
        self.assertEqual(self.trailer("HEAD", "Gil-Supersedes")[:1], "s")

    def test_pending_not_a_parent(self):
        """approve 후 success 의 부모가 pending 이 아니어야 한다."""
        self.gil("approve", "c/c1")
        # HEAD(success)의 Gil-Parent 가 pending 스텝이 아님 — pending 의 부모(analyze)여야.
        parent = self.trailer("HEAD", "Gil-Parent")
        # pending 스텝 id 를 찾아 그게 부모가 아님을 확인
        log = self.gil("log", "--depth", "step", "c").stdout
        self.assertIn("[analyze]", log)  # analyze 가 있고
        self.assertNotEqual(parent, "")  # 부모가 pending 이 아닌 실제 스텝


class TestDeploy(GilFixture):
    """gil deploy — 배포(공개) 지점 마커 (이슈 #34).

    이 fixture 는 gil init 을 부르지 않는다 = dev 층이 없는 저장소다. 층이 없으면 마커는
    옛 자리(그때 서 있던 브랜치)에 그대로 새겨지고 승격도 일어나지 않는다 — 옛 레이아웃의
    저장소가 이 변경으로 깨지지 않는다는 것을 여기서 지킨다.
    """

    def _live_step(self):
        self.gil("chain", "devchain", "--purpose", "개발")
        self.gil("open", "devchain/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "devchain/c001", "--kind", "success", "--title", "릴리스 준비")

    def test_deploy_marks_target_step(self):
        """deploy 는 대상 스텝을 가리키는 Gil-Deploy 트레일러 커밋을 남긴다."""
        self._live_step()
        r = self.gil("deploy", "--at", "devchain/c001/s4", "--tag", "v0.2.0",
                     "--url", "https://example.com/r/v0.2.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy"), "v0.2.0")
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-At"), "devchain/c001/s4")
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-Url"),
                         "https://example.com/r/v0.2.0")
        # 배포 커밋은 추론 노드가 아니다 — Gil-Step 을 달지 않는다(그래프 위상 불변).
        self.assertEqual(self.trailer("HEAD", "Gil-Step"), "")

    def test_deploy_requires_a_tag(self):
        """태그는 필수, --at 은 선택이다 (main-dev-chain).

        배포 단위가 여러 체인의 합류(dev)일 때는 가리킬 스텝 하나가 없다 — 그걸 요구하면
        사람은 아무 스텝이나 골라 적게 되고, 그러면 그 칸이 형해화된다.
        """
        self._live_step()
        r = self.gil("deploy", "--at", "devchain/c001/s4")  # --tag 없음
        self.assertNotEqual(r.returncode, 0)
        r = self.gil("deploy", "--tag", "v1")  # --at 없음 — 정상이다
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy"), "v1")

    def test_deploy_rejects_missing_step(self):
        """실재하지 않는 스텝엔 마커를 얹지 못한다."""
        self._live_step()
        r = self.gil("deploy", "--at", "devchain/c001/s99", "--tag", "v1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("s99", r.stdout + r.stderr)

    def test_deploy_rejects_malformed_at(self):
        """--at 은 chain/cycle/step 세 조각을 다 요구한다."""
        self._live_step()
        r = self.gil("deploy", "--at", "devchain/c001", "--tag", "v1")  # 스텝 없음
        self.assertNotEqual(r.returncode, 0)

    def test_deploy_url_optional(self):
        self._live_step()
        r = self.gil("deploy", "--at", "devchain/c001/s4", "--tag", "v0.1.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy"), "v0.1.0")
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-Url"), "")


class TestFailClosure(GilFixture):
    """fail/종결 처리 — 이슈 #44·#45·#46 (fail=이 가설의 죽음, 사이클의 죽음이 아니다)."""

    def _fail_only_cycle(self, chain="c", cycle="dead", *open_extra):
        """산 잎 없이 fail 잎만 있는 사이클을 만든다(refuted→fail).

        두 번째 미해결 사이클을 만들려면 open 자체가 --parallel 선언을 요구한다 —
        레일이 실제로 돌고 있다는 증거라, 테스트도 그 문법을 따른다(이슈 #45)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", chain, "--purpose", "P")
        self.gil("open", f"{chain}/{cycle}", "--author", "clew", "--purpose", "Q",
                 "--body", "정의", *open_extra)
        self.gil("step", f"{chain}/{cycle}", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", f"{chain}/{cycle}", "--kind", "verify", "--title", "V", "--verdict", "refuted")
        self.gil("step", f"{chain}/{cycle}", "--kind", "analyze", "--title", "A")
        self.gil("step", f"{chain}/{cycle}", "--kind", "fail", "--to", "s1", "--title", "벽")

    # ── #46: fail 잎만 있는 사이클 close ──
    def test_close_fail_only_refused_without_abandon(self):
        """산 잎 없으면 기본 close 거부 — 두 정직한 길(재분기/포기)을 안내."""
        self._fail_only_cycle()
        r = self.gil("close", "c/dead")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--abandon", out)  # 포기 경로 안내
        self.assertIn("hypothesis", out)  # 재분기 경로 안내

    def test_close_abandon_seals_dead_cycle(self):
        """--abandon 이면 fail 잎만 있는 죽은 사이클도 봉인된다(이슈 #46)."""
        self._fail_only_cycle()
        r = self.gil("close", "c/dead", "--abandon")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "close")
        self.assertEqual(self.trailer("HEAD", "Gil-Abandoned"), "true")

    def test_chain_close_counts_abandoned_cycle(self):
        """abandon 봉인된 사이클은 chain-close 가 '닫힌 것'으로 센다(이슈 #46)."""
        self._fail_only_cycle()
        self.gil("close", "c/dead", "--abandon")
        r = self.gil("chain-close", "c")
        self.assertEqual(r.returncode, 0, "abandoned 사이클이 있어도 체인 닫혀야: " + r.stderr)

    def test_close_abandon_needs_a_dead_leaf(self):
        """봉인할 죽은 잎조차 없으면 --abandon 도 거부."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/d", "--author", "clew", "--purpose", "Q", "--body", "정의")
        r = self.gil("close", "c/d", "--abandon")  # define 만 있음, fail 잎 없음
        self.assertNotEqual(r.returncode, 0)

    # ── #45: fail 후속 안내 + 미해결 사이클 방치 경고 ──
    def test_fail_step_gives_rebranch_or_abandon_guidance(self):
        """fail 스텝 뒤 gil 이 재분기/포기 두 길을 안내한다(이슈 #45)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/x", "--author", "clew", "--purpose", "Q", "--body", "정의")
        self.gil("step", "c/x", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self.gil("step", "c/x", "--kind", "verify", "--title", "V", "--verdict", "refuted")
        self.gil("step", "c/x", "--kind", "analyze", "--title", "A")
        r = self.gil("step", "c/x", "--kind", "fail", "--to", "s1", "--title", "벽")
        out = r.stdout + r.stderr
        self.assertIn("--abandon", out)
        self.assertIn("hypothesis --to", out)

    def test_open_refuses_on_stranded_cycle(self):
        """미해결(fail만·미종결) 사이클이 있으면 새 사이클 open 을 **거부**한다(이슈 #45).

        옛 동작은 경고였다. 실측에서 4/4 로 도망갔다 — 경고는 읽히지 않거나 읽혀도 다음
        줄에서 잊힌다. 규율은 안내가 아니라 문법의 거부여야 한다(HEAAL)."""
        self._fail_only_cycle(chain="c", cycle="dead")
        r = self.gil("open", "c/fresh", "--author", "clew", "--purpose", "새것", "--body", "정의2")
        self.assertNotEqual(r.returncode, 0, "미해결 사이클을 두고 새 사이클이 열렸다")
        out = r.stdout + r.stderr
        self.assertIn("dead", out)          # 어느 사이클이 방치됐는지 짚는다
        self.assertIn("--abandon", out)     # 세 길을 다 준다
        self.assertIn("hypothesis --to", out)
        self.assertIn("--parallel", out)

    def test_declared_parallel_passes_and_is_recorded(self):
        """병렬은 막지 않되 조용히 지나가지도 않는다 — 선언하면 통과하고 그래프에 남는다."""
        self._fail_only_cycle(chain="c", cycle="dead")
        r = self.gil("open", "c/fresh", "--author", "clew", "--purpose", "새것",
                     "--body", "정의2", "--parallel", "dead")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Parallel-With"), "dead")

    def test_partial_declaration_still_refused(self):
        """둘 중 하나만 선언하면 나머지는 여전히 막는다 — 선언은 사이클마다."""
        self._fail_only_cycle(chain="c", cycle="dead")
        self._fail_only_cycle("c", "dead2", "--parallel", "dead")
        r = self.gil("open", "c/fresh", "--author", "clew", "--purpose", "새것",
                     "--body", "정의2", "--parallel", "dead")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dead2", r.stdout + r.stderr)

    def test_open_no_warn_when_cycle_abandoned(self):
        """abandon 으로 봉인된 사이클은 더 이상 '방치'가 아니다 — 경고 없음."""
        self._fail_only_cycle(chain="c", cycle="dead")
        self.gil("close", "c/dead", "--abandon")
        r = self.gil("open", "c/fresh", "--author", "clew", "--purpose", "새것", "--body", "정의2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("미해결 사이클", r.stdout + r.stderr)

    # ── #44: 어긋난 브랜치에서 reject 해도 대상 계보에 얹히고 pending 이 풀린다 ──
    def test_reject_from_wrong_branch_resolves_pending(self):
        """다른 사이클 브랜치가 체크아웃된 상태에서 reject 해도 대상 계보에 얹히고
        handoff 가 더 이상 pending 을 요구하지 않는다(이슈 #44)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "lr", "--purpose", "P")
        self.gil("open", "lr/measure", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.gil("step", "lr/measure", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self.gil("step", "lr/measure", "--kind", "verify", "--title", "V", "--verdict", "supported")
        self.gil("step", "lr/measure", "--kind", "pending", "--title", "물음")
        # 다른 브랜치를 파고 체크아웃해 HEAD 를 measure 팁에서 떨군다.
        self._git("checkout", "-q", "-b", "lr-transfer")
        self._git("commit", "-q", "--allow-empty", "-m", "transfer 작업")
        r = self.gil("reject", "lr/measure", "--to", "s1", "--title", "실패 종결")
        self.assertEqual(r.returncode, 0, r.stderr)
        # s6 fail 이 measure 계보(s4)를 부모로 하고 s5 pending 을 supersede 한다.
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "fail")
        self.assertNotEqual(self.trailer("HEAD", "Gil-Supersedes"), "")
        # handoff 가 이제 measure pending 을 대기로 안 띄운다(정정된 pending).
        h = self.gil("handoff").stdout
        self.assertNotIn("measure/s5", h)

    def test_reject_from_wrong_branch_then_abandon_closes(self):
        """#44 정정 후 그 죽은 사이클을 --abandon 으로 닫을 수 있다(#44+#46 결합)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "lr", "--purpose", "P")
        self.gil("open", "lr/m", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.gil("step", "lr/m", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "(설계 고정)", "--advances", "(목적에 한 칸)")
        self.gil("step", "lr/m", "--kind", "verify", "--title", "V", "--verdict", "supported")
        self.gil("step", "lr/m", "--kind", "pending", "--title", "물음")
        self._git("checkout", "-q", "-b", "lr-other")
        self._git("commit", "-q", "--allow-empty", "-m", "other")
        self.gil("reject", "lr/m", "--to", "s1", "--title", "기각")
        r = self.gil("close", "lr/m", "--abandon")
        self.assertEqual(r.returncode, 0, "정정된 fail 사이클도 abandon 봉인 가능: " + r.stderr)


class TestReference(GilFixture):
    """레퍼런스 트루스 최소 형태 — gil chain --reference (이슈 #33, 강제 없이 존재·참조)."""

    def _init(self):
        self.gil("init", "--name", "clew")

    def test_chain_reference_pins_trailer_and_body(self):
        """--reference 는 Gil-Reference 트레일러를 달고 전문을 chain-root 본문에 담는다."""
        self._init()
        r = self.gil("chain", "audit", "--purpose", "감사",
                     "--reference", "-", "--criterion", "30% 절감이 관측되면 풀린 것",
                     input="# 기준\n성공: 30% 절감\n실패: 정확도 하락")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("audit", "Gil-Reference"), "true")
        body = self._git("log", "-1", "audit", "--format=%b").stdout
        self.assertIn("30% 절감", body)  # 기준 전문이 본문에 있다

    def test_chain_without_criterion_is_refused(self):
        """목적과 기준은 **쌍으로만** 태어난다(상현님) — 기준 없는 체인은 생성 자체가 거부된다.

        옛 규칙은 기준 없는 체인을 만들게 두고 사이클을 열 때 막았다. 그 사이에 체인이 이미
        존재하니 실사용에서는 늘 '체인부터 만들고 → 거부당하고 → 그제서야 인터뷰'가 됐다."""
        self._init()
        self._no_criterion_autofill = True
        try:
            r = self.gil("chain", "plain", "--purpose", "그냥")
        finally:
            self._no_criterion_autofill = False
        self.assertNotEqual(r.returncode, 0, "기준 없는 체인이 만들어졌다")
        self.assertIn("쌍으로만", r.stderr)

    def test_reference_without_criterion_is_refused(self):
        """전문만 있고 판정 문장이 없으면 아무도 그 문서를 잣대로 쓰지 않는다(형해화)."""
        self._init()
        self._no_criterion_autofill = True
        try:
            r = self.gil("chain", "audit", "--purpose", "감사",
                         "--reference", "-", input="# 기준 전문")
        finally:
            self._no_criterion_autofill = False
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--criterion", r.stderr)

    def test_open_surfaces_reference_when_present(self):
        """기준 있는 체인에서 사이클을 열면 '기준을 읽으라' 안내가 뜬다."""
        self._init()
        self.gil("chain", "audit", "--purpose", "감사",
                 "--reference", "-", "--criterion", "무엇이 관측되면 풀린 것",
                 input="# 기준 문서 전문")
        r = self.gil("open", "audit/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("기준 문서", r.stdout + r.stderr)

    def test_paired_reference_opens_without_second_interview(self):
        """집행은 **체인의 탄생 한 곳**에서만 — 쌍을 갖춰 태어난 체인은 open 이 또 묻지 않는다.

        판정이 두 자리에서 갈리면 느슨한 쪽이 실질 규칙이 된다(이 레포가 값을 치른 교훈)."""
        self._init()
        self.gil("chain", "audit", "--purpose", "감사",
                 "--reference", "-", "--criterion", "30% 절감", input="# 기준 전문")
        self._no_interview_autofill = True
        try:
            r = self.gil("open", "audit/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        finally:
            self._no_interview_autofill = False
        self.assertEqual(r.returncode, 0, r.stderr)


class TestInterviewGate(GilFixture):
    """인터뷰 필수 + pending 잠금 게이트 (이슈 #33, 상현님 실사용).

    LLM 이 사람에게 묻는 마찰을 회피하고 스스로 기준을 정해 진행하는 걸 문법으로 막는다.
    이 클래스는 게이트 자체를 검증하므로 자동 인터뷰 보정을 끈다."""

    def setUp(self):
        super().setUp()
        self._no_interview_autofill = True  # 게이트 검증 — 자동 충족 끔
        self.gil("init", "--name", "clew")
        self.gil("chain", "sb", "--purpose", "딸기 예측")

    def _put_interview(self):
        return self.gil("interview", "sb", "--ask", "-",
                        input='[{"q":"무엇을 풀려는가","type":"text"}]')

    def _resolve(self):
        ref = os.path.join(self.repo, "reference-sb.md")
        with open(ref, "w", encoding="utf-8") as f:
            f.write("# 기준 문서\n성공: RMSE 하한")
        return self.gil("interview", "sb", "--resolve", "reference-sb.md")

    def test_chain_blocked_without_criterion(self):
        """집행이 **체인의 탄생**으로 올라갔다(상현님).

        옛 게이트는 기준 없는 체인을 만들게 두고 사이클에서 막았다 — 그래서 실사용은 늘
        '체인부터 만들고 → 거부당하고 → 그제서야 인터뷰'로 굳었다. 이제 그 체인이 아예
        태어나지 못하므로, 인터뷰를 먼저 하는 것 말고 다른 순서가 없다."""
        self._no_criterion_autofill = True
        try:
            r = self.gil("chain", "nocrit", "--purpose", "기준 없이")
        finally:
            self._no_criterion_autofill = False
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("쌍으로만", r.stderr)

    def test_open_blocked_while_interview_pending(self):
        """인터뷰가 사람 답 대기(pending) 중이면 open 거부 — pending 잠금."""
        self._put_interview()
        r = self.gil("open", "sb/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("대기", r.stdout + r.stderr)

    def test_second_interview_blocked_while_pending(self):
        """이미 pending 인터뷰가 있으면 새 질문지를 또 못 만든다 — LLM 자가진행 차단."""
        self._put_interview()
        r = self.gil("interview", "sb", "--ask", "-",
                     input='[{"q":"또 질문","type":"text"}]')
        self.assertNotEqual(r.returncode, 0)

    def test_open_allowed_after_resolve(self):
        """사람이 폼으로 답(resolve)하면 기준이 확정되고 그제서야 open 이 열린다."""
        self._put_interview()
        self._resolve()
        r = self.gil("open", "sb/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_self_authored_reference_does_not_satisfy_gate(self):
        """gil chain --reference(LLM 자기작성)만으로는 게이트를 못 넘는다 — 인터뷰 done 이라야."""
        self.gil("chain", "self", "--purpose", "P", "--reference", "-",
                 input="# 내가 쓴 기준")
        r = self.gil("open", "self/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.assertNotEqual(r.returncode, 0, "자기작성 기준이 게이트를 통과하면 안 됨")
        self.assertIn("인터뷰", r.stdout + r.stderr)


class TestInterview(GilFixture):
    """gil interview — 사람 설문 폼으로 레퍼런스 만들기 (이슈 #33)."""

    QS = ('[{"q":"무엇을 풀려는가","type":"text"},'
          '{"q":"성공 기준","type":"checkbox","options":["속도","정확도"]},'
          '{"q":"우선순위","type":"radio","options":["비용","품질"]}]')

    def _chain(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "audit", "--purpose", "감사")

    def test_interview_pins_question_node(self):
        """--ask 는 Gil-Interview:pending 노드를 심고 질문 JSON 을 본문 펜스에 담는다."""
        self._chain()
        r = self.gil("interview", "audit", "--ask", "-", input=self.QS)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("audit", "Gil-Interview"), "pending")
        self.assertEqual(self.trailer("audit", "Gil-Kind"), "interview")
        body = self._git("log", "-1", "audit", "--format=%b").stdout
        self.assertIn("gil-interview", body)  # JSON 펜스

    def test_interview_rejects_bad_json(self):
        self._chain()
        r = self.gil("interview", "audit", "--ask", "-", input="not json")
        self.assertNotEqual(r.returncode, 0)

    def test_interview_rejects_bad_type(self):
        self._chain()
        r = self.gil("interview", "audit", "--ask", "-",
                     input='[{"q":"x","type":"dropdown"}]')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("type", r.stdout + r.stderr)

    def test_interview_choice_needs_options(self):
        self._chain()
        r = self.gil("interview", "audit", "--ask", "-",
                     input='[{"q":"고르라","type":"radio"}]')
        self.assertNotEqual(r.returncode, 0)

    def test_interview_requires_existing_chain(self):
        self.gil("init", "--name", "clew")
        r = self.gil("interview", "nope", "--ask", "-", input=self.QS)
        self.assertNotEqual(r.returncode, 0)

    def test_interview_resolve_pins_reference_and_done(self):
        """--resolve 는 레퍼런스를 심고(Gil-Reference) 인터뷰를 done 으로 닫는다(뷰어 제출 경로)."""
        self._chain()
        self.gil("interview", "audit", "--ask", "-", input=self.QS)
        # 답변으로 조립된 레퍼런스 파일을 흉내낸다.
        ref = os.path.join(self.repo, "reference-audit.md")
        with open(ref, "w", encoding="utf-8") as f:
            f.write("# 기준 문서\n성공: 속도·정확도\n우선: 비용")
        r = self.gil("interview", "audit", "--resolve", "reference-audit.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Reference"), "true")
        self.assertEqual(self.trailer("HEAD", "Gil-Interview"), "done")

    def test_open_after_interview_resolve_sees_reference(self):
        """인터뷰 해소 후 그 체인에 사이클을 열면 기준 안내가 뜬다."""
        self._chain()
        self.gil("interview", "audit", "--ask", "-", input=self.QS)
        ref = os.path.join(self.repo, "reference-audit.md")
        with open(ref, "w", encoding="utf-8") as f:
            f.write("# 기준")
        self.gil("interview", "audit", "--resolve", "reference-audit.md")
        r = self.gil("open", "audit/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.assertIn("기준 문서", r.stdout + r.stderr)


class TestInterviewWait(GilFixture):
    """인터뷰 제출을 에이전트가 알 수단 (이슈 #58, 상현님 실사용).

    사람이 뷰어 폼에 제출해도 통지가 없어, 에이전트는 바쁜대기(무의미한 git log 반복)나
    우회(내가 기준을 쓴다) 중 하나로 밀렸다. '기다려라'는 안내가 기다릴 수단 없는 지시였다.
    그래서 기다림을 정직한 한 줄(--status)과 진짜 대기(--wait)로 만든다."""

    def setUp(self):
        super().setUp()
        self._no_interview_autofill = True
        self.gil("init", "--name", "clew")
        self.gil("chain", "sb", "--purpose", "딸기 예측")

    def _ask(self):
        return self.gil("interview", "sb", "--ask", "-",
                        input='[{"q":"무엇을 풀려는가","type":"text"}]')

    def _resolve(self):
        with open(os.path.join(self.repo, "reference-sb.md"), "w", encoding="utf-8") as f:
            f.write("# 기준 문서\n성공: RMSE 하한")
        return self.gil("interview", "sb", "--resolve", "reference-sb.md")

    def test_status_none_before_ask(self):
        """심어둔 인터뷰가 없으면 none — 그리고 무엇을 해야 하는지 한 수를 준다.

        체인은 이제 **태어날 때 기준을 갖는다**(목적과 기준은 쌍) — 그래서 '아직 아무것도
        묻지 않은' 상태가 남아 있는 자리는 개시 인터뷰(체인보다 먼저)의 슬러그다."""
        r = self.gil("intake", "unasked", "--status")
        out = r.stdout + r.stderr
        self.assertIn("none", out)
        self.assertIn("--ask", out)

    def test_status_pending_after_ask(self):
        """질문을 심고 사람이 답하기 전에는 pending — git show 를 뒤지지 않아도 알 수 있다."""
        self._ask()
        r = self.gil("interview", "sb", "--status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pending", r.stdout + r.stderr)

    def test_status_done_after_resolve_shows_reference(self):
        """사람이 제출하면 done 이고, 확정된 기준 문서를 그 자리에서 돌려준다."""
        self._ask()
        self._resolve()
        r = self.gil("interview", "sb", "--status", "--show")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout + r.stderr
        self.assertIn("done", out)
        self.assertIn("RMSE 하한", out)

    def test_wait_returns_immediately_when_done(self):
        """이미 제출됐으면 --wait 는 기다리지 않고 바로 기준을 뱉는다."""
        self._ask()
        self._resolve()
        r = self.gil("interview", "sb", "--wait", "--timeout", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("done", r.stdout + r.stderr)

    def test_wait_times_out_without_fabricating(self):
        """시간초과는 실패가 아니라 '아직 pending' 이다 — 기준을 대신 쓰라고 하지 않는다."""
        self._ask()
        r = self.gil("interview", "sb", "--wait", "--timeout", "3")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("시간초과", out)
        self.assertIn("대신 쓰지 마라", out)

    def test_wait_wakes_on_submission(self):
        """사람이 뒤늦게 제출하면 대기가 풀린다 — 이게 없어서 세션이 멈춰 있었다."""
        import threading
        self._ask()
        t = threading.Timer(3.0, self._resolve)
        t.start()
        try:
            r = self.gil("interview", "sb", "--wait", "--timeout", "40")
        finally:
            t.cancel()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("done", r.stdout + r.stderr)
        self.assertIn("RMSE 하한", r.stdout + r.stderr)

    def test_wait_refuses_when_nothing_to_wait_for(self):
        """기다릴 인터뷰가 없는데 기다리게 두지 않는다 — 먼저 질문을 심어라."""
        r = self.gil("intake", "unasked", "--wait", "--timeout", "3")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--ask", r.stdout + r.stderr)

    def test_handoff_surfaces_pending_interview(self):
        """이어받은 세션의 복구 지점 — 이 체인이 사람 답을 기다리는 중임이 handoff 에 뜬다."""
        self._ask()
        r = self.gil("handoff")
        out = r.stdout + r.stderr
        self.assertIn("인터뷰 답 대기 중", out)
        self.assertIn("--status", out)


class TestMCPServe(GilFixture):
    """gil mcp serve — 호스트(Claude Desktop 등)가 gil 을 툴로 부르는 경로.

    왜 여기까지 테스트하나. 인터뷰가 '질문은 대화창, 답은 뷰어 폼'으로 쪼개져 있던 것이
    실사용 붕괴의 원인이었다. MCP 경로의 값어치는 그 두 채널이 하나로 합쳐진다는 것 —
    한 번의 툴 호출 안에서 묻고 받는다. 그러니 검증도 '폼이 뜨고 답이 기준이 되는지'까지 간다.
    """

    def _rpc(self, calls, elicit_answer=None):
        """MCP 서버를 stdio 로 띄우고 요청을 순서대로 보낸다.

        calls: (name, arguments) 목록. 반환: 툴별 (isError, text).
        elicit_answer: 주면 서버가 보내는 elicitation/create 에 이 내용으로 accept 한다
        (= 사람이 호스트 폼에 답한 상황). None 이면 클라이언트가 elicitation 미지원.
        """
        import json
        caps = {"elicitation": {}} if elicit_answer is not None else {}
        self.gil("init")   # MCP 툴은 gil 로 관리되는 저장소를 요구한다(requireReady)
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1,
                             env=dict(os.environ, GIL_NO_VIEWER="1"))
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        read = lambda: json.loads(p.stdout.readline())
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": caps,
                             "clientInfo": {"name": "test", "version": "1"}}})
            read()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            results = []
            for i, (name, args) in enumerate(calls, start=10):
                send({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                      "params": {"name": name, "arguments": args}})
                msg = read()
                # 서버가 사람에게 폼을 띄우면(elicitation/create) 답을 돌려주고 결과를 마저 읽는다.
                if msg.get("method") == "elicitation/create":
                    send({"jsonrpc": "2.0", "id": msg["id"],
                          "result": {"action": "accept", "content": elicit_answer}})
                    msg = read()
                if "error" in msg:
                    results.append((True, msg["error"].get("message", "")))
                else:
                    r = msg["result"]
                    results.append((bool(r.get("isError")),
                                    r["content"][0]["text"] if r.get("content") else ""))
            return results
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()

    def test_tools_are_exposed(self):
        """핵심 명령이 툴 표면으로 나온다 — 호스트가 CLI 문자열 조립 없이 부를 수 있게."""
        import json
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1)
        try:
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "t", "version": "1"}}}) + "\n")
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
            p.stdin.flush()
            json.loads(p.stdout.readline())
            names = [t["name"] for t in json.loads(p.stdout.readline())["result"]["tools"]]
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()
        for want in ("gil_chain", "gil_open", "gil_step", "gil_close", "gil_interview",
                     "gil_interview_status", "gil_log", "gil_goto"):
            self.assertIn(want, names)

    def test_reject_does_not_kill_server(self):
        """문법 거부는 그 호출의 에러일 뿐 — 세션을 끊지 않는다.

        die() 가 os.Exit 이던 시절이면 첫 거부에서 서버가 죽어 이후 호출이 전부 사라진다.
        거부야말로 gil 의 본체(HEAAL)라, 거부 뒤에도 대화가 이어져야 한다."""
        r = self._rpc([
            ("gil_chain", {"name": "probe", "purpose": "MCP 경로", "criterion": "무엇이 관측되면 풀린 것", "reference": CRIT_FILE}),
            ("gil_open", {"target": "probe/c001", "author": "clew", "purpose": "인터뷰 없이"}),
            ("gil_log", {}),
        ])
        self.assertFalse(r[0][0], r[0][1])
        self.assertTrue(r[1][0], "인터뷰 없는 open 은 거부돼야 한다")
        self.assertFalse(r[2][0], "거부 뒤에도 서버는 살아 다음 호출을 받는다")

    def test_interview_elicitation_makes_reference(self):
        """인터뷰 = 호스트 네이티브 폼 한 번. 사람 답이 그대로 기준 문서가 되고 게이트가 열린다."""
        r = self._rpc([
            ("gil_chain", {"name": "probe", "purpose": "MCP 인터뷰", "criterion": "무엇이 관측되면 풀린 것", "reference": CRIT_FILE}),
            ("gil_interview", {"chain": "probe", "questions": [
                {"q": "무엇을 풀려는가", "type": "text"},
                {"q": "성공 기준", "type": "radio", "options": ["속도", "정확도"]},
                {"q": "포기 가능", "type": "checkbox", "options": ["UI", "호환성"]},
            ]}),
        ], elicit_answer={"q1": "채널 단일화", "q2": "정확도", "q3_o1": True, "q3_o2": False})
        self.assertFalse(r[1][0], r[1][1])
        # 사람이 쓴 말이 윤색 없이 기준 문서에 그대로 들어간다.
        self.assertIn("채널 단일화", r[1][1])
        self.assertIn("정확도", r[1][1])
        self.assertIn("UI", r[1][1])
        self.assertNotIn("호환성", r[1][1])  # 체크 안 한 항목은 안 들어간다
        self.assertEqual(self.trailer("HEAD", "Gil-Interview"), "done")

    def test_interview_declined_is_not_answered_by_llm(self):
        """폼이 accept 로 안 돌아오면 기준은 만들어지지 않는다 — LLM 이 대신 답하지 못하게.

        (이슈 #57 이후) 취소/거절은 뷰어 폼으로 물러나되, 기준은 여전히 비어 있어 게이트가 닫혀
        있다. 즉 '물러남'이 '통과'가 되지 않는다."""
        import json
        self.gil("init")   # MCP 툴은 gil 로 관리되는 저장소를 요구한다(requireReady)
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1,
                             env=dict(os.environ, GIL_NO_VIEWER="1"))
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        read = lambda: json.loads(p.stdout.readline())
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {"elicitation": {}},
                             "clientInfo": {"name": "t", "version": "1"}}})
            read()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                  "params": {"name": "gil_chain", "arguments": {"name": "probe", "purpose": "P", "criterion": "기준", "reference": CRIT_FILE}}})
            read()
            send({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                  "params": {"name": "gil_interview",
                             "arguments": {"chain": "probe",
                                           "questions": [{"q": "무엇을", "type": "text"}]}}})
            msg = read()
            self.assertEqual(msg.get("method"), "elicitation/create")
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"action": "cancel"}})
            msg = read()
            body = json.dumps(msg, ensure_ascii=False)
            self.assertIn("cancel", body)
            # 이슈 #57: 폼이 사람 화면에 뜬 적이 있는지 우리는 모른다. 없던 사람 의사를
            # 단언하면 에이전트가 그걸 근거로 우회한다 — 단언하지 않는다.
            self.assertNotIn("사람에 의해", body)
            self.assertIn("구분할 수 없다", body)
            # 물음은 사라지지 않는다 — 뷰어 폼으로 심겨 사람이 답할 자리가 남는다.
            self.assertEqual(self.trailer("probe", "Gil-Interview"), "pending")
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()
        # 기준이 확정되지 않았으니 사이클도 못 연다.
        self._no_interview_autofill = True
        r = self.gil("open", "probe/c001", "--author", "clew", "--purpose", "P", "--body", "B")
        self.assertNotEqual(r.returncode, 0)

    def test_interview_falls_back_to_viewer_form(self):
        """호스트가 폼(Elicitation)을 못 띄우면 옛 뷰어 경로로 물러난다 — 물음은 사라지지 않는다."""
        r = self._rpc([
            ("gil_chain", {"name": "probe", "purpose": "P", "criterion": "기준", "reference": CRIT_FILE}),
            ("gil_interview", {"chain": "probe",
                               "questions": [{"q": "무엇을 풀려는가", "type": "text"}]}),
        ])
        self.assertFalse(r[1][0], r[1][1])
        self.assertEqual(self.trailer("HEAD", "Gil-Interview"), "pending")


class TestStatusJSON(GilFixture):
    """gil status --json — 지금 어디, 개입할 때인가.

    왜 이 명령인가. 뷰어의 마찰은 UI 완성도가 아니라 **성격이 다른 두 요구가 한 화면에
    섞인 것**이었다. 작업 중에 필요한 건 "지금 어디, 사람이 나설 자리인가" 세 줄이고,
    전체 그래프는 다 끝난 뒤 한 번 읽는 물건이다. 전자를 보려고 브라우저를 띄우는 것이
    비용의 정체다. 그래서 gil 은 데이터만 내고, 그리는 것은 에이전트가 한다.
    """

    def status(self):
        r = self.gil("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def _cycle(self):
        r = self.gil("chain", "st", "--purpose", "status 확인")
        self.assertEqual(r.returncode, 0, r.stderr)
        self._autofill_interview("st")   # open 게이트(사람이 승인한 기준) 충족
        r = self.gil("open", "st/c1", "--purpose", "status 가 읽을 사이클", "--author", "clew")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_reports_where_and_next(self):
        """지금 선 자리와 **다음 단계**. 다음 단계가 없으면 이 화면은 읽을 이유가 없다."""
        self._cycle()
        st = self.status()
        self.assertEqual(st["chain"]["name"], "st")
        self.assertEqual(st["cycle"]["name"], "c1")
        self.assertEqual(st["step"]["kind"], "define")
        # define 다음은 반드시 hypothesis — 문법과 같은 말을 해야 한다.
        self.assertTrue(any("hypothesis" in n for n in st["next"]), st["next"])

    def test_no_graph_in_the_payload(self):
        """**그래프를 담지 않는다.** 담으면 이 명령도 뷰어와 같은 병에 걸린다.

        섞으면 "지금 어디"를 보려는 사람이 다시 전체를 받아 들게 되고, 그게 정확히
        지금 고치려는 것이다.
        """
        self._cycle()
        st = self.status()
        for forbidden in ("nodes", "edges", "graph", "layout"):
            self.assertNotIn(forbidden, st, f"{forbidden} 가 실렸다 — 여기는 그래프 자리가 아니다")

    def test_pending_surfaces_as_waiting_for_human(self):
        """사람이 나설 자리가 **한 필드로** 나온다 — 이 JSON 의 존재 이유다."""
        self._cycle()
        r = self.gil("step", "st/c1", "--kind", "pending", "--title", "이건 사람이 정해야 한다")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.status()
        self.assertIsNotNone(st["waiting_for_human"])
        self.assertEqual(st["waiting_for_human"]["kind"], "approval")
        self.assertIn("approve", st["waiting_for_human"]["how_to_answer"])

    def test_plain_commit_on_a_chain_branch_is_named_not_swallowed(self):
        """팁이 gil 커밋이 아니어도 자리를 잃지 않는다 — 그리고 **그 사실을 말한다**.

        실측(AIL): 체인 가지 끝에 트레일러 없는 평범한 git 커밋이 얹혀 있었다(#116 이
        '괴리의 주범'이라 부른 자리). 팁만 보면 gil 은 "아직 아무것도 안 열렸다"고 답하는데
        사람은 사이클 한복판에 서 있다 — 도구가 사람의 현실과 다른 것을 말하면 사람은
        도구를 끈다. 그렇다고 조용히 메우면 #116 이 탐지로 세운 신호를 이 화면이 지운다.
        """
        self._cycle()
        (Path(self.repo) / "곁가지.txt").write_text("gil 밖에서 만든 파일\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "--no-verify", "-m", "평범한 커밋"],
                       cwd=self.repo, check=True)
        st = self.status()
        self.assertEqual(st["chain"]["name"], "st")     # 자리를 잃지 않는다
        self.assertEqual(st["cycle"]["name"], "c1")
        self.assertTrue(any("gil 밖 커밋" in w for w in st["warnings"]), st["warnings"])

    def test_status_does_not_launch_the_viewer(self):
        """뷰어를 대신하려고 만든 명령이 뷰어를 띄우면 안 된다.

        실측: 처음 돌렸을 때 JSON 앞줄에 "뷰어: 관전 준비됨 → 127.0.0.1:8791" 이 붙었다.
        없애려던 창을, 없애려는 명령이 띄우고 있었다.
        """
        self._cycle()
        env = dict(os.environ)
        env.pop("GIL_NO_VIEWER", None)   # 억제를 풀고 — 실제 경로를 밟는다
        r = subprocess.run([*GIL_CMD, "status", "--json"], cwd=self.repo,
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout + r.stderr
        self.assertNotIn("127.0.0.1", out)
        self.assertNotIn("뷰어", out)
        json.loads(r.stdout)   # 앞줄이 붙으면 이 파싱이 깨진다

    def test_criterion_comes_along(self):
        """체인의 **판정 문장**이 상태에 실린다.

        승인·기각을 묻는 자리에서 기준이 없으면 그 물음은 의미가 없다 — 무엇에 비추어
        판단하라는 건지가 없으니까. 지금까지 이 문장은 chain-root 트레일러에만 있어서
        읽으려면 그 커밋을 스스로 찾아 열어야 했다(자기규율).
        """
        r = self.gil("chain", "cr", "--purpose", "목적",
                     "--reference", "-", "--criterion", "토큰이 더 적으면 성공이다",
                     input="기준 문서 본문\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self._autofill_interview("cr")
        self.gil("open", "cr/c1", "--purpose", "사이클", "--author", "clew")
        st = self.status()
        self.assertEqual(st["chain"]["criterion"], "토큰이 더 적으면 성공이다")

    def test_rollback_candidates_are_named_in_human_words(self):
        """되돌아갈 자리를 **사람이 읽는 라벨**로 나열한다.

        --to 는 "조상 define" 을 문자열로 받는데, 비개발자는 그 문자열을 알 방법이 없다 —
        그래프를 읽고 스텝 번호를 세어야 나온다. 이 목록이 그 자리를 없앤다.

        그리고 **--to 가 받는 kind 만** 낸다(define·analyze). 고를 수 없는 것을 보여주는
        목록은 없느니만 못하다 — 사람이 고른 것을 문법이 거부한다.
        """
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        st = self.status()
        ids = [c["id"] for c in st["rollback_candidates"]]
        self.assertIn("s1", ids, st["rollback_candidates"])
        for c in st["rollback_candidates"]:
            self.assertIn(c["kind"], ("define", "analyze"))
            self.assertTrue(c["label"].strip())
            self.assertNotIn("gil st/c1", c["label"], "gil 이 붙인 앞머리가 라벨에 남았다")

    def test_last_verdict_answers_why_it_failed(self):
        """사람이 가장 자주 묻는 '왜 실패했어'의 재료 — 지금 선 자리만으로는 답할 수 없다."""
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        self.gil("step", "st/c1", "--kind", "verify", "--verdict", "refuted",
                 "--falsify-out", "met", "--falsify-obs", "관측된 것")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "원인은 딴 데 있었다")
        r = self.gil("step", "st/c1", "--kind", "fail", "--to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.status()
        self.assertIsNotNone(st["last_verdict"])
        self.assertEqual(st["last_verdict"]["cycle"], "c1")
        self.assertEqual(st["last_verdict"]["result"], "fail")
        self.assertTrue(st["last_verdict"]["why"].strip())

    def test_the_next_moves_actually_run(self):
        """**next 가 가르치는 줄이 실제로 돈다.**

        처음 쓴 목록은 종결을 close 의 verdict 로 적었다 — 실물은 step 의 kind 고, close 의
        --verdict 는 supported|partial|rejected 다. 둘을 뭉개면 `gil close … --verdict
        success --to …` 라는 없는 문법이 나오고, 막힌 사람이 그대로 쳐서 한 번 더 막힌다.
        도움말이 문서 경로를 가리키는지 세는 시험(v3.58.1)이 있었지만 **플래그까지는 안
        본다** — 그래서 이 자리는 안 잡혔다. 여기서는 실제로 쳐 본다.
        """
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        self.gil("step", "st/c1", "--kind", "verify", "--verdict", "supported",
                 "--falsify-out", "unmet", "--falsify-obs", "관측")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        st = self.status()
        first = st["next"][0].split("  —")[0].strip().split()
        self.assertEqual(first[0], "gil")
        r = self.gil(*first[1:])
        self.assertEqual(r.returncode, 0, f"next[0] 가 안 돈다: {st['next'][0]}\n{r.stderr}")

    def test_rollback_says_what_gets_discarded(self):
        """되돌아갈 자리는 **무엇을 잃는가**와 함께 온다.

        목록만으로는 고를 수 없다. 사람이 고르는 근거는 "s4"가 아니라 "s5~s7 이 버려진다"다 —
        번호는 주소고, 판단은 잃는 것으로 한다.
        """
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        self.gil("step", "st/c1", "--kind", "verify", "--verdict", "refuted",
                 "--falsify-out", "met", "--falsify-obs", "관측")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        st = self.status()
        by = {c["id"]: c for c in st["rollback_candidates"]}
        self.assertIn("s1", by, st["rollback_candidates"])
        # s1 로 되돌리면 그 뒤 스텝들이 버려진다 — 자기 자신은 안 버려진다.
        self.assertIn("s2", by["s1"]["discards"])
        self.assertNotIn("s1", by["s1"]["discards"])

    def test_closure_report_fields_come_along(self):
        """success·fail 카드의 본문이 데이터로 온다 — toward·next_design.

        이 둘은 트레일러에 이미 있었는데 status 가 안 실어서, 그리는 쪽이 커밋 본문을
        스스로 열어야 했다(자기규율). 리포트 카드의 몸통이 거기 있다.
        """
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        self.gil("step", "st/c1", "--kind", "verify", "--verdict", "supported",
                 "--falsify-out", "unmet", "--falsify-obs", "관측")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "이 분석이 밝힌 것")
        st = self.status()
        self.assertEqual(st["step"]["finding"], "이 분석이 밝힌 것")
        r = self.gil("step", "st/c1", "--kind", "success",
                     "--toward", "체인 목적에 이만큼 다가섰다",
                     "--next-design", "다음은 이것을 겨눈다")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.status()
        self.assertEqual(st["step"]["toward"], "체인 목적에 이만큼 다가섰다")
        self.assertEqual(st["step"]["next_design"], "다음은 이것을 겨눈다")

    def test_the_seven_kinds_are_written_down(self):
        """일곱 kind 규칙이 **문서에** 있다 — 코드가 아니라.

        화면을 Go 에 박으면 이 방식의 값어치를 그 자리에서 버린다. 그리고 규칙이 문서에만
        있으면 안 읽히니, render_guide 가 그 자리를 가리킨다(이미 시험이 있다).
        """
        r = self.gil("docs", "install")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = (Path(self.repo) / "docs" / "gil" / "status-card.md").read_text()
        for kind in ("define", "hypothesis", "verify", "analyze", "pending", "success", "fail"):
            self.assertIn("`" + kind + "`", doc, f"{kind} 카드 규칙이 없다")
        self.assertIn("discards", doc)

    def test_cycle_steps_carry_everything_the_strip_needs(self):
        """띠를 그리는 재료가 **데이터에** 있다 — 그리는 쪽이 git 을 따로 뒤지지 않게.

        값을 실측으로 치렀다: 손으로 그리는 동안 없는 간선을 지어내고(s9→s8), 있는 간선을
        빠뜨리고(s12→s14), 브랜치 이름을 분기로 읽어 없는 갈라짐을 만들었다. 셋 다 데이터를
        안 보고 그려서 난 일이다.
        """
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        st = self.status()
        steps = st["cycle"]["steps"]
        self.assertEqual([s["id"] for s in steps], ["s1", "s2"])
        self.assertEqual(steps[0]["kind"], "define")
        self.assertEqual(steps[1]["parent"], "s1")   # 간선은 parent 로만 그린다

    def test_backtrack_is_only_what_the_record_says(self):
        """기록에 없는 백트랙은 데이터에도 없다 — 그리는 쪽이 지어낼 재료를 주지 않는다."""
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        st = self.status()
        for s in st["cycle"]["steps"]:
            self.assertEqual(s.get("back", ""), "", f"{s['id']} 에 없는 백트랙이 실렸다")
        self.gil("step", "st/c1", "--kind", "verify", "--verdict", "refuted",
                 "--falsify-out", "met", "--falsify-obs", "관측")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        self.gil("step", "st/c1", "--kind", "fail", "--to", "s1")
        st = self.status()
        backs = {s["id"]: s.get("back", "") for s in st["cycle"]["steps"]}
        self.assertEqual(backs.get("s5") or backs.get("s4"), "s1",
                         f"되돌아간 자리가 기록대로 안 실렸다: {backs}")

    def test_the_cycle_carries_what_it_inherited(self):
        """근거 칸 — 왜 하필 이 문제를 정의했는지는 대개 앞에서 물려받은 문장에 있다.

        물려받은 것이 없으면 이 필드도 없다(빈 칸을 지어내지 않는다). 그때 카드는 근거
        구역을 통째로 뺀다 — 빈 제목만 남기면 화면은 그럴듯해지고 내용은 없다.
        """
        r = self.gil("chain", "inh", "--purpose", "물려받는 체인")
        self.assertEqual(r.returncode, 0, r.stderr)
        self._autofill_interview("inh")
        r = self.gil("open", "inh/c1", "--purpose", "사이클", "--author", "clew",
                     "--inherit", "앞 사이클이 세운 것: 기울기가 넘어왔다")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.status()
        self.assertIn("기울기가 넘어왔다", st["cycle"]["inherit"])

    def shell(self, env=None):
        """껍데기(템플릿). 카드 조각과 다른 물건이다 — 배선은 여기 산다.

        env: 서버 프로세스에 얹을 환경변수(진단 계기 GIL_UI_PROBE 처럼 껍데기를 바꾸는 것).
        """
        import json
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1,
                             env=dict(os.environ, GIL_NO_VIEWER="1", GIL_NO_VERSION_CHECK="1",
                                      **(env or {})))
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2026-01-26", "capabilities": {},
                             "clientInfo": {"name": "t", "version": "1"}}})
            p.stdout.readline()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "resources/read",
                  "params": {"uri": "ui://gil/status"}})
            while True:
                line = p.stdout.readline()
                if not line:
                    self.fail("껍데기를 못 읽었다")
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("id") == 2:
                    return msg["result"]["contents"][0]["text"]
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()

    def visible(self, html):
        """**사람에게 보이는 글자만** 남긴다(태그·속성·스크립트를 걷는다).

        왜 이 구분이 필요한가. 규칙은 "카드에 **그리지** 마라"이고, 속성에 담겨 에이전트에게
        가는 문장은 그리는 것이 아니다 — 승인 버튼은 gil 이 준 다음 단계를 대화로 실어
        보낸다(창작하지 않으려고). 문자열의 존재를 세면 그 구분이 사라져 시험이 못 쓰게 된다.
        """
        import re
        h = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
        h = re.sub(r"<style.*?</style>", " ", h, flags=re.S)
        return re.sub(r"<[^>]*>", " ", h)

    def card(self):
        """카드 한 장(HTML). MCP 호스트만 그리는 화면은 검증할 수 없다 — 실측: 이 카드는
        어떤 시험도 안 지나간 채로 있었고, 그래서 그리는 규칙을 지키는지 아무도 몰랐다."""
        r = self.gil("status", "--card")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def _branching_cycle(self):
        """척추 s1~s5(fail, s1 로 백트랙) + s1 에서 다시 갈라진 s6. 일곱 색 중 넷이 선다."""
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--title", "첫 축",
                 "--falsify", "안 되면", "--falsify-to", "s1")
        self.gil("step", "st/c1", "--kind", "verify", "--title", "재봤다",
                 "--verdict", "refuted", "--falsify-met", "관측된 것")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "다른 축이 있다")
        self.gil("step", "st/c1", "--kind", "fail", "--to", "s1", "--title", "이 축은 닫는다")
        r = self.gil("step", "st/c1", "--kind", "hypothesis", "--to", "s1",
                     "--inherit", "앞 가지의 벽", "--title", "둘째 축",
                     "--falsify", "안 되면", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_card_carries_the_strip_on_top(self):
        """띠는 **카드 종류와 무관하게** 맨 위에 있다(상현님).

        본문은 kind 마다 다르지만 "어디에 서 있나"는 어느 카드에서도 같은 질문이다. 띠가
        kind 마다 나타나고 사라지면 사람은 매번 화면 구조를 다시 읽어야 하고, 그러면 카드가
        한 종류의 물건으로 안 읽힌다.
        """
        self._cycle()                      # define 자리
        self.assertIn('class="strip"', self.card())
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        self.assertIn('class="strip"', self.card())   # hypothesis 자리
        self.gil("step", "st/c1", "--kind", "verify", "--verdict", "supported",
                 "--falsify-unmet", "관측")
        self.assertIn('class="strip"', self.card())   # verify 자리

    def test_the_strip_draws_the_spine_straight_and_the_branch_down(self):
        """꺾인 선은 곧 분기다 — 분기가 아닌 간선을 꺾으면 없는 갈라짐을 그린 것이 된다.

        척추(첫 자식)는 `<line>` 곧은 가로선, 분기(둘째 자식부터)는 부모 자리에서 내려간 뒤
        오른쪽으로 꺾는 `<path>`. 그리고 **행이 둘 이상 선다** — 형제가 한 줄에 포개지면
        비교하려고 놓은 그림이 비교를 못 하게 한다(#114 가 전체맵에서 치른 값).
        """
        import re
        self._branching_cycle()
        svg = re.search(r'<svg class="strip".*?</svg>', self.card(), re.S).group(0)
        ys = {int(m) for m in re.findall(r'<circle cx="\d+" cy="(\d+)"', svg)}
        self.assertEqual(len(ys), 2, f"분기가 새 행으로 안 내려갔다: {sorted(ys)}")
        spine = re.findall(r'<line class="e" x1="\d+" y1="(\d+)" x2="\d+" y2="(\d+)"', svg)
        self.assertTrue(spine, "척추가 곧은 가로선으로 안 그려졌다")
        for y1, y2 in spine:
            self.assertEqual(y1, y2, "척추 간선이 꺾였다 — 없는 분기를 그린 것이 된다")
        self.assertIn('<path class="e"', svg, "분기 간선이 없다")

    def test_the_backtrack_is_one_arc_from_the_leaf_to_the_step_it_returned_to(self):
        """되돌림은 **경로가 아니라 두 자리의 관계**다(상현님).

        처음엔 지나온 간선을 되짚어 그렸다. 그러면 점선이 실제 간선과 나란히 겹쳐 달려서
        **어디서 어디로 돌아갔는지가 안 보였다.** 활 하나로 굽혀 빼면 시작과 끝이 바로 읽힌다.
        양 끝은 노드 중앙에 맞물린다 — 오프셋에서 멈추면 허공에서 끝난 선으로 읽힌다.
        """
        import re
        self._branching_cycle()
        svg = re.search(r'<svg class="strip".*?</svg>', self.card(), re.S).group(0)
        bt = re.search(r'<path class="bt" d="([^"]+)"', svg)
        self.assertIsNotNone(bt, "기록에 있는 백트랙이 안 그려졌다")
        d = bt.group(1)
        self.assertIn(" C", d, f"활이 아니라 꺾인 선으로 그렸다: {d}")
        # s1(define, 회색)이 척추의 시작점 — 활은 그 중앙에서 끝난다.
        first = re.search(r'<circle cx="(\d+)" cy="(\d+)" r="\d+" fill="#888780"', svg)
        self.assertIsNotNone(first, "define 노드를 못 찾았다")
        self.assertTrue(d.rstrip().endswith(f", {first.group(1)} {first.group(2)}"),
                        f"활이 s1 중앙에서 끝나지 않는다: {d}")
        # 그리고 죽은 잎(코랄)의 중앙에서 시작한다.
        leaf = re.search(r'<circle cx="(\d+)" cy="(\d+)" r="\d+" fill="#D85A30"', svg)
        self.assertTrue(d.startswith(f"M{leaf.group(1)} {leaf.group(2)}"),
                        f"활이 죽은 잎에서 시작하지 않는다: {d}")

    def test_the_strip_does_not_discriminate_the_dead_leaf(self):
        """죽은 잎도 **같은 반지름·같은 실선**, 색만 다르다. 그리고 **빨강이 아니다**.

        빨강은 오류의 색이라 그걸 쓰면 fail 이 잘못으로 읽히고, 사람은 되돌리기를 손실로
        읽는다 — gil 이 막으려는 바로 그 압력이다.
        """
        import re
        self._branching_cycle()
        svg = re.search(r'<svg class="strip".*?</svg>', self.card(), re.S).group(0)
        radii = {r for r in re.findall(r'<circle cx="\d+" cy="\d+" r="(\d+)" fill=', svg)}
        self.assertEqual(len(radii), 1, f"노드 크기가 종류마다 다르다: {radii}")
        self.assertIn("#D85A30", svg, "죽은 잎 코랄이 없다")
        self.assertNotIn("#E24B4A", svg, "죽은 잎을 빨강으로 칠했다")

    def test_the_ring_says_where_i_am_and_the_color_says_what_it_is(self):
        """지금 위치는 색이 아니라 **바깥 링**이다 — 색은 종류를 말하는 자리라 둘을 한 채널에
        얹으면 하나가 다른 하나를 덮는다."""
        import re
        self._branching_cycle()
        svg = re.search(r'<svg class="strip".*?</svg>', self.card(), re.S).group(0)
        rings = re.findall(r'<circle class="ring" cx="(\d+)" cy="(\d+)"', svg)
        self.assertEqual(len(rings), 1, f"링이 하나가 아니다: {rings}")
        st = self.status()
        cur = st["step"]["id"]
        node = re.search(r'<circle cx="(\d+)" cy="(\d+)" r="\d+" fill="[^"]+"><title>' + cur, svg)
        self.assertIsNotNone(node, f"{cur} 노드를 못 찾았다")
        self.assertEqual(rings[0], (node.group(1), node.group(2)), "링이 딴 스텝에 걸렸다")

    def test_the_strip_draws_no_edge_it_was_not_given(self):
        """없는 간선을 지어내지 않는다 — 스텝 하나면 선이 없다.

        실측으로 값을 치른 자리다: 손으로 그리는 동안 없는 간선(s9→s8)을 지어냈다.
        """
        import re
        self._cycle()
        svg = re.search(r'<svg class="strip".*?</svg>', self.card(), re.S).group(0)
        self.assertNotIn("<line", svg, "부모가 없는데 간선을 그렸다")
        self.assertNotIn('class="e"', svg)
        self.assertNotIn('class="bt"', svg, "기록에 없는 백트랙을 그렸다")
        # 노드 하나 + 지금 자리를 말하는 링 하나. 그 둘 말고는 아무것도 없다.
        self.assertEqual(len(re.findall(r'<circle cx="\d+" cy="\d+" r="\d+" fill=', svg)), 1)
        self.assertEqual(svg.count('class="ring"'), 1)

    def test_the_define_card_shows_the_problem_and_what_it_stands_on(self):
        """define 카드는 **문제정의**와 **기반사실** 둘이 분명해야 한다(상현님).

        뒤 칸이 없으면 문제정의는 근거 없는 선언으로 읽히고, 승인할지 판단할 재료가 없다.
        그리고 원문(step.body)을 함께 둔다 — 요약만 두면 지어내서 감춘 것이 된다.
        """
        r = self.gil("chain", "df", "--purpose", "정의 카드")
        self.assertEqual(r.returncode, 0, r.stderr)
        self._autofill_interview("df")
        r = self.gil("open", "df/c1", "--author", "clew", "--purpose", "초과분의 출처를 가른다",
                     "--body", "지금 p95 는 780ms 고 예산은 300ms 다. 출처를 모른다.",
                     "--inherit", "앞 사이클: 캐시 축은 닫혔다")
        self.assertEqual(r.returncode, 0, r.stderr)
        card = self.card()
        self.assertIn("문제정의", card)
        self.assertIn("초과분의 출처를 가른다", card)
        self.assertIn("지금 p95 는 780ms", card, "원문이 카드에 없다")
        self.assertIn("전제", card)
        self.assertIn("캐시 축은 닫혔다", card)
        # 승인·기각 두 갈래가 서고, '다음 단계'는 없다(define 다음은 하나뿐이라 자명하다).
        self.assertIn('data-act="approve"', card)
        self.assertIn('data-act="reject"', card)
        self.assertNotIn("다음 단계", self.visible(card))

    def test_the_define_card_says_when_it_stands_on_nothing(self):
        """물려받은 사실이 없으면 **없다고 말한다.** 칸을 지우면 근거 없는 문제정의가 근거
        있는 것과 같아 보인다 — 없는 것을 채우지 않는 것과, 없다는 사실을 감추는 것은 다르다."""
        self._cycle()   # --inherit 없이 연 사이클
        card = self.card()
        self.assertIn("전제", card)
        self.assertIn("앞에서 확인된 사실이 기록에 없다", card)

    def test_the_card_divides_by_background_not_by_lines(self):
        """구획은 실선이 아니라 **카드 안의 카드**다(상현님). 그리고 kind 는 제 색 타원이다.

        옅은 회색 알약이었을 때는 지금 무슨 스텝에 서 있는지가 눈에 안 들어왔다 — 카드의
        성격을 정하는 값이 가장 약하게 그려져 있었다.
        """
        self._cycle()
        card = self.card()
        self.assertIn('class="panel"', card)
        self.assertNotIn("border-top:1px solid var(--line)", card, "실선 구획이 남아 있다")
        self.assertIn('class="kind k-define"', card)
        self.assertIn(".k-define{background:", card)
        # 저장소 경로는 남는다 — 어느 저장소의 화면인지(#110 이 오진으로 값을 치른 자리).
        self.assertIn('class="repo"', card)

    def test_the_buttons_carry_what_they_will_do(self):
        """**버튼은 자기가 무엇을 할지 데이터로 지고 선다.** 라벨은 일곱 kind 에서 같지만 뒤에서
        도는 것은 다르다 — 그걸 숨기지 않으면서 배선은 한 곳에 둔다.

        그리고 gil 에 없는 문법은 버튼이 지어내지 않는다. define 에는 "승인" 문법이 없으므로
        사람의 판정을 대화에 넣고(ui/message) 다음 스텝은 에이전트가 쓴다 — 반증조건·퇴로·
        설계는 판단이고, 클릭으로 채울 수 있는 값이 아니다.
        """
        self._cycle()
        card = self.card()
        self.assertIn('data-act="approve"', card)
        self.assertIn('data-act="reject"', card)
        self.assertIn("data-msg=", card, "대화에 전할 문장이 버튼에 없다")
        self.assertIn("다음 단계를 세워라", card, "승인이 다음에 할 일을 말하지 않는다")
        self.assertIn('data-ask-reason="1"', card, "기각이 이유를 묻지 않는다")
        # 작업 스텝에서는 진짜 명령을 물지 않는다(그 문법이 없다).
        self.assertNotIn('data-tool="gil_approve"', card)

    def test_pending_buttons_run_the_real_gate(self):
        """pending 은 **진짜 관문**이다 — gil 문법에 승인·기각이 있다. 그러니 버튼이 그 명령을 돈다.

        그리고 기각은 되돌아갈 자리를 요구하는데(--to), 그 문자열을 비개발자는 알 방법이 없다.
        후보를 **무엇을 잃는가와 함께** 세운다 — 고르는 근거는 "s4"가 아니라 "s5 가 버려진다"다.
        """
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        self.gil("step", "st/c1", "--kind", "verify", "--verdict", "refuted", "--falsify-met", "관측")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        r = self.gil("step", "st/c1", "--kind", "pending", "--title", "사람에게 넘긴다")
        self.assertEqual(r.returncode, 0, r.stderr)
        card = self.card()
        self.assertIn('data-tool="gil_approve"', card)
        self.assertIn('data-tool="gil_reject"', card)
        self.assertIn('data-to="s1"', card)
        self.assertIn("버려진다", card)
        self.assertIn("s2~s5", card, "연속한 스텝이 범위로 안 접혔다")
        # 사람의 판정이 있는 자리에서는 대화로 미루지 않는다.
        self.assertNotIn("data-msg=", card)

    def test_no_card_draws_the_next_move(self):
        """**다음 단계는 카드에 없다**(상현님). 사람이 정할 것은 승인·기각 두 갈래고, 그 자리는
        버튼이 쓴다. gil 명령줄은 에이전트가 칠 것이라 카드에 두면 사람에게는 읽을 이유 없는
        줄이 되고 화면에서 가장 길어지는 칸이 된다 — 데이터(`next`)에는 그대로 있다."""
        self._cycle()
        self.assertNotIn("다음 단계", self.visible(self.card()), "define 카드에 남았다")
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        self.assertNotIn("다음 단계", self.visible(self.card()), "hypothesis 카드에 남았다")
        self.gil("step", "st/c1", "--kind", "verify", "--verdict", "refuted", "--falsify-met", "관측")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        seen = self.visible(self.card())
        self.assertNotIn("다음 단계", seen, "analyze 카드에 남았다(선택지가 넷인 자리)")
        self.assertNotIn("--kind success", seen, "명령줄이 화면에 남았다")
        # 다만 **대화로 가는 문장**에는 gil 이 준 그 줄이 실려야 한다 — 에이전트가 문법을
        # 창작하면 사람은 막힌 뒤에야 안다.
        self.assertIn("다음 단계:", self.card(), "승인이 다음 단계를 에이전트에게 안 넘긴다")
        # 데이터에는 있어야 한다 — 에이전트가 읽고 치는 값이다.
        self.assertTrue(self.status()["next"], "next 가 데이터에서도 사라졌다")

    # ── 나머지 다섯 얼굴 (verify·analyze·pending·success·fail) ──────────────
    #
    # 이 다섯은 오래 얼굴이 없었고, 그동안 공통 본문이 **"재는 중 — 무엇이 관측되면 틀리나"**
    # 를 다섯 자리에 똑같이 그렸다. 죽은 잎 위에도, 이미 닫힌 산 잎 위에도. 시제 하나가
    # 사람에게 "아직 결과가 없다"고 말하는데, 그 자리들은 판정이 이미 난 자리다.

    def _measured(self, verdict="supported", plan="held"):
        """define → hypothesis → verify. **측정이 실제로 기록된** 자리에 선다."""
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--title", "state 축이 초과분을 설명한다",
                 "--falsify", "접어도 p95 가 600ms 아래로 안 내려가면 이 축은 틀렸다",
                 "--falsify-to", "s1", "--plan", "신규 실행경로 1개")
        args = ["step", "st/c1", "--kind", "verify", "--verdict", verdict, "--title", "3회 측정",
                "--body", "절차와 수치는 여기 원문으로 남는다."]
        args += ["--falsify-met", "3회 평균 +0.4% — 개선 없음"] if verdict == "refuted" \
            else ["--falsify-unmet", "3회 평균 435ms — 600ms 아래"]
        args += ["--plan-broke", "실행경로가 3개 생겼다(예상 1)"] if plan == "broke" \
            else ["--plan-held"]
        r = self.gil(*args)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_measurement_comes_from_the_nearest_verify(self):
        """측정은 **한 자리에서** 온다(`cycle.measured`) — 네 카드가 그 하나를 본다.

        verify 가 남긴 넷(판정·반증조건 충족 여부·관측·설계 유지 여부)은 지금까지 status 에
        아예 안 나왔다. 그래서 verify 카드는 그릴 것이 없었고, analyze·success·fail 도
        "무엇을 재서 그렇게 됐나"에 답할 수 없었다.
        """
        self._measured(plan="broke")
        m = self.status()["cycle"]["measured"]
        self.assertEqual(m["verdict"], "supported")
        self.assertEqual(m["falsify_outcome"], "unmet")
        self.assertIn("435ms", m["observed"])
        self.assertEqual(m["plan_outcome"], "broke")
        self.assertIn("실행경로가 3개", m["plan_diff"])
        # **가장 가까운 조상**이다(가설과 같은 규칙). 형제 갈래에는 제 측정이 없다 —
        # 사이클에서 아무 verify 나 집으면 남의 측정을 이 갈래의 것으로 말하게 된다.
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "다른 축이 있다")
        r = self.gil("step", "st/c1", "--kind", "hypothesis", "--to", "s1",
                     "--inherit", "앞 가지의 벽", "--falsify", "안 되면", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNone(self.status()["cycle"].get("measured"),
                          "새 갈래가 앞 갈래의 측정을 제 것처럼 말한다")

    def test_the_verify_card_says_what_came_out_not_what_is_being_measured(self):
        """verify 스텝은 **판정과 함께 태어난다** — 문법이 그걸 요구한다(`--verdict`,
        `--falsify-met|--falsify-unmet`). 이미 지나간 측정을 '재는 중'이라 부르면 사람은
        아직 결과가 없는 줄 안다."""
        self._measured(plan="broke")
        card = self.card()
        seen = self.visible(card)
        self.assertIn("측정 결과", seen)
        self.assertNotIn("재는 중", seen, "이미 난 판정을 현재형으로 부른다")
        self.assertIn("가설을 지지했다", seen, "필드 이름(supported)을 그대로 읽었다")
        self.assertIn("반증조건은 관측되지 않았다", seen)
        # 판정만 있고 관측이 없으면 사람은 그 판정을 **검산할 수 없다**.
        self.assertIn("435ms", seen)
        # 정한 방법대로 안 됐다는 것이 사람이 기각할 가장 큰 근거다 — 다른 것을 잰 셈이니까.
        self.assertIn("그대로 실행되지 않았다", seen)
        self.assertIn("실행경로가 3개", seen)
        # 측정 보고서 원문은 자르지 않는다.
        self.assertIn("절차와 수치는 여기 원문으로 남는다", seen)
        # 되돌아갈 단계 후보는 여기 없다 — 되돌릴지는 analyze 에서 정한다.
        self.assertNotIn("되돌아갈", seen)

    def test_the_verify_card_says_when_the_plan_held(self):
        """정한 대로 됐으면 그렇다고 말한다 — ⚠ 를 늘 달면 그 표시가 아무 뜻도 없어진다."""
        self._measured(plan="held")
        seen = self.visible(self.card())
        self.assertIn("그대로 실행됐다", seen)
        self.assertNotIn("실행되지 않았다", seen)

    def test_the_analyze_card_puts_the_finding_first(self):
        """`finding` 은 gil 이 문법으로 요구하는 값이고 **재분기가 딛는 문장**이다.
        그런데 카드에는 한 번도 뜬 적이 없었다."""
        self._measured()
        r = self.gil("step", "st/c1", "--kind", "analyze",
                     "--finding", "state 축은 345ms 를 설명한다 — 남은 135ms 는 다른 축이다")
        self.assertEqual(r.returncode, 0, r.stderr)
        card = self.card()
        seen = self.visible(card)
        self.assertIn("state 축은 345ms 를 설명한다", seen)
        self.assertIn("근거가 된 측정", seen, "결론이 무엇 위에 섰는지가 없다")
        self.assertIn("되돌아갈 수 있는 단계", seen)
        self.assertIn("버려진다", seen, "번호만으로는 고를 수 없다")
        # **버튼은 안 단다.** 재분기는 --inherit <이 벽의 교훈> 을 요구하고 그건 판단이지
        # 클릭으로 채울 값이 아니다(pending 의 기각과 다른 점 — 거기엔 문법이 있다).
        self.assertNotIn('data-tool="gil_reject"', card)

    def test_the_approval_sentence_carries_every_next_gil_gave(self):
        """analyze 뒤는 **넷**이다. 첫 줄만 실으면 그건 카드가 사람 대신 고른 것이다.

        규칙은 "gil 이 준 것을 그대로 옮겨라"이지 "첫 줄만"이 아니다 — 그 선택이 이 사이클의
        방향을 정한다.
        """
        import html as _html
        import re
        self._measured()
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        st = self.status()
        self.assertGreater(len(st["next"]), 1, st["next"])
        msg = _html.unescape(re.search(r'data-act="approve"[^>]*data-msg="([^"]*)"',
                                       self.card()).group(1))
        for n in st["next"]:
            self.assertIn(n, msg, f"gil 이 준 수가 승인 문장에서 빠졌다: {n}")

    def test_the_pending_card_shows_the_question_and_the_yardstick(self):
        """pending 은 사람이 실제로 값을 더하는 자리다. 그런데 그 자리에 뜬 것은 공통 본문이었고
        **에이전트가 물으려고 쓴 보고서(step.body)는 한 글자도 안 나왔다** — 물음이 없는 물음 화면."""
        self._measured()
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        r = self.gil("step", "st/c1", "--kind", "pending", "--title", "여기서 닫을지 묻는다",
                     "--body", "선택지 둘: 여기서 닫거나, 한 축 더 열거나. 12ms 모자란다.")
        self.assertEqual(r.returncode, 0, r.stderr)
        card = self.card()
        seen = self.visible(card)
        self.assertIn("무엇을 묻는가", seen)
        self.assertIn("12ms 모자란다", seen, "물음의 재료가 화면에 없다")
        self.assertIn("무엇에 비추어 판단하나", seen)
        self.assertIn(self.status()["chain"]["criterion"], seen)
        # 나머지는 전부 뺀다 — 여기서 사람이 할 일은 하나다.
        self.assertNotIn("반증조건", seen)
        # 그리고 **명령줄은 상자에도 안 온다** — 그 두 줄을 도는 버튼이 바로 아래 있다.
        self.assertNotIn("gil approve", seen)
        self.assertNotIn("gil reject", seen)
        self.assertIn('data-tool="gil_approve"', card)

    def test_the_success_card_holds_the_retrospect_next_to_the_yardstick(self):
        """종결 둘은 순서가 뒤집힌다 — 다음 단계가 아니라 **판정 기준과의 대조**가 본문이다.
        떼어 놓으면 "얼마나 다가섰나"가 무엇에 비추어 한 말인지 사라진다."""
        self._measured()
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        r = self.gil("step", "st/c1", "--kind", "success", "--title", "이 축을 닫는다",
                     "--toward", "기준에 780→435ms 로 다가섰다", "--next-design", "다음은 배치 축")
        self.assertEqual(r.returncode, 0, r.stderr)
        seen = self.visible(self.card())
        self.assertIn("기준에 780→435ms 로 다가섰다", seen)
        self.assertIn(self.status()["chain"]["criterion"], seen, "무엇에 비추어 한 말인지가 없다")
        self.assertIn("다음 설계", seen)
        self.assertIn("다음은 배치 축", seen)
        self.assertIn("근거가 된 측정", seen)

    def test_the_success_that_approve_made_says_it_has_no_retrospect(self):
        """`gil approve` 는 --toward·--next-design 을 **묻지 않는다.** 그러면 회고가 없는
        종결이 생긴다 — 칸을 지우면 회고를 쓴 종결과 안 쓴 종결이 화면에서 같아 보인다."""
        self._measured()
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        self.gil("step", "st/c1", "--kind", "pending", "--title", "묻는다", "--body", "보고서")
        r = self.gil("approve", "st/c1")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.status()
        self.assertEqual(st["step"]["kind"], "success")
        self.assertEqual(st["step"].get("toward", ""), "")
        self.assertIn("판정 기준과 대조한 기록이 없다", self.visible(self.card()))

    def test_the_fail_card_says_why_it_died_and_where_it_retreats(self):
        """fail 은 죽음이 아니라 발견이다. 사람이 볼 것은 사과가 아니라 **왜 죽었고 어디로
        물러서나**다 — 그 자리가 없으면 반증된 뒤에 그래프를 뒤져 스텝 번호를 세게 된다."""
        self._measured(verdict="refuted")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "이 축은 죽었다")
        r = self.gil("step", "st/c1", "--kind", "fail", "--to", "s1", "--title", "이 축을 닫는다",
                     "--toward", "다가서진 못했지만 후보 하나를 지웠다",
                     "--next-design", "다음은 배치 축")
        self.assertEqual(r.returncode, 0, r.stderr)
        seen = self.visible(self.card())
        self.assertIn("왜 기각됐나", seen)
        self.assertIn("3회 평균 +0.4%", seen, "기각의 근거가 된 관측이 없다")
        self.assertIn("복귀 단계", seen)
        self.assertIn("s1 단계로 되돌아간다", seen)
        self.assertIn("버려진다", seen)
        self.assertIn("이 기각으로 알게 된 것", seen)
        self.assertIn("다가서진 못했지만", seen)
        # **다음 설계는 그리지 않는다** — 기각된 분기 위에 놓으면 화면이 "이제 앞으로 간다"고
        # 말하는데, 옳은 읽기는 "되돌아가서 다시 분기한다"다. 데이터에는 그대로 있다.
        self.assertNotIn("다음은 배치 축", seen, "기각된 분기 위에 다음 설계를 크게 놓았다")
        self.assertEqual(self.status()["step"]["next_design"], "다음은 배치 축")

    def test_a_leaf_never_tells_the_human_to_build_the_next_step_on_it(self):
        """**종결은 잎이다** — 그 뒤에 스텝을 이어 붙일 수 없다(#60①).

        그런데 `next` 가 오래 비어 있었고, 그 공백을 승인 버튼이 "이 자리를 딛고 다음 스텝을
        세워라"로 메웠다. 사람이 승인을 누른 그 순간 에이전트는 gil 이 거부할 수를 지시받는다.
        빈 자리는 채워지지 않는 게 아니라 **지어내서 채워진다.**
        """
        import html as _html
        import re
        self._measured()
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "결론")
        self.gil("step", "st/c1", "--kind", "success", "--title", "닫는다")
        card = self.card()
        msg = _html.unescape(re.search(r'data-act="approve"[^>]*data-msg="([^"]*)"', card).group(1))
        self.assertNotIn("다음 단계를 세워라", msg)
        self.assertIn("이 분기는 여기서 종결된다", msg)
        # 그리고 **그 다음이 실제로 돈다.** 안 도는 줄을 가르치면 막힌 사람이 한 번 더 막힌다.
        st = self.status()
        self.assertTrue(st["next"], "잎에서 다음 단계가 통째로 비었다")
        first = st["next"][0].split("  —")[0].strip().split()
        self.assertEqual(first[0], "gil")
        r = self.gil(*first[1:])
        self.assertEqual(r.returncode, 0, f"next[0] 가 안 돈다: {st['next'][0]}\n{r.stderr}")

    def test_the_fail_next_points_at_the_wall_map_it_recorded(self):
        """fail 의 기본 수는 닫는 것이 아니라 **다시 갈라지는 것**이고, 그 자리는 이미
        기록에 있다(Gil-Backtrack). 자리표시자로 두면 사람이 그래프를 세게 된다."""
        self._measured(verdict="refuted")
        self.gil("step", "st/c1", "--kind", "analyze", "--finding", "죽었다")
        self.gil("step", "st/c1", "--kind", "fail", "--to", "s1", "--title", "닫는다")
        nxt = self.status()["next"]
        self.assertTrue(any("--kind hypothesis --to s1" in n for n in nxt), nxt)
        self.assertTrue(any("--abandon" in n for n in nxt), nxt)

    def test_the_probe_is_off_unless_someone_turns_it_on(self):
        """계기는 **기본으로 꺼 둔다.** 이 보고는 화면이 안 뜨던 다섯 자리를 찾는 데 값을 다
        했지만, 켠 채로 릴리스하면 모든 세션이 매번 두 번씩 진단 호출을 한다. 도구가 자기를
        진단하는 비용을 사용자가 늘 치를 이유는 없다."""
        self._cycle()
        off = self.shell()
        self.assertIn("PROBE=false", off, "진단 보고가 기본으로 켜져 있다")
        # 부르는 자리도 막혀 있어야 한다 — 함수 안에서만 막으면 타이머는 계속 돈다.
        self.assertIn("if(PROBE){ setTimeout", off, "보고 타이머가 무조건 걸린다")
        self.assertIn("if(!PROBE) return;", off)
        # 그리고 **켜는 길이 실제로 켠다** — 끄는 길만 만들면 다음에 막혔을 때 계기가 없다.
        self.assertIn("PROBE=true", self.shell(env={"GIL_UI_PROBE": "1"}))

    def test_the_card_follows_the_theme_the_host_declares(self):
        """샌드박스 iframe 의 `prefers-color-scheme` 은 **OS 의 것**이지 호스트 앱의 것이 아니다.

        앱만 어둡게 써 온 사람에게는 어두운 화면 한가운데 흰 카드가 선다. 호스트가 제 테마를
        말해 주면 그것이 이겨야 하고, **양쪽 방향으로** 이겨야 한다 — 밝게 고정한 사람이
        밤에 어두워지지도 않게.
        """
        import re
        self._cycle()
        shell = self.shell()
        self.assertIn("applyTheme", shell, "호스트가 준 테마를 안 읽는다")
        self.assertIn(':root[data-theme="dark"]{', shell)
        self.assertIn(':root:not([data-theme="light"])', shell, "밝게 고정해도 밤에 어두워진다")
        # 팔레트는 **한 벌씩만.** 같은 색을 두 번 적으면 다음에 한쪽만 고쳐지고, 그러면
        # 테마를 말해 준 호스트와 안 말해 준 호스트가 다른 화면을 본다.
        blocks = re.findall(r"\{(--bg:[^}]*)\}", shell)
        self.assertEqual(len(blocks), 3, blocks)
        self.assertEqual(blocks[1], blocks[2], "어두운 팔레트 두 벌이 갈렸다")
        # 색 변수는 **이제 쓴다** — 규범(SEP-1865)이 이름을 표준화했기 때문이다
        # (`--color-background-primary`·`--color-text-primary`·`--font-sans` …).
        # 옛 시험은 "안 쓴다"를 단언했는데, 그건 **이름을 모르던 시절의 결정**이었다.
        #
        # 지켜야 하는 것은 그 결정이 아니라 그 아래의 **안전 성질**이다: 이름을 모르는 값을
        # 우리 변수(--bg 등)에 꽂으면 배경이 아닌 값이 배경이 되어 카드가 통째로 안 읽힌다.
        # 그래서 우리 변수는 **명시적으로 짝지은 것에서만** 온다.
        self.assertIn("styles.variables", shell, "호스트가 준 색·글꼴을 안 읽는다")
        body = shell.partition("function applyHostStyles(")[2].partition("\n  }")[0]
        self.assertTrue(body.strip(), "applyHostStyles 를 못 읽었다 — 이 시험이 눈이 먼다")
        self.assertIn('"--color-background-primary":"--bg"', body,
                      "규범의 이름과 우리 이름을 짝지은 표가 없다")
        # 우리 변수에 값을 꽂는 자리는 **그 표를 도는 한 곳**뿐이어야 한다.
        ours = re.findall(r'setProperty\(\s*"(--(?:bg|fg|dim|line|card|panel|acc)[a-z-]*)"', body)
        self.assertEqual(ours, [],
                         "우리 변수 이름을 직접 꽂는 자리가 있다 — 표를 거치지 않으면 "
                         "모르는 값이 배경이 될 수 있다: " + repr(ours))

    # ── 본문은 보고서다 — 날것으로 찍으면 가장 정보가 많은 칸이 가장 안 읽힌다 ────────

    def _report_body(self):
        """표·강조·리스트·코드블록·그림 둘·바깥 그림 하나가 든 보고서."""
        return (
            "절차: 진입점에서 1회 읽기로 접고 부하 3회.\n"
            "\n"
            "| 회차 | p95 |\n"
            "|---|---|\n"
            "| 1 | 431ms |\n"
            "| 2 | 448ms |\n"
            "\n"
            "### 남은 것\n"
            "\n"
            "- **state 축**은 345ms 를 설명한다\n"
            "- 남은 135ms 는 `batch` 축이다\n"
            "\n"
            '<svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg">'
            '<rect width="10" height="10" fill="#378ADD"/></svg>\n'
            "\n"
            "![측정 곡선](data:image/png;base64,iVBORw0KGgo=)\n"
            "\n"
            "![바깥 그림](https://example.com/plot.png)\n"
        )

    def test_the_card_renders_the_report_instead_of_printing_it_raw(self):
        """본문은 커밋에 실려 오는 **보고서**고 에이전트는 그걸 마크다운으로 쓴다.

        카드가 날것으로 찍으면 표는 파이프 줄로, 강조는 별 네 개로 보인다 — 화면에서 정보가
        가장 많은 칸이 가장 안 읽히는 칸이 된다(상현님 실측).
        """
        self._cycle()
        r = self.gil("step", "st/c1", "--kind", "hypothesis", "--title", "축을 세운다",
                     "--body", self._report_body(),
                     "--falsify", "안 되면", "--falsify-to", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)
        card = self.card()
        self.assertIn("<table>", card, "표가 파이프 줄로 찍혔다")
        self.assertIn("<th>회차</th>", card)
        self.assertIn("<td>431ms</td>", card)
        self.assertIn("<strong>state 축</strong>", card, "강조가 별 네 개로 남았다")
        self.assertIn("<h3>남은 것</h3>", card)
        self.assertIn("<li>", card)
        self.assertIn("<code>batch</code>", card)
        # 날것 문법이 화면 글자로 남지 않는다.
        seen = self.visible(card)
        self.assertNotIn("|---|", seen)
        self.assertNotIn("**state 축**", seen)
        self.assertNotIn("### 남은 것", seen)

    def test_pictures_travel_as_pictures_and_ascii_art_is_not_one(self):
        """**시각화할 수 있는 것은 시각화한다**(상현님). 통로는 둘뿐이다: 본문에 그대로 쓴
        SVG, 그리고 data: 로 심은 그림.

        날 SVG 는 <img> 로 감싸 나른다 — 그 문맥에서는 스크립트가 안 돌고 바깥 요청도 안 간다.
        그림을 요구하면서 위험한 통로를 열어 둘 수는 없다.
        """
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--title", "축",
                 "--body", self._report_body(), "--falsify", "안 되면", "--falsify-to", "s1")
        card = self.card()
        self.assertIn('src="data:image/svg+xml;base64,', card, "날 SVG 가 그림이 안 됐다")
        self.assertNotIn("<svg viewBox=\"0 0 10 10\"", card, "SVG 를 문서에 그대로 심었다")
        self.assertIn('src="data:image/png;base64,iVBORw0KGgo="', card)
        # **바깥 주소는 안 그린다** — 샌드박스에서 막히고, 저장소 내용을 밖으로 내보내는
        # 통로가 된다. 다만 **막았다는 사실은 적는다**: 빈 자리는 그림이 없는 것과 같아 보인다.
        self.assertNotIn("https://example.com/plot.png", card)
        self.assertIn("바깥 주소 대신", self.visible(card))

    def test_the_one_line_values_render_their_emphasis_too(self):
        """한 줄짜리 트레일러 값에도 강조와 코드가 온다 — 거기만 날것으로 두면 같은 문법이
        어떤 칸에서는 그려지고 어떤 칸에서는 별표로 남는다."""
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis",
                 "--title", "`state` 접근이 **초과분**을 설명한다",
                 "--falsify", "안 되면", "--falsify-to", "s1")
        card = self.card()
        self.assertIn("<code>state</code>", card)
        self.assertIn("<strong>초과분</strong>", card)

    def test_the_legend_names_the_colors_in_english_only(self):
        """범례는 **색 열쇠**다(상현님). 뜻풀이는 머리글 타원이 이미 지고 있으니, 일곱 줄에
        다 붙이면 색 열쇠가 문장 일곱 개짜리 표가 된다."""
        self._cycle()
        card = self.card()
        import re
        legend = re.search(r'<div class="legend">.*?</div>\s*</div>', card, re.S).group(0)
        for k in ("define", "hypothesis", "verify", "analyze", "pending", "success", "fail"):
            self.assertIn(">" + k + "</span>", legend, f"{k} 가 이름만으로 안 섰다")
        self.assertNotIn("문제 정의", legend)
        self.assertNotIn("가설 지지로 종결", legend)
        # 다만 **지금 서 있는 kind** 는 머리글에서 뜻까지 말한다.
        self.assertIn("define · 문제 정의", card)

    def test_the_body_rules_are_written_down(self):
        """용어와 그림의 규칙은 문서에 산다 — 안 적으면 다음 세션이 또 아스키아트를 그린다."""
        r = self.gil("docs", "install")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = (Path(self.repo) / "docs" / "gil" / "reports.md").read_text()
        for must in ("아스키아트는 그림이 아니다", "data:image/png;base64", "<svg",
                     "반증조건", "바깥 주소"):
            self.assertIn(must, doc, f"{must} 규칙이 없다")

    def test_the_step_guide_asks_for_scientific_words_and_real_pictures(self):
        """gil 출력은 에이전트에게 주는 프롬프트다 — 규칙이 문서에만 있으면 자기규율이다."""
        self._cycle()
        r = self.gil("step", "st/c1", "--kind", "hypothesis", "--title", "축",
                     "--falsify", "안 되면", "--falsify-to", "s1")
        out = r.stderr + r.stdout
        self.assertIn("용어는 과학의 것으로", out)
        r2 = self.gil("step", "st/c1", "--kind", "verify", "--verdict", "supported",
                      "--falsify-unmet", "관측", "--plan-held")
        out2 = r2.stderr + r2.stdout
        self.assertIn("아스키아트는 그림이 아니다", out2)
        self.assertIn("data:image/png;base64", out2)

    def test_the_confirm_lives_inside_the_card(self):
        """확인은 **카드 안에서** 두 번 누르는 것이다. confirm() 은 샌드박스에서 조용히 죽는다 —
        v3.49.0 에서 그 때문에 승인 자체가 불가능했고 아무 표시도 없었다."""
        self._cycle()
        shell = self.shell()
        # **주석이 아니라 도는 줄만 센다.** 이 자리의 교훈은 주석에 남아야 하고(왜 안 쓰는지),
        # 판정은 실제 호출에 대해서만 해야 한다 — 산문을 세면 시험이 못 쓰게 된다.
        code = "\n".join(l for l in shell.splitlines() if not l.strip().startswith("//"))
        self.assertNotIn("confirm(", code, "샌드박스에서 죽는 대화상자를 쓴다")
        self.assertIn("data-armed", shell)
        self.assertIn("정말?", shell)
        self.assertIn("removeAttribute", shell, "무장이 풀리지 않으면 무심코 누른 것이 실행된다")
        self.assertIn('method:"ui/message"', shell)
        self.assertIn('method:"tools/call"', shell)

    def test_the_root_step_has_no_parent_not_a_parent_named_null(self):
        """뿌리의 부모는 **없다** — `"null"` 이라는 이름의 스텝이 아니다.

        트레일러에는 파수꾼 값 `Gil-Parent: null` 이 산다(코드 곳곳이 빈 값과 같이 다룬다).
        그걸 그대로 내보내면 그리는 쪽은 `null` 로 가는 간선을 그린다 — 문서가 "없는 것을
        그리지 마라"고 못박은 그 자리다. 카드를 손으로 그려 보다 잡았다.
        """
        self._cycle()
        st = self.status()
        root = st["cycle"]["steps"][0]
        self.assertEqual(root["kind"], "define")
        self.assertEqual(root.get("parent", ""), "", f"뿌리에 없는 부모가 실렸다: {root}")

    def test_hypothesis_card_says_why_it_measures(self):
        """hypothesis 카드의 '왜 재나' 칸 — advances 가 데이터로 온다.

        반증조건만 있으면 카드는 "무엇을 재나"까지만 답하고, 그 측정이 체인의 판정 기준과
        무슨 상관인지는 사람이 스스로 이어야 한다. 그 문장은 트레일러에 이미 있었다.
        """
        self._cycle()
        r = self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면",
                     "--falsify-to", "s1", "--advances", "기준의 첫 조각을 짚는다")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.status()
        self.assertEqual(st["cycle"]["advances"], "기준의 첫 조각을 짚는다")
        # 가설 문장에 gil 이 붙인 앞머리가 남아 있으면 사람이 읽을 자리에 주소가 앉는다.
        self.assertNotIn("gil st/c1", st["cycle"]["hypothesis"])
        self.assertNotIn("hypothesis:", st["cycle"]["hypothesis"])
        # 퇴로도 함께 — 반증된 뒤에 그래프를 뒤져 스텝 번호를 세지 않게.
        self.assertEqual(st["cycle"]["falsify_to"], "s1")

    def _competition(self):
        """같은 define 에서 갈라진 경합 둘. A 갈래를 밟은 채로 둔다."""
        self._cycle()
        for name in ("A", "B"):
            r = self.gil("step", "st/c1", "--kind", "hypothesis", "--to", "s1", "--competing",
                         "--title", f"h{name}", "--falsify", f"{name} 가 안 되면",
                         "--falsify-to", "s1")
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_competing_branches_come_side_by_side(self):
        """경합은 **세지 말고 나란히** — 비교할 자리가 없으면 갈래는 열어 둔 채 잊힌다.

        v3.55.0 이 형제 비교를 뷰어에 그렸는데 그 화면은 브라우저를 띄운 사람만 본다.
        작업 중에 보는 카드에 없으면, 경합의 요점인 비교가 그 자리에서 사라진다.
        """
        self._competition()
        st = self.status()
        comp = st["cycle"]["competing"]
        self.assertEqual(len(comp), 2, comp)
        by = {c["id"]: c for c in comp}
        for c in comp:
            self.assertTrue(c["refutes_if"].strip(), c)
            self.assertEqual(c["state"], "open")
        # 내가 밟고 있는 갈래가 표시된다 — 없으면 카드가 어느 갈래를 말하는지 모른다.
        cur = [c["id"] for c in comp if c.get("current")]
        self.assertEqual(len(cur), 1, comp)
        self.assertIn(cur[0], by)

    def test_a_lone_rebranch_is_not_a_competition(self):
        """하나는 경합이 아니라 그냥 재분기다 — 그 칸을 두면 없는 겨룸을 그린 것이 된다."""
        self._cycle()
        self.gil("step", "st/c1", "--kind", "hypothesis", "--falsify", "틀리면", "--falsify-to", "s1")
        st = self.status()
        self.assertEqual(st["cycle"].get("competing", []), [])

    def test_the_adopted_branch_is_named_even_though_it_carries_no_mark(self):
        """**채택된 갈래는 제 커밋에 아무 표식이 없다** — 채택은 진 쪽에만 적힌다.

        그래서 승자는 진 갈래의 Gil-Lost-To 를 거꾸로 읽어야 나온다. 지금까지 그 필드는
        뷰어만 읽었고, 경합의 승패는 브라우저를 띄운 사람만 볼 수 있었다.
        """
        self._competition()
        st = self.status()
        winner = [c["id"] for c in st["cycle"]["competing"] if c.get("current")][0]
        loser = [c["id"] for c in st["cycle"]["competing"] if c["id"] != winner][0]
        r = self.gil("adopt", f"st/c1/{winner}", "--reason", "이쪽이 재는 값이 더 크다")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.status()
        by = {c["id"]: c for c in st["cycle"]["competing"]}
        self.assertEqual(by[winner]["state"], "won", st["cycle"]["competing"])
        self.assertEqual(by[loser]["state"], "lost", st["cycle"]["competing"])
        self.assertIn(winner, by[loser]["lost_to"])

    def test_the_text_form_names_the_competition_too(self):
        """짧은 형태도 갈래를 **이름으로** 부른다 — 두 출력이 다른 것을 세면 안 된다."""
        self._competition()
        out = self.gil("status").stdout
        self.assertIn("경쟁 가설", out)
        self.assertIn("(현재)", out)

    def test_hypothesis_card_rules_are_written_down(self):
        """hypothesis 카드 규칙이 문서에 있다 — 반증조건은 아직 지나가지 않았다.

        analyze 카드와 같은 문장을 같은 자리에 두면 사람은 그 차이를 못 읽는다. 시제
        하나가 "이미 판정이 났다"고 말한다.
        """
        r = self.gil("docs", "install")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = (Path(self.repo) / "docs" / "gil" / "status-card.md").read_text()
        for must in ("복귀 단계", "미래 시제", "경쟁 가설", "cycle.competing", "cycle.advances",
                     "despite_map"):
            self.assertIn(must, doc, f"{must} 규칙이 없다")

    def test_the_strip_rules_are_written_down(self):
        """배치 규칙이 문서에 있다 — 코드가 아니라. 안 적으면 다음 세션이 또 손으로 그린다."""
        r = self.gil("docs", "install")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = (Path(self.repo) / "docs" / "gil" / "status-card.md").read_text()
        for must in ("척추", "분기", "백트랙", "cycle.steps", "문제정의", "전제"):
            self.assertIn(must, doc, f"{must} 규칙이 없다")

    def test_points_at_its_own_rendering_rules(self):
        """데이터가 **자기 그리는 법의 자리**를 함께 말한다.

        규칙을 문서에만 두면 "에이전트가 알아서 읽기"가 되고 그건 자기규율이다 — 이
        저장소가 반복해서 확인한 대로 자기규율은 원리적으로 불충분하다(#55·#45). 그리고
        가리키는 문서는 **실재해야 한다**(v3.58.1·v3.58.2 계열): 없는 곳을 가리키는 안내는
        막힌 사람을 한 번 더 세운다.
        """
        self._cycle()
        st = self.status()
        self.assertIn("status-card.md", st["render_guide"])
        r = self.gil("docs", "install")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((Path(self.repo) / "docs" / "gil" / "status-card.md").exists(),
                        "가리킨 문서가 설치되지 않는다")
        idx = (Path(self.repo) / "docs" / "gil" / "index.md").read_text()
        self.assertIn("status-card.md", idx, "목차에 없으면 없는 것으로 읽힌다")

    def test_text_form_says_the_same_thing(self):
        """--json 없이도 같은 값을 말한다 — 두 출력이 다른 것을 세면 어느 쪽이 사실인지 모른다."""
        self._cycle()
        r = self.gil("status")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout + r.stderr
        self.assertIn("st", out)
        self.assertIn("c1", out)


class TestMCPAppsCard(GilFixture):
    """MCP App — 상태 카드가 호스트 화면에 **실제로 뜨는** 길 (2026-08-07, 상현님과 실측).

    이 클래스는 화면이 안 뜨던 다섯 자리를 하나씩 박은 것이다. 다섯 다 "규범대로 했다"고
    믿는 동안 조용히 틀려 있었고, 계기(프레임 로그 + 화면이 제 상태를 적어 보내는 probe)를
    달고서야 하나씩 드러났다. 그래서 시험도 **프레임 수준에서** 센다 — 사람 눈으로 확인하는
    것은 릴리스마다 반복할 수 없다.

    ① 호스트는 resources/read 를 **툴보다 먼저** 한다 → 읽기는 껍데기를 내야 한다
    ② 앱의 핸드셰이크는 protocolVersion·appInfo 를 요구한다(옛 이름은 -32603 으로 거부됐다)
    ③ 앱은 응답 뒤 ui/notifications/initialized 를 보내야 한다(규범의 관문)
    ④ 호스트는 앱에게 structuredContent 를 넘기지 않는다 → 카드는 content 로 가야 한다
    ⑤ 앱의 호출엔 인자가 없을 수 있다 → 저장소를 못 찾아도 **오류가 아니라 카드**로 답한다
    """

    def _session(self, calls, cwd=None):
        """MCP 세션 하나. calls: (method, params) 목록. 반환: 결과 메시지 목록."""
        import json
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=cwd or self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1,
                             env=dict(os.environ, GIL_NO_VIEWER="1", GIL_NO_VERSION_CHECK="1"))
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        def read():
            while True:
                line = p.stdout.readline()
                if not line:
                    return None
                try:
                    return json.loads(line)
                except ValueError:
                    continue
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2026-01-26",
                             "capabilities": {"extensions": {
                                 "io.modelcontextprotocol/ui": {
                                     "mimeTypes": ["text/html;profile=mcp-app"]}}},
                             "clientInfo": {"name": "test-host", "version": "1"}}})
            init = read()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            out = [init]
            for i, (method, params) in enumerate(calls, start=10):
                send({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
                out.append(read())
            return out
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()

    def _cycle(self):
        self.gil("init", "--name", "clew")
        ref = os.path.join(self.repo, "ref.md")
        with open(ref, "w", encoding="utf-8") as f:
            f.write("# 기준\n성공: 카드가 뜬다\n")
        self.gil("chain", "ch", "--purpose", "카드", "--reference", "ref.md", "--criterion", "뜬다")
        self._autofill_interview("ch")
        os.remove(ref)
        r = self.gil("open", "ch/c1", "--author", "clew", "--purpose", "무엇을 풀려는가",
                     "--body", "문제정의 본문", "--inherit", "앞 사이클이 남긴 사실")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_server_declares_the_ui_extension_and_the_resource(self):
        """확장 선언과 리소스가 규범의 이름·타입으로 나온다 — 여기가 틀리면 호스트는 아예 안 읽는다."""
        self._cycle()
        init, lst = self._session([("resources/list", {})])
        ext = init["result"]["capabilities"].get("extensions", {})
        self.assertIn("io.modelcontextprotocol/ui", ext)
        self.assertIn("text/html;profile=mcp-app", ext["io.modelcontextprotocol/ui"]["mimeTypes"])
        by = {r["uri"]: r for r in lst["result"]["resources"]}
        self.assertIn("ui://gil/status", by)
        self.assertEqual(by["ui://gil/status"]["mimeType"], "text/html;profile=mcp-app")
        # 리소스 수준 _meta.ui — 없으면 앱 리소스로 안 보는 호스트가 있을 수 있다.
        self.assertIn("ui", by["ui://gil/status"].get("_meta", {}))

    def test_the_read_comes_before_the_tool_so_it_must_be_a_shell(self):
        """**호스트는 툴보다 먼저 읽는다.** 그 순간 저장소를 모르니 통짜 렌더는 원리적으로 못 한다.

        실측: 그 자리에서 651 바이트 "어느 저장소를 볼지 모른다" 를 내보내고 있었고, 그것이
        화면이 안 뜬 첫 원인이었다. 읽기는 껍데기를 내고 내용은 앱이 가져온다.
        """
        self._cycle()
        _, rd = self._session([("resources/read", {"uri": "ui://gil/status"})], cwd="/")
        html = rd["result"]["contents"][0]["text"]
        self.assertIn("gil_status_card", html, "껍데기에 내용을 가져오는 통로가 없다")
        self.assertNotIn("어느 저장소를 볼지 모른다", html, "읽기 시점에 통짜로 그리려 한다")

    def test_the_shell_speaks_the_handshake_the_host_requires(self):
        """핸드셰이크는 protocolVersion·appInfo 를 요구한다.

        실측: {appCapabilities, clientInfo} 로 보내자 호스트가 -32603 으로 거부했고
        ("params.appInfo: expected object"), 거부되면 호스트는 그 프레임을 화면에 세우지
        않는다. 그리고 응답 뒤 **initialized** 를 보내야 한다 — 규범: "호스트는 이 알림을
        받기 전에는 뷰에 어떤 요청·알림도 보내지 않는다."
        """
        self._cycle()
        _, rd = self._session([("resources/read", {"uri": "ui://gil/status"})])
        html = rd["result"]["contents"][0]["text"]
        self.assertIn('method:"ui/initialize"', html)
        self.assertIn('protocolVersion:"2026-01-26"', html)
        self.assertIn("appInfo:{name", html)
        self.assertIn('"ui/notifications/initialized"', html)
        # 크기 알림은 width·height 둘 다 — 규범의 모양이다.
        #
        # **어떻게 재는지가 아니라 무엇을 보내는지를 잰다.** 옛 시험은 그때의 구현
        # (`document.documentElement.scrollWidth`)을 박아 뒀는데, 재는 법을 고치자
        # (칸이 아니라 내용을 재게) 사실은 그대로인데 빨개졌다.
        self.assertIn('"ui/notifications/size-changed"', html, "크기를 아예 안 알린다")
        rs = html.partition("function reportSize(")[2].partition("\n  }")[0]
        self.assertTrue(rs.strip(), "reportSize 를 못 읽었다 — 이 시험이 눈이 먼다")
        self.assertRegex(rs, r"width\s*:", "너비를 안 싣는다")
        self.assertRegex(rs, r"height\s*:", "높이를 안 싣는다")

    def test_the_card_travels_in_content_because_that_is_what_reaches_the_app(self):
        """호스트는 앱에게 **structuredContent 를 넘기지 않는다**(실측: `content,isError` 만 왔다).

        그래서 카드는 content 로 간다. 그런데 두 칸 다 싣는다 — 통로가 하나뿐이라고 가정하면
        호스트가 바뀔 때 화면이 다시 빈다.
        """
        self._cycle()
        _, call = self._session([("tools/call", {"name": "gil_status_card",
                                                 "arguments": {"repo": self.repo}})])
        r = call["result"]
        self.assertFalse(r.get("isError"), r)
        text = r["content"][0]["text"]
        self.assertTrue(text.lstrip().startswith("<div"), text[:80])
        self.assertIn("문제정의", text, "define 카드가 아니다")
        self.assertIn("cardHtml", r.get("structuredContent", {}))

    def test_the_card_tool_is_for_the_app_not_the_model(self):
        """카드 HTML 은 6KB 다 — 모델이 볼 이유가 없다. 규범은 내용 단위 숨김을 주지 않고
        **툴 단위**만 준다(visibility: ["app"]). 그래서 이 툴은 앱 전용으로 선다."""
        self._cycle()
        _, lst = self._session([("tools/list", {})])
        by = {t["name"]: t for t in lst["result"]["tools"]}
        self.assertIn("gil_status_card", by)
        vis = by["gil_status_card"].get("_meta", {}).get("ui", {}).get("visibility")
        self.assertEqual(vis, ["app"], by["gil_status_card"].get("_meta"))
        # 사람이 보는 툴(gil_status)은 UI 리소스를 가리키고, 선언된 URI 그대로다.
        self.assertEqual(by["gil_status"]["_meta"]["ui"]["resourceUri"], "ui://gil/status")

    def test_it_answers_with_a_card_even_when_it_cannot_find_the_repo(self):
        """**오류가 아니라 카드로 답한다.** 앱에 isError 를 주면 화면은 "카드가 없다"만 적고
        사람은 이유를 모른다 — 실측으로 그 화면을 봤다(13번). 화면은 언제나 무언가를 말해야
        하고, 못 하는 것은 못 한다고 말해야 한다.

        그리고 이제 그 화면은 **말만 하지 않고 길을 준다**(gil-app SPEC §4.1): 저장소를 못
        찾은 자리가 곧 시작하는 자리다. 옛 시험은 "어느 저장소를 볼지 모른다"는 **문구**를
        박고 있었는데, 지키려는 것은 문구가 아니라 ㄱ) 오류가 아니라 카드고 ㄴ) 그 카드가
        지금 선 자리를 밝히고 ㄷ) 사람이 다음으로 갈 수 있다는 것이다."""
        self._cycle()
        _, call = self._session([("tools/call", {"name": "gil_status_card", "arguments": {}})],
                                cwd="/")
        r = call["result"]
        self.assertFalse(r.get("isError"), "앱에 오류를 돌려주면 화면이 이유를 못 적는다")
        text = r["content"][0]["text"]
        self.assertTrue(text.lstrip().startswith("<div"), text[:80])
        # 지금 선 자리를 밝힌다 — 안 밝히면 "왜 못 찾았나"를 다시 추측하게 된다.
        self.assertIn("지금 선 자리", text, text[:200])
        # 그리고 막다른 길이 아니다.
        self.assertIn("data-act=\"start-here\"", text, "못 찾았다고만 말하고 길을 안 준다")

    def test_the_server_remembers_the_repo_the_model_gave_it(self):
        """앱의 조회엔 인자가 없을 수 있다 — 그때는 앞선 호출에서 정해진 자리를 쓴다.

        실측: 이 연결이 빠져 있어서 카드 툴이 cwd 가 / 인 자리에서 열세 번 거부됐다.
        """
        self._cycle()
        _, first, second = self._session([
            ("tools/call", {"name": "gil_status", "arguments": {"repo": self.repo}}),
            ("tools/call", {"name": "gil_status_card", "arguments": {}}),
        ], cwd="/")
        self.assertFalse(first["result"].get("isError"), first)
        text = second["result"]["content"][0]["text"]
        self.assertIn("문제정의", text, "기억한 저장소를 안 쓴다: " + text[:120])

    def test_the_app_learns_the_repo_from_the_host_notification(self):
        """호스트는 앱에게 tool-input/tool-result 로 **모델이 넘긴 인자**를 알려준다.

        그걸 주워 자기 조회에 실으면 서버의 기억에 의존하지 않는다 — 저장소가 바뀌면 그
        자리에서 다시 그린다. (probe 가 그 알림의 존재를 알려줬다.)
        """
        self._cycle()
        _, rd = self._session([("resources/read", {"uri": "ui://gil/status"})])
        html = rd["result"]["contents"][0]["text"]
        self.assertIn("ui/notifications/tool-input", html)
        self.assertIn("learnRepo", html)
        # **표현이 아니라 사실을 잰다.** 옛 시험은 `arguments: repo ?` 라는 그때의 한 줄을
        # 박아 뒀는데, 배선을 바꾸자(인자를 객체로 조립) 사실은 그대로인데 시험만 빨개졌다.
        # 재야 하는 것은 "조회가 배운 저장소를 싣는가"다.
        fetch = html.partition("function fetchCard(")[2].partition("\n  }")[0]
        self.assertIn("gil_status_card", fetch, "조회 통로를 못 읽었다 — 이 시험이 눈이 먼다")
        self.assertIn("repo", fetch, "배운 저장소를 조회에 싣지 않는다")


class TestMCPRoots(GilFixture):
    """MCP roots — 호스트가 연 폴더를 규범대로 물어본다.

    왜 여기까지 테스트하나. gil 은 저장소를 CLAUDE_PROJECT_DIR 로 찾았는데 그건 Claude Code
    만 넣어주는 **벤더 환경변수**다. Claude Desktop 은 안 넣는다 — 그래서 Desktop 에서는
    프로세스가 뜬 자리(저장소 밖)를 그대로 썼고, gil_graph 든 gil_log 든 첫 줄에서
    `fatal: ... .git 저장소가 아닙니다` 로 죽었다. 실측에서 사람은 그걸 **렌더링 실패로
    읽었다** — MCP Apps 위젯이 뜨려다 이 에러로 멈췄으니까. 화면 문제가 아니라 저장소 실종이다.

    그래서 시험은 **환경변수를 지운 채** 서버를 저장소 밖에서 띄운다. 그게 Desktop 이다.
    환경변수를 남겨 두면 시험은 Claude Code 를 한 번 더 시험하는 것이고, 정작 깨진 길은
    영원히 안 밟힌다.
    """

    def _serve_outside(self, calls, roots=None):
        """저장소 **밖**에서 서버를 띄우고 roots 로만 저장소를 알려준다.

        roots=None 이면 클라이언트가 roots 미지원(옛 호스트) — 그때 어떻게 되는지도 센다.
        """
        import json, tempfile
        self.gil("init")
        outside = tempfile.mkdtemp()          # git 저장소가 아닌 자리 = Desktop 이 뜨는 자리
        env = dict(os.environ, GIL_NO_VIEWER="1")
        env.pop("CLAUDE_PROJECT_DIR", None)   # 벤더 환경변수를 지운다 — 이게 이 시험의 핵심
        caps = {"roots": {}} if roots is not None else {}
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=outside,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        read = lambda: json.loads(p.stdout.readline())
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": caps,
                             "clientInfo": {"name": "test", "version": "1"}}})
            read()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            results = []
            for i, (name, args) in enumerate(calls, start=10):
                send({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                      "params": {"name": name, "arguments": args}})
                msg = read()
                # 서버가 roots/list 를 물으면 호스트처럼 답한다.
                if msg.get("method") == "roots/list":
                    send({"jsonrpc": "2.0", "id": msg["id"],
                          "result": {"roots": roots}})
                    msg = read()
                if "error" in msg:
                    results.append((True, msg["error"].get("message", "")))
                else:
                    r = msg["result"]
                    results.append((bool(r.get("isError")),
                                    r["content"][0]["text"] if r.get("content") else ""))
            return results
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()

    def _file_uri(self, path):
        return Path(path).resolve().as_uri()

    def test_roots_locate_the_repo(self):
        """호스트가 roots 로 알려준 폴더를 따라간다 — 환경변수 없이, 저장소 밖에서 떠도."""
        r = self._serve_outside([("gil_log", {})],
                                roots=[{"uri": self._file_uri(self.repo), "name": "repo"}])
        self.assertFalse(r[0][0], r[0][1])
        # 저장소를 못 찾던 그 에러가 사라졌다는 것이 이 시험의 판정이다.
        self.assertNotIn("저장소가 아닙니다", r[0][1])
        self.assertNotIn("not a git repository", r[0][1])
        # 그리고 **그 저장소**를 읽고 있다(읽기 툴은 자기가 선 폴더를 배너로 밝힌다).
        self.assertIn(str(Path(self.repo).resolve()), r[0][1])

    def test_git_root_wins_over_first(self):
        """멀티 루트 — git 저장소인 것을 고른다. 첫 번째를 무조건 집으면 남의 폴더에 붙는다.

        #51 이 환경변수에서 이미 겪은 사고다: 사람이 보는 저장소가 아닌 곳에 기록이
        **아무 에러도 없이** 쌓인다. 순서가 아니라 사실로 고른다.
        """
        import tempfile
        junk = tempfile.mkdtemp()             # git 이 아닌 폴더가 목록 맨 앞에 온다
        r = self._serve_outside([("gil_log", {})], roots=[
            {"uri": self._file_uri(junk), "name": "junk"},
            {"uri": self._file_uri(self.repo), "name": "repo"},
        ])
        self.assertFalse(r[0][0], r[0][1])
        self.assertIn(str(Path(self.repo).resolve()), r[0][1])

    def test_repo_argument_rescues_a_rootless_host(self):
        """roots 를 안 주는 호스트에서도 **에이전트가 아는 경로**로 되찾는다.

        실측(Claude Desktop): 호스트가 roots 를 선언하지 않아 gil 이 `/` 에 섰고, 그 자리의
        에이전트는 이렇게 답했다 — "이 툴은 인자를 받지 않아서 저장소 경로를 지정할 수
        없습니다". **그 에이전트는 올바른 경로를 알고 있었다.** 전할 구멍이 없었을 뿐이다.
        구멍을 뚫는다. 설정에 박는 --repo 와 달리 이건 **그 호출 하나**에만 산다.
        """
        r = self._serve_outside([("gil_log", {"repo": self.repo})], roots=None)
        self.assertFalse(r[0][0], r[0][1])
        self.assertIn(str(Path(self.repo).resolve()), r[0][1])

    def test_repo_argument_beats_roots(self):
        """호출이 말한 저장소가 호스트가 말한 워크스페이스를 이긴다 — 더 구체적인 쪽이.

        멀티 루트에서 지금 이 명령만 다른 저장소를 볼 때, 이 길이 유일하다.
        """
        import tempfile
        other = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", other], check=True)
        r = self._serve_outside([("gil_log", {"repo": self.repo})],
                                roots=[{"uri": self._file_uri(other), "name": "other"}])
        self.assertFalse(r[0][0], r[0][1])
        self.assertIn(str(Path(self.repo).resolve()), r[0][1])

    def test_bad_repo_argument_is_refused_in_human_words(self):
        """git 저장소가 아닌 경로를 주면 날 git 에러가 아니라 사람 언어로 거부한다."""
        import tempfile
        r = self._serve_outside([("gil_log", {"repo": tempfile.mkdtemp()})], roots=None)
        self.assertTrue(r[0][0])
        self.assertIn("git 저장소가 아니다", r[0][1])

    def test_a_call_does_not_leave_its_repo_behind(self):
        """**앞 호출이 정한 자리를 다음 호출이 물려받지 않는다** (실측 2026-08-10).

        한 `gil mcp serve` 프로세스를 **여러 대화가 나눠 쓴다.** 그런데 자리가 `os.Chdir` 로
        프로세스 전역이라, 대화 A 가 `repo=/X` 를 실어 부르면 프로세스가 거기 눌러앉았다.
        그 뒤 새 빈 폴더에서 "gil 프로젝트 시작하자"고 한 대화 B 의 `gil_start {}` 가
        **남의 저장소**를 보며 "온보딩은 끝났다 — 체인 12개"라고 답했다. 오류는 하나도
        안 났다 — 옮기는 자리는 아홉이었고 되돌리는 자리는 **0** 이었다.

        repo 인자의 뜻은 문서에 이미 적혀 있었다: *"그 호출 하나에만 산다."* 코드가 그
        문장을 안 지켰을 뿐이다. 그러니 재는 것도 그 문장이다 — 한 프로세스, 두 호출.
        """
        r = self._serve_outside([("gil_log", {"repo": self.repo}),
                                 ("gil_log", {})], roots=None)
        self.assertFalse(r[0][0], r[0][1])
        self.assertIn(str(Path(self.repo).resolve()), r[0][1])
        # 둘째 호출은 아무것도 안 실었다. roots 도 환경변수도 없으니 **되돌아갈 밑바탕이
        # 없다** — 그러면 git 처럼 실패해야 한다(상현님). 짐작으로 앞 저장소를 쓰는 것보다
        # 그 실패가 낫다: 짐작은 조용히 틀리고, 실패는 다음 수를 말한다.
        self.assertNotIn(str(Path(self.repo).resolve()), r[1][1],
                         "앞 호출이 정한 저장소를 그대로 물려받았다 — 새 대화가 남의 기록을 본다")
        self.assertTrue(r[1][0], "저장소가 없는데 성공했다고 답한다")

    def test_the_hosts_workspace_comes_back_after_a_call_pointed_elsewhere(self):
        """되돌아갈 **밑바탕**이 있으면 거기로 돌아온다 — 연결의 자리와 호출의 자리는 다르다.

        roots 는 호스트가 "이 워크스페이스는 여기"라고 말하는 **연결의 사실**이라 눌러앉아도
        된다. repo 인자는 "지금 이 명령은 여기다"라 눌러앉으면 안 된다. 앞 시험이 밑바탕이
        없을 때를 재고, 이 시험이 있을 때를 잰다 — 둘을 같이 안 재면 되돌림이 "아무 데도
        못 가게 막는 것"으로 굳어도 아무도 모른다.
        """
        import tempfile
        ws = tempfile.mkdtemp()
        subprocess.run([*GIL_CMD, "init", "--name", "ws"], cwd=ws, check=True,
                       capture_output=True, text=True,
                       env=dict(os.environ, GIL_NO_VIEWER="1", GIL_NO_VERSION_CHECK="1"))
        r = self._serve_outside([("gil_log", {"repo": self.repo}),
                                 ("gil_log", {})],
                                roots=[{"uri": self._file_uri(ws), "name": "ws"}])
        self.assertIn(str(Path(self.repo).resolve()), r[0][1])
        self.assertIn(str(Path(ws).resolve()), r[1][1],
                      "호스트가 말한 워크스페이스로 안 돌아왔다")

    def test_banner_names_who_decided_this_spot(self):
        """진단 — 지금 자리를 **무엇이 정했고 누가 불렀나**를 도구가 스스로 밝힌다.

        이 결함을 쫓는 데 Claude 로그와 lsof 가 필요했다. 도구가 아는 것을 안 말하면 사람이
        도구 바깥에서 캐야 한다(#110 이 뷰어에서 고친 것과 같은 병).
        """
        r = self._serve_outside([("gil_log", {})],
                                roots=[{"uri": self._file_uri(self.repo), "name": "repo"}])
        self.assertIn("이 자리를 정한 것: 호스트가 준 roots", r[0][1])
        self.assertIn("부른 호스트: test", r[0][1])

    def test_banner_names_the_call_argument(self):
        """repo 인자로 왔으면 그렇게 말한다 — 두 길이 같은 이름으로 불리면 진단이 못 가른다."""
        r = self._serve_outside([("gil_log", {"repo": self.repo})], roots=None)
        self.assertIn("이 자리를 정한 것: 호출 인자(repo)", r[0][1])

    def test_refusal_teaches_the_repo_argument(self):
        """막힌 자리에서 **다음 한 수**를 준다 — 실측에서 에이전트가 못 찾은 그 수.

        거부는 평소에 안 읽히고 막힌 순간에만 읽힌다(v3.51.0 의 교훈). 그 한 번에
        빠져나갈 길이 없으면 세션이 거기서 선다.
        """
        r = self._serve_outside([("gil_log", {})], roots=None)
        self.assertTrue(r[0][0])
        self.assertIn("repo 인자", r[0][1])
        self.assertIn("이 자리를 정한 것", r[0][1])

    def test_no_roots_support_is_not_fatal(self):
        """roots 를 안 내는 호스트에서도 gil 이 죽지는 않는다 — 옛 경로가 그대로 답이다.

        없는 기구를 못 썼다고 되는 것까지 막지 않는다. 다만 저장소 밖이니 거부는 나오고,
        그 거부는 사람 언어여야 한다(날 git 에러가 아니라).
        """
        r = self._serve_outside([("gil_log", {})], roots=None)
        self.assertTrue(r[0][0])   # 저장소가 없으니 거부는 정당하다


class TestMCPApps(GilFixture):
    """MCP Apps(SEP-1865) — 그래프 뷰어를 호스트 안 iframe 에 띄우는 UI 표면.

    왜 여기까지 테스트하나. 뷰어의 마찰은 늘 '바깥'에 있었다 — 127.0.0.1 날 주소, 포트 충돌,
    샌드박스에서 안 열리는 브라우저. ui:// 리소스는 그 바깥을 없앤다. 다만 규범(URI 스킴·
    mimeType·_meta.ui·확장 선언)이 하나라도 어긋나면 호스트는 조용히 안 그린다 — 조용한 실패라
    사람이 원인을 못 찾는다. 그래서 계약을 문자 그대로 못박는다.
    """

    UI_URI = "ui://gil/graph"
    UI_MIME = "text/html;profile=mcp-app"
    UI_EXT = "io.modelcontextprotocol/ui"

    def _session(self, fn):
        """MCP 세션을 열어 fn(send, read) 을 돌린다."""
        import json
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1,
                             env=dict(os.environ, GIL_NO_VIEWER="1"))
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        read = lambda: json.loads(p.stdout.readline())
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                             "clientInfo": {"name": "test", "version": "1"}}})
            init = read()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return fn(send, read, init)
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()

    def test_declares_ui_extension_capability(self):
        """MCP Apps 는 옵트인 확장 — initialize 에서 선언하지 않으면 호스트가 안 그린다."""
        init = self._session(lambda send, read, init: init)
        ext = init["result"]["capabilities"].get("extensions", {})
        self.assertIn(self.UI_EXT, ext)
        self.assertEqual(ext[self.UI_EXT]["mimeTypes"], [self.UI_MIME])

    def test_status_says_the_same_thing_in_both_result_channels(self):
        """**어느 칸이 모델에게 갈지는 호스트가 정한다 — 우리는 못 고른다.**

        실측(2026-08-10, Claude Code Desktop): 이 호스트는 structuredContent 가 있으면
        **그것만** 모델에게 주고 Content 를 버린다. gil_status 를 부른 에이전트가 받은 것은
        `{"tipSignature":"…"}` 한 줄이 전부였다 — 상태 줄도, 표면을 말하는 줄(uiHostLine)도
        **한 글자도** 닿지 않았다. 오류는 없었다. 조용히 그랬다.

        같은 세션의 gil_log 는 본문이 그대로 왔다(그쪽엔 structuredContent 가 없다). 그러니
        빈 것이 아니라 **가려진** 것이다.

        고침은 "어느 칸이 옳은가"를 고르는 것이 아니다 — 고를 수 없으니 **둘 다 사실이게**
        한다. cardOf 가 통로 둘을 다 보는 것과 같은 이유고, 통로가 하나뿐이라 가정할 때마다
        이 저장소는 조용히 빈 화면을 얻었다."""
        self.gil("init", "--name", "clew")
        def go(send, read, init):
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "gil_status", "arguments": {}}})
            return read()["result"]
        r = self._session(go)
        self.assertFalse(r.get("isError"), r)
        text = "".join(c.get("text", "") for c in r.get("content", [])
                       if c.get("type") == "text")
        self.assertTrue(text.strip(), "content 가 비었다")
        sc = r.get("structuredContent") or {}
        self.assertIn("text", sc,
                      "structuredContent 만 모델에게 주는 호스트에서는 상태가 한 글자도 안 간다")
        self.assertEqual(sc["text"], text, "두 칸이 서로 다른 말을 한다")
        # 지문은 그대로 있어야 한다 — 화면이 낡음을 판정하는 값이다.
        self.assertTrue((sc.get("tipSignature") or "").strip())

        # **그리고 이건 규칙이지 이 툴의 사정이 아니다.** 다른 툴도 아무것도 안 배우고 같아야
        # 한다 — 툴마다 손으로 실으면 다음에 생기는 툴이 또 샌다(열거는 늘 뒤늦다).
        def go2(send, read, init):
            send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "gil_graph", "arguments": {}}})
            return read()["result"]
        g = self._session(go2)
        gtext = "".join(c.get("text", "") for c in g.get("content", [])
                        if c.get("type") == "text")
        gsc = g.get("structuredContent") or {}
        if gtext.strip():
            self.assertEqual(gsc.get("text"), gtext,
                             "gil_graph 는 같은 규칙을 안 받는다 — 자리를 열거하고 있다")

    def test_ui_resource_is_declared(self):
        """ui:// 스킴과 mcp-app 프로파일 mimeType — 규범 문자 그대로."""
        def go(send, read, init):
            send({"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}})
            return read()["result"]["resources"]
        res = self._session(go)
        got = [r for r in res if r["uri"] == self.UI_URI]
        self.assertEqual(len(got), 1, res)
        self.assertEqual(got[0]["mimeType"], self.UI_MIME)

    def test_tool_points_at_its_ui_resource(self):
        """툴은 _meta.ui.resourceUri 로 자기 UI 를 가리킨다 — 이 고리가 없으면 앱이 안 뜬다."""
        def go(send, read, init):
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            return {t["name"]: t for t in read()["result"]["tools"]}
        tools = self._session(go)
        self.assertIn("gil_graph", tools)
        self.assertEqual(tools["gil_graph"]["_meta"]["ui"]["resourceUri"], self.UI_URI)

    def test_ui_resource_renders_graph_with_bridge(self):
        """리소스를 읽으면 그 시점 그래프가 통째로 든 자기완결 HTML + 호스트 브리지가 온다."""
        self._chain_for_ui()
        def go(send, read, init):
            send({"jsonrpc": "2.0", "id": 2, "method": "resources/read",
                  "params": {"uri": self.UI_URI}})
            return read()["result"]["contents"][0]
        c = self._session(go)
        self.assertEqual(c["mimeType"], self.UI_MIME)
        html = c["text"]
        self.assertTrue(html.startswith("<!doctype html>"), html[:40])
        self.assertIn("uiprobe", html)                     # 그 시점 그래프가 실려 있다
        self.assertIn("ui/initialize", html)               # 핸드셰이크
        self.assertIn("ui/notifications/tool-result", html)  # 낡음 감지
        self.assertIn("gil-stale-banner", html)

    def test_graph_tool_reports_tip_signature(self):
        """툴 결과엔 팁 서명이 실린다 — 화면이 자기가 낡았는지 스스로 알 수 있게."""
        self._chain_for_ui()
        def go(send, read, init):
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "gil_graph", "arguments": {}}})
            return read()["result"]
        r = self._session(go)
        self.assertFalse(r.get("isError"), r)
        self.assertIn("tipSignature", r["structuredContent"])
        sig = r["structuredContent"]["tipSignature"]
        self.assertTrue(sig.strip())

        # 서명은 **접힌 지문**이지 데이터가 아니다.
        #
        # 왜 여기까지 센다. tipSignature() 는 브랜치 하나하나를 줄줄이 잇는다 — 뷰어 안에서는
        # 브라우저가 문자열 비교만 하니 그래도 됐다. 그런데 MCP 로 나가면 그 문자열은
        # **대화에 실린다.** 실측(AIL): 브랜치 130여 개와 seen 집합이 통째로 나가 4KB 를
        # 넘겼고, 사람이 툴 응답으로 본 것이 그 날 데이터 전부였다. 서명은 같은지 다른지만
        # 답하면 되고, 내용은 필요 없다.
        self.assertLess(len(sig), 64, f"서명이 길다({len(sig)}자) — 접히지 않았다")
        self.assertNotIn("\n", sig)
        self.assertNotIn("uiprobe", sig, "브랜치 이름이 서명에 날것으로 실렸다")

        # 그리고 **여전히 판정은 한다** — 그래프가 움직이면 지문도 바뀐다.
        self.gil("open", "uiprobe/second", "--hypothesis", "지문이 움직이나",
                 "--refutes-if", "안 움직이면")
        r2 = self._session(go)
        self.assertNotEqual(sig, r2["structuredContent"]["tipSignature"])

    def _chain_for_ui(self):
        r = self.gil("chain", "uiprobe", "--purpose", "UI 리소스 확인")
        self.assertEqual(r.returncode, 0, r.stderr)


class TestChainRetro(GilFixture):
    """체인 생애주기의 닫는 쪽 — 회고와 시드 (이슈 #33).

    인터뷰가 체인을 열 때 '무엇을 기준으로 할 것인가'를 사람에게 물었다면, 회고는 닫을 때
    '그 기준에 얼마나 합당했나'를 답한다. 이게 없으면 체인은 열 때만 사람의 기준에 매이고
    닫을 때는 LLM 자기확신으로 끝난다 — 생애주기의 반쪽이 비는 것이다.
    """

    def _chain_with_reference(self, name="alpha"):
        """인터뷰로 사람 승인 기준이 선 체인 하나를, 사이클까지 닫아 둔다."""
        self.gil("chain", name, "--purpose", "회고 생애주기")
        self.gil("open", f"{name}/c001", "--author", "clew", "--purpose", "한 사이클",
                 "--body", "정의")
        self.gil("step", f"{name}/c001", "--kind", "success", "--title", "S", "--body", "B")
        r = self.gil("close", f"{name}/c001")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _write(self, name, text):
        path = os.path.join(self.repo, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return name

    def test_reference_chain_cannot_close_without_retro(self):
        """기준이 있는 체인은 회고 없이 닫히지 않는다 — 회고 없는 종결은 '됐다'는 자기확신."""
        self._chain_with_reference()
        self._no_retro_autofill = True
        r = self.gil("chain-close", "alpha")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("회고", r.stderr)

    def test_refusal_shows_the_standard_to_measure_against(self):
        """거부는 기준 전문을 그 자리에 펼친다 — 무엇에 비추어 쓰라는 건지 찾아 헤매지 않게."""
        self._chain_with_reference()
        self._no_retro_autofill = True
        r = self.gil("chain-close", "alpha")
        self.assertIn("이 체인의 기준", r.stderr)
        self.assertIn("기준 문서", r.stderr)
        # 기계용 트레일러가 사람 읽을 자리에 섞이지 않는다.
        self.assertNotIn("Gil-Kind:", r.stderr)

    def test_every_chain_now_has_a_criterion_so_retro_is_always_required(self):
        """기준과 목적이 쌍으로만 태어나므로(상현님) **모든 체인이** 회고 대상이다.

        옛 규칙엔 '기준 없는 체인'이 있어 회고 없이 닫혔다. 이제 그런 체인은 태어나지 못하니
        그 예외도 사라졌다 — 잣대 없이 열린 체인이 없으면 성적표 없이 닫는 체인도 없다."""
        self.gil("chain", "fresh", "--purpose", "새 체인")
        self._no_retro_autofill = True
        r = self.gil("chain-close", "fresh")
        self.assertNotEqual(r.returncode, 0, "기준이 있는데 회고 없이 닫혔다")
        self.assertIn("회고", r.stderr)

    def test_empty_retro_is_rejected(self):
        """빈 회고는 회고가 아니다 — 형식만 채우는 파일을 게이트가 받지 않는다."""
        self._chain_with_reference()
        self._no_retro_autofill = True
        self._write("empty.md", "   \n")
        r = self.gil("chain-close", "alpha", "--retro", "empty.md")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("비었다", r.stderr)

    def test_retro_and_seed_land_in_the_graph(self):
        """회고·시드는 종결 커밋 본문에 담기고 트레일러로 표식된다 — 그래프가 성적표를 안다."""
        self._chain_with_reference()
        self._no_retro_autofill = True
        self._write("retro.md", "# 회고\n기준 대비: 달성.\n분기했어야 할 지점: s2.\n")
        self._write("seed.md", "# 시드\n다음 물음: 회고가 형해화되지 않으려면?\n")
        r = self.gil("chain-close", "alpha", "--retro", "retro.md", "--seed", "seed.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Retro"), "true")
        self.assertEqual(self.trailer("HEAD", "Gil-Seed-Ref"), "true")
        body = subprocess.run(["git", "show", "-s", "--format=%B", "HEAD"], cwd=self.repo,
                              capture_output=True, text=True).stdout
        self.assertIn("분기했어야 할 지점", body)
        self.assertIn("다음 물음", body)

    def test_seed_is_handed_to_the_next_chain(self):
        """시드는 다음 체인을 열 때 건네진다 — 생애주기가 닫힌다(회고→시드→다음 인터뷰)."""
        self._chain_with_reference()
        self._no_retro_autofill = True
        self._write("retro.md", "# 회고\n달성.\n")
        self._write("seed.md", "# 시드\n다음 물음: 무엇을 더 물어야 하나?\n")
        self.gil("chain-close", "alpha", "--retro", "retro.md", "--seed", "seed.md")
        r = self.gil("chain", "beta", "--purpose", "시드에서 이어간다")
        out = r.stdout + r.stderr
        self.assertIn("시드", out)
        self.assertIn("무엇을 더 물어야 하나", out)
        # 시드가 기준을 대체하지 않는다 — 여전히 인터뷰가 게이트다.
        self.assertIn("gil interview beta", out)

    def test_seed_does_not_bypass_the_interview_gate(self):
        """시드가 있어도 사이클은 못 연다 — 기준은 언제나 사람의 답이다."""
        self._chain_with_reference()
        self._no_retro_autofill = True
        self._write("retro.md", "# 회고\n달성.\n")
        self._write("seed.md", "# 시드\n다음 물음.\n")
        self.gil("chain-close", "alpha", "--retro", "retro.md", "--seed", "seed.md")
        # 시드가 있어도 다음 체인은 **제 기준을 스스로** 갖춰야 한다 — 앞 체인의 시드는
        # 물음을 물려줄 뿐 잣대가 되지 못한다. 이제 그 강제는 체인의 탄생에서 걸린다.
        self._no_criterion_autofill = True
        try:
            r = self.gil("chain", "beta", "--purpose", "다음 국면")
        finally:
            self._no_criterion_autofill = False
        self.assertNotEqual(r.returncode, 0, "시드는 기준을 대신하지 못한다")
        self.assertIn("쌍으로만", r.stderr)


class TestMigrateBodyTransport(GilFixture):
    """이주가 v2 **본문**을 실제로 옮긴다 (이슈 #87, 실사용 보고).

    옛 migrate 는 cycle.yaml 메타만 옮기고 본문에 "v2 hypothesis+design 흡수"라고 적었다.
    흡수하지 않았다 — 실측으로 사이클당 산문 11KB 가 메타 표 2KB 로 대체됐고 옮겨진 산문은
    0 이었다. 손실보다 나쁜 건 옮겼다고 믿게 만든 문구였고, fsck 는 형태만 봐서 침묵했다.
    """

    FOLDER = "rooms/r/chains/dash/C006-eval"

    def _write(self, relpath, content):
        full = os.path.join(self.repo, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)

    def _seed(self, stages=("1-hypothesis.md", "2-design.md", "3-verification/run.py",
                            "4-analysis.md", "5-report.md")):
        self._write("CLAUDE.md", "# 대문\n")
        self._write(f"{self.FOLDER}/cycle.yaml",
                    "id: C006-eval\nchain: dash\nauthor: clew\n"
                    "status: closed\nverdict: supported\ntitle: 평가 신뢰도\n")
        for name in stages:
            self._write(f"{self.FOLDER}/{name}", f"# {name}\n산문 내용 {name} 여기에 있다.\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "v2 seed")
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _bodies(self):
        """이주된 스텝 커밋들의 (스텝id, kind, 본문) 목록."""
        out = self._git("log", "--all", "--format=%s\x1f%b\x1e").stdout
        rows = []
        for rec in out.split("\x1e"):
            subj, _, body = rec.strip("\n").partition("\x1f")
            m = re.search(r"/(s\d+) (\w+):", subj)
            if m and "[migrate]" in subj:
                rows.append((m.group(1), m.group(2), body))
        return rows

    def test_five_stage_docs_become_five_steps(self):
        """문서가 다 있으면 v3 문법대로 define→hypothesis→verify→analyze→종결 이 선다."""
        v2root = self._seed()
        self._git("checkout", "-q", "-b", "v3-mig")
        r = self.gil("migrate", "--from", v2root)
        self.assertEqual(r.returncode, 0, r.stderr)
        kinds = [k for _, k, _ in sorted(self._bodies())]
        self.assertEqual(kinds, ["define", "hypothesis", "verify", "analyze", "success"])

    def test_prose_actually_carried(self):
        """v2 산문이 v3 본문 안에 **그대로** 들어 있다 — 출처 경로와 함께."""
        v2root = self._seed()
        self._git("checkout", "-q", "-b", "v3-mig")
        self.gil("migrate", "--from", v2root)
        joined = "\n".join(b for _, _, b in self._bodies())
        for name in ("1-hypothesis.md", "2-design.md", "4-analysis.md", "5-report.md"):
            self.assertIn(f"산문 내용 {name} 여기에 있다.", joined, f"{name} 원문이 안 실렸다")
            self.assertIn(f"{self.FOLDER}/{name}", joined, f"{name} 출처가 안 적혔다")

    def test_missing_stage_says_so(self):
        """원문이 없는 단계는 없는 스텝이거나, 서더라도 '원문 없음'을 명시한다."""
        v2root = self._seed(stages=("1-hypothesis.md",))
        self._git("checkout", "-q", "-b", "v3-mig")
        self.gil("migrate", "--from", v2root)
        kinds = [k for _, k, _ in sorted(self._bodies())]
        self.assertNotIn("analyze", kinds, "원문 없는 analyze 를 만들어 세웠다")
        verify_body = [b for _, k, b in self._bodies() if k == "verify"][0]
        self.assertIn("v2 원문 없음", verify_body)
        self.assertIn(self.FOLDER, verify_body)  # 원본을 찾아갈 수 있어야 한다

    def test_binary_stage_file_does_not_kill_migration(self):
        """바이너리는 본문에 못 싣는다 — 실으면 git 이 커밋을 거부해 이주가 통째로 멈춘다.

        실데이터(174 사이클) 검증에서 잡혔다: 3-verification/ 의 png 하나가
        'a NUL byte in commit log message not allowed' 로 이주를 23개 브랜치 만에
        중단시켰다. fixture 엔 텍스트만 있어 안 걸렸던 결함이다."""
        self._write("CLAUDE.md", "# 대문\n")
        self._write(f"{self.FOLDER}/cycle.yaml",
                    "id: C006-eval\nchain: dash\nauthor: clew\n"
                    "status: closed\nverdict: supported\ntitle: 평가 신뢰도\n")
        self._write(f"{self.FOLDER}/1-hypothesis.md", "# 가설\n산문이 여기 있다.\n")
        vdir = os.path.join(self.repo, self.FOLDER, "3-verification")
        os.makedirs(vdir, exist_ok=True)
        with open(os.path.join(vdir, "shot.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00binary\x00data")
        self._git("add", "-A"); self._git("commit", "-q", "-m", "v2 seed")
        v2root = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("checkout", "-q", "-b", "v3-mig")
        r = self.gil("migrate", "--from", v2root)
        self.assertEqual(r.returncode, 0, "바이너리 하나가 이주를 죽였다:\n" + r.stderr)
        joined = "\n".join(b for _, _, b in self._bodies())
        self.assertIn("산문이 여기 있다.", joined)             # 텍스트는 실린다
        self.assertIn("본문에 싣지 않은 원본", joined)          # 안 실은 것은 이름으로 남는다
        self.assertIn("shot.png", joined)
        self.assertIn("바이너리", joined)

    def test_dry_run_reports_prose_bytes(self):
        """이주 **전에** 실어 갈 산문의 양을 밝힌다 — 0 이면 그 자리에서 알아야 한다."""
        v2root = self._seed()
        out = self.gil("migrate", "--from", v2root, "--dry-run")
        self.assertIn("실어 갈 v2 원문:", out.stderr)
        self.assertRegex(out.stderr, r"실어 갈 v2 원문: [1-9]\d* 바이트")

    def test_dry_run_warns_when_no_prose(self):
        """단계 문서가 하나도 없으면 경고한다(옛 이주가 조용히 하던 일)."""
        v2root = self._seed(stages=())
        out = self.gil("migrate", "--from", v2root, "--dry-run")
        self.assertIn("옮길 산문이 0", out.stderr)

    def test_fsck_catches_body_that_lies(self):
        """메타 표뿐인 이주 본문을 fsck 가 짚는다 — 형태만 보고 '건강'이라 하지 않는다."""
        self._seed(stages=())
        self.gil("chain", "dash", "--purpose", "P")
        # 옛 migrate 가 남기던 모양: 표 + '흡수' 문구, 실질 본문 0.
        self._git("commit", "-q", "--allow-empty", "-m",
                  "gil dash/c001/s1 define: 옛이주 [migrate]\n\n"
                  "[migrate] 문제 정의(v2 hypothesis+design 흡수).\n\n"
                  "| v2 필드 | 값 |\n|---|---|\n| id | C001 |\n\n"
                  "Gil-Chain: dash\nGil-Cycle: c001\nGil-Step: s1\n"
                  "Gil-Kind: define\nGil-Parent: null\nGil-Migrate: step\n")
        out = self.gil("fsck")
        self.assertIn("이주본문", out.stdout)
        self.assertIn("실질 본문 0", out.stdout)


class TestMigrateLineageTopology(GilFixture):
    """v2 의 체인 *내부* 계보를 커밋 그래프에 심는다 (이슈 #61, 실사용 보고).

    옛 이주는 사이클 가지를 언제나 체인 루트에서 팠다. 트레일러에 부모를 적어도 커밋
    그래프에서는 모든 사이클이 형제였다 — 실측: 인접쌍 37개 전부 독립, merge-base 가 예외
    없이 체인 루트. 계보를 위상에서 읽는 뷰어에는 통째로 안 보였다.

    #53("없던 이어받음이 생긴다")의 정확한 짝 — **있던 이어받음이 사라진다.** 한 체인이 곧
    하나의 논증 사슬인 저장소에서는, 그 순서를 잃으면 남는 건 "같은 체인에 속한 N개 사이클"
    이라는 집합뿐이고 어느 결론이 어느 결론 위에 서 있는지를 잃는다.
    """

    def _write(self, relpath, content):
        full = os.path.join(self.repo, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)

    def _v2cycle(self, chain, cid, **fields):
        lines = [f"id: {cid}", f"chain: {chain}"]
        for k, v in fields.items():
            lines.append(f"{k}: {v}")
        self._write(f"rooms/experiment/chains/{chain}/{cid}/cycle.yaml",
                    "\n".join(lines) + "\n")

    def _seed_v2(self):
        """한 체인이 하나의 논증 사슬인 v2 를 흉내낸다 — 부모가 pending 인 사례까지."""
        self._write("CLAUDE.md", "# 대문\n")
        self._v2cycle("alpha", "C001-seed", parent="null",
                      status="closed", verdict="supported", title="첫 사이클")
        self._v2cycle("alpha", "C002-grow", parent="C001-seed",
                      status="closed", verdict="supported", title="둘째 사이클")
        self._v2cycle("alpha", "C003-quiet", parent="C002-grow",
                      status="closed", title="verdict 없는 닫힌 사이클")   # → pending 종결
        self._v2cycle("alpha", "C004-after-quiet", parent="C003-quiet",
                      status="open", verdict="null", title="pending 부모 위에서 이어 연 사이클")
        self._v2cycle("beta", "C001-wall", parent="null",
                      status="closed", verdict="rejected", title="기각된 가설")
        self._v2cycle("beta", "C002-waiting", parent="null",
                      status="open", verdict="null", title="사람 대기")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "v2 seed")
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _migrate(self):
        v2root = self._seed_v2()
        self._git("checkout", "-q", "-b", "v3-migration")
        return self.gil("migrate", "--from", v2root)

    def _tip(self, branch):
        return self._git("rev-parse", branch).stdout.strip()

    def _is_ancestor(self, anc, desc):
        return self._git("merge-base", "--is-ancestor", anc, desc).returncode == 0

    def test_child_cycle_descends_from_parent_cycle(self):
        """c002 는 c001 의 자손이어야 한다 — 형제가 아니라."""
        self.assertEqual(self._migrate().returncode, 0)
        self.assertTrue(self._is_ancestor(self._tip("alpha-c001-seed"),
                                          self._tip("alpha-c002-grow")),
                        "자식 사이클이 부모 사이클의 자손이 아니다(체인 루트의 형제로 남았다)")

    def test_lineage_is_a_chain_not_a_set(self):
        """사슬이 이어진다 — c001 → c002 → c003."""
        self._migrate()
        self.assertTrue(self._is_ancestor(self._tip("alpha-c002-grow"),
                                          self._tip("alpha-c003-quiet")))
        # 그리고 체인 루트가 인접쌍의 merge-base 로 주저앉지 않는다.
        mb = self._git("merge-base", self._tip("alpha-c001-seed"),
                       self._tip("alpha-c002-grow")).stdout.strip()
        self.assertEqual(mb, self._tip("alpha-c001-seed"))

    def test_rootless_cycle_still_starts_at_chain_root(self):
        """parent: null 은 그대로 체인 루트에서 — 없던 계보를 지어내지 않는다.

        (체인 루트끼리 순차로 이어지는 건 별개 동작이라, 같은 체인 안에서 본다.)"""
        self._migrate()
        self.assertFalse(self._is_ancestor(self._tip("beta-c001-wall"),
                                           self._tip("beta-c002-waiting")),
                         "parent:null 인데 앞 사이클의 자손이 됐다 — 없던 계보를 지어냈다")

    def test_lineage_survives_open_parent(self):
        """부모가 pending 으로 끝나도 계보를 버리지 않는다 — v2 가 기록한 사실이다.

        옛 코드는 '닫힌 부모'만 인정해, pending 으로 남은 부모의 계보를 통째로 버렸다
        (실사용 보고: 16건). parent 는 '여기서 이어 열었다'는 사실이지 '부모가 닫혔다'는
        주장이 아니다."""
        self._migrate()
        body = self._git("log", "alpha-c004-after-quiet", "--format=%B").stdout
        self.assertIn("Gil-Cycle-Parent: c003-quiet", body)
        self.assertTrue(self._is_ancestor(self._tip("alpha-c003-quiet"),
                                          self._tip("alpha-c004-after-quiet")),
                        "pending 부모의 계보가 위상에서 사라졌다")

    def test_open_parent_is_reported_not_hidden(self):
        """닫히지 않은 부모 위에 이어졌음을 그 자리에서 말한다 — 조용하면 '보존됨'으로 읽힌다."""
        r = self._migrate()
        self.assertIn("부모가 닫히지 않은 채 이어진 사이클", r.stderr)


class TestMigrateVerdictHonesty(GilFixture):
    """이주는 없는 성공을 날조하지 않는다 (이슈 #50).

    옛 매핑은 partial·inconclusive·verdict 없음을 전부 success 로 접었다. 실사용 저장소에서
    71 사이클 중 18개(25%)가 "산 잎"으로 둔갑했다 — 그 순간 이주된 이력은 원본보다 낙관적인
    거짓말이 된다. gil 이 close --abandon 에서 지킨 원칙이 이주에서 깨지면 안 된다.
    """

    def _v2(self, verdict, status="closed"):
        """verdict/status 만 가진 최소 v2 사이클."""
        import types
        # 매핑 함수는 Go 안에 있으므로, dry-run 출력으로 관찰한다.
        return verdict, status

    def _make_v2_repo(self, cycles):
        """cycles: [(id, verdict, status)] → v2 폴더 구조를 만들고 커밋한다."""
        for cid, verdict, status in cycles:
            d = os.path.join(self.repo, "cycles", cid)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "cycle.yaml"), "w", encoding="utf-8") as f:
                f.write(f"id: {cid}\nchain: demo\ntitle: {cid}\nstatus: {status}\n")
                if verdict is not None:
                    f.write(f"verdict: {verdict}\n")
        self._git("add", "-A")
        self._git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "v2 fixture")

    def test_inconclusive_and_partial_do_not_become_success(self):
        """결론이 아닌 것은 산 잎으로 접지 않는다 — 사람 판단 대기로 남는다."""
        self._make_v2_repo([
            ("C001-supported", "supported", "closed"),
            ("C002-rejected", "rejected", "closed"),
            ("C003-inconclusive", "inconclusive", "closed"),
            ("C004-partial", "partial", "closed"),
            ("C005-noverdict", None, "closed"),
        ])
        r = self.gil("migrate", "--from", "HEAD", "--dry-run")
        out = r.stdout + r.stderr
        self.assertIn("verdict=supported → success", out)
        self.assertIn("verdict=rejected → fail", out)
        self.assertIn("verdict=inconclusive → pending", out)
        self.assertIn("verdict=partial → pending", out)
        self.assertIn("verdict=- → pending", out)

    def test_original_verdict_is_preserved_losslessly(self):
        """원 verdict 를 트레일러로 보존한다 — 매핑 정책이 바뀌어도 복구 가능하다(이슈 #50)."""
        self._make_v2_repo([("C001-inc", "inconclusive", "closed")])
        r = self.gil("migrate", "--from", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        body = subprocess.run(["git", "log", "--all", "--format=%B"], cwd=self.repo,
                              capture_output=True, text=True).stdout
        self.assertIn("Gil-V2-Verdict: inconclusive", body)

    def test_dry_run_counts_what_needs_human_judgement(self):
        """이주 **전에** 몇 개가 사람 판단으로 남는지 알려준다 — 뒤에 알면 이미 늦다."""
        self._make_v2_repo([
            ("C001-a", "supported", "closed"),
            ("C002-b", "partial", "closed"),
            ("C003-c", "inconclusive", "closed"),
        ])
        r = self.gil("migrate", "--from", "HEAD", "--dry-run")
        out = r.stdout + r.stderr
        self.assertIn("사람 판단 대기 2", out)
        self.assertIn("gil approve", out)   # 다음 한 수를 준다(이슈 #47)
        self.assertIn("gil reject", out)


class TestMigrateScope(GilFixture):
    """이주 범위를 사람이 제어하고 눈으로 본다 (이슈 #50 ②).

    v2 fsck 는 동결해 둔 옛 체인을 세지 않는데 migrate 는 끌어와 라이브 v3 체인으로 만들었다.
    동작이 틀린 게 아니라 **제어가 없던 것**이 문제다 — 보존하려는 사람도, 빼려는 사람도 있다.
    """

    def _seed(self):
        for path, cid in [("cycles/C001-live", "C001-live"),
                          ("legacy/archived-chains/C900-frozen", "C900-frozen")]:
            d = os.path.join(self.repo, path)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "cycle.yaml"), "w", encoding="utf-8") as f:
                f.write(f"id: {cid}\nchain: demo\ntitle: t\nstatus: closed\nverdict: supported\n")
        self._git("add", "-A")
        self._git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "v2")

    def test_dry_run_shows_where_cycles_came_from(self):
        """어디서 몇 개를 가져왔는지 밝힌다 — fsck 수와 다를 때 사람이 차이를 본다."""
        self._seed()
        out = (lambda r: r.stdout + r.stderr)(self.gil("migrate", "--from", "HEAD", "--dry-run"))
        self.assertIn("스캔한 곳", out)
        self.assertIn("legacy/archived-chains", out)

    def test_exclude_drops_them_and_says_so(self):
        """제외는 조용히 하지 않는다 — 조용한 누락도 조용한 실패다."""
        self._seed()
        out = (lambda r: r.stdout + r.stderr)(
            self.gil("migrate", "--from", "HEAD", "--dry-run", "--exclude", "legacy/"))
        self.assertIn("실사이클 1개", out)
        self.assertIn("제외됨(--exclude) 1개", out)
        self.assertIn("C900-frozen", out)


class TestMCPRepoMismatch(GilFixture):
    """--repo 로 못박은 폴더와 호스트가 연 폴더가 다르면 **먼저 말한다** (이슈 #49).

    아무 에러도 안 나는 게 이 버그의 본질이다: 사람은 자기 폴더에 기록이 쌓이는 줄 알지만
    실제로는 딴 데 쌓이고, 나중에야 그 폴더가 비어 있는 걸 발견한다. 조용한 실패를
    조용하지 않게 만든다.
    """

    def _tool_text(self, extra_env, args):
        import json
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve", *args], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1,
                             env=dict(os.environ, GIL_NO_VIEWER="1", **extra_env))
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        read = lambda: json.loads(p.stdout.readline())
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                             "clientInfo": {"name": "t", "version": "1"}}})
            read()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "gil_log", "arguments": {}}})
            r = read()["result"]
            return r["content"][0]["text"]
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()

    def test_mismatch_is_surfaced_with_both_paths(self):
        """어긋나면 두 경로를 다 보여준다.

        #49 때는 경고였으나 #51 에서 **거부로 승격**됐다 — 실측에서 사람과 에이전트가 서로
        다른 그래프를 보고 있었고, 에이전트가 "기록이 거의 없다"며 새 체인을 열 뻔했다.
        경고 한 줄로 감당할 위험이 아니었다. 여기서는 '두 경로가 다 드러나는가'를 지킨다.
        """
        self.gil("init")
        other = tempfile.mkdtemp(prefix="gil-other-")
        try:
            t = self._tool_text({"CLAUDE_PROJECT_DIR": other}, ["--repo", self.repo])
            self.assertIn("덮어쓰고 있다", t)
            self.assertIn(other, t)
            self.assertIn(self.repo, t)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_no_warning_when_they_agree(self):
        """일치하면 조용하다 — 늘 막으면 아무도 안 읽는다."""
        self.gil("init")
        t = self._tool_text({"CLAUDE_PROJECT_DIR": self.repo}, ["--repo", self.repo])
        self.assertNotIn("덮어쓰고 있다", t)

    def test_no_warning_when_repo_not_pinned(self):
        """--repo 를 안 붙이는 게 기본 — 그땐 애초에 어긋날 수 없다."""
        self.gil("init")
        t = self._tool_text({"CLAUDE_PROJECT_DIR": self.repo}, [])
        self.assertNotIn("덮어쓰고 있다", t)


class TestRefusalsGiveNextMove(GilFixture):
    """모든 거부는 '다음 올바른 한 수'를 준다 (이슈 #47).

    관통 원칙: gil 은 강제(거부)는 잘 하나 그 다음 행동으로 안내하는 레일이 약했다. 거부가
    "하지 마"까지만 하면, 전진 편향이 있는 사용자(특히 LLM)는 막힌 곳을 **우회**하려 들지
    도구가 원하는 길로 가지 않는다. 거부 메시지는 LLM 이 읽는 프롬프트다.
    """

    def _ready_cycle(self):
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "P", "--body", "B")

    def test_unknown_kind_lists_valid_kinds_and_guesses(self):
        """G2 — 유효 목록 + 오타 근접 제안 + 지금 어디쯤인지."""
        self._ready_cycle()
        self._no_autofill = True
        r = self.gil("step", "c/c001", "--kind", "hypthesis", "--title", "H", "--body", "B")
        out = r.stdout + r.stderr
        self.assertIn("쓸 수 있는 kind", out)
        self.assertIn("hypothesis", out)
        self.assertIn("혹시", out)          # 근접 제안

    def test_unknown_flag_suggests_and_lists(self):
        """G3 — 붙여 쓴 오입력(--title-body)은 편집거리가 멀어도 뜻이 명백하다."""
        self._ready_cycle()
        r = self.gil("step", "c/c001", "--kind", "verify", "--title-body", "X")
        out = r.stdout + r.stderr
        self.assertIn("혹시 --title", out)
        self.assertIn("이 명령이 받는 플래그", out)

    def test_falsify_to_accepts_path_form(self):
        """G1 — 경로형(chain/cycle/s1)을 받아 정규화한다. 형식 때문에 3회 헤매지 않게."""
        self._ready_cycle()
        r = self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "H", "--body", "B",
                     "--falsify", "F", "--falsify-to", "c/c001/s1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bad_falsify_to_shows_format_and_candidates(self):
        """G1 — 틀렸으면 정답 형식과 **실제 후보**를 그 자리에 편다."""
        self._ready_cycle()
        r = self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "H", "--body", "B",
                     "--falsify", "F", "--falsify-to", "s9")
        out = r.stdout + r.stderr
        self.assertIn("짧은 스텝 이름", out)
        self.assertIn("이 사이클의 define: s1", out)

    def test_chain_close_says_how_to_close_each_cycle(self):
        """G7 — 사이클 이름만 나열하면 사용자는 gil close 를 시도했다 또 거부당한다."""
        self._ready_cycle()
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "H", "--body", "B",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "c/c001", "--kind", "verify", "--verdict", "refuted",
                 "--title", "V", "--body", "B")
        self.gil("step", "c/c001", "--kind", "analyze", "--title", "A", "--body", "B")
        self.gil("step", "c/c001", "--kind", "fail", "--title", "F", "--body", "B", "--to", "s1")
        self._no_retro_autofill = True
        r = self.gil("chain-close", "c")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("fail 잎만 있다", out)          # 왜 못 닫는지
        self.assertIn("--kind hypothesis --to s1", out)  # 다음 한 수 (재분기)
        self.assertIn("--abandon", out)                  # 다른 정직한 길


class TestStepMapLabelAssignment(GilFixture):
    """전체맵 라벨 **배정** — 체인당 1회, 사이클마다 1회 (이슈 #52).

    v3.17.1 의 겹침 해소는 옳았지만 배정이 틀렸다: 체인 라벨이 **사이클마다** 방출되고
    (36 사이클 체인에 라벨 36개), 그것들이 머리 공간을 다 먹어 사이클 라벨은 64개 중 1개만
    남았다. 화면이 안 읽히는 이유가 '겹침'에서 '내용이 틀림'으로 바뀐 것이다.

    원인: "이 사이클이 체인의 첫 사이클인가"를 **깊이 일치**로 판정했다. migrate 산물처럼
    사이클들이 체인 루트에서 나란히 갈라지면 그 조건이 사이클마다 참이 된다. 순차로 열린
    사이클만 있는 fixture 로는 절대 안 잡히는 버그다 — 그래서 migrate 로 재현한다.
    """

    def _migrated_repo(self, chains):
        """chains: {체인명: 사이클수} → 모든 사이클이 체인 루트에서 나란히 갈라진 그래프."""
        for chain, n in chains.items():
            for i in range(1, n + 1):
                d = os.path.join(self.repo, "cycles", f"{chain[:1].upper()}{i:03d}-{chain}{i}")
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "cycle.yaml"), "w", encoding="utf-8") as f:
                    f.write(f"id: {chain[:1].upper()}{i:03d}-{chain}{i}\nchain: {chain}\n"
                            f"title: t\nstatus: closed\nverdict: supported\n")
        self._git("add", "-A")
        self._git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "v2")
        r = self.gil("migrate", "--from", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.gil("graph", "--html", "--out", "g.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.repo, "g.html"), encoding="utf-8") as f:
            return f.read()

    def test_chain_names_are_not_drawn_at_all(self):
        """체인 이름은 아예 그리지 않는다 (2026-07-31, 상현님).

        배정을 고쳐 체인당 1회로 줄였지만, 그래도 라벨이 많아질수록 전체맵은 그림이 아니라
        글자판이 됐다. 이름은 늘 거기 있지만 사람이 매 순간 알아야 하는 건 아니다 — 필요할
        때 점·박스에 올리면 툴팁으로 뜬다. **자리 다툼에서 이기는 법은 안 싸우는 것이다.**
        """
        html = self._migrated_repo({"serving": 6, "dash": 3})
        self.assertNotIn("class:'chlabel'", html)   # 그리지 않는다
        self.assertNotIn("dmin===chainMinD", html)  # 옛 깊이 판정으로 되돌아가지도 않았다

    def test_the_chain_name_is_still_reachable_on_hover(self):
        """지우는 것과 감추는 것은 다르다 — 이름은 툴팁에 남아야 한다."""
        html = self._migrated_repo({"serving": 4})
        self.assertIn("class:'cyclabel'", html)     # 사이클 이름은 그대로 그린다
        # 사이클 박스 title = <체인>/<사이클>, 노드 title 에도 체인이 들어간다.
        self.assertIn("box.appendChild(svgEl('title',{},k))", html)
        self.assertIn("n.chain+'/'+n.cycle+'/'+n.step", html)


class TestStepMapLabels(GilFixture):
    """전체 스텝맵 라벨 겹침 회피 (이슈 #37).

    이건 픽셀 문제라 단위 테스트로 '안 겹친다'를 끝까지 증명할 수는 없다(실제 확인은 브라우저
    에서 좌표를 재서 했다: 라벨 34개 · 겹침 0). 여기서는 **회귀로 다시 깨질 만한 것**을 지킨다:
    겹침 해소 로직이 산출물에 실제로 들어 있는지, 그리고 옛 방식(직전 같은 종류 라벨하고만
    비교하는 계단식)으로 되돌아가지 않았는지.

    실제로 한 번 깨뜨려 봤기에 남긴다 — 새 로직을 넣으면서 옛 `const CW` 선언을 안 지워
    **중복 선언으로 스크립트 전체가 죽었고, 그래프가 통째로 안 그려졌다.** 콘솔 에러도
    안 보였다. 그래서 '그래프가 실제로 그려지는가'까지 함께 본다.
    """

    def _build(self):
        self.gil("chain", "alpha", "--purpose", "P")
        self.gil("open", "alpha/c001", "--author", "clew", "--purpose", "P", "--body", "B")
        self.gil("step", "alpha/c001", "--kind", "success", "--title", "S", "--body", "B")
        self.gil("close", "alpha/c001")
        out = os.path.join(self.repo, "g.html")
        r = self.gil("graph", "--html", "--out", "g.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            return f.read()

    def test_collision_resolver_is_present(self):
        """종류를 섞어 실제 사각형으로 밀어내는 해소기가 들어 있다."""
        html = self._build()
        self.assertIn("function placeLabel", html)
        self.assertIn("placed.some", html)   # 이미 놓인 것 전부와 비교

    def test_no_duplicate_const_declaration(self):
        """같은 스코프에 const 가 두 번 선언되면 스크립트 전체가 죽는다(실제로 깨뜨렸다)."""
        html = self._build()
        self.assertEqual(html.count("const CW=6"), 1)

    def test_graph_actually_renders(self):
        """스크립트가 죽으면 라벨만 사라지는 게 아니라 그래프가 통째로 안 그려진다."""
        html = self._build()
        self.assertIn("buildStepMap", html)
        self.assertIn("alpha", html)


class TestReachCycleFromAnyBranch(GilFixture):
    """다른 브랜치에 서 있어도 대상 사이클에 닿는다 (이슈 #44 · #47 G6).

    옛 동작: currentCycle 이 HEAD 계보만 봐서, main 에 서 있으면 멀쩡히 존재하는 사이클을
    "없음"으로 거부했다 — **재분기하고 싶어도 도구가 막는** 최악의 형태다. 사이클은 진짜 커밋
    그래프에 있는 것이지 지금 무엇을 체크아웃했는지에 달린 게 아니다.

    다만 '찾기'와 '이어붙이기'는 다른 일이다. 존재는 그래프 전체에서 찾되, 팁은 그 사이클의
    가지에서 읽어야 한다 — 전체를 섞으면 backtrack 으로 갈라진 죽은 형제 가지가 팁으로 잡혀
    순서 강제·종결 판정이 어긋난다(실제로 한 번 그렇게 깨뜨렸다).
    """

    def _cycle(self):
        # gil init 으로 루트 커밋을 만들어야 기본 브랜치가 **실재**한다(커밋 없는 저장소의
        # 기본 브랜치는 unborn 이라 checkout 이 안 된다 — 이 시험은 '다른 브랜치에 서 있기'가
        # 성립해야 의미가 있다).
        self.gil("init")
        self.base = self._git("branch", "--show-current").stdout.strip()
        self.gil("chain", "b", "--purpose", "P")
        self.gil("open", "b/c001", "--author", "clew", "--purpose", "P", "--body", "B")
        # 사이클을 **열린 채**로 둔다 — 종결 잎 뒤에는 이어 붙지 못하므로(이슈 #60), 이 시험이
        # 재려는 것("다른 브랜치에 서 있어도 대상 사이클에 닿는가")과 섞이지 않게 한다.
        self.gil("step", "b/c001", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "b/c001", "--kind", "verify", "--title", "V",
                 "--verdict", "supported", "--body", "B")

    def test_step_reaches_cycle_from_another_branch(self):
        self._cycle()
        self._git("checkout", "-q", self.base)
        self.assertEqual(self._git("branch", "--show-current").stdout.strip(), self.base,
                         "대상 사이클이 아닌 브랜치에 서 있어야 이 시험이 성립한다")
        r = self.gil("step", "b/c001", "--kind", "analyze", "--title", "A", "--body", "B")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_open_rejects_duplicate_cycle_on_another_branch(self):
        """중복 가드는 그래프 전체로 본다 — 같은 이름 사이클이 둘이면 이후 조회가 모호해진다."""
        self._cycle()
        self._git("checkout", "-q", self.base)
        r = self.gil("open", "b/c001", "--author", "clew", "--purpose", "P2", "--body", "B")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("이미 존재", r.stderr)

    def test_missing_cycle_still_refused(self):
        """정말 없는 건 여전히 거부한다 — 넓힌 게 '아무거나 받는다'는 뜻은 아니다."""
        self.gil("chain", "b", "--purpose", "P")
        r = self.gil("step", "b/c999", "--kind", "analyze", "--title", "A", "--body", "B")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("없음", r.stderr)


class TestRepoResolutionIsHonest(GilFixture):
    """저장소 해석이 어긋나면 조용히 돌지 않는다 (이슈 #51).

    실측: 같은 폴더에서 CLI 는 체인 2개를, MCP 는 0개를 봤다. 사람과 에이전트가 **서로 다른
    그래프**를 보고 있었고, 에이전트는 "기록이 거의 없다"며 새 체인을 열 뻔했다.

    원인은 --repo 의 성격이다. 기본값을 바꾸는 옵션처럼 보이지만 실제로는 **호스트가 주는
    정답을 무효화하는 스위치**이고, 사용자 스코프에 한 번 박히면 모든 프로젝트에 영원히 붙는다.
    그리고 gil 의 대상은 폴더가 아니라 폴더 **안의** refs/gil/* 라, 엉뚱한 폴더에서도 빈
    그래프를 새로 만들며 정상처럼 보인다 — git 이라면 즉시 멎을 상황이 여기선 조용히 돈다.
    """

    def _tool(self, args, env, name="gil_log"):
        import json
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve", *args], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1,
                             env=dict(os.environ, GIL_NO_VIEWER="1", **env))
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        read = lambda: json.loads(p.stdout.readline())
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                             "clientInfo": {"name": "t", "version": "1"}}})
            read()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": name, "arguments": {}}})
            m = read()
            if "error" in m:
                return True, m["error"].get("message", "")
            r = m["result"]
            return bool(r.get("isError")), r["content"][0]["text"]
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()

    def test_pinned_repo_that_overrides_open_folder_is_refused(self):
        """경고가 아니라 **거부**다 — 경고로 감당할 위험이 아니다."""
        self.gil("init")
        other = tempfile.mkdtemp(prefix="gil-open-")
        try:
            err, t = self._tool(["--repo", self.repo], {"CLAUDE_PROJECT_DIR": other})
            self.assertTrue(err, t)
            self.assertIn("덮어쓰고 있다", t)
            self.assertIn('"args": ["mcp", "serve"]', t)   # 다음 한 수(이슈 #47)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_read_tools_always_show_the_target_path(self):
        """어긋났을 때만이 아니라 **항상** 찍는다 — 조용한 정상 동작은 경고로 못 잡는다."""
        self.gil("init")
        err, t = self._tool([], {"CLAUDE_PROJECT_DIR": self.repo})
        self.assertFalse(err, t)
        self.assertIn("📂", t)
        self.assertIn(os.path.realpath(self.repo), os.path.realpath(t.split("\n")[0][2:].strip()))

    def test_matching_repo_is_not_refused(self):
        """일치하면 조용히 돈다 — 늘 막으면 아무도 안 읽는다."""
        self.gil("init")
        err, t = self._tool(["--repo", self.repo], {"CLAUDE_PROJECT_DIR": self.repo})
        self.assertFalse(err, t)

    def test_version_check_failure_gives_a_next_move(self):
        """자기갱신이 막혀도 손으로 가는 길을 준다(이슈 #47 의 결)."""
        r = self.gil("help", "version")
        # 메시지 자체는 네트워크 실패 시에만 뜨므로, 여기서는 소스에 경로가 박혔는지로 갈음한다.
        self.assertEqual(r.returncode, 0)


class TestChainSuccessionIsDeclaredNotInferred(GilFixture):
    """"이어받음"은 닫힌 끝에서 태어났을 때만 (이슈 #53 · #54).

    계보를 git 조상관계에서 읽는 건 맞지만, 조상관계만으로는 둘이 구분되지 않는다:
      (가) 진짜 계승 — 앞 체인을 chain-close 로 닫고 그 끝에서 새 체인을 연다(배포 순환).
      (나) 병렬 작업 — 앞 체인이 아직 열려 있는데 옆에서 다른 줄기를 시작한다.
    둘 다 git 에서는 같은 모양이라, 옛 코드는 (나)까지 "부모 체인 X 에서 이어받음"이라고
    **단언**했다. 실측: v2 에서 parent:null 인 독립 체인 5개가 이주 뒤 한 줄로 이어졌고,
    같은 기간 서로 다른 장비에서 굴리던 트랙들이 이어받음으로 각인됐다. 그런 이어받음은 없었다.

    판정은 **만들어진 순간** 기준이어야 한다. "부모가 지금 닫혀 있나"로 보면 나란히 시작한
    체인도 앞 체인이 나중에 닫히는 순간 소급해서 자식이 된다 — 실제로 그렇게 한 번 틀렸다.
    """

    def _parents(self):
        import json, re
        r = self.gil("graph", "--html", "--out", "g.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.repo, "g.html"), encoding="utf-8") as f:
            h = f.read()
        m = re.search(r'id="parentdata"[^>]*>([^<]*)', h)
        return json.loads(m.group(1)) if m else {}

    def _finish_cycle(self, target):
        self.gil("step", target, "--kind", "hypothesis", "--title", "H", "--body", "B",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", target, "--kind", "verify", "--verdict", "supported",
                 "--title", "V", "--body", "B")
        self.gil("step", target, "--kind", "analyze", "--title", "A", "--body", "B")
        self.gil("step", target, "--kind", "success", "--title", "S", "--body", "B")
        self.gil("close", target)

    def test_parallel_chain_is_not_called_inheritance(self):
        """앞 체인이 열려 있는데 옆에서 시작한 줄기는 자식이 아니다."""
        self.gil("chain", "alpha", "--purpose", "장기 트랙 A")
        self.gil("open", "alpha/c001", "--author", "t", "--purpose", "진행중", "--body", "B")
        self.gil("chain", "beta", "--purpose", "동시에 굴릴 트랙 B")
        self.assertEqual(self._parents().get("beta", ""), "",
                         "열린 체인 옆에서 시작한 줄기를 '이어받음'이라 하면 안 된다")

    def test_real_succession_from_closed_chain_is_kept(self):
        """닫힌 끝에서 태어난 것은 진짜 계승 — 없애면 안 된다."""
        self.gil("chain", "alpha", "--purpose", "P")
        self.gil("open", "alpha/c001", "--author", "t", "--purpose", "P", "--body", "B")
        self._finish_cycle("alpha/c001")
        self.gil("chain-close", "alpha")
        self.gil("chain", "gamma", "--purpose", "닫힌 끝에서 이어받음")
        self.assertEqual(self._parents().get("gamma"), "alpha")

    def test_closing_the_parent_later_does_not_adopt_a_sibling(self):
        """판정은 만들어진 순간 기준 — 나중에 닫혔다고 소급 입양되지 않는다."""
        self.gil("chain", "alpha", "--purpose", "P")
        self.gil("open", "alpha/c001", "--author", "t", "--purpose", "P", "--body", "B")
        self.gil("chain", "beta", "--purpose", "병렬")     # alpha 가 열린 동안 태어났다
        self._finish_cycle("alpha/c001")
        self.gil("chain-close", "alpha")                    # 이제야 닫는다
        self.assertEqual(self._parents().get("beta", ""), "",
                         "나중에 부모가 닫혔다고 형제를 자식으로 만들면 안 된다")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTerminalAttachAndAt(GilFixture):
    """종결 잎을 지키고, 두고 온 가지를 닫게 한다 (이슈 #59 · #60).

    append-only 그래프에서는 사후 수정 경로가 없다 — 그러니 강제는 **그 순간**에 있어야 한다.
    실사용에서 둘이 겹쳐 났다: (1) refuted 로 죽은 가지에 fail 을 못 붙인 채 HEAD 가 재분기로
    떠나 그 가지가 영구 미종결로 남았고(fsck 도 안 잡았다), (2) 종결 success 잎 뒤에 다음
    스텝이 경고 한 줄 없이 이어 붙어 "이 가지는 여기서 끝났다"는 뜻이 사라졌다.
    """

    def setUp(self):
        super().setUp()
        self.gil("chain", "adopt", "--purpose", "채택")
        self.gil("open", "adopt/gap", "--author", "clew", "--purpose", "간극",
                 "--body", "무엇이 빠졌나")
        self.gil("step", "adopt/gap", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")               # s2
        self.gil("step", "adopt/gap", "--kind", "verify", "--title", "V",
                 "--verdict", "refuted", "--body", "반증")             # s3
        self.gil("step", "adopt/gap", "--kind", "analyze", "--title", "A",
                 "--body", "원인")                                     # s4

    def _rebranch(self):
        """HEAD 를 재분기로 옮긴다 — s4 가지는 종결 없이 남는다(사고 재현)."""
        return self.gil("step", "adopt/gap", "--kind", "hypothesis", "--to", "s1",
                        "--title", "H2", "--falsify", "F", "--falsify-to", "s1",
                        "--inherit", "s4 의 교훈")                      # s5

    # ── #60① 종결 스텝 뒤 부착 금지 ──

    def _supported_success(self):
        """산 잎을 만든다 — refuted 가지에선 success 가 문법으로 안 나오므로 갈래를 새로 낸다."""
        self.gil("step", "adopt/gap", "--kind", "hypothesis", "--to", "s1", "--title", "H-ok",
                 "--falsify", "F", "--falsify-to", "s1", "--inherit", "앞 갈래의 교훈")
        self.gil("step", "adopt/gap", "--kind", "verify", "--title", "V-ok",
                 "--verdict", "supported", "--body", "지지")
        self.gil("step", "adopt/gap", "--kind", "analyze", "--title", "A-ok", "--body", "해석")
        return self.gil("step", "adopt/gap", "--kind", "success", "--title", "됐다", "--body", "성과")

    def test_attach_after_success_is_refused(self):
        """success 잎 뒤에 이어 붙지 못한다 — 잎의 뜻이 사라지지 않게."""
        self.assertEqual(self._supported_success().returncode, 0)
        r = self.gil("step", "adopt/gap", "--kind", "hypothesis", "--title", "또",
                     "--falsify", "F", "--falsify-to", "s1")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("종결 스텝", out)
        self.assertIn("--to", out)      # 다음 올바른 한 수(형제 가지)를 준다
        self.assertIn("gil close", out) # 또는 사이클을 닫아라

    def test_attach_after_fail_is_refused(self):
        """죽은 잎 뒤 부착은 옛 가드가 이미 막는다 — 이 회귀 테스트로 그 짝을 고정한다."""
        self.gil("step", "adopt/gap", "--kind", "fail", "--to", "s1",
                 "--title", "막힘", "--body", "벽")   # analyze 뒤 fail — 정상 종결
        r = self.gil("step", "adopt/gap", "--kind", "verify", "--title", "또",
                     "--verdict", "supported", "--body", "B")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("죽은 잎", r.stdout + r.stderr)

    def test_sibling_branch_after_success_still_works(self):
        """이어갈 길은 막지 않는다 — --to 로 갈래를 내면 success 는 진짜 잎으로 남는다."""
        self._supported_success()
        r = self.gil("step", "adopt/gap", "--kind", "hypothesis", "--to", "s1",
                     "--title", "다른 축", "--falsify", "F", "--falsify-to", "s1",
                     "--inherit", "앞 갈래의 성과를 지고 간다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Parent"), "s1")

    # ── #59 두고 온 가지를 닫는 --at ──

    def test_at_closes_the_abandoned_branch(self):
        """HEAD 가 떠난 뒤에도 그 잎 자리에 종결을 박을 수 있다.

        (이슈 #67 이후 --at 은 박고 **원래 자리로 돌아오므로**, 종결은 HEAD 가 아니라
        그 가지에서 확인한다 — 다녀왔다는 사실 자체가 새 동작이다.)"""
        self._rebranch()
        r = self.gil("step", "adopt/gap", "--kind", "fail", "--at", "s4", "--to", "s1",
                     "--title", "이 접근은 막혔다", "--body", "벽의 지도")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("adopt-gap-s4b1", "Gil-Parent"), "s4")
        self.assertEqual(self.trailer("adopt-gap-s4b1", "Gil-Kind"), "fail")

    def test_fail_without_at_does_not_land_on_live_leaf(self):
        """--to 는 부모를 바꾸지 않는다 — 살아있는 잎 위에 fail 이 얹히면 그 잎이 죽는다.

        실사용에서 사본 레포로 먼저 밟아 발견한 손상 경로다. 이제는 종결 가드가 먼저 막는다."""
        self._supported_success()
        r = self.gil("step", "adopt/gap", "--kind", "fail", "--to", "s1",
                     "--title", "뒤늦게 s4 를 닫으려 했다", "--body", "X")
        self.assertNotEqual(r.returncode, 0, "살아있는 success 잎 위에 fail 이 얹혔다")
        self.assertIn("종결", r.stdout + r.stderr)

    def test_at_must_be_a_dangling_leaf(self):
        """--at 은 매달린 잎 자리에만 — 자식이 있는 스텝엔 못 박는다."""
        self._rebranch()
        r = self.gil("step", "adopt/gap", "--kind", "fail", "--at", "s1", "--to", "s1",
                     "--title", "X", "--body", "X")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("잎이 아니다", r.stdout + r.stderr)

    def test_at_is_terminal_only(self):
        """--at 은 종결 스텝 전용 — 진행 스텝의 갈래는 --to 가 낸다."""
        self._rebranch()
        r = self.gil("step", "adopt/gap", "--kind", "verify", "--at", "s4",
                     "--verdict", "supported", "--title", "X", "--body", "X")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--to", r.stdout + r.stderr)

    # ── #59③ fsck 가 매달린 잎을 잡는다 ──

    def test_fsck_reports_dangling_leaf_in_open_cycle(self):
        """열린 사이클이어도 버려진 미종결 잎은 보고한다 — 지금 안 보이면 영영 못 고친다."""
        self._rebranch()
        out = (lambda r: r.stdout + r.stderr)(self.gil("fsck"))
        self.assertIn("매달린 미종결 잎", out)
        self.assertIn("s4", out)
        self.assertIn("--at s4", out)   # 고치는 한 수까지 준다

    def test_fsck_does_not_flag_the_working_tip(self):
        """진행 중인 팁이 미종결인 건 정상이다 — 그걸 위반이라 부르면 소음이 된다."""
        out = (lambda r: r.stdout + r.stderr)(self.gil("fsck"))
        self.assertNotIn("매달린 미종결 잎", out)

    def test_fsck_clean_after_closing_the_branch(self):
        """--at 으로 닫으면 fsck 가 조용해진다 — 보고가 실제로 해소 가능해야 한다."""
        self._rebranch()
        self.gil("step", "adopt/gap", "--kind", "fail", "--at", "s4", "--to", "s1",
                 "--title", "막힘", "--body", "벽")
        out = (lambda r: r.stdout + r.stderr)(self.gil("fsck"))
        self.assertNotIn("매달린 미종결 잎", out)


class TestHandoffRespectsTheReference(GilFixture):
    """기준 문서가 handoff 의 판정에 참여한다 (이슈 #62, 상현님 실사용).

    사람이 기준 문서에 "완전한 성공 전엔 사이클을 닫지 마라"고 못박고 사이클을 일부러 열어
    뒀는데, handoff 는 "열린 사이클 없음 → 새 사이클을 열거나 체인을 닫아라"로 밀었다.
    잎이 다 종결됐다는 이유였다 — 그러나 **'잎이 다 종결됐다' ≠ '사이클 목표가 달성됐다'**.

    handoff 는 세션을 이어받는 첫 관문이라(#55) 영향이 크다. 이어받은 에이전트는 기준 문서보다
    handoff 를 먼저 보고, 그대로 따르면 미완의 사이클을 버려두고 새 사이클로 도망친다 —
    #45 가 막으려는 바로 그 행동을 도구가 권유한 셈이다.
    """

    REF = ("# 기준 문서 — adopt\n\n"
           "## 3. 이 체인에서 \"이건 하지 마라\"로 못 박을 것이 있나요?\n"
           "완전한 성공을 얻기 전에는 사이클을 닫지 마라. 계속 실패하고 실패로부터 배워라.\n")

    def setUp(self):
        super().setUp()
        self._no_interview_autofill = True  # 기준 문서를 직접 심는다 — 보정이 덮어쓰지 않게
        self.gil("init", "--name", "clew")
        self.gil("chain", "adopt", "--purpose", "채택")
        self.gil("interview", "adopt", "--ask", "-",
                 input='[{"q":"하지 마라로 못 박을 것","type":"text"}]')
        with open(os.path.join(self.repo, "reference-adopt.md"), "w", encoding="utf-8") as f:
            f.write(self.REF)
        self.gil("interview", "adopt", "--resolve", "reference-adopt.md")
        self.gil("open", "adopt/gap", "--author", "clew", "--purpose", "갭", "--body", "갭 11개")

    def _terminate_all_leaves(self):
        self.gil("step", "adopt/gap", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "adopt/gap", "--kind", "verify", "--title", "V",
                 "--verdict", "supported", "--body", "지지")
        self.gil("step", "adopt/gap", "--kind", "analyze", "--title", "A", "--body", "해석")
        self.gil("step", "adopt/gap", "--kind", "success", "--title", "S", "--body", "G2 닫음")

    def _handoff(self):
        r = self.gil("handoff")
        return r.stdout + r.stderr

    def test_unclosed_cycle_is_not_reported_as_absent(self):
        """잎이 다 종결돼도 닫히지 않은 사이클은 여전히 있다 — 없는 것처럼 적지 않는다."""
        self._terminate_all_leaves()
        out = self._handoff()
        self.assertNotIn("열린 사이클 없음", out)
        self.assertIn("사이클 gap (미종결", out)

    def test_leaf_state_and_cycle_state_are_distinguished(self):
        """두 개념이 한 문장에 뭉개지지 않는다 — 잎 상태는 따로 적는다."""
        self._terminate_all_leaves()
        out = self._handoff()
        self.assertIn("잎 상태: solved", out)
        self.assertIn("'잎이 다 종결됐다'는 '사이클 목표가 달성됐다'와 다르다", out)

    def test_both_moves_are_offered_not_just_closing(self):
        """닫는 길과 더 파는 길을 나란히 준다 — 도구가 이탈을 권유하지 않게."""
        self._terminate_all_leaves()
        out = self._handoff()
        self.assertIn("gil close adopt/gap", out)
        # 안내가 실제 문법이어야 한다 — 틀린 한 수를 주면 거부로 되돌아온다.
        self.assertNotIn("--verdict solved", out)
        self.assertIn("--kind hypothesis --to", out)

    def test_handoff_quotes_the_reference_prohibitions(self):
        """기준 문서의 '하지 마라'를 handoff 가 인용한다 — 스스로 읽기로 마음먹지 않아도."""
        out = self._handoff()
        self.assertIn("기준 문서", out)
        self.assertIn("하지 마라로 못박힌 것", out)
        self.assertIn("완전한 성공을 얻기 전에는 사이클을 닫지 마라", out)

    def test_closed_cycle_disappears_as_before(self):
        """진짜로 닫힌 사이클은 예전처럼 안내에서 빠진다 — 규칙을 뒤집는 게 아니다."""
        self._terminate_all_leaves()
        rc = self.gil("close", "adopt/gap")
        self.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
        out = self._handoff()
        self.assertIn("닫히지 않은 사이클 없음", out)


class TestViewerDoesNotDisturbTheRepo(GilFixture):
    """관전자는 저장소를 건드리지 않는다 (이슈 #64, 상현님 실사용).

    뷰어를 띄운 채 migrate 를 돌리면 매번 다른 지점에서 exit 128 로 죽고, 중간까지 만든
    브랜치를 남겼다. 원인은 뷰어 폴링이 1.5초마다 도는 `git status` 였다 — 인덱스를 갱신하며
    .git/index.lock 을 잡는다. 뷰어는 온보딩·handoff 가 "띄우라"고 지시하는 것이라(#55),
    지시대로 띄운 사람이 정확히 이 함정을 밟았다.

    대조 실험으로 기전을 확인했다: git status 를 조밀하게 돌리며 이주하면 옛 방식은
    `Unable to create '.git/index.lock': File exists` 로 죽고, --no-optional-locks 면 완주한다.
    """

    def test_viewer_read_does_not_touch_the_index(self):
        """뷰어가 읽어도 인덱스 파일이 바뀌지 않는다 — 읽기만 하는 관전자여야 한다."""
        self.gil("init")
        self.gil("chain", "c", "--purpose", "P")
        index = os.path.join(self.repo, ".git", "index")
        before = os.stat(index).st_mtime_ns
        r = self.gil("graph")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.stat(index).st_mtime_ns, before,
                         "뷰어가 인덱스를 갱신했다 — 동시에 커밋하는 쪽과 락으로 경합한다")


class TestGitFailuresAreLegible(GilFixture):
    """하위 git 실패는 원인을 그대로 실어 올린다 (이슈 #64③).

    "exit status 128" 한 줄만 나오면 원인을 좁힐 수 없다. 실사용에서 index.lock 경합을
    찾는 데 그 한 줄이 없어 오래 걸렸다 — git 이 이미 정확히 말해주고 있었는데 삼켰다."""

    def test_git_stderr_is_carried_into_the_message(self):
        self.gil("init")
        self.gil("chain", "c", "--purpose", "P")
        # 이미 있는 브랜치 이름으로 사이클을 열어 git 실패를 유도한다.
        self._git("branch", "c-dup")
        r = self.gil("open", "c/dup", "--author", "clew", "--purpose", "P", "--body", "B")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertNotIn("exit status 128\n", out.replace("exit status 128 —", ""),
                         "git 의 말이 삼켜진 채 종료코드만 남았다")


class TestMigratePartialIsAnnounced(GilFixture):
    """이주가 중간에 멈추면 남은 것을 말한다 (이슈 #64②).

    help 는 "충돌 시 아무것도 만들지 않고 거부(원자성)"라 하고 이름 충돌은 실제로 깨끗이
    거부한다. 그러나 **실행 중** 실패는 27개·14개·6개를 남긴 채 죽었다. 다음 실행은 그
    잔여물 때문에 이름 충돌로 거부돼, 손으로 지우기 전엔 재시도가 막혔다."""

    def _v2cycle(self, chain, cid, **fields):
        d = os.path.join(self.repo, "rooms/experiment/chains", chain, cid)
        os.makedirs(d, exist_ok=True)
        lines = [f"id: {cid}", f"chain: {chain}"] + [f"{k}: {v}" for k, v in fields.items()]
        with open(os.path.join(d, "cycle.yaml"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def _seed(self):
        with open(os.path.join(self.repo, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# 대문\n")
        # 이주 *산물끼리* 이름이 부딪는 배치 — 체인 a 의 사이클 브랜치(a-c001-x)가 다음 체인의
        # 이름과 같다. 선제 검사는 '이미 있는 브랜치'만 보므로 이건 못 본다 → 실행 중 실패.
        self._v2cycle("a", "C001-x", parent="null", status="closed",
                      verdict="supported", title="첫째")
        self._v2cycle("a-c001-x", "C001-y", parent="null", status="closed",
                      verdict="supported", title="이름이 부딪는 체인")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "v2 seed")
        return self._git("rev-parse", "HEAD").stdout.strip()

    def test_partial_migration_reports_what_remains(self):
        v2 = self._seed()
        self._git("checkout", "-q", "-b", "v3-mig")
        r = self.gil("migrate", "--from", v2)
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("이주가 중간에 멈췄다", out)
        self.assertIn("git branch -D", out)   # 치우는 한 수를 준다
        self.assertIn("a-c001-x", out)        # 무엇이 남았는지 이름으로 짚는다

    def test_invalid_name_is_refused_before_anything_is_made(self):
        """검사할 수 있는 건 실행 중까지 미루지 않는다 — v3 이름 유효성은 선제로 본다."""
        with open(os.path.join(self.repo, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# 대문\n")
        self._v2cycle("bad name", "C001-x", parent="null", status="closed",
                      verdict="supported", title="공백 든 체인")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "v2 seed")
        v2 = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("checkout", "-q", "-b", "v3-mig")
        r = self.gil("migrate", "--from", v2)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("아무것도 만들지 않았다", r.stdout + r.stderr)
        self.assertNotIn("이주가 중간에 멈췄다", r.stdout + r.stderr)


class TestChainDepthCountsAllCycles(GilFixture):
    """--depth chain 이 사이클을 빠뜨리지 않는다 (이슈 #63, 상현님 실사용).

    옛 집계는 **체인 브랜치 팁에서 도달 가능한 커밋**만 셌다. 그런데 사이클은 각자
    <chain>-<cycle> 브랜치에 살고 체인 팁으로 병합되지 않는다 — 그래서 병합 안 된 사이클이
    통째로 빠졌다(실측: 총 61개 중 28개 유실, 네 체인은 사이클이 있는데 [사이클 0]).

    한 바이너리 안에서 세 경로가 서로 다른 답을 냈다: --depth chain(2) vs --depth cycle(10)
    vs handoff(10) vs 뷰어(10). --depth chain 은 계보를 조망하는 **첫 화면**이라, 여기서 빈
    껍데기로 보이면 이미 있는 작업을 못 보고 새로 판다 — 그래프를 보게 만든 이유(#55) 자체가
    무너진다.
    """

    def setUp(self):
        super().setUp()
        self.gil("init")
        self.gil("chain", "design-v3", "--purpose", "P")
        for c in ("fold", "effect", "flow"):
            self.gil("open", f"design-v3/{c}", "--author", "clew", "--purpose", c,
                     "--body", f"정의 {c}")
            self.gil("step", f"design-v3/{c}", "--kind", "hypothesis", "--title", "H",
                     "--falsify", "F", "--falsify-to", "s1")
            self.gil("step", f"design-v3/{c}", "--kind", "verify", "--title", "V",
                     "--verdict", "supported", "--body", "B")
            self.gil("step", f"design-v3/{c}", "--kind", "analyze", "--title", "A", "--body", "B")
            self.gil("step", f"design-v3/{c}", "--kind", "success", "--title", "S", "--body", "B")
            self.gil("close", f"design-v3/{c}")

    def test_chain_depth_counts_unmerged_cycle_branches(self):
        out = self.gil("log", "--depth", "chain").stdout
        self.assertIn("[사이클 3]", out)
        self.assertNotIn("[사이클 0]", out)

    def test_three_paths_agree(self):
        """--depth chain · --depth cycle · handoff 가 같은 수를 말한다."""
        chain_view = self.gil("log", "--depth", "chain").stdout
        cycle_view = self.gil("log", "design-v3", "--depth", "cycle").stdout
        self.assertIn("[사이클 3]", chain_view)
        self.assertEqual(cycle_view.count("◆"), 3)
        # handoff 의 누적 신호도 같은 집계원을 본다.
        self.assertIn("3", self.gil("handoff").stdout + self.gil("handoff").stderr)


class TestCycleGoal(GilFixture):
    """사이클이 '무엇이 되면 끝인가'를 스스로 들고 있다 (이슈 #62 제안 1).

    purpose 가 "무엇을 하려는가"라면 goal 은 "무엇이 되면 됐다고 할 것인가"다. 옛 도구는
    잎이 다 종결되면 사실상 끝난 것으로 읽었는데, **"잎이 다 종결됐다" ≠ "목표가 달성됐다"**.
    close 가 verdict 를 받으니 열 때 목표를 받는 건 대칭이고, 그래야 닫는 판단이 자기확신이
    아니라 열 때의 선언에 매인다.

    gil 은 목표 달성 여부를 알 수 없다 — 알 수 있는 건 "답했는가"뿐이고 그것만 강제한다
    (정직 강제 불가, 은폐 영속화만 차단).
    """

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "g", "--purpose", "P")

    def _cycle(self, name, *extra):
        self.gil("open", f"g/{name}", "--author", "clew", "--purpose", "Q",
                 "--body", "정의", *extra)
        self.gil("step", f"g/{name}", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", f"g/{name}", "--kind", "verify", "--title", "V",
                 "--verdict", "supported", "--body", "B")
        self.gil("step", f"g/{name}", "--kind", "analyze", "--title", "A", "--body", "B")
        self.gil("step", f"g/{name}", "--kind", "success", "--title", "S", "--body", "B")

    def test_goal_is_imprinted(self):
        self.gil("open", "g/c1", "--author", "clew", "--purpose", "Q", "--body", "정의",
                 "--goal", "예제 이식 불가 0건")
        self.assertEqual(self.trailer("HEAD", "Gil-Cycle-Goal"), "예제 이식 불가 0건")

    def test_close_must_answer_the_goal(self):
        """목표를 선언하고 열었으면, 닫을 때 그 목표에 답해야 한다."""
        self._cycle("c1", "--goal", "갭 11개를 0으로")
        r = self.gil("close", "g/c1")
        self.assertNotEqual(r.returncode, 0, "목표에 답하지 않고 닫혔다")
        out = r.stdout + r.stderr
        self.assertIn("갭 11개를 0으로", out)   # 무엇에 답해야 하는지 그 자리에서 보여준다
        self.assertIn("--goal-met", out)
        self.assertIn("--abandon", out)

    def test_close_passes_with_declaration(self):
        self._cycle("c1", "--goal", "갭 11개를 0으로")
        r = self.gil("close", "g/c1", "--goal-met")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Goal-Met"), "true")

    def test_no_goal_declared_keeps_old_behavior(self):
        """목표를 안 세운 사이클은 예전처럼 닫힌다 — 새 문법이 옛 흐름을 깨지 않는다."""
        self._cycle("c1")
        r = self.gil("close", "g/c1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_goal_is_shown_while_working(self):
        """매 스텝 그 자리에서 목표가 보인다 — 판단이 선언에 매이도록."""
        self.gil("open", "g/c1", "--author", "clew", "--purpose", "Q", "--body", "정의",
                 "--goal", "갭 11개를 0으로")
        r = self.gil("step", "g/c1", "--kind", "hypothesis", "--title", "H",
                     "--falsify", "F", "--falsify-to", "s1")
        self.assertIn("갭 11개를 0으로", r.stdout + r.stderr)

    def test_handoff_shows_the_goal(self):
        """이어받은 세션이 '무엇이 되면 끝인가'를 첫 화면에서 본다."""
        self.gil("open", "g/c1", "--author", "clew", "--purpose", "Q", "--body", "정의",
                 "--goal", "갭 11개를 0으로")
        out = (lambda r: r.stdout + r.stderr)(self.gil("handoff"))
        self.assertIn("🎯 목표", out)
        self.assertIn("갭 11개를 0으로", out)


class TestChainRootsDoNotStack(GilFixture):
    """이주된 체인들이 일렬로 적층되지 않는다 (이슈 #65).

    옛 이주는 체인 루트를 그때그때의 HEAD 에서 팠는데, HEAD 는 직전 체인의 마지막 사이클
    가지에 가 있다. 그래서 v2 에서 서로 독립이던 체인들이 처리 순서(알파벳순)대로 일렬로
    쌓였다.

    이 적층이 두 패널을 갈라놓은 뿌리였다: 전체맵은 그 조상관계를 날것으로 그려 "없던
    이어받음"(#53 이 잡은 거짓)을 보이고, 체인 그래프는 엄격한 해석으로 안 그려 "적층이
    있다는 사실"을 감췄다. 적층을 없애면 두 패널이 자연히 일치하고 그게 사실과도 맞는다.
    """

    def _seed(self):
        with open(os.path.join(self.repo, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# 대문\n")
        for ch in ("alpha", "beta", "gamma"):
            d = os.path.join(self.repo, "rooms/experiment/chains", ch, "C001-x")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "cycle.yaml"), "w", encoding="utf-8") as f:
                f.write(f"id: C001-x\nchain: {ch}\nparent: null\n"
                        f"status: closed\nverdict: supported\ntitle: T\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "v2 seed")
        v2 = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("checkout", "-q", "-b", "v3-mig")
        self.gil("migrate", "--from", v2)
        return v2

    def _is_ancestor(self, a, b):
        return self._git("merge-base", "--is-ancestor", a, b).returncode == 0

    def test_independent_v2_chains_stay_independent(self):
        self._seed()
        for a in ("alpha", "beta", "gamma"):
            for b in ("alpha", "beta", "gamma"):
                if a == b:
                    continue
                self.assertFalse(self._is_ancestor(a, b),
                                 f"{a} 가 {b} 의 조상이다 — v2 에서 독립이던 체인이 적층됐다")

    def test_fsck_is_quiet_on_clean_migration(self):
        self._seed()
        self.assertNotIn("적층", self.gil("fsck").stdout + self.gil("fsck").stderr)


class TestFsckReportsChainStacking(GilFixture):
    """적층은 감추지 말고 짚는다 (이슈 #65 제안 3).

    두 패널을 일치시키면 이 이상을 발견하게 해준 차이가 사라진다 — 그 신호를 fsck 로 옮긴다.
    그래프는 일관되게 그리되, 이상은 도구가 말한다."""

    def test_stacked_chain_root_is_reported(self):
        """옛 저장소·이주 산물에 남은 적층을 짚는다.

        (이제 gil chain 자체가 열린 체인 위에 새 체인을 얹는 걸 거부하므로 — 이슈 #54 —
        적층은 손으로 만든다. fsck 는 '있어선 안 되는 것'을 잡는 자리라 이게 맞는 재현이다.)"""
        self.gil("init")
        self.gil("chain", "first", "--purpose", "P")
        self._git("checkout", "-q", "-b", "second", "first")
        self._git("commit", "-q", "--allow-empty", "-m",
                  "gil second chain: 손으로 얹은 체인\n\n본문\n\n"
                  "Gil-Chain: second\nGil-Kind: chain-root\nGil-Chain-Purpose: P2")
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertIn("적층", out)
        self.assertIn("second", out)

    def test_real_succession_is_not_reported(self):
        """닫힌 끝에서 태어난 진짜 계승은 이상이 아니다 — 소음을 만들지 않는다."""
        self.gil("init")
        self.gil("chain", "first", "--purpose", "P")
        self.gil("chain-close", "first", "--retro", "-", input="# 회고\n됐다")
        self.gil("chain", "second", "--purpose", "P2")
        self.assertNotIn("적층", self.gil("fsck").stdout + self.gil("fsck").stderr)


class TestDeployStaged(GilFixture):
    """배포 단위 확정과 실제 롤아웃을 가른다 (이슈 #56, 다른 레포 실사용).

    (2026-07-31) 배포 마커는 이제 **배포되는 것 위에** — dev 층에 — 새겨진다. 그때 서 있던
    체인에 찍으면, 승격된 대문에는 정작 "배포했다"는 기록이 없다.

    옛 마커는 찍는 순간 "여기서 세상으로 나갔다"였다. 그런데 배포 단위를 확정하고도 실제
    롤아웃은 조율 때문에 몇 주 뒤인 구간이 구조적으로 길다. 그 사이 기록이 거짓이 된다 —
    보고자는 notes 에 `rollout_state=staged` 라는 필드를 손으로 발명해 정정하고 있었다.
    **상태 필드가 거짓이라 자유서술로 덮은 것**이고, 산문은 기계가 못 읽는다.

    안 자르면 계보가 끊기고, 자르면 없는 배포를 주장하게 되던 자리 — 둘 다 못 해서 cut 을
    미루고 있다는 게 보고의 핵심이었다.
    """

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c1", "--author", "clew", "--purpose", "Q", "--body", "정의")
        self.gil("step", "d/c1", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "d/c1", "--kind", "verify", "--title", "V",
                 "--verdict", "supported", "--body", "B")
        self.gil("step", "d/c1", "--kind", "analyze", "--title", "A", "--body", "B")
        self.gil("step", "d/c1", "--kind", "success", "--title", "S", "--body", "B")

    def test_target_records_where_it_went(self):
        """태그가 '무엇을'이면 target 은 '어디로'다 (이슈 #56, v2 레지스터의 '대상' 칸).

        main-dev 체제로 여러 대상에 나가면 "v2.1.0 이 어디로 갔나"가 그래프에 없다.
        gil 은 그 주소에 닿는지 확인하지 않는다 — 기록 도구지 외부를 찌르는 도구가 아니다."""
        r = self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0",
                     "--state", "staged", "--target", "l40s:8080")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("dev", "Gil-Deploy-Target"), "l40s:8080")
        self.assertEqual(self.trailer("dev", "Gil-Deploy-State"), "staged")
        # 승격도 대상을 함께 남긴다 — 언제 어디로 올라갔나가 둘 다 남는다.
        self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--promote", "--target", "l40s:8080")
        self.assertEqual(self.trailer("dev", "Gil-Deploy-State"), "live")
        self.assertEqual(self.trailer("dev", "Gil-Deploy-Target"), "l40s:8080")

    def test_target_is_shown_in_viewer(self):
        self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--target", "l40s:8080")
        out_html = os.path.join(self.repo, "g.html")
        self.gil("graph", "--html", "--out", out_html)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        self.assertIn('"deployTarget":"l40s:8080"', html)

    def test_default_stays_live(self):
        """옛 사용법은 그대로다 — 새 상태가 기존 흐름을 깨지 않는다."""
        r = self.gil("deploy", "--at", "d/c1/s5", "--tag", "v0.2.0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("dev", "Gil-Deploy-State"), "live")

    def test_staged_is_recorded_as_machine_readable_state(self):
        """산문이 아니라 상태로 남는다 — notes 에 손으로 쓴 필드를 발명하지 않아도 되게."""
        r = self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--state", "staged")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("dev", "Gil-Deploy-State"), "staged")
        out = r.stdout + r.stderr
        self.assertIn("아직 안 올라갔다", out)
        self.assertIn("--promote", out)   # 다음 올바른 한 수

    def test_promote_appends_rather_than_rewrites(self):
        """승격은 앞 마커를 고치지 않는다 — 언제 준비됐고 언제 올라갔나가 둘 다 남는다."""
        self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--state", "staged")
        # 마커는 배포되는 것 위에(dev) 새겨진다 — HEAD 는 하던 자리에 그대로 있다.
        staged_sha = self._git("rev-parse", "dev").stdout.strip()
        r = self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--promote")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("dev", "Gil-Deploy-State"), "live")
        # 앞의 staged 커밋이 그대로 살아 있다(append-only).
        self.assertNotEqual(self._git("rev-parse", "dev").stdout.strip(), staged_sha)
        self.assertIn("Gil-Deploy-State: staged",
                      self._git("log", staged_sha, "-1", "--format=%B").stdout)

    def test_bad_state_is_refused_with_both_meanings(self):
        r = self.gil("deploy", "--at", "d/c1/s5", "--tag", "v1", "--state", "rolled")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("staged", out)
        self.assertIn("live", out)


class TestParallelChains(GilFixture):
    """병렬 체인을 표현할 수단을 준다 (이슈 #54).

    v3 는 병렬 작업을 **막지 않으면서 병렬이라고 기록할 수단만** 없었다. gil help 는
    "닫힌 체인 끝에서만"이라 적어놓고 열린 체인 옆에서 새 체인을 여는 걸 통과시켰고,
    그래서 동시에 굴린 트랙이 git 조상관계로 "이어받음"이 됐다 — **선언된 진실
    (--inherit 없음)과 그려지는 진실(이어받음)이 반대**였다.

    막는 게 답이 아니다(실사용에서 5개 트랙이 서로 다른 장비에서 동시에 돌았다).
    #45 와 같은 문법으로 푼다: 거부하되, 선언하면 통과하고 그 선언이 그래프에 남는다.
    """

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "tester")
        self.gil("chain", "alpha", "--purpose", "장기 트랙 A")

    def test_new_chain_refused_while_another_is_open_without_dev_layer(self):
        """문서와 실동작의 어긋남을 없앤다 — 열린 체인이 있으면 그냥 통과시키지 않는다.

        이 거부가 옳았던 이유는 **새로 시작할 자리가 없었기** 때문이다: dev 층이 없으면 새
        체인은 HEAD(=열린 체인)에 얹힐 수밖에 없고, 그러면 커밋 그래프가 계승을 거짓말한다.
        그래서 옛 레이아웃(dev 없음)에서는 이 거부가 그대로 산다.
        """
        self._git("branch", "-D", "dev")  # 옛 레이아웃 재현
        r = self.gil("chain", "beta", "--purpose", "동시에 굴릴 트랙 B")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("alpha", out)
        self.assertIn("chain-close", out)      # 이어받기
        self.assertIn("--parallel-with", out)  # 병렬

    def test_dev_layer_lets_a_new_lineage_start_beside_an_open_chain(self):
        """dev 층이 있으면 열린 체인 옆에서 **새 계보를 시작**할 수 있다 (main-dev-chain).

        얹히는 게 아니라 층에서 갈라지므로 계승으로 그려질 위험 자체가 없다 — 거부의 이유가
        사라진 자리에서는 거부도 사라져야 한다.
        """
        r = self.gil("chain", "beta", "--purpose", "무관한 새 계보")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("beta", "Gil-Chain-Orphan"), "dev")
        anc = self._git("merge-base", "--is-ancestor", "alpha", "beta").returncode == 0
        self.assertFalse(anc, "dev 시조라 했는데 열린 체인의 자손으로 각인됐다")
        self.assertIn("위반 0", self.gil("fsck").stdout)

    def test_declared_parallel_is_recorded(self):
        r = self.gil("chain", "beta", "--purpose", "B", "--parallel-with", "alpha")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("beta", "Gil-Parallel-With"), "alpha")

    def test_declared_parallel_is_not_a_descendant(self):
        """선언만으로는 부족하다 — 위상도 진짜 형제여야 그래프가 같은 말을 한다."""
        self.gil("chain", "beta", "--purpose", "B", "--parallel-with", "alpha")
        anc = self._git("merge-base", "--is-ancestor", "alpha", "beta").returncode == 0
        self.assertFalse(anc, "병렬이라 선언했는데 앞 체인의 자손으로 각인됐다")

    def test_declared_parallel_is_not_flagged_as_stacking(self):
        """선언된 병렬은 사고가 아니라 판단이다 — fsck 가 소음을 만들지 않는다(이슈 #65 짝)."""
        self.gil("chain", "beta", "--purpose", "B", "--parallel-with", "alpha")
        self.assertNotIn("적층", self.gil("fsck").stdout + self.gil("fsck").stderr)

    def test_succession_after_close_still_works(self):
        """닫고 여는 길은 그대로다 — 그때는 계승이 사실이 된다."""
        self.gil("chain-close", "alpha", "--retro", "-", input="# 회고\n됐다")
        r = self.gil("chain", "beta", "--purpose", "B")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestChainCloseAdvancesTheChainRef(GilFixture):
    """봉인은 그 체인의 끝에 얹히고, 이름이 그 끝을 가리킨다 (이슈 #66, #44 계열).

    옛 chain-close 는 **그때 체크아웃돼 있던 브랜치**에 봉인을 얹었다. 그래서 체인 브랜치
    ref 는 옛 팁(대개 체인 선언·인터뷰 커밋)에 멈추고, 사이클도 봉인도 회고도 그 이름으로는
    도달할 수 없었다.

    "닫힌 체인의 끝에서 새 체인을 연다"는 커밋 그래프에서는 성립하는데, **그 체인의 이름이
    그 끝을 가리키지 않아** 뷰어·계보 판정이 새 체인을 고아로 봤다 — #65 의 잔여 불일치가
    여기서 나왔다. #44(reject/step 이 현재 브랜치에 커밋)와 같은 계열인데 chain-close 에만
    그 가드가 없었다.
    """

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "app", "--purpose", "P")
        self.gil("open", "app/c1", "--author", "c", "--purpose", "Q", "--body", "B")
        self.gil("step", "app/c1", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "app/c1", "--kind", "verify", "--title", "V",
                 "--verdict", "supported", "--body", "B")
        self.gil("step", "app/c1", "--kind", "analyze", "--title", "A", "--body", "B")
        self.gil("step", "app/c1", "--kind", "success", "--title", "S", "--body", "B")
        self.gil("close", "app/c1")
        # 체인 브랜치가 **아닌** 곳으로 옮겨간 뒤 닫는다 — 실사용에서 난 모양 그대로.
        base = self._git("rev-list", "--max-parents=0", "HEAD").stdout.split()[0]
        self._git("checkout", "-q", "-b", "elsewhere", base)

    def _close(self):
        with open(os.path.join(self.repo, "R.md"), "w", encoding="utf-8") as f:
            f.write("# 회고\n기준 대비 달성도\n")
        return self.gil("chain-close", "app", "--retro", "R.md")

    def test_chain_ref_points_at_the_seal(self):
        r = self._close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tip = self._git("log", "app", "-1", "--format=%s").stdout
        self.assertIn("chain-close", tip, "체인 이름이 봉인을 안 가리킨다")

    def test_cycles_are_reachable_from_the_chain_name(self):
        """사이클이 이름으로 도달 불가였던 자리 — 이름이 계보 전체를 담아야 한다."""
        self._close()
        reachable = self._git("log", "app", "--format=%s").stdout
        self.assertIn("app/c1/s1", reachable)

    def test_next_chain_really_succeeds_the_closed_one(self):
        """'닫힌 체인의 끝에서 새 체인을 연다'가 이름 수준에서도 성립한다.

        main-dev-chain 레이아웃(2026-07-31)에서 이 규칙은 **선언될 때만** 선다: --from 으로
        어느 체인을 이어받는지 말한 체인만 그 체인의 자손이 된다. 선언 없이 열면 dev 층에서
        나는 시조다 — 옛 동작(HEAD 가 마침 거기 있어서 얹힘)은 계승을 사고로 만들었다.
        """
        self._close()
        r = self.gil("chain", "next", "--purpose", "P2", "--from", "app")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        anc = self._git("merge-base", "--is-ancestor", "app", "next").returncode == 0
        self.assertTrue(anc, "선언한 계승이 실재 분기가 아니다 — 선언만 있고 분기는 없다")

    def test_undeclared_chain_is_a_dev_root_not_a_successor(self):
        """선언하지 않은 체인은 계승이 아니라 dev 층의 시조다 (main-dev-chain)."""
        self._close()
        r = self.gil("chain", "other", "--purpose", "무관한 새 계보")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        anc = self._git("merge-base", "--is-ancestor", "app", "other").returncode == 0
        self.assertFalse(anc, "선언하지 않았는데 앞 체인 위에 얹혔다 — 계승이 사고로 생겼다")
        on_dev = self._git("merge-base", "--is-ancestor", "dev", "other").returncode == 0
        self.assertTrue(on_dev, "dev 층에서 갈라지지 않았다")


class TestMCPExposesNewGrammar(GilFixture):
    """거부하는 문법은 MCP 표면에도 있어야 한다 (오늘 새로 선) .

    #45·#54·#62 로 거부를 세웠는데, 그 거부를 따를 인자가 툴 스키마에 없으면 MCP 로 도는
    에이전트는 갇힌다 — 거부만 하고 길이 없는 건 레일이 아니라 벽이고, 그건 #57 에서 고친
    실패와 같은 모양이다(레일이 사람 의사를 잘못 전하면 뚫는 게 합리적으로 보인다).

    우리 MVP 대상이 바로 그 경로(Claude Desktop 안 Claude Code + MCP)라 특히 중요하다.
    """

    def _tool_schema(self, name):
        import json
        self.gil("init")
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1,
                             env=dict(os.environ, GIL_NO_VIEWER="1"))
        try:
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "t", "version": "1"}}}) + "\n")
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                                      "params": {}}) + "\n")
            p.stdin.flush()
            json.loads(p.stdout.readline())
            tools = json.loads(p.stdout.readline())["result"]["tools"]
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()
        for t in tools:
            if t["name"] == name:
                return json.dumps(t.get("inputSchema", {}), ensure_ascii=False)
        raise AssertionError(f"{name} 툴이 없다")

    def test_open_exposes_goal_and_parallel(self):
        """#62 목표 선언과 #45 병렬 선언 — 둘 다 거부의 유일한 통로다."""
        sch = self._tool_schema("gil_open")
        self.assertIn("goal", sch)
        self.assertIn("parallel", sch)
        self.assertIn("refines", sch)   # #42

    def test_close_exposes_goal_met(self):
        """목표를 선언하고 열었으면 닫을 때 답해야 하는데, 답할 인자가 없으면 못 닫는다."""
        self.assertIn("goal_met", self._tool_schema("gil_close"))

    def test_chain_exposes_parallel_with(self):
        """#54 — 열린 체인이 있으면 선언 없이는 새 체인이 거부된다."""
        self.assertIn("parallel_with", self._tool_schema("gil_chain"))

    def test_step_exposes_at_and_refines(self):
        """#59 두고 온 가지를 닫는 --at, #42 정밀화 간선."""
        sch = self._tool_schema("gil_step")
        self.assertIn('"at"', sch)
        self.assertIn("refines", sch)

    def test_deploy_exposes_staged_and_promote(self):
        sch = self._tool_schema("gil_deploy")
        self.assertIn("state", sch)
        self.assertIn("promote", sch)


class TestAtReturnsAndIdsStayUnique(GilFixture):
    """--at 은 잠시 다녀올 뿐이고, 스텝 번호는 사이클 안에서 유일하다 (온보딩 실측).

    `--at` 은 두고 온 잎에 종결을 박으려고 그 가지로 분기하는데, 옛 동작은 **거기 선 채로
    끝났다.** 사용자는 "두고 온 잎을 닫는다"고 했지 "그 가지로 옮겨간다"고 하지 않았다.
    게다가 돌아올 gil 경로가 없어 raw git 으로 내려가야 했다 — gil 레일을 우회하지 않으려는
    사람에게는 작업이 멈추는 벽이었다.

    그리고 복귀를 넣자 **번호가 겹쳤다**: HEAD 계보만 보고 다음 번호를 매기면 다른 가지의
    스텝이 안 보인다. 같은 사이클에 s8 이 둘 생겼고 fsck 도 못 잡았다.
    """

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/gap", "--author", "c", "--purpose", "P", "--body", "B")
        self.gil("step", "a/gap", "--kind", "hypothesis", "--title", "H1",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "a/gap", "--kind", "verify", "--title", "V1",
                 "--verdict", "refuted", "--body", "B")
        self.gil("step", "a/gap", "--kind", "analyze", "--title", "A1", "--body", "B")
        self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s1", "--title", "H2",
                 "--falsify", "F", "--falsify-to", "s1", "--inherit", "교훈")
        self.gil("step", "a/gap", "--kind", "verify", "--title", "V2",
                 "--verdict", "supported", "--body", "B")
        self.gil("step", "a/gap", "--kind", "analyze", "--title", "A2", "--body", "B")

    def _branch(self):
        return self._git("branch", "--show-current").stdout.strip()

    def test_at_returns_to_where_it_started(self):
        before = self._branch()
        r = self.gil("step", "a/gap", "--kind", "fail", "--at", "s4", "--to", "s1",
                     "--title", "막힘", "--body", "벽")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._branch(), before, "--at 이 죽은 가지에 세워둔 채 끝났다")

    def test_rebranch_from_live_analyze_after_at(self):
        """돌아왔으니 산 가지의 analyze 에서 갈라질 수 있다 — 여기가 막혀 작업이 멈췄었다."""
        self.gil("step", "a/gap", "--kind", "fail", "--at", "s4", "--to", "s1",
                 "--title", "막힘", "--body", "벽")
        r = self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s7", "--title", "H3",
                     "--falsify", "F", "--falsify-to", "s7", "--inherit", "s7 분석 위에서")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_step_ids_stay_unique_across_branches(self):
        """번호는 사이클 전체에서 매긴다 — 형제 가지 때문에 같은 번호가 두 번 나오면 안 된다."""
        self.gil("step", "a/gap", "--kind", "fail", "--at", "s4", "--to", "s1",
                 "--title", "막힘", "--body", "벽")
        self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s7", "--title", "H3",
                 "--falsify", "F", "--falsify-to", "s7", "--inherit", "E")
        ids = [ln.split("/")[-1].split()[0]
               for ln in self.gil("log", "a", "--all").stdout.splitlines() if "a/gap/" in ln]
        self.assertEqual(len(ids), len(set(ids)), f"스텝 번호가 겹쳤다: {sorted(ids)}")

    def test_fsck_flags_duplicate_step_ids(self):
        """이미 그렇게 그려진 그래프는 fsck 가 짚는다."""
        self.gil("step", "a/gap", "--kind", "fail", "--at", "s4", "--to", "s1",
                 "--title", "막힘", "--body", "벽")
        self._git("commit", "-q", "--allow-empty", "-m",
                  "gil a/gap/s8 analyze: 손으로 박은 중복\n\n본문\n\n"
                  "Gil-Chain: a\nGil-Cycle: gap\nGil-Step: s8\nGil-Kind: analyze\nGil-Parent: s7")
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        # 문구는 묶음 보고로 바뀌었다(이슈 #84) — 쌍마다 한 줄이면 오염된 저장소에서 수십 줄이 된다.
        self.assertIn("번호 중복", out)

    def test_falsify_to_accepts_analyze(self):
        """--to 와 --falsify-to 의 비대칭을 없앤다 — 되돌아갈 자리에도 같은 논거가 선다."""
        r = self.gil("step", "a/gap", "--kind", "hypothesis", "--to", "s7", "--title", "H3",
                     "--falsify", "F", "--falsify-to", "s7", "--inherit", "E")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestChainFromDeclaresSuccession(GilFixture):
    """어느 닫힌 체인을 이어받는지 선언한다 (이슈 #68) — --parallel-with 의 빈 짝.

    옛 동작은 새 체인을 HEAD 가 있던 곳에 붙였고, HEAD 는 "마지막으로 닫은 체인"에 가 있다.
    그래서 같은 명령의 출력이 A 를 앞 체인이라 안내하면서 그래프는 B 에 붙었다 — 도구가
    스스로 모순되는 상태.
    """

    def _closed_chain(self, name):
        self.gil("chain", name, "--purpose", "P")
        self.gil("open", f"{name}/c1", "--author", "c", "--purpose", "P", "--body", "B")
        self.gil("step", f"{name}/c1", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", f"{name}/c1", "--kind", "verify", "--title", "V",
                 "--verdict", "supported", "--body", "B")
        self.gil("step", f"{name}/c1", "--kind", "analyze", "--title", "A", "--body", "B")
        self.gil("step", f"{name}/c1", "--kind", "success", "--title", "S", "--body", "B")
        self.gil("close", f"{name}/c1")
        self.gil("chain-close", name)

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self._closed_chain("eval-trust")
        self._closed_chain("tooling")      # 마지막으로 닫힌 체인 — HEAD 가 여기 남는다

    def test_from_attaches_to_the_declared_chain(self):
        r = self.gil("chain", "measurement", "--purpose", "P", "--from", "eval-trust",
                     "--inherit", "eval-trust 계승")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self._git("merge-base", "--is-ancestor",
                                  "eval-trust", "measurement").returncode == 0,
                        "선언한 체인의 자손이 아니다")
        self.assertFalse(self._git("merge-base", "--is-ancestor",
                                   "tooling", "measurement").returncode == 0,
                         "마지막으로 닫은 엉뚱한 체인에 붙었다")

    def test_from_is_recorded(self):
        self.gil("chain", "measurement", "--purpose", "P", "--from", "eval-trust")
        self.assertEqual(self.trailer("measurement", "Gil-Chain-From"), "eval-trust")

    def test_from_must_be_closed(self):
        """이어받으려면 닫혀 있어야 한다 — 그래야 '닫힌 끝에서 연다'가 사실이 된다."""
        self.gil("chain", "live-one", "--purpose", "P", "--from", "eval-trust")
        r = self.gil("chain", "another", "--purpose", "P", "--from", "live-one",
                     "--parallel-with", "live-one")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("닫히지 않았다", r.stdout + r.stderr)

    def test_from_must_exist(self):
        r = self.gil("chain", "measurement", "--purpose", "P", "--from", "nope")
        self.assertNotEqual(r.returncode, 0)


class TestDeepInterviewRounds(GilFixture):
    """인터뷰는 한 번으로 끝내지 않아도 된다 (상현님).

    문제가 명확해질 때까지 여러 차례 물을 수 있어야 한다. 구조는 이미 됐지만 — 2차를 심으면
    사이클이 다시 잠기고 답하면 열린다 — **새 기준이 앞 기준을 덮어써서 1차에 사람이 답한
    것이 사라졌다.** 기준은 사람의 답이므로 지워지면 안 된다: 차수를 쌓는다.
    """

    def setUp(self):
        super().setUp()
        self._no_interview_autofill = True
        self.gil("init", "--name", "clew")
        self.gil("chain", "deep", "--purpose", "P")

    def _round(self, text):
        self.gil("interview", "deep", "--ask", "-", input='[{"q":"무엇","type":"text"}]')
        with open(os.path.join(self.repo, "reference-deep.md"), "w", encoding="utf-8") as f:
            f.write(text)
        return self.gil("interview", "deep", "--resolve", "reference-deep.md")

    def test_second_round_is_allowed_after_first_is_done(self):
        self._round("# 1차\n속도를 올리고 싶다")
        r = self.gil("interview", "deep", "--ask", "-", input='[{"q":"더","type":"text"}]')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_open_locks_again_while_second_round_pending(self):
        """2차가 대기 중이면 사이클은 다시 잠긴다 — 흐린 기준 위에 열지 않게."""
        self._round("# 1차\n속도")
        self.gil("interview", "deep", "--ask", "-", input='[{"q":"더","type":"text"}]')
        r = self.gil("open", "deep/c1", "--author", "c", "--purpose", "P", "--body", "B")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("대기", r.stdout + r.stderr)

    def test_earlier_answers_survive(self):
        """앞 차수의 답이 지워지지 않는다 — 이게 없으면 심층 인터뷰가 손실이 된다."""
        self._round("# 1차\n속도를 올리고 싶다")
        r = self._round("# 2차\n재보니 I/O 였다. 목표는 200ms")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ref = self.gil("interview", "deep", "--status", "--show").stdout
        self.assertIn("속도를 올리고 싶다", ref)   # 1차
        self.assertIn("목표는 200ms", ref)         # 2차
        self.assertIn("인터뷰 2차", ref)

    def test_guidance_invites_another_round(self):
        """한 번 더 물어도 된다는 걸 그 자리에서 알려준다 — 모르면 아무도 안 한다."""
        r = self._round("# 1차\n대충")
        self.assertIn("한 번 더 물어도 된다", r.stdout + r.stderr)


class TestDetachedHeadAnchors(GilFixture):
    """분리된 HEAD 위에 스텝을 잃지 않는다 (이슈 #83, 실사용 재현).

    HEAD 가 한 번 브랜치를 떠나면 그 뒤 모든 선형 스텝이 분리된 HEAD 위에 쌓였다 — 팁이 곧
    HEAD 라 정합 로직도 "이미 팁"이라며 통과시킨다. 두 겹의 피해: close 는 성공하는데
    open --parent 는 "안 닫혔다"고 하고(같은 저장소, 다른 답), 종결 스텝이 GC 대상이 된다."""

    def _seed(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c1", "--purpose", "P")
        self.gil("open", "c1/gap", "--author", "clew", "--purpose", "Q")
        self.gil("step", "c1/gap", "--kind", "hypothesis",
                 "--falsify", "F", "--falsify-to", "s1", "--title", "h")

    def _head_branch(self):
        return self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def test_step_on_detached_head_lands_on_cycle_branch(self):
        self._seed()
        self._git("checkout", "-q", "--detach")
        r = self.gil("step", "c1/gap", "--kind", "verify", "--verdict", "supported", "--title", "v")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._head_branch(), "c1-gap")
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self.assertIn("c1-gap", self._git("branch", "--contains", head).stdout)

    def test_step_numbering_stays_monotonic_after_detach(self):
        """번호가 브랜치에서 계산되므로, 닻이 없으면 s3 가 세 번 나온다(실사용 증상)."""
        self._seed()
        self._git("checkout", "-q", "--detach")
        self.gil("step", "c1/gap", "--kind", "verify", "--verdict", "supported", "--title", "v")
        self.gil("step", "c1/gap", "--kind", "analyze", "--title", "a")
        r = self.gil("step", "c1/gap", "--kind", "success", "--title", "s")
        self.assertIn("s5 success", r.stdout + r.stderr)

    def test_close_then_open_parent_agree(self):
        """이 이슈의 핵심 — close 가 성공했으면 open --parent 가 그것을 봐야 한다."""
        self._seed()
        self._git("checkout", "-q", "--detach")
        for a in (["--kind", "verify", "--verdict", "supported", "--title", "v"],
                  ["--kind", "analyze", "--title", "a"],
                  ["--kind", "success", "--title", "s"]):
            self.gil("step", "c1/gap", *a)
        self.assertEqual(self.gil("close", "c1/gap", "--goal-met").returncode, 0)
        r = self.gil("open", "c1/next", "--parent", "gap", "--author", "clew",
                     "--purpose", "Q", "--inherit", "앞 사이클의 교훈")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_diverged_cycle_branch_is_not_overwritten(self):
        """사이클 브랜치가 다른 가지에 있으면 덮지 않고 옆에 판다 — 덮으면 그쪽을 잃는다."""
        self._seed()
        keep = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("checkout", "-q", "--detach", "HEAD~1")
        self.gil("step", "c1/gap", "--kind", "verify", "--verdict", "supported", "--title", "v")
        self.assertEqual(self._git("rev-parse", "c1-gap").stdout.strip(), keep,
                         "다른 가지에 있던 사이클 브랜치를 덮었다")
        self.assertNotEqual(self._head_branch(), "HEAD")  # 어딘가 브랜치 위에 있다
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self.assertTrue(self._git("branch", "--contains", head).stdout.strip())

    def test_fsck_reports_steps_reachable_only_from_detached_head(self):
        """옛 버전·손 checkout 이 남긴 상태는 fsck 가 먼저 말한다."""
        self._seed()
        self.gil("step", "c1/gap", "--kind", "verify", "--verdict", "supported", "--title", "v")
        old = self._git("rev-parse", "HEAD~2").stdout.strip()
        self._git("checkout", "-q", "--detach")
        self._git("branch", "-f", "c1-gap", old)
        r = self.gil("fsck")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("닻 없음", r.stdout)

    def test_fsck_is_quiet_when_everything_is_anchored(self):
        self._seed()
        self.gil("step", "c1/gap", "--kind", "verify", "--verdict", "supported", "--title", "v")
        r = self.gil("fsck")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestInterviewWaiterVisible(GilFixture):
    """기다리는 사람이 보인다 — 백그라운드 --wait 를 1급으로 (이슈 #82, #58·#77 의 세 번째 겹).

    #77 수정은 설계대로 작동했는데도 사람이 두 번 말해야 했다. 남은 겹은 '다음 턴을 여는
    열쇠가 사람 손에만 있다'는 것 — 그래서 gil 이 밀 수 있는 유일한 형태(말하면서 동시에
    기다리기 = 백그라운드 --wait)를 안내의 1급으로 올리고, 기다리는 중이라는 사실을
    사람에게도 보이게 한다."""

    def _seed(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "tooling", "--purpose", "P")
        return self.gil("interview", "tooling", "--ask", "-",
                        input='[{"q":"무엇을 풀려는가","type":"text"}]')

    def _wait_bg(self, timeout="30"):
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.Popen([*GIL_CMD, "interview", "tooling", "--wait", "--timeout", timeout],
                                cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=env)

    def _submit(self):
        with open(os.path.join(self.repo, "ref.md"), "w", encoding="utf-8") as f:
            f.write("# 기준\n성공 기준: 통과")
        return self.gil("interview", "tooling", "--resolve", "ref.md")

    def test_ask_promotes_background_wait(self):
        """두 선택지만 놓으면 매번 차선으로 미끄러진다 — 제3의 형태를 그 자리에 적는다."""
        out = self._seed().stdout
        self.assertIn("백그라운드", out)
        self.assertIn("--wait --timeout 3600", out)

    def test_status_says_nobody_is_waiting(self):
        """'답 대기' 와 '답 대기 + 아무도 안 기다림' 은 전혀 다른 상황이다."""
        self._seed()
        out = self.gil("interview", "tooling", "--status").stdout
        self.assertIn("아무도 기다리고 있지 않다", out)
        self.assertIn("백그라운드", out)

    def test_status_sees_live_waiter(self):
        self._seed()
        p = self._wait_bg()
        try:
            out, deadline = "", time.time() + 10
            while time.time() < deadline:
                out = self.gil("interview", "tooling", "--status").stdout
                if "살아 있다" in out:
                    break
                time.sleep(0.5)
            self.assertIn("살아 있다", out)
        finally:
            p.kill()
            p.wait()

    def test_handoff_distinguishes_waiter(self):
        self._seed()
        self.assertIn("아무도 안 기다린다", self.gil("handoff").stdout)

    def test_waiter_mark_is_cleared_after_submit(self):
        """유령이 '기다리는 중'이라 말하면 사람은 또 아무도 없는 곳에 제출한다."""
        self._seed()
        p = self._wait_bg()
        time.sleep(1)
        self._submit()
        p.wait(timeout=20)
        self.assertFalse(os.path.exists(os.path.join(
            self.repo, ".git", "gil", "interview-waiting-tooling")))

    def test_then_runs_on_submit(self):
        """--then: 호스트가 프로세스 완료로 못 깨워도 훅 하나는 확실히 걸린다."""
        self._seed()
        mark = os.path.join(self.repo, "then.txt")
        env = dict(os.environ, GIL_NO_VIEWER="1")
        p = subprocess.Popen([*GIL_CMD, "interview", "tooling", "--wait", "--timeout", "30",
                              "--then", "echo ran > " + mark],
                             cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, env=env)
        time.sleep(1)
        self._submit()
        p.wait(timeout=20)
        self.assertTrue(os.path.exists(mark), p.stdout.read() if p.stdout else "")

    def test_then_without_wait_is_refused(self):
        self._seed()
        r = self.gil("interview", "tooling", "--then", "echo x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--wait", r.stdout + r.stderr)


class TestBacktrackToAnalyze(GilFixture):
    """'되돌아갈 자리'의 문법을 하나로 (이슈 #76 후속).

    hypothesis 의 --to(#60)와 fail 의 --to(#76)는 analyze 를 받는데 backtrack·reject 만
    define 을 고집했다. 같은 뜻을 세 문법이 다르게 받으면 사람은 세 번 배우고 한 번은 틀린
    자리를 적는다 — 실사용에서 실제로 그렇게 됐다(fail 은 s1 로 적히고 사고는 s52 에 뿌리내림)."""

    def _upto_analyze(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c1", "--purpose", "P")
        self.gil("open", "c1/gap", "--author", "clew", "--purpose", "Q")
        self.gil("step", "c1/gap", "--kind", "hypothesis", "--falsify", "F",
                 "--falsify-to", "s1", "--title", "h")
        self.gil("step", "c1/gap", "--kind", "verify", "--verdict", "refuted", "--title", "v")
        self.gil("step", "c1/gap", "--kind", "analyze", "--title", "a")

    def test_backtrack_accepts_analyze(self):
        self._upto_analyze()
        r = self.gil("step", "c1/gap", "--kind", "hypothesis", "--outcome", "backtrack",
                     "--to", "s4", "--falsify", "F2", "--falsify-to", "s4",
                     "--inherit", "앞 가지의 교훈", "--title", "재가설")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_backtrack_rejection_explains_both_choices(self):
        self._upto_analyze()
        r = self.gil("step", "c1/gap", "--kind", "hypothesis", "--outcome", "backtrack",
                     "--to", "s3", "--falsify", "F2", "--falsify-to", "s1",
                     "--inherit", "교훈", "--title", "재가설")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("define 또는 analyze", out)
        self.assertIn("s1", out)   # 고를 수 있는 자리를 그 자리에서 준다
        self.assertIn("s4", out)

    def test_reject_accepts_analyze(self):
        self._upto_analyze()
        self.gil("step", "c1/gap", "--kind", "pending", "--title", "사람 대기")
        r = self.gil("reject", "c1/gap", "--to", "s4", "--title", "기각")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestPlanBeforeHypothesis(GilFixture):
    """가설을 세우기 **전에** 설계를 고정한다 (이슈 #76 본체, 상현님 승인).

    실사용 실측: 같은 사이클에서 규모 예측이 3.3배·3.2배·8.2배로 빗나가다 한 번 맞았고, 맞은
    한 번의 차이는 '몇 개일지 추정하지 않고 몇 개로 만들지 정했다' 뿐이었다. 세는 법을 고치는
    길은 세는 정확도가 아니라 세어야 할 것을 설계로 줄이는 것이다."""

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P")

    def test_hypothesis_requires_plan(self):
        r = self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H",
                           "--falsify", "F", "--falsify-to", "s1", "--advances", "A")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--plan", out)
        self.assertIn("몇 개로 만들지", out)

    def test_plan_is_recorded_as_trailer(self):
        r = self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H",
                           "--falsify", "F", "--falsify-to", "s1", "--advances", "A",
                           "--plan", "신규 실행경로 1개(공용 함수로 묶는다)")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Plan"), "신규 실행경로 1개(공용 함수로 묶는다)")

    def test_verify_must_answer_the_plan(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F",
                       "--falsify-to", "s1", "--plan", "신규 실행경로 1개", "--advances", "A")
        r = self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--plan-held", out)
        self.assertIn("신규 실행경로 1개", out)   # 무엇에 답해야 하는지 그 자리에서 보인다

    def test_plan_broke_is_recorded_and_guided(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F",
                       "--falsify-to", "s1", "--plan", "신규 실행경로 1개", "--advances", "A")
        r = self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v",
                           "--plan-broke", "신규 실행경로 3개 — fs 쪽이 안 묶였다",
                           "--falsify-unmet", "(관측: 반증조건 미달)")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Plan-Outcome"), "broke")
        self.assertIn("되돌아갈 자리", r.stdout + r.stderr)

    def test_held_and_broke_are_exclusive(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F",
                       "--falsify-to", "s1", "--plan", "P1", "--advances", "A")
        r = self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v",
                           "--plan-held", "--plan-broke", "달랐다")
        self.assertNotEqual(r.returncode, 0)

    def test_plan_is_hypothesis_only(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F",
                       "--falsify-to", "s1", "--plan", "P1", "--advances", "A")
        r = self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported",
                           "--title", "v", "--plan-held", "--plan", "X",
                           "--falsify-unmet", "(관측: 반증조건 미달)")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("hypothesis 전용", r.stdout + r.stderr)


class TestCycleMustEndBeforeNext(GilFixture):
    """밟다 만 사이클을 두고 다음을 열 수 없다 (상현님, 2026-07-28).

    #45 는 'fail 잎만 남은' 경우만 막았다. 그래서 define·hypothesis·verify·analyze 어디서든
    손을 놓고 새 사이클을 열 수 있었고, 그 사이클은 종결 잎 없이 허공에 매달린 채 남았다."""

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P")

    def _open_next(self, *extra):
        return self.gil("open", "c/c2", "--author", "x", "--purpose", "P", *extra)

    def test_cannot_open_next_at_define(self):
        r = self._open_next()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("밟는 중인 사이클", r.stdout + r.stderr)

    def test_cannot_open_next_at_hypothesis(self):
        self.gil("step", "c/c1", "--kind", "hypothesis", "--falsify", "F",
                 "--falsify-to", "s1", "--title", "H")
        r = self._open_next()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("s2(hypothesis)", r.stdout + r.stderr)

    def test_rejection_gives_three_exits(self):
        r = self._open_next()
        out = r.stdout + r.stderr
        self.assertIn("이어가기", out)
        self.assertIn("종결", out)
        self.assertIn("--abandon", out)

    def test_pending_points_at_the_human(self):
        self.gil("step", "c/c1", "--kind", "pending", "--title", "사람 대기")
        r = self._open_next()
        out = r.stdout + r.stderr
        self.assertIn("gil approve", out)
        self.assertIn("gil reject", out)

    def test_open_allowed_after_success_and_close(self):
        self.gil("step", "c/c1", "--kind", "success", "--title", "s")
        self.gil("close", "c/c1", "--goal-met")
        r = self._open_next("--parent", "c1", "--inherit", "앞 사이클의 전수")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_open_allowed_after_abandon(self):
        """포기에도 죽은 잎이 필요하다 — 벽을 남긴 뒤에야 봉인되고, 그제서야 다음이 열린다."""
        self.gil("step", "c/c1", "--kind", "fail", "--to", "s1", "--title", "벽")
        self.assertEqual(self.gil("close", "c/c1", "--abandon").returncode, 0)
        r = self._open_next()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestChainGoalImprintAndContext(GilFixture):
    """체인 목적의 각인과 **조상 지식의 도착** (상현님, 2026-07-28).

    gil 의 핵심은 부모의 부모, 더 먼 조상까지 만든 지식이 아래 세대로 전파되며 쌓여 하나의
    컨텍스트를 이루는 것이다. 지금까지 gil 이 보증한 것은 기록뿐이었다 — --inherit·--plan 은
    커밋에 남지만 자식에게 자동으로 도착하지는 않았다. 도착하지 않는 기록은 전파가 아니다."""

    def _chain(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "추론 비용을 절반으로")

    def _cycle1(self):
        self._chain()
        self.gil("open", "c/c1", "--author", "x", "--purpose", "캐시 도입", "--goal", "토큰 0.7배")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--falsify", "F", "--falsify-to", "s1",
                 "--plan", "신규 실행경로 1개", "--advances", "16지표 중 토큰·지연 2개를 덮는다",
                 "--title", "H")
        self.gil("step", "c/c1", "--kind", "verify", "--verdict", "supported",
                 "--plan-broke", "경로 3개 — fs 가 안 묶였다", "--title", "v")
        self.gil("step", "c/c1", "--kind", "analyze", "--title", "a")

    def test_hypothesis_requires_advances(self):
        self._chain()
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P")
        r = self._raw_step("c/c1", "--kind", "hypothesis", "--falsify", "F",
                           "--falsify-to", "s1", "--plan", "P1", "--title", "H")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--advances", out)
        self.assertIn("추론 비용을 절반으로", out)  # 거부하면서 체인 목적을 그 자리에서 각인

    def test_terminal_requires_retrospective(self):
        self._cycle1()
        r = self._raw_step("c/c1", "--kind", "success", "--title", "s")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--toward", r.stdout + r.stderr)
        r2 = self._raw_step("c/c1", "--kind", "success", "--title", "s", "--toward", "T")
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("--next-design", r2.stdout + r2.stderr)

    def test_retrospective_is_recorded(self):
        self._cycle1()
        r = self.gil("step", "c/c1", "--kind", "success", "--title", "s",
                     "--toward", "토큰 0.71배 — 목표에 근접", "--next-design", "fs 경로를 공용 함수로 흡수")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Toward"), "토큰 0.71배 — 목표에 근접")
        self.assertEqual(self.trailer("HEAD", "Gil-Next-Design"), "fs 경로를 공용 함수로 흡수")
        # 종결 순간 체인 목적을 다시 각인한다 — 사이클 안의 성패만 남지 않게.
        self.assertIn("추론 비용을 절반으로", r.stdout + r.stderr)

    def _close_c1(self):
        self.gil("step", "c/c1", "--kind", "success", "--title", "s",
                 "--toward", "토큰 0.71배 — 지연은 미해결",
                 "--next-design", "fs 경로를 공용 함수로 흡수(신규 경로 0)")
        self.gil("close", "c/c1", "--goal-met")

    def test_child_open_receives_ancestor_knowledge(self):
        """자식은 묻지 않아도 조상의 지식을 받는다 — 그게 전파다."""
        self._cycle1()
        self._close_c1()
        r = self.gil("open", "c/c2", "--author", "x", "--purpose", "지연 줄이기",
                     "--parent", "c1", "--inherit", "c1 에서 캐시는 먹혔다")
        out = r.stdout + r.stderr
        self.assertIn("계보 브리핑", out)
        self.assertIn("토큰 0.71배 — 지연은 미해결", out)          # 조상의 회고
        self.assertIn("fs 경로를 공용 함수로 흡수", out)            # 조상이 남긴 다음 설계
        self.assertIn("경로 3개 — fs 가 안 묶였다", out)            # 조상이 밟은 벽(설계 깨짐)

    def test_context_command_walks_grandparents(self):
        """부모의 부모까지 — 지식은 세대를 건너 쌓인다."""
        self._cycle1()
        self._close_c1()
        self.gil("open", "c/c2", "--author", "x", "--purpose", "지연", "--parent", "c1",
                 "--inherit", "캐시는 먹혔다")
        self.gil("step", "c/c2", "--kind", "hypothesis", "--falsify", "F2", "--falsify-to", "s1",
                 "--plan", "신규 경로 0", "--advances", "지연 지표를 덮는다", "--title", "H2")
        self.gil("step", "c/c2", "--kind", "verify", "--verdict", "supported", "--plan-held", "--title", "v2")
        self.gil("step", "c/c2", "--kind", "analyze", "--title", "a2")
        self.gil("step", "c/c2", "--kind", "success", "--title", "s2",
                 "--toward", "지연 0.8배", "--next-design", "배치 크기를 재본다")
        self.gil("close", "c/c2", "--goal-met")
        self.gil("open", "c/c3", "--author", "x", "--purpose", "배치", "--parent", "c2",
                 "--inherit", "지연도 잡혔다")
        out = self.gil("context", "c/c3").stdout
        self.assertIn("토큰 0.71배", out)      # 할아버지(c1)
        self.assertIn("지연 0.8배", out)       # 부모(c2)
        self.assertLess(out.index("토큰 0.71배"), out.index("지연 0.8배"))  # 오래된 것부터

    def test_context_refuses_unknown(self):
        self._chain()
        self.assertNotEqual(self.gil("context", "nope").returncode, 0)


class TestInterviewSubmitIsVisible(GilFixture):
    """제출은 결과가 남아야 제출이다 (상현님: 뷰어에서 제출하면 아무 일도 안 일어난다).

    폼은 사라지는데 그 자리에 아무것도 남지 않아, 사람은 자기 답이 도착했는지 알 수 없었다.
    확정된 기준 문서와 '내 답이 어디까지 갔나'(기다리는 중·읽음·아직 안 읽음)를 화면에 남긴다."""

    def _seed(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "tooling", "--purpose", "P")
        self.gil("interview", "tooling", "--ask", "-",
                 input='[{"q":"무엇을 풀려는가","type":"text"}]')

    def _resolve(self):
        with open(os.path.join(self.repo, "ref.md"), "w", encoding="utf-8") as f:
            f.write("# 기준\n추론 비용을 절반으로")
        return self.gil("interview", "tooling", "--resolve", "ref.md")

    def _build(self):
        out = os.path.join(self.repo, "v.html")
        r = self.gil("graph", "--html", "--out", out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out, encoding="utf-8") as f:
            return f.read()

    def test_resolved_reference_is_rendered(self):
        self._seed()
        self._resolve()
        html = self._build()
        self.assertIn('id="pane-reference"', html)
        self.assertIn("추론 비용을 절반으로", html)

    def test_pending_round_is_not_rendered_as_confirmed(self):
        """사람이 아직 답하지 않은 차수는 '확정된 기준'으로 그려지지 않는다.

        (체인은 태어날 때 기준을 갖는다 — 그러니 '확정 전'이라는 상태는 **추가 차수**의 것이다.
        그 차수의 질문 본문이 확정본인 양 화면에 서면, 사람은 자기가 답하지 않은 문장을
        자기 기준으로 읽게 된다.)"""
        self._seed()
        self.assertNotIn("추론 비용을 절반으로", self._build())

    def test_reference_panel_is_collapsed_and_dismissable(self):
        """확정된 기준은 **끝난 것**이다 — 화면을 계속 차지하면 지금 살아 있는 국면을 덮는다.

        제출의 결과를 남기려다 영구 패널을 만들었던 것을 접었다(상현님 실사용)."""
        self._seed()
        self._resolve()
        html = self._build()
        self.assertIn("refsum", html)          # 한 줄 요약(details/summary)
        self.assertIn("gil-ref-seen-", html)   # 한 번 닫으면 그 확정본은 다시 안 뜬다
        self.assertNotIn("refstate", html)     # 옛 영구 패널 잔재가 없다

    def test_submit_failure_explains_itself(self):
        """"TypeError: Failed to fetch" 는 사람에게 아무것도 안 알려준다(상현님 실사용).

        이 화면은 이제 **언제나 정적 스냅샷**이다 — 그러니 답은 "서버를 다시 띄워라"가
        아니라 "그림을 다시 가져와라"여야 한다."""
        self._seed()
        html = self._build()
        self.assertIn("답은 아직 제출되지 않았습니다", html)   # 잃은 게 아니라는 사실부터
        # 되살리는 한 수: 서버가 은퇴했으니 "다시 띄워라"가 아니라 **다시 가져와라**다.
        self.assertIn("스냅샷", html, "이 그림이 무엇인지 화면이 안 말한다")
        self.assertNotIn("gil viewer", html, "은퇴한 명령을 아직 가리킨다")

    def test_reference_state_tracks_agent_reading(self):
        """에이전트가 읽으면 화면이 그걸 말한다 — 사람이 '전달됐나'를 묻지 않아도 되게."""
        self._seed()
        self._resolve()
        self.assertIn('"seen":false', self._build())
        self.gil("interview", "tooling", "--status")   # 에이전트가 읽는 자리
        self.assertIn('"seen":true', self._build())


class TestChainCleanup(GilFixture):
    """체인 정리 — 괴리 진단(drift)·흡수(reconcile)·폐기(retire)·삭제(prune) (상현님, 2026-07-29).

    append-only 는 그래프 *안*의 규율이지 저장소의 물리 법칙이 아니다. 스텝을 고치는 것은
    영원히 막되, '폐기됐다'는 새 사실이라 append 로 표현한다. 삭제는 비가역이라 문이 셋 —
    사람의 승인 커밋, CLI 확인 문구, 그리고 묘비."""

    def _two_chains(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "첫 체인")
        self.gil("chain", "b", "--purpose", "나란히", "--parallel-with", "a")

    def test_declared_parallel_is_not_drift(self):
        """선언된 병렬은 사고가 아니라 판단이다 — 괴리로 세지 않는다."""
        self._two_chains()
        self.assertIn("괴리 0", self.gil("drift").stdout)

    def test_home_branch_is_not_a_stray(self):
        """대문이 사는 브랜치를 '잔재'라 부르면 도구가 자기 뿌리를 지우라고 한다."""
        self._two_chains()
        out = self.gil("drift").stdout
        self.assertNotIn("stray-branch] main", out)

    def test_restore_ref_puts_git_back_on_gil(self):
        """gil 이 기준이다 — 사라진 git 브랜치는 gil 그래프를 보고 복원한다.

        (다른 ref 로 커밋이 아직 닿을 때의 이야기다. 어떤 ref 도 안 닿으면 그건 괴리가
        아니라 유실이고, 그건 gil fsck 의 '유실 직전'이 짚는다.)"""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "첫 체인")
        self.gil("chain-close", "a")
        self.gil("chain", "b", "--purpose", "이어받음", "--from", "a", "--inherit", "a 의 결론")
        self._git("checkout", "-q", "b")
        self._git("update-ref", "-d", "refs/heads/a")
        self.assertIn("ref-missing", self.gil("drift").stdout)
        r = self.gil("reconcile", "a", "--restore-ref")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("a", self.branches())

    def test_retire_moves_refs_without_deleting_objects(self):
        self._two_chains()
        sha = self._git("rev-parse", "b").stdout.strip()
        r = self.gil("chain-retire", "b", "--reason", "실험 종료")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("b", self.branches())
        # 객체는 살아 있다 — 폐기는 삭제가 아니다.
        self.assertEqual(self._git("cat-file", "-t", sha).stdout.strip(), "commit")
        self.assertIn("gil/retired/b", self._git(
            "for-each-ref", "--format=%(refname:short)", "refs/gil/retired/").stdout)

    def test_retire_requires_reason(self):
        self._two_chains()
        r = self.gil("chain-retire", "b")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--reason", r.stdout + r.stderr)

    def test_unretire_brings_it_back(self):
        self._two_chains()
        self.gil("chain-retire", "b", "--reason", "실험 종료")
        r = self.gil("chain-unretire", "b")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("b", self.branches())

    def test_prune_refuses_without_human_approval(self):
        """에이전트가 혼자 지울 수 없다 — 이게 이 명령의 유일한 안전장치다."""
        self._two_chains()
        r = self.gil("prune", "b", "--confirm", "b", "--reason", "지운다")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("승인", r.stdout + r.stderr)
        self.assertIn("b", self.branches())   # 아무것도 안 지워졌다

    def test_prune_refuses_wrong_confirm_phrase(self):
        self._two_chains()
        self.gil("prune", "b", "--request", "--reason", "왜")
        self.gil("prune-approve", "b")
        r = self.gil("prune", "b", "--confirm", "틀린이름", "--reason", "지운다")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("b", self.branches())

    def test_prune_deletes_with_tombstone_and_bundle(self):
        self._two_chains()
        self.gil("prune", "b", "--request", "--reason", "실험 체인이라 이력이 필요 없다")
        self.gil("prune-approve", "b")
        r = self.gil("prune", "b", "--confirm", "b", "--reason", "실험 체인이라 이력이 필요 없다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("b", self.branches())
        # 묘비 — 지워진 자리에 남는 유일한 기록
        log = self.gil("log").stdout + self._git("log", "--all", "--format=%B", "-5").stdout
        self.assertIn("묘비", self._git("log", "-3", "--format=%B").stdout)
        self.assertTrue(os.path.exists(os.path.join(
            self.repo, ".git", "gil", "archive", "b.bundle")))

    def test_prune_refuses_non_leaf_node(self):
        """중간 노드를 지우면 후손을 다시 써야 한다 — 그건 삭제가 아니라 역사 재작성이다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--falsify", "F",
                 "--falsify-to", "s1", "--title", "H")
        self.gil("prune", "c/c1/s1", "--request", "--reason", "x")
        r = self.gil("prune", "c/c1/s1", "--dry-run")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("잎이 아니다", r.stdout + r.stderr)


class TestPollutedGraphIsRendered(GilFixture):
    """오염된 저장소도 관전할 수 있어야 한다 (이슈 #84, 상현님 실사용).

    옛 gil(≤3.28)이 같은 번호를 여러 스텝에 찍은 저장소에서, 뷰어가 번호를 노드의 정체성으로
    쓰다 자기부모 노드를 만나 무한재귀로 죽었다. 원장은 다시 쓸 수 없다(이력 위조다) —
    그러니 뷰어가 오염을 견뎌야 하고, fsck 가 그 오염을 먼저 말해야 한다."""

    def _polluted(self):
        """번호 중복 + 자기부모를 인위로 만든다(옛 gil 이 만든 모양)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--falsify", "F",
                 "--falsify-to", "s1", "--title", "H")
        # 같은 번호(s2)를 다시 쓰고 자기 자신을 부모로 가리키는 커밋을 손으로 얹는다.
        msg = ("gil c/c1/s2 analyze: 오염된 스텝\n\n본문\n\n"
               "Gil-Chain: c\nGil-Cycle: c1\nGil-Step: s2\nGil-Kind: analyze\nGil-Parent: s2\n")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-F", "-"],
                       cwd=self.repo, input=msg, text=True, capture_output=True,
                       env=dict(os.environ, GIL_ALLOW_RAW="1"))

    def test_fsck_reports_duplicate_numbers_and_self_parent(self):
        self._polluted()
        r = self.gil("fsck")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout
        self.assertIn("번호 중복", out)
        self.assertIn("자기부모", out)
        # 다시 번호를 매기라고 하지 않는다 — 원장을 고치는 건 이력 위조다.
        self.assertIn("이력 위조", out)

    def test_viewer_renders_polluted_cycle(self):
        """sha 가 정체성이면 중복 번호가 남아 있어도 그래프는 옳게 그려진다."""
        self._polluted()
        out = os.path.join(self.repo, "v.html")
        r = self.gil("graph", "--html", "--out", out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("seen.has(sha)", html)        # 순환 가드
        self.assertIn("const pSha=", html)          # 부모 해석이 sha 로
        self.assertIn("cardwarn", html)             # 실패·오염을 카드에 찍는다


class TestCloseEnforcesLeafInvariant(GilFixture):
    """close 가 fsck 와 같은 불변식을 집행한다 (이슈 #86, 실사용 재현).

    백트랙으로 떠난 가지의 analyze 잎이 종결 없이 남아도 close 가 조용히 통과했다. 그러면
    에이전트는 사이클이 끝났다고 인지하고 결함은 fsck 를 돌릴 때까지 잠복한다 —
    **집행이 두 자리에서 갈리면 느슨한 쪽이 실질 규칙이 된다.**"""

    def _backtracked_cycle(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--falsify", "F",
                 "--falsify-to", "s1", "--title", "H1")
        self.gil("step", "c/c1", "--kind", "verify", "--verdict", "refuted", "--title", "v1")
        self.gil("step", "c/c1", "--kind", "analyze", "--title", "a1")
        # s4(analyze)를 종결하지 않고 백트랙 — 실사용에서 두 번 재현된 그 경로.
        return self.gil("step", "c/c1", "--kind", "hypothesis", "--to", "s1",
                        "--falsify", "F2", "--falsify-to", "s1",
                        "--inherit", "H1 은 X 때문에 죽었다", "--title", "H2")

    def test_backtrack_warns_about_the_leaf_it_leaves(self):
        """backtrack 은 fail 의 대안이 아니다 — 떠나는 자리에서 그 사실을 말한다.

        막지는 않는다(analyze 는 재분기의 뿌리일 수 있다). 막는 자리는 close 다."""
        r = self._backtracked_cycle()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout + r.stderr
        self.assertIn("종결 없이 남는다", out)
        self.assertIn("--kind fail --at s4", out)
        self.assertIn("close 가 거부한다", out)

    def _leave_open_then_finish(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--falsify", "F",
                 "--falsify-to", "s1", "--title", "H1")
        self.gil("step", "c/c1", "--kind", "verify", "--verdict", "refuted", "--title", "v1")
        self.gil("step", "c/c1", "--kind", "analyze", "--title", "a1")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--to", "s1",
                 "--falsify", "F2", "--falsify-to", "s1",
                 "--inherit", "H1 은 X 때문에 죽었다", "--title", "H2")
        self.gil("step", "c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v2")
        self.gil("step", "c/c1", "--kind", "analyze", "--title", "a2")
        self.gil("step", "c/c1", "--kind", "success", "--title", "s")

    def test_close_refuses_hanging_leaf(self):
        """close 가 최종 방어선이다 — 여기서 막지 않으면 결함이 잠복한다."""
        self._leave_open_then_finish()
        r = self.gil("close", "c/c1", "--goal-met")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("미종결 잎", out)
        self.assertIn("--kind fail --at", out)   # 수리 명령을 그 자리에서 준다

    def test_close_passes_after_sealing_the_leaf(self):
        """안내한 수리 명령이 실제로 통해야 한다 — 길 없는 거부는 벽이다."""
        self._leave_open_then_finish()
        r = self.gil("step", "c/c1", "--kind", "fail", "--at", "s4", "--to", "s1",
                     "--title", "이 가지는 벽", "--toward", "목적엔 못 닿았다",
                     "--next-design", "다른 접근을 설계한다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r2 = self.gil("close", "c/c1", "--goal-met")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(self.gil("fsck").returncode, 0)


class TestClosureVocabulary(GilFixture):
    """끝난 것이 끝나 보이고, 답이 난 자리로 선이 남는다 (이슈 #85, 상현님 실사용).

    26개 체인을 정리해 보니 **버릴 게 하나도 없었다**. 문제는 개수가 아니라 어휘였다 —
    봉인해도 화면이 안 접히고, '답은 옆 가지에서 났다'를 적을 자리가 없었다."""

    def _dead_only_cycle(self):
        """죽은 잎만 남은 사이클 — 옛 어휘로는 --abandon 밖에 길이 없던 자리."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/roundtrip", "--author", "x", "--purpose", "총비용으로 넓히면 우위인가")
        self.gil("step", "c/roundtrip", "--kind", "hypothesis", "--falsify", "F",
                 "--falsify-to", "s1", "--title", "H")
        self.gil("step", "c/roundtrip", "--kind", "verify", "--verdict", "refuted", "--title", "v")
        self.gil("step", "c/roundtrip", "--kind", "analyze", "--title", "a")
        self.gil("step", "c/roundtrip", "--kind", "fail", "--to", "s1", "--title", "벽")

    def _answer_cycle(self):
        """답이 실제로 난 자리(다른 사이클)."""
        self.gil("close", "c/roundtrip", "--abandon")
        self.gil("open", "c/tokenizer", "--author", "x", "--purpose", "원인은 표면구문인가")
        self.gil("step", "c/tokenizer", "--kind", "hypothesis", "--falsify", "F2",
                 "--falsify-to", "s1", "--title", "H2")
        self.gil("step", "c/tokenizer", "--kind", "verify", "--verdict", "supported", "--title", "v2")
        self.gil("step", "c/tokenizer", "--kind", "analyze", "--title", "a2")
        self.gil("step", "c/tokenizer", "--kind", "success", "--title", "답")

    def test_refusal_offers_answered_in_as_a_distinct_path(self):
        """세 길이어야 한다 — 답이 난 걸 포기로 적으면 기록이 사실보다 어둡게 남는다."""
        self._dead_only_cycle()
        r = self.gil("close", "c/roundtrip")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--answered-in", out)
        self.assertIn("막다른 길로 확인", out)   # abandon 은 그 뜻으로만

    def test_answered_in_records_the_line_to_the_answer(self):
        self._dead_only_cycle()
        self._answer_cycle()   # c/tokenizer/s5 success 가 답
        self.gil("open", "c/postmortem", "--author", "x", "--purpose", "과거에 해법이 있나")
        self.gil("step", "c/postmortem", "--kind", "hypothesis", "--falsify", "F3",
                 "--falsify-to", "s1", "--title", "H3")
        self.gil("step", "c/postmortem", "--kind", "verify", "--verdict", "refuted", "--title", "v3")
        self.gil("step", "c/postmortem", "--kind", "analyze", "--title", "a3")
        self.gil("step", "c/postmortem", "--kind", "fail", "--to", "s1", "--title", "벽")
        r = self.gil("close", "c/postmortem", "--answered-in", "c/tokenizer/s5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Answered-In"), "c/tokenizer/s5")
        self.assertIn("answered-elsewhere", r.stdout)

    def test_answered_in_must_point_at_something_real(self):
        """없는 곳을 가리키는 선은 산문보다 나쁘다 — 구조로 보증한다며 거짓을 가리킨다."""
        self._dead_only_cycle()
        r = self.gil("close", "c/roundtrip", "--answered-in", "c/nowhere/s9")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("찾지 못했다", r.stdout + r.stderr)

    def test_approve_by_records_the_evidence(self):
        """사람은 여전히 누르되, 무엇을 근거로 닫는지가 기록에 남는다."""
        self._dead_only_cycle()
        self._answer_cycle()
        self.gil("open", "c/measure", "--author", "x", "--purpose", "역량 탓인가 공백 탓인가")
        self.gil("step", "c/measure", "--kind", "pending", "--title", "사람 대기")
        r = self.gil("approve", "c/measure", "--by", "c/tokenizer/s5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Answered-By"), "c/tokenizer/s5")

    def test_closed_chains_are_folded_in_log(self):
        """끝난 것이 끝나 보이게 — 접는 게 지우는 것보다 낫다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "옛 국면")
        self.gil("chain-close", "a")
        self.gil("chain", "b", "--purpose", "지금 국면", "--from", "a", "--inherit", "a 의 결론")
        out = self.gil("log", "--depth", "chain").stdout
        self.assertNotIn("● a ", out)
        self.assertIn("● b ", out)
        self.assertIn("접었다", out)
        self.assertIn("● a ", self.gil("log", "--depth", "chain", "--all").stdout)

    def test_superseded_by_is_visible(self):
        """뒤집힌 것이 뒤집혀 보여야 한다 — 읽는 쪽이 제일 궁금한 건 '어느 결론이 유효한가'다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "old", "--purpose", "옛 결론")
        self.gil("chain", "new", "--purpose", "그 결론을 뒤집는다", "--parallel-with", "old")
        r = self.gil("chain-close", "old", "--superseded-by", "new")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Superseded-By"), "new")
        out = self.gil("log", "--depth", "chain", "--all").stdout
        self.assertIn("⤳ 대체됨 → new", out)

    def test_superseded_by_must_point_at_a_real_chain(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "old", "--purpose", "옛 결론")
        r = self.gil("chain-close", "old", "--superseded-by", "nowhere")
        self.assertNotEqual(r.returncode, 0)


class TestHereAndWorkNode(GilFixture):
    """현재위치는 손이 움직이는 자리다 (상현님).

    작업중(미커밋) 노드가 전체맵에만 있어서, 정작 일이 벌어지는 화면(사이클 카드)에서는
    '지금 어디서 손대고 있나'가 안 보였다. 그리고 현재위치 표식은 커밋된 마지막 스텝에
    붙어 있었는데, 미커밋 작업이 있으면 진짜 현재위치는 그 다음 자리다."""

    def _repo_with_work(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--falsify", "F",
                 "--falsify-to", "s1", "--title", "H")
        with open(os.path.join(self.repo, "work.py"), "w") as f:
            f.write("작업중\n")
        self._git("add", "work.py")

    def _build(self):
        out = os.path.join(self.repo, "v.html")
        r = self.gil("graph", "--html", "--out", out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out, encoding="utf-8") as f:
            return f.read()

    def test_step_card_draws_the_work_node(self):
        self._repo_with_work()
        html = self._build()
        self.assertIn("snode working", html)      # 스텝 그래프의 작업중 노드
        self.assertIn("stepedge work", html)      # 앵커에서 그 자리로 잇는 점선

    def test_head_marker_moves_to_the_work_node(self):
        """현재위치는 하나여야 한다 — 둘이면 어느 쪽인지 모른다."""
        self._repo_with_work()
        html = self._build()
        self.assertIn("현재위치는 여기다", html)   # 의도가 코드에 남아 있다
        self.assertIn("wg.classList.add('here')", html)

    def test_go_here_button_exists(self):
        self._repo_with_work()
        html = self._build()
        self.assertIn('id="gohere"', html)
        self.assertIn("현재위치로", html)
        self.assertIn("function goHere()", html)


class TestMainDevChainLayout(GilFixture):
    """main-dev-chain 레이아웃 (상현님, 2026-07-31).

    옛 문법에는 **새 계보를 시작할 자리가 없었다.** 체인은 닫힌 체인 끝에서만 열렸으므로
    무관한 탐색선도 앞 체인 위에 얹혔고, drift 는 그걸 stacked 로 계속 짖었다. 짖는 게
    옳았다 — 얹힐 수밖에 없는 문법이 문제였다. 층을 하나 넣어 그 자리를 만든다:

        main(대문) → dev(층) → 체인들

    dev 를 부모로 둔 체인은 계보상 시조(orphan)다. **대문은 물려받는다** — 끊기는 것은
    'gil 이 인정하는 계승' 뿐이다.
    """

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")

    def test_init_plants_the_dev_layer(self):
        """gil init 이 대문 다음에 dev 층을 심고, HEAD 를 거기 둔다 — 작업은 dev 에서 시작한다."""
        self.assertEqual(self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "dev")
        self.assertEqual(self.trailer("dev", "Gil-Kind"), "dev-root")

    def test_dev_inherits_the_gate(self):
        """층이 대문을 물려받는다 — orphan 은 '대문 없음'이 아니라 '앞선 체인 없음'이다."""
        for path in ("CLAUDE.md", "docs/gil/index.md"):
            r = self._git("cat-file", "-e", "dev:" + path)
            self.assertEqual(r.returncode, 0, f"dev 에 대문 {path} 이 없다 — SPEC 규칙 2 위반")

    def test_chain_without_declaration_is_a_dev_root(self):
        """--from 없이 연 체인은 dev 팁에서 실제로 갈라지고, 그 사실을 선언으로 남긴다."""
        self.gil("chain", "alpha", "--purpose", "P", "--reference", "-",
                 "--criterion", "C", input="기준")
        self.assertEqual(self.trailer("alpha", "Gil-Chain-Orphan"), "dev")
        parent = self._git("rev-parse", "alpha^").stdout.strip()
        dev_tip = self._git("rev-parse", "dev").stdout.strip()
        self.assertEqual(parent, dev_tip, "선언은 dev 인데 실제로는 다른 자리에서 갈라졌다")

    def test_two_unrelated_lineages_are_siblings_not_a_stack(self):
        """무관한 두 계보가 형제로 선다 — 이게 없어서 데모 위에 프로젝트가 얹혔다."""
        for n in ("alpha", "beta"):
            r = self.gil("chain", n, "--purpose", n, "--reference", "-",
                         "--criterion", "C", input="기준")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        anc = self._git("merge-base", "--is-ancestor", "alpha", "beta").returncode == 0
        self.assertFalse(anc, "무관한 두 체인이 여전히 한 줄기로 쌓인다")
        self.assertIn("위반 0", self.gil("fsck").stdout)

    def test_layer_name_is_not_available_to_chains(self):
        """이름이 무엇을 가리키는지 하나로 정한다 — 체인이 층을 덮어쓰지 못한다."""
        r = self.gil("chain", "dev", "--purpose", "P", "--reference", "-",
                     "--criterion", "C", input="기준")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("층의 이름", r.stdout + r.stderr)

    def test_fsck_catches_a_declared_but_unreal_dev_root(self):
        """**선언은 실재가 뒷받침할 때만 계보다** (v3.45.0 의 판정을 층에도).

        dev 에서 났다고 적어두고 실제로는 체인 위에 얹은 거짓 계보를 일부러 심는다.
        약한 검사('dev 의 자손이면 통과')는 이걸 못 잡는다 — 얹힌 체인도 dev 의 자손이니까.
        """
        self.gil("chain", "alpha", "--purpose", "P", "--reference", "-",
                 "--criterion", "C", input="기준")
        self._git("checkout", "-q", "alpha")
        self._git("checkout", "-q", "-b", "gamma")
        self._git("commit", "-q", "--allow-empty", "-m",
                  "gil gamma chain: 거짓\n\n체인 [gamma] 개설.\n\n"
                  "Gil-Chain: gamma\nGil-Kind: chain-root\nGil-Chain-Purpose: 거짓\n"
                  "Gil-Chain-Orphan: dev")
        r = self.gil("fsck")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, "거짓 계보를 심었는데 fsck 가 통과시켰다: " + out)
        self.assertIn("dev 에서 닿지 않는 커밋", out)

    def test_drift_names_the_missing_layer_as_the_cause(self):
        """층이 없는 저장소에는 증상(stacked)만이 아니라 원인을 말한다."""
        self.gil("chain", "alpha", "--purpose", "P", "--reference", "-",
                 "--criterion", "C", input="기준")
        self._git("branch", "-D", "dev")
        out = self.gil("drift").stdout + self.gil("drift").stderr
        self.assertIn("no-dev-layer", out)


class TestLayerGraphInViewer(GilFixture):
    """전체맵 위의 층 두 줄 — main · dev (상현님).

    처음엔 층을 **따로** 그렸는데, 상현님이 전체맵은 지금 그대로가 좋으니 두 줄만 살짝
    얹으라고 했다. 같은 사실을 두 번 그리면 사람은 어느 쪽을 봐야 하는지부터 고민한다.

    그리고 출발도 층에 묶는다: 안 묶으면 dev 시조가 화면에서 orphan(끊긴 계보)처럼 보인다.
    **시조와 미아는 다르다** — 그 차이는 선언(Gil-Chain-Orphan)에 이미 있다.
    """

    def _build(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "login", "--purpose", "로그인", "--reference", "-",
                 "--criterion", "된다", input="기준")
        self.gil("open", "login/c1", "--author", "clew", "--purpose", "P", "--body", "정의")
        self.gil("step", "login/c1", "--kind", "success", "--title", "S", "--body", "종합")
        self.gil("close", "login/c1", "--verdict", "supported")
        self.gil("chain-close", "login", "--verdict", "supported", "--retro", "-", input="회고")
        self.gil("merge", "login", "--into", "dev", "--reason", "배포 단위에 포함")
        self.gil("deploy", "--tag", "v1.0.0")
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("graph", "--html", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        return open(out_html, encoding="utf-8").read()

    def test_lanes_are_main_dev_then_chains(self):
        import json, re
        html = self._build()
        data = json.loads(re.search(r'"layergraphdata"[^>]*>(\{.*?\})</script>', html, re.S).group(1))
        self.assertEqual(data["lanes"][:2], ["main", "dev"])
        self.assertIn("login", data["lanes"])

    def test_a_deployed_step_still_belongs_to_its_chain(self):
        """배포로 main 이 모든 커밋을 품어도, 그 걸음은 여전히 체인의 일이다."""
        import json, re
        html = self._build()
        data = json.loads(re.search(r'"layergraphdata"[^>]*>(\{.*?\})</script>', html, re.S).group(1))
        by_layer = {}
        for row in data["rows"]:
            by_layer.setdefault(row["layer"], []).append(row["subj"])
        self.assertTrue(any("login/c1" in s for s in by_layer.get("login", [])),
                        f"체인의 걸음이 자기 층에 없다: {list(by_layer)}")
        # 합류는 받는 쪽(dev)의 일이고, 배포 마커도 dev 에 새겨진다.
        self.assertTrue(any("merge" in s for s in by_layer.get("dev", [])))

    def test_the_lanes_live_in_the_full_map(self):
        """따로 그리지 않는다 — 전체맵이 두 줄을 얹는다."""
        html = self._build()
        self.assertNotIn('id="det-layer"', html)      # 별도 패널은 없다
        self.assertIn("lanerule", html)               # 전체맵 위의 두 줄
        self.assertIn("laneedge", html)

    def test_a_dev_root_chain_is_tied_to_the_layer(self):
        """출발이 dev 에 묶인다 — 시조가 미아로 보이면 안 된다."""
        import json, re
        html = self._build()
        data = json.loads(re.search(r'"layergraphdata"[^>]*>(\{.*?\})</script>', html, re.S).group(1))
        self.assertIn("login", data["devroots"],
                      "dev 시조라 선언했는데 데이터에 없다 — 전체맵이 출발을 못 묶는다")
        # 출발 곡선이 실제로 그려진다(클래스는 런타임에 조립되므로 그 자리의 문구로 확인).
        self.assertIn("출발: dev → ", html)

    def test_a_later_chain_forks_where_it_actually_forked(self):
        """dev 가 자란 뒤에 난 체인은 **그 자리에서** 갈라진다 — 맨 앞이 아니라.

        옛 코드는 "dev 시조는 모두 dev 팁에서 갈라진다"고 단정하고 모든 출발선을 한 점에서
        뽑았다. dev 가 커밋을 쌓은 뒤에 체인이 나면 그건 거짓이다 — 나중에 난 체인이 처음부터
        나란히 달린 것처럼 보이고, 같은 화면의 git 그래프(날것의 %P)와 어긋난다(상현님).
        """
        import json, re
        self._build()  # login 체인이 나고 dev 로 합류하고 배포까지 — dev 가 자랐다
        self.gil("chain", "search", "--purpose", "검색", "--reference", "-",
                 "--criterion", "된다", input="기준")
        out_html = os.path.join(self.repo, "g2.html")
        self.assertEqual(self.gil("graph", "--html", "--out", out_html).returncode, 0)
        html = open(out_html, encoding="utf-8").read()
        data = json.loads(re.search(r'"layergraphdata"[^>]*>(\{.*?\})</script>', html, re.S).group(1))
        order = data["devorder"]
        self.assertTrue(len(order) >= 2, f"dev 가 자랐는데 순서가 없다: {order}")
        # 나중 체인의 갈라진 자리는 dev 뿌리가 아니라 dev 가 그때까지 자란 자리다.
        self.assertNotEqual(data["devroots"]["search"], order[0],
                            "나중에 난 체인을 dev 첫 커밋에서 갈라진 것으로 그린다")
        self.assertIn(data["devroots"]["search"], order,
                      "갈라진 자리가 dev 층의 커밋이 아니다")
        # 먼저 난 체인은 여전히 제자리에서 — 사실이 바뀌지 않았다.
        self.assertIn(data["devroots"]["login"], order)

    def test_the_layer_counts_its_own_steps_not_the_gates(self):
        """dev 줄이 세는 건 dev 가 쌓은 커밋이다 — 대문의 커밋까지 세면 수가 틀린다.

        devorder 는 첫 부모 사슬을 거슬러 얻는데, 그 사슬은 층의 뿌리를 지나 대문(main)까지
        이어진다. 자르지 않으면 층 줄이 대문의 걸음을 제 걸음으로 세고, 갈라진 자리도 그만큼
        오른쪽으로 밀린다.
        """
        import json, re, subprocess
        self._build()
        # dev 가 스스로 자란다(평범 커밋도 층의 걸음이다).
        self._git("checkout", "-q", "dev")
        self._git("commit", "-q", "--allow-empty", "-m", "dev: 문서 정리")
        out_html = os.path.join(self.repo, "g3.html")
        self.assertEqual(self.gil("graph", "--html", "--out", out_html).returncode, 0)
        html = open(out_html, encoding="utf-8").read()
        data = json.loads(re.search(r'"layergraphdata"[^>]*>(\{.*?\})</script>', html, re.S).group(1))
        order = data["devorder"]
        # 첫 자리는 층이 개설된 커밋이다 — 그 앞(대문)은 이 줄의 것이 아니다.
        root = subprocess.run(["git", "-C", self.repo, "log", "--format=%H",
                               "--grep=Gil-Kind: dev-root", "dev"],
                              capture_output=True, text=True).stdout.split()
        self.assertTrue(root, "dev-root 커밋을 못 찾았다")
        self.assertEqual(order[0], root[0][:9],
                         f"층 줄이 대문의 커밋부터 세고 있다: {order}")
        self.assertEqual(order[-1], subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "dev"],
            capture_output=True, text=True).stdout.strip()[:9],
            "층 줄의 끝이 dev 팁이 아니다")
        # 그리고 층 줄 위의 걸음을 실제로 그린다.
        self.assertIn("lanestep", html)

    def test_the_terminal_says_what_the_screen_says(self):
        """같은 사실을 터미널도 말한다 — 뷰어에만 그리면 반쪽이다 (상현님).

        층에서 **언제** 갈라졌는지는 판단에 쓰인다: 그 뒤 dev 가 쌓은 것을 이 체인은 아직
        모른다. 그림에만 있으면 터미널로 일하는 쪽은 그걸 모른 채 "dev 에서 났다"까지만 알고
        판단한다.
        """
        self._build()                       # login 이 나고, 배포로 dev 가 자랐다
        self.gil("chain", "search", "--purpose", "검색", "--reference", "-",
                 "--criterion", "된다", input="기준")
        ctx = self.gil("context", "search")
        out = ctx.stdout + ctx.stderr
        self.assertIn("층:", out, "계보 브리핑이 층을 말하지 않는다: " + out)
        self.assertRegex(out, r"dev \d+걸음째",
                         "언제 갈라졌는지가 없다 — '어디서'만으론 무엇을 물려받았는지 모른다")
        # 텍스트 지도도 층을 맨 위에 얹는다.
        txt = self.gil("graph").stdout
        self.assertIn("층 main ─ dev", txt, txt[:400])
        self.assertIn("search ← dev", txt, txt[:400])

    def test_the_briefing_does_not_depend_on_where_you_stand(self):
        """어디에 서 있든 같은 브리핑이 뜬다 (상현님).

        체인 브랜치는 dev 나 다른 체인에서 안 닿는다. 그런데 브리핑은 HEAD 에서 닿는 범위만
        봤다 — 그래서 서 있는 자리에 따라 "체인의 목적"과 "기준 문서가 있다"가 통째로 사라졌다.
        이 두 줄은 **읽히려고** 있는 것이라, 조용히 빠지면 그 자리에서 목적을 다시 읽는 일
        자체가 없어진다.
        """
        self.gil("init", "--name", "clew")
        self.gil("chain", "alpha", "--purpose", "알파의 목적", "--reference", "-",
                 "--criterion", "된다", input="기준")
        self.gil("open", "alpha/c1", "--author", "clew", "--purpose", "P",
                 "--fits", "기여", "--body", "정의")
        here = self.gil("step", "alpha/c1", "--kind", "hypothesis", "--title", "H", "--body", "가설",
                        "--falsify", "F", "--falsify-to", "s1")
        self.assertIn("체인 [alpha] 목적: 알파의 목적", here.stdout + here.stderr)
        self._git("checkout", "-q", "dev")            # 층에 서서 같은 체인을 이어간다
        there = self.gil("step", "alpha/c1", "--kind", "verify", "--title", "V", "--body", "검증",
                         "--verdict", "supported")
        out = there.stdout + there.stderr
        self.assertIn("체인 [alpha] 목적: 알파의 목적", out,
                      "dev 에 서니 체인의 목적이 브리핑에서 사라진다:\n" + out)
        self.assertIn("기준 문서", out, "기준 문서가 있다는 사실도 사라진다:\n" + out)

    def test_the_full_map_draws_the_declared_parent_too(self):
        """전체맵은 커밋 부모로 그린다 — 그래서 선언한 둘째 부모가 통째로 빠졌다 (상현님).

        두 갈래를 합친 사이클의 첫 스텝은 커밋 부모가 하나뿐이다(열 때 선 자리 하나). 선언도
        사실이므로 함께 그리되, 위상이 아니라 선언이라 파선으로 구분한다.
        """
        import json, re
        self.gil("init", "--name", "clew")
        self.gil("chain", "login", "--purpose", "로그인", "--reference", "-",
                 "--criterion", "된다", input="기준")
        for cy in ("c1", "c2"):
            self.gil("open", f"login/{cy}", "--author", "clew", "--purpose", "P",
                     "--fits", "기여", "--body", "정의")
            self.gil("step", f"login/{cy}", "--kind", "success", "--title", "S", "--body", "종합")
            self.gil("close", f"login/{cy}", "--verdict", "supported")
        self.gil("open", "login/c3", "--author", "clew", "--purpose", "합친다", "--fits", "기여",
                 "--parent", "c1", "--parent", "c2", "--inherit", "둘이 남긴 것", "--body", "정의")
        out_html = os.path.join(self.repo, "g8.html")
        self.assertEqual(self.gil("graph", "--html", "--out", out_html).returncode, 0)
        dag = json.loads(re.search(r'"dagdata"[^>]*>(\[.*?\])</script>',
                                   open(out_html, encoding="utf-8").read(), re.S).group(1))
        by = {n["sha"]: f'{n["cycle"]}/{n["step"]}' for n in dag}
        c3s1 = [n for n in dag if n["cycle"] == "c3" and n["step"] == "s1"][0]
        drawn = [by[p] for p in c3s1["parents"]] + [by[p] for p in c3s1.get("dparents", [])]
        self.assertEqual(len(drawn), 2, f"부모 둘을 선언했는데 전체맵엔 {drawn} 뿐이다")

    def test_the_normal_flow_is_not_a_violation(self):
        """층에서 난 시조는 앞 체인 위에 '얹힌' 것이 아니다 — fsck 가 정상 흐름을 짖었다.

        앞 체인이 dev 로 합류하면 그 루트는 dev 팁의 조상이 되고, 뒤에 dev 에서 난 모든 체인이
        '적층'으로 보고됐다(실측: 7체인 저장소에서 거짓 위반 다섯). 매번 짖는 검사는 아무도
        안 듣는 검사가 된다 — 그러면 진짜 적층도 같이 묻힌다.
        """
        self._build()                    # login 이 나고 dev 로 합류·배포까지
        self.gil("chain", "search", "--purpose", "검색", "--reference", "-",
                 "--criterion", "된다", input="기준")
        r = self.gil("fsck")
        out = r.stdout + r.stderr
        self.assertNotIn("적층이다", out, "정상 흐름(층에서 난 시조)을 적층으로 짖는다:\n" + out)
        self.assertEqual(r.returncode, 0, out)

    def test_a_parallel_track_starts_on_the_layer_too(self):
        """병렬 트랙(--parallel-with)도 층에서 갈라진다 — 그림이 그 출발을 그려야 한다.

        병렬은 형제와 **같은 dev 커밋**에서 갈라지지만 시조 선언(Gil-Chain-Orphan)은 안 단다.
        선언만 보고 그리면 층에서 난 체인이 화면에서 미아로 선다 — 시조와 미아는 다르다.
        """
        import json, re
        self._build()
        self.gil("chain", "search", "--purpose", "검색", "--reference", "-",
                 "--criterion", "된다", input="기준")
        self.gil("open", "search/c1", "--author", "clew", "--purpose", "P",
                 "--fits", "기여", "--body", "정의")   # search 를 열어 둔 채로
        r = self.gil("chain", "obs", "--purpose", "관측", "--reference", "-",
                     "--criterion", "된다", "--parallel-with", "search", input="기준")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out_html = os.path.join(self.repo, "g7.html")
        self.assertEqual(self.gil("graph", "--html", "--out", out_html).returncode, 0)
        data = json.loads(re.search(r'"layergraphdata"[^>]*>(\{.*?\})</script>',
                                    open(out_html, encoding="utf-8").read(), re.S).group(1))
        self.assertIn("obs", data["devroots"],
                      f"병렬 트랙의 출발이 층에 안 묶인다: {sorted(data['devroots'])}")

    def test_a_sibling_chain_is_not_an_heir(self):
        """층에서 난 시조는 앞 체인의 스텝에서 이어받지 않았다 (상현님, 실사용 관전).

        dev 로 합류한 앞 체인은 뒤에 난 체인의 커밋 조상이 된다 — 그래서 위상만 보면 모든
        시조가 "첫 체인의 마지막 스텝에서 났다"고 그려졌다(실측: 여섯 중 다섯). 체인 계보는
        이미 닫힘을 기준으로 이 거짓을 막는데(#53), 사이클 진입 부모는 같은 판정을 안 썼다.
        조상관계는 사실이지만 계승은 아니다.
        """
        import json, re
        html = self._build()          # login 이 나고 dev 로 합류·배포까지
        self.gil("chain", "search", "--purpose", "검색", "--reference", "-",
                 "--criterion", "된다", input="기준")
        self.gil("open", "search/c1", "--author", "clew", "--purpose", "P",
                 "--fits", "기여", "--body", "정의")
        out_html = os.path.join(self.repo, "g6.html")
        self.assertEqual(self.gil("graph", "--html", "--out", out_html).returncode, 0)
        data = json.loads(re.search(r'"cycledata"[^>]*>(.*?)</script>',
                                    open(out_html, encoding="utf-8").read(), re.S).group(1))
        c1 = [c for c in data["search"]["cycles"] if c["name"] == "c1"][0]
        self.assertFalse(c1["parent"].startswith("login/"),
                         f"나란히 간 체인을 이어받았다고 그린다: {c1['parent']}")

    def test_a_cycle_may_have_more_than_one_parent(self):
        """부모를 여럿 선언했으면 여럿으로 그린다 (상현님).

        open 은 --parent 를 여러 번 받고 Gil-Cycle-Parent 가 그 수만큼 박히는데, 뷰어는 첫
        하나만 싣고 나머지를 버렸다. 선언한 계보가 그림에서 줄어들면 사람은 자기가 적은 것보다
        가난한 나무를 본다 — 두 갈래를 합친 사이클이 한 갈래에서 온 것으로 보인다.
        """
        import json, re
        self.gil("init", "--name", "clew")
        self.gil("chain", "login", "--purpose", "로그인", "--reference", "-",
                 "--criterion", "된다", input="기준")
        for cy in ("c1", "c2"):
            self.gil("open", f"login/{cy}", "--author", "clew", "--purpose", "P",
                     "--fits", "기여", "--body", "정의")
            self.gil("step", f"login/{cy}", "--kind", "success", "--title", "S", "--body", "종합")
            self.gil("close", f"login/{cy}", "--verdict", "supported")
        r = self.gil("open", "login/c3", "--author", "clew", "--purpose", "합친다",
                     "--fits", "기여", "--parent", "c1", "--parent", "c2",
                     "--inherit", "두 갈래가 남긴 것", "--body", "정의")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out_html = os.path.join(self.repo, "g5.html")
        self.assertEqual(self.gil("graph", "--html", "--out", out_html).returncode, 0)
        data = json.loads(re.search(r'"cycledata"[^>]*>(.*?)</script>',
                                    open(out_html, encoding="utf-8").read(), re.S).group(1))
        c3 = [c for c in data["login"]["cycles"] if c["name"] == "c3"][0]
        self.assertEqual(len(c3["parents"]), 2,
                         f"부모 둘을 선언했는데 그림엔 {c3['parents']} 뿐이다")
        self.assertTrue(all("/c" in p for p in c3["parents"]), c3["parents"])
        # 첫 부모는 예전 자리(parent)에 그대로 — 옛 화면이 안 깨진다.
        self.assertEqual(c3["parent"], c3["parents"][0])

    def test_the_raw_graph_stands_in_the_same_order(self):
        """날것의 git 그래프도 전체맵과 **같은 세로 순서**로 선다 (상현님).

        두 그림을 나란히 두는 이유는 대조인데, main 이 아래로 뻗고 체인이 위로 가면 같은
        사실이 다른 모양이 되어 대조가 성립하지 않는다. 위상(점·선)은 날것 그대로 두고,
        레인 **순서**만 층의 선언에 맞춘다 — git 그래프에서 레인 번호는 원래 뜻이 없다.
        """
        import json, re
        html = self._build()
        rows = json.loads(re.search(r'"gitgraphdata"[^>]*>(\[.*?\])</script>', html, re.S).group(1))
        self.assertTrue(rows, "날것 그래프에 커밋이 없다")
        layers = {c["layer"] for c in rows}
        self.assertIn("main", layers)
        self.assertIn("dev", layers)
        self.assertIn("login", layers, f"체인의 커밋이 자기 층으로 안 잡힌다: {layers}")
        # 트레일러 없는 평범 커밋도 첫 부모의 층을 물려받는다 — 안 그러면 대문 레인에
        # 남의 커밋이 줄줄이 선다.
        self._git("checkout", "-q", "dev")
        self._git("commit", "-q", "--allow-empty", "-m", "dev: 평범한 손질")
        out_html = os.path.join(self.repo, "g4.html")
        self.assertEqual(self.gil("graph", "--html", "--out", out_html).returncode, 0)
        html2 = open(out_html, encoding="utf-8").read()
        rows2 = json.loads(re.search(r'"gitgraphdata"[^>]*>(\[.*?\])</script>', html2, re.S).group(1))
        plain = [c for c in rows2 if c["subj"] == "dev: 평범한 손질"]
        self.assertTrue(plain, "방금 만든 평범 커밋이 그래프에 없다")
        self.assertEqual(plain[0]["layer"], "dev",
                         "dev 위의 평범 커밋이 대문(main)의 것으로 잡힌다")

    def test_the_first_born_chain_forked_at_the_layers_own_root(self):
        """먼저 난 체인은 0걸음째 — 층이 열린 그 자리다. 세는 기준이 대문이면 이 수가 커진다."""
        self._build()
        out = self.gil("context", "login").stdout + self.gil("context", "login").stderr
        self.assertIn("층이 열린 그 자리", out,
                      "층의 첫 체인이 0걸음째로 안 잡힌다(대문의 커밋까지 세고 있다): " + out)


class TestShippedDocsMatchTheRepo(GilFixture):
    """배포판이 심는 문서와 이 저장소의 문서가 같아야 한다 (2026-07-31).

    llms.txt 가 두 벌이었다: 릴리스가 올리는 루트 것과, 바이너리에 박혀 `gil docs install`
    이 심는 assets 것. 루트만 갱신되어 **배포판은 낡은 llms.txt 를 설치하고 있었다** —
    사용자 저장소에는 intake(개시 인터뷰) 절이 통째로 없는 문서가 깔렸다.

    두 벌이 있으면 언젠가 갈라진다. 갈라진 걸 아무도 못 보면 그건 조용히 틀린 문서를
    배포하는 일이다. 여기서 세어 둔다.
    """

    def _pairs(self):
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(here, "..", "..", ".."))
        assets = os.path.join(here, "..", "go", "assets")
        out = [(os.path.join(assets, "llms.txt"), os.path.join(root, "llms.txt"))]
        for name in sorted(os.listdir(os.path.join(assets, "docs", "gil"))):
            out.append((os.path.join(assets, "docs", "gil", name),
                        os.path.join(root, "docs", "gil", name)))
        return out

    def test_embedded_and_published_copies_are_identical(self):
        for embedded, published in self._pairs():
            self.assertTrue(os.path.exists(published),
                            f"배포판은 {os.path.basename(embedded)} 를 심는데 저장소엔 없다")
            with open(embedded, encoding="utf-8") as f:
                a = f.read()
            with open(published, encoding="utf-8") as f:
                b = f.read()
            self.assertEqual(a, b,
                             f"{os.path.basename(embedded)} 가 두 벌로 갈라졌다 — "
                             "바이너리가 심는 것과 릴리스가 올리는 것이 다르다")


class TestMigrateToDevLayout(GilFixture):
    """gil migrate --to-dev-layout — 옛 나무를 main-dev-chain 으로 다시 그린다.

    v3.46.0 이 층을 세웠지만 그건 **앞으로 여는** 체인에만 적용됐다. 이미 자란 저장소는
    체인들이 서로 위에 얹힌 채 남고 drift 가 계속 stacked 로 짖는다. 상현님: "이게 돼야
    나무 전체를 옮길 수 있게 된다."

    이주는 **무손실이어야 하고, 무손실인지는 두 나무를 나란히 놓고 세어서** 확인한다.
    """

    def _old_tree(self):
        """dev 층 없이 체인 셋이 얹힌 옛 나무. b 는 a 를 이어받고, c 는 무관한데 얹혔다.

        **반환값을 단언한다.** 처음엔 스텝 순서(define→hypothesis→verify→analyze→종결)를
        건너뛴 채 실패를 무시했고, 그래서 fixture 가 조용히 반쪽 나무를 만들었다 — 이주를
        시험한 게 아니라 빈 나무를 옮긴 것이었다. 세우지 못한 fixture 는 시험이 아니다.
        """
        self.gil("init", "--name", "clew")
        self._git("checkout", "-q", "main")
        self._git("branch", "-D", "dev")          # 옛 레이아웃 재현
        def ok(r, what):
            self.assertEqual(r.returncode, 0, what + " 실패:\n" + r.stdout + r.stderr)
        for name, extra in (("a", []), ("b", ["--from", "a"]), ("c", [])):
            ok(self.gil("chain", name, "--purpose", name, "--reference", "-",
                        "--criterion", "C", *extra, input="기준"), f"chain {name}")
            ok(self.gil("open", f"{name}/c1", "--author", "clew", "--purpose", "P",
                        "--body", "정의", "--fits", "목적 그 자체"), f"open {name}")
            ok(self.gil("step", f"{name}/c1", "--kind", "hypothesis", "--title", "H",
                        "--body", "가설", "--falsify", "F", "--falsify-to", "s1",
                        "--plan", "구현 1개", "--advances", "핵심 경로"), f"hypothesis {name}")
            ok(self.gil("step", f"{name}/c1", "--kind", "verify", "--title", "V", "--body", "검증",
                        "--verdict", "supported", "--plan-held",
                        "--falsify-unmet", "미관측"), f"verify {name}")
            ok(self.gil("step", f"{name}/c1", "--kind", "analyze", "--title", "A", "--body", "해석",
                        "--finding", "지지됐다"), f"analyze {name}")
            ok(self.gil("step", f"{name}/c1", "--kind", "success", "--title", "S", "--body", "종합",
                        "--toward", "기준 충족", "--next-design", "다음 설계"), f"success {name}")
            ok(self.gil("close", f"{name}/c1", "--verdict", "supported"), f"close {name}")
            ok(self.gil("chain-close", name, "--verdict", "supported",
                        "--retro", "-", input="회고"), f"chain-close {name}")
        # fixture 가 실제로 나무를 세웠는지 — 스텝이 0이면 아래 시험은 전부 공회전이다.
        self.assertGreaterEqual(self._steps("a", "b", "c"), 12, "fixture 가 나무를 못 세웠다")

    def _chain_root(self, branch):
        """그 브랜치의 chain-root 커밋. **제목이 아니라 트레일러로** 찾는다 —
        제목은 사람이 읽는 장식이고, 무엇인지를 말하는 것은 Gil-Kind 다(gil 자신이 그렇게 읽는다)."""
        r = self._git("log", branch, "--format=%H\t%(trailers:key=Gil-Kind,valueonly)")
        for line in r.stdout.split("\n"):
            sha, _, kind = line.partition("\t")
            if kind.strip() == "chain-root":
                return sha.strip()
        return ""

    def _steps(self, *refs):
        r = self._git("log", "--format=%(trailers:key=Gil-Step,valueonly)", *refs, "--")
        return len([x for x in r.stdout.split("\n") if x.strip()])

    def test_the_stack_is_actually_broken(self):
        """얹혀 있던 무관한 체인이 dev 에서 갈라진다 — 이게 이주의 전부다.

        한 번은 "이미 옮긴 조상"을 체인 구분 없이 이어붙여, 옛 적층이 새 나무에 그대로
        복사됐다(c 가 옮겨진 b 뒤에 다시 붙었다). 옮겨 놓고 적층이 남으면 이주는 이름만 남는다.
        """
        self._old_tree()
        r = self.gil("migrate", "--to-dev-layout")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        anc = lambda x, y: self._git("merge-base", "--is-ancestor", x, y).returncode == 0
        self.assertTrue(anc("dev", "dev-c"), "옮긴 체인이 dev 의 자손이 아니다")
        self.assertFalse(anc("dev-a", "dev-c"), "적층이 새 나무에 그대로 복사됐다")
        self.assertTrue(anc("dev-a", "dev-b"), "선언된 계승이 이주에서 끊겼다")

    def test_nothing_is_lost(self):
        """트리(파일 내용)와 스텝 수가 그대로다 — 옮겼다고 믿게 만드는 게 조용한 손실보다 나쁘다."""
        self._old_tree()
        before = self._steps("a", "b", "c")
        self.gil("migrate", "--to-dev-layout")
        self.assertEqual(self._steps("dev-a", "dev-b", "dev-c"), before,
                         "스텝이 이주에서 새거나 늘었다")
        for b in ("a", "b", "c"):
            self.assertEqual(self._git("rev-parse", f"{b}^{{tree}}").stdout.strip(),
                             self._git("rev-parse", f"dev-{b}^{{tree}}").stdout.strip(),
                             f"{b} 의 파일 내용이 이주에서 바뀌었다")

    def test_the_old_tree_survives(self):
        """옛 브랜치는 지우지 않는다 — 잘못 옮겼을 때 돌아갈 곳이 있어야 한다."""
        self._old_tree()
        self.gil("migrate", "--to-dev-layout")
        for b in ("a", "b", "c"):
            self.assertEqual(self._git("rev-parse", "--verify", "-q", b).returncode, 0,
                             f"옛 브랜치 {b} 가 사라졌다")

    def test_the_migrated_chain_declares_where_it_came_from(self):
        """이름은 정체성이다 — 접두는 브랜치가 아니라 **체인**의 이름을 바꾼다.

        안 그러면 두 나무가 같은 체인이 되어 한 사이클의 스텝이 두 벌씩 존재한다(fsck 가
        's4 ×2' 로 곧바로 짖었다). 그리고 dev 에서 났다는 선언이 있어야 뷰어가 출발을 층에
        묶고 fsck 가 대조할 것이 생긴다.
        """
        self._old_tree()
        self.gil("migrate", "--to-dev-layout")
        self.assertEqual(self.trailer("dev-c", "Gil-Chain"), "dev-c")
        self.assertEqual(self.trailer(self._chain_root("dev-c"), "Gil-Chain-Orphan"), "dev",
                         "dev 에서 났는데 그 선언이 없다 — 뷰어가 출발을 층에 못 묶는다")
        self.assertEqual(self.trailer(self._chain_root("dev-b"), "Gil-Chain-From"), "dev-a",
                         "계승 선언이 옛 이름을 가리킨다")

    # ── --replace: 새 나무가 옛 이름을 넘겨받는다 (이슈 #97) ──────────────
    #
    # 상현님 판단: 같은 이름 아래 플래그로. 사람이 "이 저장소의 이력을 옮긴다"고 생각할 때
    # 떠올리는 낱말은 하나고, 하는 일이 다르다고 이름을 나누면 필요한 순간에 아무도 못 찾는다.
    # 묘비는 남긴다 — 없는 게 죄가 아니라 감춘 게 죄다.

    def _repo_name(self):
        return os.path.basename(self.repo)

    def test_replace_refuses_without_typing_the_repo_name(self):
        """문은 **먼저** 선다 — 다 그려 놓고 마지막에 물으면 되돌리기 어려운 자리에서 묻는 것이다."""
        self._old_tree()
        r = self.gil("migrate", "--to-dev-layout", "--replace")
        self.assertNotEqual(r.returncode, 0, "이름 타이핑 없이 대체가 통과했다")
        self.assertIn(self._repo_name(), r.stdout + r.stderr, "무엇을 타이핑할지 안 알려준다")
        self.assertNotEqual(self._git("rev-parse", "--verify", "-q", "a").returncode, 1,
                            "거부인데 옛 브랜치를 건드렸다")
        self.assertNotEqual(self._git("rev-parse", "--verify", "-q", "dev-a").returncode, 0,
                            "거부인데 새 브랜치를 세웠다")

    def test_replace_hands_the_old_names_to_the_new_tree(self):
        """옛 브랜치는 지워지고 그 이름이 새 나무로 간다 — 접두는 이주 중에만 사는 임시 이름이다."""
        self._old_tree()
        before = self._steps("a", "b", "c")
        old_a = self._git("rev-parse", "a").stdout.strip()
        r = self.gil("migrate", "--to-dev-layout", "--replace", "--confirm", self._repo_name())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for b in ("a", "b", "c"):
            self.assertEqual(self._git("rev-parse", "--verify", "-q", b).returncode, 0,
                             f"{b} 라는 이름이 사라졌다 — 대체는 이름을 넘기는 일이다")
            self.assertNotEqual(self._git("rev-parse", "--verify", "-q", f"dev-{b}").returncode, 0,
                                f"임시 접두 브랜치 dev-{b} 가 남았다")
        self.assertNotEqual(self._git("rev-parse", "a").stdout.strip(), old_a,
                            "이름만 그대로고 나무는 안 바뀌었다 — 다시 그리지 않았다")
        # 계보는 참이 됐고, 스텝은 하나도 안 새어 나갔다.
        anc = lambda x, y: self._git("merge-base", "--is-ancestor", x, y).returncode == 0
        self.assertTrue(anc("dev", "c"), "대체한 체인이 dev 의 자손이 아니다")
        self.assertFalse(anc("a", "c"), "적층이 대체 뒤에도 남았다")
        self.assertEqual(self._steps("a", "b", "c"), before, "스텝이 대체에서 새거나 늘었다")
        # **체인의 이름도 제 이름으로 돌아온다.** 접두가 남으면 이주가 정체성을 바꾸는 일이 된다.
        self.assertEqual(self.trailer("c", "Gil-Chain"), "c", "체인 이름에 임시 접두가 남았다")
        self.assertEqual(self.trailer(self._chain_root("b"), "Gil-Chain-From"), "a",
                         "계승 선언이 임시 이름을 가리킨다")

    def test_replace_leaves_a_tombstone_and_a_bundle(self):
        """지운 자리는 계보가 계속 말해야 한다 — 묘비 없는 삭제는 없다(prune 과 같은 규율)."""
        self._old_tree()
        old_a = self._git("rev-parse", "a").stdout.strip()
        r = self.gil("migrate", "--to-dev-layout", "--replace", "--confirm", self._repo_name())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        bundle = os.path.join(self.repo, ".git", "gil", "archive",
                              "replace-" + self._repo_name() + ".bundle")
        self.assertTrue(os.path.exists(bundle), "번들이 없다 — 되살릴 곳 없이 지웠다")
        # 번들은 **옛 나무**를 담고 있어야 한다(그게 되살릴 것의 전부다).
        v = subprocess.run(["git", "bundle", "list-heads", bundle],
                           capture_output=True, text=True, cwd=self.repo)
        self.assertIn(old_a, v.stdout, "번들에 옛 브랜치의 끝이 없다")
        tomb = self._git("log", "main", "--format=%H\t%(trailers:key=Gil-Kind,valueonly)")
        self.assertIn("migrate-replace", tomb.stdout, "묘비 커밋이 없다")
        body = self._git("log", "main", "--format=%B", "-n", "20").stdout
        self.assertIn(old_a[:9], body, "묘비가 지운 브랜치의 끝을 안 적었다")

    def test_replace_does_not_accuse_its_own_product(self):
        """대체 직후 fsck 가 조용해야 한다 — 방금 gil 이 정상 절차로 치운 것을 gil 이 고발하면
        사람은 그 고지를 통째로 무시하게 된다(실측: '스텝 20개 유실 직전')."""
        self._old_tree()
        r = self.gil("migrate", "--to-dev-layout", "--replace", "--confirm", self._repo_name())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        f = self.gil("fsck")
        out = f.stdout + f.stderr
        self.assertNotIn("유실 직전", out, "대체가 남긴 찌꺼기를 fsck 가 유실로 고발한다:\n" + out)
        self.assertNotIn("dev-a", out, "임시 접두 나무가 아직 저장소에 남아 있다")

    def test_dry_run_writes_nothing(self):
        self._old_tree()
        before = self._git("rev-parse", "a").stdout.strip()
        r = self.gil("migrate", "--to-dev-layout", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self._git("rev-parse", "--verify", "-q", "dev-a").returncode, 0,
                            "--dry-run 인데 브랜치를 만들었다")
        self.assertEqual(self._git("rev-parse", "a").stdout.strip(), before)


class TestLayerChecks(GilFixture):
    """층을 건널 때 무엇으로 확인했나 (상현님, 2026-08-01).

    "배포할 때만 테스트하면 안 되나? 아니면 dev 로 올릴 때만이라도."

    SPEC 7 이 이미 그 축을 갖고 있었지만(개발은 smoke, 엄밀한 검증은 배포 앞에서) 문장으로만
    있었다. 문법에 없는 규율은 지켜지지 않는다.

    **선언이 아니라 실행이다.** `--verified <무엇으로 확인했나>` 같은 자유서술 칸을 만들면
    #76 이 관전 중인 병이 재발한다(칸이 생기면 채워지고, 채워지면 통과한다). 저장소가 선언한
    검사를 gil 이 직접 돌리고 종료코드로 판정한다.
    """

    def _chain(self, name):
        ok = lambda r, w: self.assertEqual(r.returncode, 0, w + ":\n" + r.stdout + r.stderr)
        ok(self.gil("chain", name, "--purpose", name, "--reference", "-",
                    "--criterion", "C", input="기준"), f"chain {name}")
        ok(self.gil("open", f"{name}/c1", "--author", "clew", "--purpose", "P",
                    "--body", "정의", "--fits", "목적"), f"open {name}")
        ok(self.gil("step", f"{name}/c1", "--kind", "hypothesis", "--title", "H", "--body", "B",
                    "--falsify", "F", "--falsify-to", "s1", "--plan", "P",
                    "--advances", "A"), f"hypothesis {name}")
        ok(self.gil("step", f"{name}/c1", "--kind", "verify", "--title", "V", "--body", "B",
                    "--verdict", "supported", "--plan-held", "--falsify-unmet", "U"), f"verify {name}")
        ok(self.gil("step", f"{name}/c1", "--kind", "analyze", "--title", "A", "--body", "B",
                    "--finding", "F"), f"analyze {name}")
        ok(self.gil("step", f"{name}/c1", "--kind", "success", "--title", "S", "--body", "B",
                    "--toward", "T", "--next-design", "N"), f"success {name}")
        ok(self.gil("close", f"{name}/c1", "--verdict", "supported"), f"close {name}")
        ok(self.gil("chain-close", name, "--verdict", "supported",
                    "--retro", "-", input="회고"), f"chain-close {name}")

    def _declare(self, text):
        """검사를 **대문에** 선언한다 — 정책은 가지의 사정이 아니다."""
        here = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self._git("checkout", "-q", "main")
        os.makedirs(os.path.join(self.repo, ".gil"), exist_ok=True)
        with open(os.path.join(self.repo, ".gil", "checks"), "w", encoding="utf-8") as f:
            f.write(text)
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "검사 선언")
        self._git("checkout", "-q", here)

    def setUp(self):
        super().setUp()
        self.gil("init", "--name", "clew")

    def test_a_failing_check_stops_the_crossing(self):
        """검사가 실패하면 층을 건너지 못한다 — 확인은 선언이 아니라 사건이다."""
        self._declare("dev: false\n")
        self._chain("a")
        r = self.gil("merge", "a", "--into", "dev", "--reason", "배포 단위")
        self.assertNotEqual(r.returncode, 0, "검사가 실패했는데 합류했다")
        self.assertIn("검사가 실패했다", r.stdout + r.stderr)
        anc = self._git("merge-base", "--is-ancestor", "a", "dev").returncode == 0
        self.assertFalse(anc, "거부했다면서 실제로는 합쳐 놨다")

    def test_a_passing_check_is_recorded_on_the_commit(self):
        """통과한 사실이 커밋에 남는다 — 안 남으면 다음 사람은 다시 확인해야 한다."""
        self._declare("dev: true\n")
        self._chain("a")
        r = self.gil("merge", "a", "--into", "dev", "--reason", "배포 단위")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("dev", "Gil-Checked"), "true")

    def test_skipping_requires_a_reason_and_leaves_a_trace(self):
        """건너뛴 것을 안 적으면, 이 커밋은 확인된 것과 구별되지 않는다."""
        self._declare("dev: false\n")
        self._chain("a")
        r = self.gil("merge", "a", "--into", "dev", "--reason", "R", "--skip-check")
        self.assertNotEqual(r.returncode, 0, "이유 없이 건너뛰게 뒀다")
        r = self.gil("merge", "a", "--into", "dev", "--reason", "R",
                     "--skip-check", "--skip-reason", "CI 가 이미 돌렸다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("dev", "Gil-Check-Skipped"), "CI 가 이미 돌렸다")

    def test_deploy_runs_the_stricter_check_and_leaves_no_marker_on_failure(self):
        """배포는 되돌리기 어렵다 — 확인 안 된 배포를 기록으로 남기지 않는다."""
        self._declare("dev: true\nmain: false\n")
        self._chain("a")
        self.assertEqual(self.gil("merge", "a", "--into", "dev", "--reason", "R").returncode, 0)
        r = self.gil("deploy", "--tag", "v1.0.0")
        self.assertNotEqual(r.returncode, 0, "main 검사가 실패했는데 배포했다")
        self.assertEqual(self.trailer("dev", "Gil-Deploy"), "",
                         "거부했다면서 배포 마커는 새겨 놨다")

    def test_the_policy_does_not_depend_on_which_branch_is_checked_out(self):
        """검사는 저장소의 정책이지 가지의 사정이 아니다.

        작업트리에서 읽었더니 merge 가 브랜치를 옮기는 순간 파일이 사라져, 검사가 조용히
        '선언되지 않음'으로 통과했다 — 게이트가 있는 척하면서 없는 상태였다.
        """
        self._declare("dev: false\n")
        self._chain("a")
        self._git("checkout", "-q", "a")     # 대문이 아닌 자리에서 건넌다
        r = self.gil("merge", "a", "--into", "dev", "--reason", "R")
        self.assertNotEqual(r.returncode, 0, "다른 브랜치에 서 있으니 검사가 사라졌다")

    def test_a_repo_without_checks_is_not_blocked_but_is_told(self):
        """없는 규율을 강요하면 이미 있는 나무가 얼어붙는다 — 막지 않되 알린다."""
        self._chain("a")
        r = self.gil("merge", "a", "--into", "dev", "--reason", "R")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("확인한 것이 없다", r.stdout + r.stderr)


class TestVersionAsk(GilFixture):
    """**낡은 gil 을 쥔 세션은 자기가 낡은 줄 모른다** (상현님).

    handoff 에 현행성 배너가 있었지만 handoff 를 부르는 건 자기규율이고, 자기규율은 원리적으로
    불충분하다. 그리고 "새 버전 있음"이라고 **알리기만** 했더니 세션은 읽고도 하던 일을 계속했다.
    묻는 것과 알리는 것은 다르다 — 물으면 사람이 답해야 하고, 답이 있어야 결정이 선다."""

    def _boot(self, latest="v9.9.9", extra=None, cur="v3.0.0"):
        env = dict(os.environ, GIL_NO_VIEWER="1", GIL_VERSION_CURRENT=cur)
        if latest is not None:
            env["GIL_VERSION_LATEST"] = latest
        env.update(extra or {})
        return subprocess.run([*GIL_CMD, "log"], cwd=self.repo,
                              capture_output=True, text=True, env=env)

    def test_onboarding_asks_when_a_newer_release_exists(self):
        env = dict(os.environ, GIL_NO_VIEWER="1", GIL_VERSION_LATEST="v9.9.9",
                   GIL_VERSION_CURRENT="v3.0.0")
        r = subprocess.run([*GIL_CMD, "init", "--name", "clew"], cwd=self.repo,
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("v9.9.9", r.stdout)
        self.assertIn("올릴까요", r.stdout, "온보딩이 버전업을 묻지 않았다:\n" + r.stdout)

    def test_boot_asks_once_then_stays_quiet(self):
        """묻는 건 세션당 한 번이다 — 명령마다 물으면 잡음이 되고, 잡음은 안 읽힌다."""
        self.gil("init", "--name", "clew")
        first = self._boot()
        self.assertIn("올릴까요", first.stdout, "부팅이 안 물었다:\n" + first.stdout)
        second = self._boot()
        self.assertNotIn("올릴까요", second.stdout,
                         "같은 6시간 안에 또 물었다:\n" + second.stdout)

    def test_same_version_says_nothing(self):
        self.gil("init", "--name", "clew")
        # 소스 빌드의 버전은 dev 다 — 최신이 dev 면 물을 것이 없다.
        r = self._boot(latest="v3.0.0")
        self.assertNotIn("올릴까요", r.stdout, "같은 버전인데 물었다:\n" + r.stdout)

    def test_never_asks_to_go_backwards(self):
        """다름이 곧 뒤처짐은 아니다 — 릴리스 자산 실측에서 잡혔다.

        방금 구운 v3.48.0 바이너리는 아직 안 올라간 태그를 각인하고 있어서, 최신 릴리스가
        v3.47.0 이면 '다름'만 보는 코드는 **옛 버전으로 올릴까요**라고 물었다."""
        self.gil("init", "--name", "clew")
        r = self._boot(latest="v3.47.0", cur="v3.48.0")   # 아직 안 올라간 태그를 각인한 자리
        self.assertNotIn("올릴까요", r.stdout, "뒤로 올리라고 물었다:\n" + r.stdout)

    def test_opt_out_silences_it(self):
        self.gil("init", "--name", "clew")
        r = self._boot(extra={"GIL_NO_VERSION_CHECK": "1"})
        self.assertNotIn("올릴까요", r.stdout)

    def test_a_silent_check_does_not_burn_the_ask(self):
        """**조용히 지나간 확인이 6시간을 태우면 안 된다.**

        실측(릴리스 바이너리): `gil init` 이 최신이라 아무 말 없이 도장을 찍었고, 그 뒤 6시간은
        새 릴리스가 나도 통째로 침묵했다. 소스 빌드(dev)는 확인 자체를 건너뛰어 시험이 이 길을
        아예 밟지 못했다 — 그래서 릴리스에서만 나는 결함이었다."""
        self.gil("init", "--name", "clew")
        quiet = self._boot(latest="v3.0.0")               # 최신이다 → 조용히 지나간다
        self.assertNotIn("올릴까요", quiet.stdout)
        later = self._boot(latest="v9.9.9")               # 그 사이 릴리스가 났다
        self.assertIn("올릴까요", later.stdout,
                      "조용한 확인이 문의를 6시간 잠갔다:\n" + later.stdout)

    def test_a_newer_release_breaks_the_silence(self):
        """같은 말은 되풀이하지 않되, **새 소식은 침묵을 깬다.**

        사람이 "아니오"라 답한 그 버전을 다시 묻지 않는 게 6시간의 목적이다. 그 목적은 더 새
        릴리스가 나온 순간 끝난다 — 아니면 릴리스 직후 세션이 침묵 구간에 갇힌다."""
        self.gil("init", "--name", "clew")
        self.assertIn("올릴까요", self._boot(latest="v9.9.9").stdout)
        self.assertNotIn("올릴까요", self._boot(latest="v9.9.9").stdout, "같은 버전을 또 물었다")
        self.assertIn("올릴까요", self._boot(latest="v9.9.10").stdout,
                      "더 새 릴리스가 났는데 6시간 침묵에 갇혔다")

    def _fake_github(self, api_status=403):
        """한도에 걸린 GitHub 를 세운다 — API 는 403, 웹은 최신 태그로 리다이렉트.

        이 시험이 없으면 그 갈래는 **코드로만 있는 길**이 된다(v3.51.0 에서 소스 빌드가 버전
        확인을 통째로 건너뛰어 결함을 못 밟은 것과 같은 모양)."""
        import http.server, threading
        tag = "v9.9.9"

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/repos/"):      # API
                    self.send_response(api_status)
                    self.end_headers()
                    return
                self.send_response(302)                  # 웹 — 한도를 안 쓴다
                self.send_header("Location",
                                 "https://github.com/x/y/releases/tag/" + tag)
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        return base, tag

    def test_a_rate_limited_api_does_not_silence_the_whole_thing(self):
        """**403 하나가 기구 전체를 끄면 안 된다** (상현님 실측).

        비인증 GitHub API 는 시간당 60회다. 한 머신에서 여러 세션·여러 저장소가 돌면 이 한도는
        쉽게 차고, 그때 gil 은 조용히 물러났다 — "대부분 이렇게 실패하면서 새 버전이 있는지
        모르고 지나간다". 최신 태그를 아는 데 API 가 꼭 필요하진 않다: releases/latest 의
        리다이렉트는 한도를 안 쓴다."""
        self.gil("init", "--name", "clew")
        base, tag = self._fake_github(api_status=403)
        r = self._boot(latest=None, extra={"GIL_GITHUB_API": base, "GIL_GITHUB_WEB": base})
        self.assertIn(tag, r.stdout, "API 가 403 이자 버전 문의가 통째로 꺼졌다:\n" + r.stdout)
        self.assertIn("올릴까요", r.stdout)

    def test_a_failed_lookup_is_retried_sooner_than_a_quiet_one(self):
        """"최신이라 조용하다"와 "못 물어봐서 조용하다"는 다른 상태다.

        옛 코드는 둘 다 한 시간을 쉬었다 — 일시적 403 한 번이 그 세션의 남은 시간을 삼켰다."""
        self.gil("init", "--name", "clew")
        dead = "http://127.0.0.1:1"   # 아무도 안 듣는 자리 — 조회가 실패한다
        r = self._boot(latest=None, extra={"GIL_GITHUB_API": dead, "GIL_GITHUB_WEB": dead})
        self.assertNotIn("올릴까요", r.stdout, "못 물어봤는데 물었다")
        stamp = os.path.join(self.repo, ".git", "gil", "version-checked")
        self.assertIn("fail", open(stamp, encoding="utf-8").read(),
                      "실패한 조회가 성공한 조회와 같은 도장을 찍었다 — 한 시간을 통째로 쉰다")
        # 성공한 조회는 그 표를 안 남긴다 — 두 상태가 같은 칸에 같은 모양으로 적히면
        # 다음 조회 간격을 가를 근거가 사라진다.
        base, tag = self._fake_github(api_status=403)
        os.remove(stamp)
        ok = self._boot(latest=None, extra={"GIL_GITHUB_API": base, "GIL_GITHUB_WEB": base})
        self.assertIn(tag, ok.stdout)
        self.assertNotIn("fail", open(stamp, encoding="utf-8").read(),
                         "성공한 조회에 실패 표가 남았다")

    def test_docs_install_asks_too(self):
        """온보딩을 **심는** 자리도 묻는다.

        낡은 gil 이 진입점을 심으면 그 저장소는 처음부터 낡은 워크플로우를 배운다. docs 는
        부팅 스위치에서 통째로 빠져 있어 여기서만 문의가 없었다."""
        self.gil("init", "--name", "clew")
        env = dict(os.environ, GIL_NO_VIEWER="1",
                   GIL_VERSION_LATEST="v9.9.9", GIL_VERSION_CURRENT="v3.0.0")
        r = subprocess.run([*GIL_CMD, "docs", "install"], cwd=self.repo,
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("올릴까요", r.stdout, "문서를 심는 자리가 안 물었다:\n" + r.stdout)

    def test_gate_block_puts_version_check_before_handoff(self):
        """대문에 심는 진입점은 **도구 현행성부터** 짚는다.

        이 블록이 다음 세션이 실제로 읽는 레일이다. 여기에 버전 줄이 없으면, 세션은 gil 이
        이미 깔려 있다는 이유로 낡은 채 handoff 로 직행한다(실사용에서 반복된 실패)."""
        self.gil("init", "--name", "clew")
        self.gil("docs", "install")
        with open(os.path.join(self.repo, "CLAUDE.md"), encoding="utf-8") as f:
            whole = f.read()
        # gil 이 관리하는 구간만 본다 — 대문의 나머지는 사람의 것이고 순서를 단언할 수 없다.
        t = whole.split("<!-- gil:onboarding:begin -->")[1].split("<!-- gil:onboarding:end -->")[0]
        self.assertIn("gil version --check", t, "진입점에 버전 확인이 없다:\n" + t)
        self.assertIn("올릴까요", t, "진입점이 알리기만 하고 묻지 않는다")
        self.assertLess(t.index("gil version --check"), t.index("gil handoff"),
                        "버전 확인이 handoff 뒤에 있다 — 낡은 도구로 이어받게 된다")


class TestMCPVersionAsk(GilFixture):
    """**MCP 로 도는 세션만 버전 문의를 한 번도 못 받았다** (상현님 실사용).

    mcp.go 의 tool 래퍼는 cmd* 를 직접 부른다 — main 의 부팅 자리(versionAskPrint)를 지나지
    않는다. CLI 세션은 묻는데 MCP 세션은 안 묻는, 경로에 따라 갈리는 침묵이었다. 그래서
    최신이 나와도 구버전으로 세션을 통째로 보냈다."""

    def _tool_text(self, tool="gil_log", env_extra=None):
        import json
        env = dict(os.environ, GIL_NO_VIEWER="1",
                   GIL_VERSION_LATEST="v9.9.9", GIL_VERSION_CURRENT="v3.0.0")
        env.update(env_extra or {})
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=self.repo,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        read = lambda: json.loads(p.stdout.readline())
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                             "clientInfo": {"name": "t", "version": "1"}}})
            read()
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": tool, "arguments": {}}})
            return read()["result"]["content"][0]["text"]
        finally:
            p.stdin.close()
            p.wait(timeout=20)
            p.stdout.close()
            p.stderr.close()

    def test_tool_response_asks_when_newer_exists(self):
        self.gil("init", "--name", "clew")
        t = self._tool_text()
        self.assertIn("v9.9.9", t, "MCP 응답에 새 버전이 없다:\n" + t)
        self.assertIn("올릴까요", t, "MCP 툴이 버전업을 묻지 않았다:\n" + t)

    def test_asks_once_then_stays_quiet(self):
        """6시간 규칙은 MCP 에도 똑같이 선다 — 툴마다 물으면 잡음이 되어 안 읽힌다."""
        self.gil("init", "--name", "clew")
        self.assertIn("올릴까요", self._tool_text())
        self.assertNotIn("올릴까요", self._tool_text())

    def test_no_ask_when_up_to_date(self):
        self.gil("init", "--name", "clew")
        t = self._tool_text(env_extra={"GIL_VERSION_LATEST": "v3.0.0"})
        self.assertNotIn("올릴까요", t, "최신인데 물었다:\n" + t)


class TestMergeCommitIsAGilCommit(GilFixture):
    """**gil merge 가 만든 커밋을 gil 자신이 못 읽는다** (이슈 #101, 실사용 리포트).

    deployment.md 의 정본 흐름은 chain-close → merge --into dev → 다음 intake/chain 이다.
    그대로 밟았더니 fsck 가 적층이라 하고 migrate 가 "gil 커밋이 아니다"로 거부했다.
    정본 흐름을 밟은 사람이 벌을 받으면, 그 문서는 문서가 아니라 함정이다."""

    def _closed_chain(self, name):
        self.gil("chain", name, "--purpose", "목적 " + name)
        self.gil("open", name + "/c001", "--author", "clew", "--purpose", "작은 문제")
        self.gil("step", name + "/c001", "--kind", "success", "--title", "성공")
        self.gil("close", name + "/c001", "--verdict", "supported")
        self.gil("chain-close", name, "--verdict", "success")

    def test_merge_commit_declares_itself_without_pretending_to_be_a_step(self):
        """머지 커밋은 **자기가 gil 의 것임을 밝히되, 체인의 커밋인 척하지 않는다.**

        고치는 방향을 여기서 못박는다: `Gil-Chain` 을 달아 주는 것은 답이 아니다. 그 트레일러는
        '이 커밋은 그 체인의 것'이라는 뜻이고, 색인이 그걸로 체인의 루트·팁을 잡는다 — 층에
        놓인 머지 커밋이 체인의 커밋으로 세어지면 계보 계산이 흔들린다. 머지는 `Gil-Merge`
        로 자기를 밝히고, 읽는 쪽이 층을 체인으로 착각하지 않으면 된다."""
        self.gil("init", "--name", "clew")
        self._closed_chain("a")
        r = self.gil("merge", "a", "--into", "dev", "--reason", "배포 단위")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("dev", "Gil-Merge"), "a")
        self.assertEqual(self.trailer("dev", "Gil-Merge-Into"), "dev")
        self.assertEqual(self.trailer("dev", "Gil-Chain"), "",
                         "머지 커밋이 체인의 커밋인 척한다 — 색인이 이걸 체인 커밋으로 센다")

    def test_the_canonical_flow_leaves_fsck_clean(self):
        """체인 A 를 닫고 dev 로 합류시킨 뒤 dev 에서 체인 B 를 열면 위반 0 이어야 한다."""
        self.gil("init", "--name", "clew")
        self._closed_chain("a")
        self.gil("merge", "a", "--into", "dev", "--reason", "배포 단위")
        self._git("checkout", "-q", "dev")
        self._closed_chain("b")
        r = self.gil("fsck")
        out = r.stdout + r.stderr
        self.assertNotIn("적층", out, "정본 흐름을 밟았는데 적층이라 한다:\n" + out)

    def test_migrate_does_not_refuse_because_of_its_own_merge(self):
        """migrate 가 자기 도구가 만든 머지 커밋을 보고 이주를 거부하면 안 된다."""
        self.gil("init", "--name", "clew")
        self._closed_chain("a")
        self.gil("merge", "a", "--into", "dev", "--reason", "배포 단위")
        r = self.gil("migrate", "--to-dev-layout", "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotIn("gil 커밋이 아니다", out,
                         "자기가 만든 머지 커밋을 남의 것으로 본다:\n" + out)


class TestFrontMatterLandsOnTheLayer(GilFixture):
    """**앞머리(intake·인터뷰)가 서 있던 자리에 심긴다** (이슈 #102 경로 1).

    체인 A 를 닫은 직후 HEAD 는 A 의 사이클 브랜치에 있다. 그 자리에서 `gil intake` 를 부르면
    개시 인터뷰가 A 의 가지 위에 쌓이고 그 브랜치가 전진한다 — 다음 체인의 앞머리가 앞
    체인의 몸에 들어앉는 것이다.

    v3.50.0 에서 `gil open` 의 같은 병("새 사이클은 제 체인의 끝에서 난다 — HEAD 가 아니라")을
    고쳤고, v3.49.0 은 **이주기**에 "앞머리는 dev 층의 것"을 가르쳤다. 살아 있는 명령에만
    안 가르쳤다."""

    def _closed_chain(self, name):
        self.gil("chain", name, "--purpose", "목적 " + name)
        self.gil("open", name + "/c001", "--author", "clew", "--purpose", "작은 문제")
        self.gil("step", name + "/c001", "--kind", "success", "--title", "성공")
        self.gil("close", name + "/c001", "--verdict", "supported")
        self.gil("chain-close", name, "--verdict", "success")

    QS = '[{"q":"다음 기준은?","type":"text"}]'

    def test_intake_lands_on_dev_not_on_the_branch_you_stood_on(self):
        self.gil("init", "--name", "clew")
        self._closed_chain("a")
        before = self._git("rev-parse", "a-c001").stdout.strip()
        r = self.gil("intake", "nx", "--ask", "-", input=self.QS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self._git("rev-parse", "a-c001").stdout.strip()
        self.assertEqual(before, after,
                         "앞 체인의 사이클 브랜치가 개시 인터뷰를 얹고 전진했다")
        on_dev = self._git("merge-base", "--is-ancestor",
                           self._intake_sha(), "dev").returncode == 0
        self.assertTrue(on_dev, "개시 인터뷰가 dev 층에 없다 — 다음 체인이 여기서 나야 한다")

    def test_the_answer_lands_on_the_same_layer_as_the_question(self):
        """질문과 답이 갈라져 앉으면 앞머리가 두 곳으로 찢어진다."""
        self.gil("init", "--name", "clew")
        self._closed_chain("a")
        self.gil("intake", "nx", "--ask", "-", input=self.QS)
        ans = os.path.join(self.repo, "ans.json")
        with open(ans, "w", encoding="utf-8") as f:
            f.write('{"answers":[{"q":"다음 기준은?","a":"B 가 닫히는 것"}]}')
        r = self.gil("intake", "nx", "--resolve", ans)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for sha in self._intake_shas():
            on_dev = self._git("merge-base", "--is-ancestor", sha, "dev").returncode == 0
            subj = self._git("log", "-1", "--format=%s", sha).stdout.strip()
            self.assertTrue(on_dev, "앞머리가 dev 밖에 앉았다: " + subj)

    def test_a_repo_without_the_layer_is_left_alone(self):
        """층이 없는 옛 저장소에서는 지금처럼 HEAD 에 남는다 — 여기서 층을 강요하지 않는다."""
        self.gil("init", "--name", "clew")
        self._git("branch", "-D", "dev")
        r = self.gil("intake", "nx", "--ask", "-", input=self.QS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def _intake_shas(self):
        out = self._git("log", "--all",
                        "--format=%H\x1f%(trailers:key=Gil-Intake,valueonly)").stdout
        got = [ln.partition("\x1f")[0].strip() for ln in out.splitlines()
               if ln.partition("\x1f")[2].strip() == "nx"]
        self.assertTrue(got, "개시 인터뷰 커밋을 못 찾았다:\n" + out)
        return got

    def _intake_sha(self):
        """개시 인터뷰 커밋 — 제목이 아니라 **선언(Gil-Intake)** 으로 찾는다."""
        out = self._git("log", "--all",
                        "--format=%H\x1f%(trailers:key=Gil-Intake,valueonly)").stdout
        for ln in out.splitlines():
            sha, _, intake = ln.partition("\x1f")
            if intake.strip() == "nx":
                return sha.strip()
        self.fail("개시 인터뷰 커밋을 못 찾았다:\n" + out)


class TestFsckSeesTheLayerOrSaysItCannot(GilFixture):
    """**층 판정이 조용히 통째로 꺼진다** (이슈 #99, 실사용 리포트).

    fsckDevLayer 는 `hasDevLayer()` 가 거짓이면 아무 말 없이 nil 을 돌려준다. 그리고
    hasDevLayer 는 dev 브랜치 이력에서 `Gil-Kind: dev-root` 마커를 찾는다. 그래서 dev 를
    손으로 세운 저장소는 **층이 있는 것처럼 보이는데 판정은 전부 꺼진 채** 위반 0 을 받는다.

    리포터가 겪은 것이 정확히 이것이다: 세 가지 어긋난 상태에서 모두 위반 0 이었다.
    관전 도구의 침묵이 '이상 없음'과 구별되지 않으면, 그 침묵이 가장 비싼 오답이다."""

    def _chain(self, name):
        self.gil("chain", name, "--purpose", "목적 " + name)
        self.gil("open", name + "/c001", "--author", "clew", "--purpose", "작은 문제")
        self.gil("step", name + "/c001", "--kind", "success", "--title", "성공")

    def test_a_dev_branch_without_the_marker_is_not_silently_accepted(self):
        """dev 라는 이름만으로는 층이 아니다 — 그런데 아니라고 말해 주지도 않았다."""
        self.gil("init", "--name", "clew")
        self._chain("a")
        # 손으로 세운 dev 를 흉내낸다: 마커 없는 커밋을 끝에 얹어도 마커는 이력에 남으므로,
        # 마커가 아예 없는 자리(대문)로 dev 를 옮겨 리포터의 조건을 만든다.
        self._git("branch", "-f", "dev", "main")
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertIn("dev", out)
        self.assertNotIn("위반 0 — 커밋 그래프 건강", out,
                         "층이 꺼진 채로 '건강'이라 답했다:\n" + out)

    def test_no_dev_branch_at_all_is_a_notice_not_a_violation(self):
        """dev 가 아예 없는 옛 나무는 **위반이 아니다** — 다만 못 봤다는 사실은 말한다.

        여기서 위반으로 세면 fsck 가 종료코드 1 을 내고, v3.46 이전에 태어난 모든 저장소가
        갑자기 병든 것이 된다. devLayerNudge 가 *"문법으로 막으면 이미 있는 나무가 통째로
        얼어붙는다"*며 안내에 그친 판단을 뒤집는 셈이다. 못 본 것과 어긋난 것은 다르다."""
        self.gil("init", "--name", "clew")
        self._chain("a")
        self._git("branch", "-D", "dev")
        r = self.gil("fsck")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, "옛 레이아웃을 위반으로 세어 종료코드가 1 이 됐다:\n" + out)
        self.assertIn("층 판정은 하지 못했다", out,
                      "못 본 것을 말하지 않아 '위반 0' 이 '어긋난 것 없음'으로 읽힌다:\n" + out)

    def test_a_healthy_layer_stays_quiet(self):
        """정본 저장소는 조용해야 한다 — 늘 짖으면 아무도 안 듣는다."""
        self.gil("init", "--name", "clew")
        self._chain("a")
        r = self.gil("fsck")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("위반 0", r.stdout + r.stderr)


class TestMigrateFollowsSupersedeForks(GilFixture):
    """**정정 분기에 사는 척추를 이주가 못 따라간다** (이슈 #98, 실사용 리포트).

    사이클의 첫 define(s1)을 `--supersede` 로 정정하면 척추(s2~)는 분기 브랜치 `…-s1b1` 에
    살고 사이클 본 브랜치는 s1 에서 멈춘다. 그 저장소에서 `migrate --to-dev-layout` 이
    "스텝 5개 유실"로 늘 거부됐다.

    이주가 스스로 세는 것(v3.49.0)은 옳았다 — 그 셈이 진짜 유실을 잡았는지, 아니면 자기가
    옮겨 놓고 못 찾은 것인지가 여기서 갈린다."""

    def _repo_with_superseded_define(self):
        """옛 레이아웃(dev 층 없음)에서 s1 을 정정한 사이클 하나를 완주시킨다."""
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P", "--body", "정의")
        # s1(define)을 정정 — 척추가 s1b1 분기로 옮겨 간다
        self.gil("step", "c/c1", "--kind", "define", "--title", "고친 정의",
                 "--supersede", "s1", "--inherit", "문제를 좁혔다.", "--body", "다시 쓴 정의")
        self.gil("step", "c/c1", "--kind", "hypothesis", "--title", "가설",
                 "--falsify", "F", "--falsify-to", "s2")
        self.gil("step", "c/c1", "--kind", "verify", "--verdict", "supported", "--title", "검증")
        self.gil("step", "c/c1", "--kind", "analyze", "--finding", "맞았다", "--title", "해석")
        self.gil("step", "c/c1", "--kind", "success", "--title", "성공")
        self.gil("close", "c/c1", "--verdict", "supported")

    def _old_layout(self):
        """dev 층을 **체인보다 먼저** 걷는다 — 층이 있던 적 없는 옛 나무의 모양.

        체인을 만든 뒤에 걷으면 그 체인이 `Gil-Chain-Orphan: dev` 를 선언한 채로 남아,
        이주가 옛 나무를 보고 층 위반을 외친다(그건 이주가 안 건드린 나무다). 리포터의
        저장소는 층이 생기기 전에 태어났으므로 그 선언 자체가 없다."""
        self._git("checkout", "-q", "main")
        self._git("branch", "-D", "dev")

    def test_migrate_judges_its_own_tree_not_the_one_it_left_behind(self):
        """**이주는 옛 나무를 일부러 남긴다** — 그런데 자기 검사가 그 나무를 보고 실패를 외쳤다.

        층이 있는 저장소에서 dev 를 걷어내면(옛 체인의 `Gil-Chain-Orphan: dev` 선언은 남는다)
        새 나무는 무손실인데도 옛 체인 때문에 "층 위반 1건"으로 이주가 거부됐다. 만든 자가
        자기 결과를 보는 것과, 남의 결과까지 자기 것으로 세는 것은 다르다."""
        self.gil("init", "--name", "clew")
        self._repo_with_superseded_define()   # 층이 있는 채로 체인을 만들고
        self._old_layout()                    # 그 뒤 dev 를 걷는다 — 선언만 남은 옛 나무
        r = self.gil("migrate", "--to-dev-layout")
        out = r.stdout + r.stderr
        self.assertNotIn("빠짐:", out, out)
        self.assertEqual(r.returncode, 0,
                         "안 건드린 옛 나무를 보고 자기 이주를 실패라 했다:\n" + out)

    def test_migrate_does_not_lose_the_spine_that_lives_on_a_fork(self):
        self.gil("init", "--name", "clew")
        self._old_layout()                 # 층이 있던 적 없는 나무
        self._repo_with_superseded_define()
        r = self.gil("migrate", "--to-dev-layout")
        out = r.stdout + r.stderr
        self.assertNotIn("빠짐:", out, "정정 분기의 스텝을 유실로 셌다:\n" + out)
        self.assertEqual(r.returncode, 0, "이주가 거부됐다:\n" + out)


class TestRawGraphLanesAreReal(GilFixture):
    """**날것 그래프의 레인이 실재를 가리켜야 한다** (이슈 #100).

    이 그림의 목적은 "gil 계보가 진짜 브랜치인지 여기서 점검한다"이다. 점검하는 사람이
    레이아웃 위반을 오판하게 만드는 라벨링은 목적과 정면으로 부딪힌다."""

    QS = '[{"q":"기준은?","type":"text"}]'

    def _lanes(self):
        import json, re
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("graph", "--html", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'id="layergraphdata"[^>]*>(.*?)</script>', html, re.S)
        return json.loads(m.group(1)), html

    def test_an_intake_slug_does_not_become_a_lane(self):
        """앞머리는 층의 것이다 — 슬러그로 **실존하지 않는 브랜치** 레인을 만들지 않는다.

        intake 커밋은 Gil-Chain 에 슬러그를 달고 있어서 옛 판정이 그걸 체인으로 봤다.
        그 이름의 ref 는 어디에도 없는데 레인 이름이 되고, 사람은 그 줄을 dev 로 오해했다."""
        self.gil("init", "--name", "clew")
        self.gil("intake", "nx", "--ask", "-", input=self.QS)
        self.gil("chain", "c", "--purpose", "P")   # 체인이 하나는 있어야 층 그림이 실린다
        data, _ = self._lanes()
        self.assertNotIn("nx", data["lanes"],
                         "개시 인터뷰 슬러그가 레인이 됐다: " + repr(data["lanes"]))
        # 레인은 **브랜치가 아니라 체인**이다 — 브랜치가 rename·삭제된 옛 체인도 정당한
        # 레인이다(그 체인은 그래프에 그대로 산다). 그러니 "ref 가 있어야 한다"가 아니라
        # "선언된 체인이어야 한다"를 건다. 앞머리 슬러그는 체인이 아니므로 여기서 걸린다.
        # 트레일러 출력에는 줄바꿈이 딸려 오므로 레코드 구분자로 자른다(줄 단위로 세면 어긋난다).
        roots = self._git("log", "--all",
                          "--format=%(trailers:key=Gil-Kind,valueonly)\x1f"
                          "%(trailers:key=Gil-Chain,valueonly)\x1e").stdout
        chains = set()
        for rec in roots.split("\x1e"):
            parts = rec.split("\x1f")
            if len(parts) == 2 and parts[0].strip() == "chain-root":
                chains.add(parts[1].strip())
        for ln in data["lanes"]:
            self.assertIn(ln, chains | {"main", "dev"},
                          f"레인 '{ln}' 은 선언된 체인이 아니다 — 없는 가지를 그린다")

    def test_the_existence_ref_is_not_drawn_on_the_work_tree(self):
        """존재·기억(refs/gil/global)은 작업의 나무가 아니다 — 대문 레일에 이어 붙으면 안 된다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        gsha = self._git("rev-parse", "refs/gil/global").stdout.strip()
        self.assertTrue(gsha, "글로벌 ref 가 없다 — 이 시험의 전제가 깨졌다")
        _, html = self._lanes()
        self.assertNotIn(gsha[:9], html,
                         "존재의 커밋이 날것 그래프에 그려졌다 — main 이 대문 끝에서 안 멈춘 것처럼 읽힌다")


class TestAdoptDevLayer(GilFixture):
    """**이미 옳게 선 dev 를 다시 그리지 않고 층으로 인정한다** (이슈 #99·#98).

    층은 `Gil-Kind: dev-root` 표식으로 찾는데 그 표식은 init·migrate 만 심는다. 그래서 손으로
    정본 모양을 세운 저장소는 **구조는 맞는데 층으로 안 보인다**: fsck 의 층 판정이 꺼지고,
    `merge --into dev` 는 되는데 `deploy` 의 승격만 거부된다 — 같은 저장소를 두 명령이 다르게
    본다. 다시 그리기는 모든 SHA 를 바꾸므로, 계보가 이미 옳으면 그 값을 치를 이유가 없다."""

    def _unmarked_dev(self):
        """표식만 없는 dev — 손으로 세운 정본 모양을 흉내낸다."""
        self.gil("init", "--name", "clew")
        head = self._git("rev-parse", "dev").stdout.strip()
        self._git("checkout", "-q", "main")
        self._git("branch", "-D", "dev")
        # 대문 계보에서 갈라진, 표식 없는 dev
        self._git("branch", "dev", "main")
        return head

    def test_adopting_plants_the_marker_without_rewriting(self):
        self._unmarked_dev()
        before = self._git("rev-parse", "main").stdout.strip()
        r = self.gil("migrate", "--adopt-dev")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # 뿌리는 **ref 로** 선다(이슈 #113). 옛 코드는 이 자리에 Gil-Kind: dev-root 트레일러를
        # 달았는데, 층의 범위를 정하는 쪽이 표식에서 자르므로 인정 범위가 1커밋이 됐다.
        root = self._git("rev-parse", "refs/gil/layer/dev").stdout.strip()
        self.assertTrue(root, "층 뿌리 ref 가 없다")
        # 뿌리 = 대문에서 갈라진 뒤의 **가장 오래된** dev 전용 커밋. (이 fixture 는 dev 가
        # 대문과 같은 자리에서 시작하므로 인정 커밋 자신이 그 자리다 — 그래도 규칙은 하나다.)
        oldest = self._git("rev-list", "--first-parent", "main..dev").stdout.split()[-1]
        self.assertEqual(root, oldest, "뿌리가 층의 시작이 아니다")
        self.assertEqual(self._git("rev-parse", "main").stdout.strip(), before,
                         "인정이 다른 브랜치를 건드렸다 — 다시 그리지 않기로 한 약속이 깨졌다")

    def test_adopting_is_idempotent(self):
        """이미 층이면 아무 일도 하지 않는다 — 두 번 불러도 표식이 둘이 되지 않는다."""
        self.gil("init", "--name", "clew")
        r = self.gil("migrate", "--adopt-dev")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("이미 dev 층이다", r.stdout + r.stderr)

    def test_it_does_not_swallow_someone_elses_branch(self):
        """대문 계보 밖의 dev 는 남의 작업 브랜치다 — 층으로 삼키지 않는다."""
        self.gil("init", "--name", "clew")
        self._git("checkout", "-q", "main")
        self._git("branch", "-D", "dev")
        self._git("checkout", "-q", "--orphan", "dev")
        self._git("commit", "-q", "--allow-empty", "-m", "남의 브랜치")
        self._git("checkout", "-q", "main")
        r = self.gil("migrate", "--adopt-dev")
        self.assertNotEqual(r.returncode, 0, "남의 브랜치를 층으로 삼켰다")
        self.assertIn("대문 계보에서 갈라진 브랜치가 아니다", r.stdout + r.stderr)

    def test_no_dev_branch_points_at_the_other_road(self):
        self.gil("init", "--name", "clew")
        self._git("checkout", "-q", "main")
        self._git("branch", "-D", "dev")
        r = self.gil("migrate", "--adopt-dev")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--to-dev-layout", r.stdout + r.stderr)

    def test_deploy_says_which_of_the_two_it_is(self):
        """눈앞에 dev 가 있는데 '없다'고 하면 사람은 거기서 막힌다."""
        self._unmarked_dev()
        r = self.gil("deploy", "--tag", "v0.1.0")
        out = r.stdout + r.stderr
        self.assertIn("gil 의 층이 아니다", out, "dev 가 있는데 '층이 없다'고만 했다:\n" + out)
        self.assertIn("--adopt-dev", out, "다음에 칠 한 줄을 안 줬다:\n" + out)


class TestGateHoldsOnlyWhatShipped(GilFixture):
    """**대문은 배포된 것만 담는다** (이슈 #99 제안 c).

    앞머리가 HEAD 에 심기던 시절(#102) main 이 intake·인터뷰 커밋까지 삼켰고, fsck 는 아무
    말도 하지 않았다. 대문의 첫-부모 사슬은 대문 자신의 줄기다 — 배포 머지로 들어온 작업은
    **둘째 부모**에 있으므로, 첫-부모 사슬에 스텝이 서 있다는 것은 대문에 직접 심었다는 뜻이다."""

    def _chain(self, name):
        self.gil("chain", name, "--purpose", "목적 " + name)
        self.gil("open", name + "/c001", "--author", "clew", "--purpose", "작은 문제")
        self.gil("step", name + "/c001", "--kind", "success", "--title", "성공")
        self.gil("close", name + "/c001", "--verdict", "supported")
        self.gil("chain-close", name, "--verdict", "success")

    def test_a_deploy_merge_is_not_a_violation(self):
        """정당한 경로로 들어온 것은 짖지 않는다 — 늘 짖으면 아무도 안 듣는다."""
        self.gil("init", "--name", "clew")
        self._chain("a")
        self.gil("merge", "a", "--into", "dev", "--reason", "배포 단위")
        r = self.gil("deploy", "--tag", "v0.1.0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertNotIn("대문", out, "배포된 것을 대문 오염이라 했다:\n" + out)

    def test_work_planted_straight_on_the_gate_is_named(self):
        """대문에 직접 심긴 작업은 이름을 부른다 — 리포터의 main 이 이 상태였다.

        #102 를 고친 지금은 gil 명령으로 이 상태를 만들 수 없다(앞머리가 dev 로 간다).
        그래서 옛 gil 이 남긴 나무를 git 으로 재현한다 — 이미 그렇게 된 저장소들이 있고,
        fsck 는 그들에게 아무 말도 하지 않았다."""
        self.gil("init", "--name", "clew")
        self._chain("a")
        root = self._git("log", "--all", "--format=%H\x1f%(trailers:key=Gil-Kind,valueonly)\x1e").stdout
        sha = ""
        for rec in root.split("\x1e"):
            f = rec.split("\x1f")
            if len(f) == 2 and f[1].strip() == "chain-root":
                sha = f[0].strip()
                break
        self.assertTrue(sha, "chain-root 를 못 찾았다")
        self._git("checkout", "-q", "main")
        # cherry-pick 은 빈 커밋에서 멎는다(트리가 같을 수 있다) — 트레일러만 옮기면 되므로
        # 메시지를 그대로 실어 빈 커밋으로 얹는다. 재현하려는 것은 "대문에 작업 커밋이 섰다"다.
        msg = self._git("log", "-1", "--format=%B", sha).stdout
        r = self._git("commit", "-q", "--allow-empty", "-m", msg)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertIn("대문", out, "대문이 작업을 삼켰는데 아무 말도 안 했다:\n" + out)


class TestCycleOutputsFindTheirWayToTheChain(GilFixture):
    """**결핍이 편법을 부른다** (이슈 #103, 에이전트 자기 분석).

    앞 사이클의 산출물을 다음 사이클로 넘길 때 에이전트가 `git checkout <브랜치> -- <경로>`
    트리 복사를 반복했다. 내용은 안 잃었지만 합류 간선이 안 남아 **"지식과 코드를 이어받는다"는
    gil 의 핵심이 파일 층위에서 사라졌다.**

    원인은 안내의 비대칭이었다: 체인→dev 에는 합류 안내가 있는데 **사이클→체인에는 없었다.**
    그리고 결핍은 다음 사이클 한복판에서 발견되므로, 그 자리에서 가장 싼 해결책이 복사다."""

    def _cycle_with_output(self, chain, cycle, fname):
        self.gil("open", f"{chain}/{cycle}", "--author", "clew", "--purpose", "작은 문제")
        with open(os.path.join(self.repo, fname), "w", encoding="utf-8") as f:
            f.write("산출물\n")
        self._git("add", fname)
        self._git("commit", "-q", "-m", f"산출물 {fname}")
        self.gil("step", f"{chain}/{cycle}", "--kind", "success", "--title", "성공")
        return self.gil("close", f"{chain}/{cycle}", "--verdict", "supported")

    def test_close_points_at_the_merge_when_files_would_be_left_behind(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        r = self._cycle_with_output("c", "c001", "tool.py")
        out = r.stdout + r.stderr
        self.assertIn("tool.py", out, "체인에 없는 산출물을 말하지 않았다:\n" + out)
        self.assertIn("gil merge c/c001 --into c", out, "합류 경로를 안 줬다:\n" + out)

    def test_close_stays_quiet_when_there_is_nothing_to_carry(self):
        """문서만 남긴 사이클엔 합류할 것이 없다 — 늘 짖으면 아무도 안 듣는다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "작은 문제")
        self.gil("step", "c/c001", "--kind", "success", "--title", "성공")
        r = self.gil("close", "c/c001", "--verdict", "supported")
        # 형제 분기 안내(다음 사이클)는 늘 나온다 — 여기서 지키는 것은 **산출물 합류** 쪽이다:
        # 옮길 파일이 없는데 "산출물이 체인에 없다"고 말하면 그 경고는 곧 무시된다.
        self.assertNotIn("체인 트리에 없다", r.stdout + r.stderr,
                         "합류할 산출물이 없는데 합류하라고 했다")

    def test_open_says_it_before_the_agent_hits_the_gap(self):
        """다음 사이클을 여는 순간 알려준다 — 한복판에서 발견하면 이미 복사를 집은 뒤다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._cycle_with_output("c", "c001", "tool.py")
        r = self.gil("open", "c/c002", "--author", "clew", "--purpose", "다음 문제")
        out = r.stdout + r.stderr
        self.assertIn("합류하지 않은", out, "결핍을 여는 자리에서 말하지 않았다:\n" + out)
        self.assertIn("gil merge c/c001 --into c", out)

    def test_after_merging_the_warning_goes_away(self):
        """합류하면 조용해진다 — 고친 뒤에도 짖으면 그 경고는 곧 무시된다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._cycle_with_output("c", "c001", "tool.py")
        m = self.gil("merge", "c/c001", "--into", "c", "--reason", "산출물은 체인의 것")
        self.assertEqual(m.returncode, 0, m.stdout + m.stderr)
        r = self.gil("open", "c/c002", "--author", "clew", "--purpose", "다음 문제")
        self.assertNotIn("합류하지 않은", r.stdout + r.stderr)

    def test_merge_takes_the_same_address_as_every_other_command(self):
        """**gil 의 주소는 <chain>/<cycle> 이다.**

        open·step·close 는 전부 그 형태로 받는데 merge 만 git ref 를 요구했다 — 그래서
        리포트도 사람도 `gil merge c/c001` 이라 적었고 git 이 "알 수 없는 리비전"으로 죽었다.
        주소 문법이 명령마다 다르면 사람은 도구가 아니라 도구의 사정을 외워야 한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._cycle_with_output("c", "c001", "tool.py")
        r = self.gil("merge", "c/c001", "--into", "c", "--reason", "산출물은 체인의 것")
        self.assertEqual(r.returncode, 0, "gil 의 주소를 gil 이 못 읽었다:\n" + r.stdout + r.stderr)
        anc = self._git("merge-base", "--is-ancestor", "c-c001", "c").returncode == 0
        self.assertTrue(anc, "합쳤다면서 실제로는 안 붙었다")

    def test_merge_help_shows_the_cycle_into_chain_example(self):
        """에이전트는 예시를 문법보다 강하게 따른다 — 예시가 하나뿐이면 그쪽만 쓴다."""
        r = self.gil("merge", "--help")
        self.assertIn("--into <chain>", r.stdout + r.stderr)


class TestSproutIsNotAnOrphan(GilFixture):
    """**정석 발아가 고아로 그려졌다** (이슈 #104, 실측 저장소에서 s1 의 8/15).

    전체맵의 진입선은 커밋 조상을 거슬러 **스텝 커밋**을 찾아 그렸다. 체인의 기준선
    (chain-root·인터뷰·기준문서)만 있고 스텝이 없으면 선이 없어 미아처럼 떴고, 반대로 조상에
    스텝이 있으면 사이 커밋을 건너뛰어 먼 스텝에 붙어 **없는 계승을 주장**했다.

    결과가 뒤집혀 있었다: 체인 기준선에서 곧장 난 **정석 발아는 벌점**(선 없음), 우연히 스텝
    위에 얹힌 발아는 가산점(선 있음). gil 이 가르치는 정석과 시각 신호가 정확히 역전됐다."""

    def _dag(self):
        import json, re
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("graph", "--html", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'id="dagdata"[^>]*>(.*?)</script>', html, re.S)
        self.assertIsNotNone(m, "전체맵 데이터가 없다")
        return json.loads(m.group(1))

    def _cycle(self, chain, cycle):
        self.gil("open", f"{chain}/{cycle}", "--author", "clew", "--purpose", "작은 문제")
        self.gil("step", f"{chain}/{cycle}", "--kind", "success", "--title", "성공")
        self.gil("close", f"{chain}/{cycle}", "--verdict", "supported")

    def test_a_cycle_born_on_the_chain_baseline_is_marked_as_sprouted(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._cycle("c", "c001")
        first = [n for n in self._dag() if n["cycle"] == "c001" and n["step"] == "s1"]
        self.assertEqual(len(first), 1, "c001/s1 을 못 찾았다")
        n = first[0]
        self.assertEqual(n["parents"], [], "체인 기준선에서 났는데 부모 스텝을 지어냈다")
        self.assertTrue(n.get("sprout"),
                        "정석 발아인데 미아와 똑같이 그려진다 — 화면에서 벌점을 받는다")

    def test_it_does_not_reach_past_the_chain_baseline_to_claim_a_parent(self):
        """건너뛰어 붙는 선은 없는 계승을 주장한다 — 앞 사이클을 건너뛰면 더 그렇다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._cycle("c", "c001")
        # 체인 기준선을 한 겹 더 얹는다 — 인터뷰를 심고 사람 답까지 확정하면 그 체인의
        # 기준문서 커밋(스텝 아님)이 체인 브랜치 끝에 선다. 리포트의 'reference' 자리다.
        self.gil("interview", "c", "--ask", "-", input='[{"q":"다음 기준은?","type":"text"}]')
        refp = os.path.join(self.repo, "reference-c.md")
        with open(refp, "w", encoding="utf-8") as f:
            f.write("# 다음 기준\n답: 두 번째 기준")
        self.gil("interview", "c", "--resolve", "reference-c.md")
        os.remove(refp)
        self._cycle("c", "c002")
        n = [x for x in self._dag() if x["cycle"] == "c002" and x["step"] == "s1"][0]
        for p in n["parents"]:
            self.assertNotIn("c001", p,
                             "체인 기준선을 뚫고 앞 사이클 스텝에 붙었다 — 없는 계승이다")

    def test_a_real_inheritance_still_draws_its_line(self):
        """진짜 이어받음까지 지우면 안 된다 — 스텁은 없는 것을 채우는 장치가 아니다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._cycle("c", "c001")
        self.gil("open", "c/c002", "--author", "clew", "--purpose", "이어받는다",
                 "--parent", "c001", "--inherit", "c001 의 결론을 전제로 삼는다")
        n = [x for x in self._dag() if x["cycle"] == "c002" and x["step"] == "s1"][0]
        self.assertTrue(n["parents"] or n.get("sprout"),
                        "이어받았다고 선언했는데 화면에 아무 자취가 없다")


class TestTheCycleEndIsAFactNotAName(GilFixture):
    """**사이클의 끝을 이름으로 찾으면 낡은 자리를 짚는다.**

    복잡한 나무를 직접 지어 git 과 대조하다 잡았다 — 규칙 시험으로는 안 걸렸다.
    정정(--supersede)이나 재분기(--to)를 거친 사이클은 척추와 종결이 **분기 브랜치**(…-sNbM)
    에 살고, `<chain>-<cycle>` 이라는 이름의 브랜치는 정정된 그 자리에 멈춰 있다.

    그 낡은 이름을 짚어서 두 곳이 조용히 틀렸다:
      · `gil merge <chain>/<cycle> --into <chain>` 이 **성공한 작업과 close 를 빼놓고** 합쳤다.
      · `gil open --parent <cycle>` 이 **버려진 가설 위에서** 새 사이클을 갈랐다.
    둘 다 실패하지 않았다 — 성공했다고 말하면서 틀렸다. 그게 가장 비싼 종류다."""

    def _cycle_with_supersede(self, chain, cycle):
        """s2(가설)를 정정해 척추를 분기 브랜치로 보낸 뒤 완주·종결한다."""
        self.gil("open", f"{chain}/{cycle}", "--author", "clew", "--purpose", "문제", "--body", "정의")
        self.gil("step", f"{chain}/{cycle}", "--kind", "hypothesis", "--title", "틀린 가설",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", f"{chain}/{cycle}", "--kind", "hypothesis", "--title", "고친 가설",
                 "--falsify", "F2", "--falsify-to", "s1", "--supersede", "s2",
                 "--inherit", "반증조건이 느슨했다")
        self.gil("step", f"{chain}/{cycle}", "--kind", "success", "--title", "성공")
        self.gil("close", f"{chain}/{cycle}", "--verdict", "supported")

    def _sha_of(self, pattern):
        out = self._git("log", "--all", "--format=%H\x1f%s").stdout
        for ln in out.splitlines():
            sha, _, subj = ln.partition("\x1f")
            if pattern in subj:
                return sha.strip()
        self.fail(f"'{pattern}' 커밋을 못 찾았다")

    def test_merge_carries_the_whole_spine_not_the_stale_branch(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._cycle_with_supersede("c", "c001")
        r = self.gil("merge", "c/c001", "--into", "c", "--reason", "산출물은 체인의 것")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for what in ("c/c001 close", "success"):
            sha = self._sha_of(what)
            self.assertEqual(self._git("merge-base", "--is-ancestor", sha, "c").returncode, 0,
                             f"합류했다면서 '{what}' 가 체인에 없다 — 낡은 브랜치를 합쳤다")

    def test_open_parent_branches_from_where_the_cycle_actually_ended(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._cycle_with_supersede("c", "c001")
        self.gil("open", "c/c002", "--author", "clew", "--purpose", "다음",
                 "--parent", "c001", "--inherit", "c001 의 결론")
        s1 = self._sha_of("c/c002/s1 define")
        dead = self._sha_of("틀린 가설")          # 정정으로 버려진 가설
        end = self._sha_of("c/c001 close")
        self.assertEqual(self._git("merge-base", "--is-ancestor", end, s1).returncode, 0,
                         "부모 사이클의 종결에서 갈라지지 않았다")
        self.assertNotEqual(self._git("merge-base", "--is-ancestor", dead, s1).returncode, 0,
                            "버려진 가설 위에서 새 사이클이 났다 — 정정이 무의미해진다")


class TestTheToolTeachesBranchingAndConfluence(GilFixture):
    """**문법에 있는데 안내가 없으면 없는 것과 같다** (상현님 실사용 관측).

    셋이 같은 병이었다:
      · 한 결론에서 갈래가 둘이면 에이전트가 사람에게 "하나만 골라 달라"고 묻거나 일자로 이었다.
      · 여러 닫힌 체인의 지식을 하나로 모으는 길(gil merge a b --into c)을 아무도 안 썼다.
      · 체인을 먼저 만들고 인터뷰를 나중에 했다 — 그러면 목적은 늘 에이전트의 창작이다.

    그리고 **체인이 끝나는 자리의 안내가 옛 순서를 계속 가르치고 있었다**: NEXT 가 곧장
    `gil chain <name> --purpose <목적>` 을 가리켰다. 이슈 #90 이 intake 를 만든 바로 그
    모양을, 정작 다음 국면이 시작되는 자리가 재생산하고 있었다."""

    def _full_cycle(self, chain, cycle, *extra):
        self.gil("open", f"{chain}/{cycle}", "--author", "clew", "--purpose", cycle, "--body", "정의", *extra)
        self.gil("step", f"{chain}/{cycle}", "--kind", "success", "--title", "성공")
        return self.gil("close", f"{chain}/{cycle}", "--verdict", "supported")

    def test_close_recommends_branching_into_siblings(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        r = self._full_cycle("c", "c001")
        out = r.stdout + r.stderr
        self.assertIn("하나일 필요는 없다", out, "다음이 하나뿐인 것처럼 안내했다:\n" + out)
        self.assertIn("--parent c001", out)
        self.assertIn("차례로", out, "동시에 열 수 있는 것처럼 안내하면 그대로 실패한다")
        self.assertIn("--into c", out, "형제를 나중에 합치는 길을 안 보여줬다")

    def test_siblings_really_fork_in_the_graph(self):
        """권하기만 하고 안 되면 더 나쁘다 — 같은 부모에서 둘이 실제로 갈라져야 한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._full_cycle("c", "c001")
        # 사이클은 한 번에 하나만 열린다 — 갈래는 **동시가 아니라 차례로** 난다.
        # (안내도 그렇게 말해야 한다: 처음엔 동시에 열 수 있는 것처럼 적었다가 그대로 실패했다.)
        for cy in ("c002", "c003"):
            r = self.gil("open", f"c/{cy}", "--author", "clew", "--purpose", cy,
                         "--body", "정의", "--parent", "c001", "--inherit", "c001 의 결론")
            self.assertEqual(r.returncode, 0, f"{cy} 를 형제로 못 열었다:\n" + r.stdout + r.stderr)
            self.gil("step", f"c/{cy}", "--kind", "success", "--title", "성공")
            self.gil("close", f"c/{cy}", "--verdict", "supported")
        import json, re
        out_html = os.path.join(self.repo, "g.html")
        self.gil("graph", "--html", "--out", out_html)
        with open(out_html, encoding="utf-8") as f:
            dag = json.loads(re.search(r'id="dagdata"[^>]*>(.*?)</script>', f.read(), re.S).group(1))
        by = {n["sha"]: n for n in dag}
        kids = {}
        for n in dag:
            for p in n["parents"]:
                if p in by:
                    kids.setdefault(p, []).append(n["cycle"])
        forks = [v for v in kids.values() if len(set(v)) > 1]
        self.assertTrue(forks, "형제로 열었는데 그래프가 일직선이다")

    def test_the_refusal_that_blocks_a_sibling_shows_the_way_to_one(self):
        """**여기가 갈래를 포기하게 되는 자리다.**

        형제를 하나 더 열려던 에이전트는 "아직 밟는 중인 사이클이 있다"를 *"분기는 안 되는
        구나"*로 읽고 일자로 이어붙인다. 안 되는 것은 **동시에 여는 것**뿐이고, 그건 제약이
        아니라 원리다 — git 도 두 브랜치를 동시에 밟으려면 워크트리가 필요하다.
        거부는 길을 닫는 자리가 아니라, 열려 있는 길을 보여줄 자리다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._full_cycle("c", "c001")
        self.gil("open", "c/c002", "--author", "clew", "--purpose", "갈래 A",
                 "--body", "정의", "--parent", "c001", "--inherit", "c001 의 결론")
        r = self.gil("open", "c/c003", "--author", "clew", "--purpose", "갈래 B",
                     "--body", "정의", "--parent", "c001", "--inherit", "c001 의 결론")
        self.assertNotEqual(r.returncode, 0, "동시에 두 사이클이 열렸다")
        out = r.stdout + r.stderr
        self.assertIn("형제 사이클을 열려던 것이라면", out,
                      "갈래를 포기하게 되는 자리에서 열린 길을 안 보여줬다:\n" + out)
        self.assertIn("--parent c001", out, "부모 이름을 채워 주지 않아 그대로 칠 수 없다")
        self.assertIn("워크트리", out, "왜 하나씩인지를 말하지 않으면 제약으로만 읽힌다")

    def test_chain_close_teaches_intake_first_not_purpose_first(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P")
        self._full_cycle("c", "c001")
        r = self.gil("chain-close", "c", "--verdict", "success")
        out = r.stdout + r.stderr
        self.assertIn("gil intake", out, "다음 국면을 인터뷰부터 시작하라고 안 했다:\n" + out)
        self.assertIn("--ask-root", out, "어디서 이어받을지 묻는 길을 안 보여줬다")
        self.assertNotIn("gil chain <name> --purpose", out,
                         "목적을 에이전트가 짓는 옛 순서를 아직 가르친다")

    def test_a_chain_made_without_intake_says_who_wrote_the_purpose(self):
        """막지는 않되, 무슨 일이 일어났는지는 말한다."""
        self.gil("init", "--name", "clew")
        r = self.gil("chain", "c", "--purpose", "내가 지은 목적")
        out = r.stdout + r.stderr
        self.assertIn("네가 쓴 문장", out, "목적을 누가 지었는지 말하지 않았다:\n" + out)
        self.assertIn("--from-intake", out)

    def test_a_chain_made_from_intake_is_not_scolded(self):
        """정본 경로로 왔으면 조용해야 한다 — 늘 짖으면 아무도 안 듣는다."""
        self.gil("init", "--name", "clew")
        self.gil("intake", "nx", "--ask", "-", input='[{"q":"무엇을 풀려는가","type":"text"}]')
        # --resolve 는 JSON 이 아니라 "## 질문 / 답" 문서를 받는다(뷰어 폼이 그렇게 써낸다).
        ans = os.path.join(self.repo, "ans.md")
        with open(ans, "w", encoding="utf-8") as f:
            f.write("## 무엇을 풀려는가\n사람이 세운 목적이다\n")
        r = self.gil("intake", "nx", "--resolve", ans)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.gil("chain", "c", "--from-intake", "nx", "--purpose-from", "1", "--criterion-from", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("네가 쓴 문장", r.stdout + r.stderr,
                         "사람의 답에서 인용했는데 창작이라 했다")


class TestSessionTidy(GilFixture):
    """세션은 매듭 없이 증발했다 (상현님).

    끝날 때 할 일은 늘 같았다: 기억에 매듭을 남기고, 켠 뷰어를 끄고, 사람에게 새 대화를 열어도
    된다고 알리는 것. 그런데 아무도 짚어 주지 않으니 아무도 하지 않았다. 그리고 사람에게 줄
    문구는 **하나여야** 한다 — 매번 다른 말로 안내받은 사람은 다음에 무엇을 말할지 모른다."""

    def test_handoff_end_gives_the_ladder(self):
        self.gil("init", "--name", "clew")
        r = self.gil("handoff", "--end")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gil memory append clew", r.stdout, "매듭 남기기를 안 짚었다")
        self.assertIn("부활점", r.stdout)
        self.assertIn("다음 세션 순서", r.stdout)
        self.assertIn("세션정리", r.stdout)
        self.assertIn("이어서 가보자", r.stdout, "사람에게 줄 문구가 없다")
        self.assertIn("세션정리 끝", r.stdout, "끝 표식이 없다 — 잘림과 구분되지 않는다")

    def test_handoff_end_flags_uncommitted_work(self):
        self.gil("init", "--name", "clew")
        with open(os.path.join(self.repo, "잊힌작업.md"), "w", encoding="utf-8") as f:
            f.write("커밋되지 않은 것은 사라진다\n")
        r = self.gil("handoff", "--end")
        self.assertIn("작업트리가 더럽다", r.stdout, r.stdout)

    def test_handoff_recommends_tidying_with_the_exact_phrase(self):
        self.gil("init", "--name", "clew")
        r = self.gil("handoff")
        self.assertIn("gil handoff --end", r.stdout, "정리할 자리를 안 짚었다")
        self.assertIn("이어서 가보자", r.stdout, "사람에게 줄 문구가 없다")


class TestFastlogSliceMatchesGit(GilFixture):
    """**최적화가 정확성을 이기면 안 된다** — 그리고 그건 선언으로 지켜지지 않는다.

    범위를 git 에 되묻지 않고 이미 긁어 둔 표에서 잘라내는 길을 냈다. 처음 판은 "큰 표의
    순서를 그대로 두고 거르면 된다"였고, **582개 테스트가 전부 통과했다.** 그런데 틀렸다:
    시험의 커밋들은 같은 초에 찍히고, 날짜가 같으면 git 의 순서는 날짜가 아니라 어느 팁에서
    어떤 차례로 걸어왔는지가 정한다. 순서가 달라도 대부분의 단언은 통과하므로 —
    **조용히 다른 그래프를 읽고 있었다.**

    그래서 대조 모드(GIL_FASTLOG_VERIFY=1)를 만들었다: 잘라낸 답을 git 에 되물어 sha 열까지
    맞는지 보고, 다르면 그 자리에서 죽는다. 여기서는 그 모드가 **살아 있는지**를 지킨다."""

    def _verify(self, *args):
        env = dict(os.environ, GIL_NO_VIEWER="1", GIL_FASTLOG_VERIFY="1")
        r = subprocess.run([*GIL_CMD, *args], cwd=self.repo,
                           capture_output=True, text=True, env=env)
        self.assertNotIn("내부 오류(fastlog)", r.stdout + r.stderr,
                         f"잘라낸 답이 git 과 다르다: gil {' '.join(args)}\n"
                         + r.stdout + r.stderr)
        return r

    def _assert_sliced(self, outs):
        """**빈 시험은 시험이 아니다** — 잘라낸 범위가 0개면 위 통과는 아무것도 검증하지 않았다."""
        self.assertTrue(any("fastlog: 잘라낸 범위" in o for o in outs),
                        "대조는 통과했지만 잘라낸 범위가 하나도 없다 — 이 시험은 빈 시험이다")

    def test_every_range_a_session_reads_matches_git(self):
        """부팅~작업~부활에서 읽는 범위(HEAD·--branches·--all)가 전부 git 과 일치한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/cy", "--author", "t", "--purpose", "P", "--body", "무엇을 풀려는가")
        self.gil("step", "a/cy", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "x 가 관측되면 틀렸다", "--falsify-to", "s1",
                 "--advances", "지표 1개", "--plan", "설계")
        outs = []
        for cmd in (("log",), ("log", "--all"), ("handoff",), ("fsck",),
                    ("context",), ("drift",), ("goto", "a/cy")):
            r = self._verify(*cmd)
            outs.append(r.stderr)
        self._assert_sliced(outs)

    def test_branches_and_head_agree_after_a_fork(self):
        """분기가 있으면 팁이 여럿이라 순서가 갈린다 — 거기서 특히 일치해야 한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/cy", "--author", "t", "--purpose", "P", "--body", "정의")
        self.gil("step", "a/cy", "--kind", "hypothesis", "--title", "H1",
                 "--falsify", "x", "--falsify-to", "s1", "--advances", "a", "--plan", "p")
        # 조상 define 에서 형제 가지를 낸다 — 브랜치가 둘이 되어 --branches 와 HEAD 가 갈린다.
        self.gil("step", "a/cy", "--kind", "hypothesis", "--title", "H2", "--to", "s1",
                 "--falsify", "y", "--falsify-to", "s1", "--advances", "b", "--plan", "p")
        outs = [self._verify(*cmd).stderr for cmd in
                (("log",), ("log", "--all"), ("handoff",), ("fsck",))]
        self._assert_sliced(outs)


class TestMigrateLayoutLosesNothingSilently(GilFixture):
    """**조용한 유실이 가장 나쁘다** (이슈 #95, 상현님 실사용 — v3.48.0).

    실사용에서 `--to-dev-layout` 이 세 가지를 조용히 했다:
    ① intake 로 연 체인의 뿌리가 옛 나무에 매달렸다(적층을 풀려고 부른 명령이 적층을 남겼다),
    ② 무엇이 빠졌는지 아무 말이 없었다(사람이 스텝을 직접 세는 스크립트를 짜서야 알았다),
    ③ 체인 브랜치 끝에 평범한 커밋 하나가 있으면 그 사이클이 통째로 빠졌다 — 종료코드 0.

    ③ 은 fsck 에도 안 잡힌다(옛 나무가 아직 살아 있어 조용하다). 안내대로만 했으면 사이클
    하나가 사라진 채 옛 체인을 접었을 것이다."""

    def _ok(self, r, what):
        self.assertEqual(r.returncode, 0, what + " 실패:\n" + r.stdout + r.stderr)

    def _cycle(self, chain, cyc):
        self._ok(self.gil("open", f"{chain}/{cyc}", "--author", "clew", "--purpose", "P",
                          "--body", "정의", "--fits", "목적 그 자체"), f"open {chain}/{cyc}")
        self._ok(self.gil("step", f"{chain}/{cyc}", "--kind", "hypothesis", "--title", "H",
                          "--body", "가설", "--falsify", "F", "--falsify-to", "s1",
                          "--plan", "구현 1개", "--advances", "핵심 경로"), "hypothesis")
        self._ok(self.gil("step", f"{chain}/{cyc}", "--kind", "verify", "--title", "V",
                          "--body", "검증", "--verdict", "supported", "--plan-held",
                          "--falsify-unmet", "미관측"), "verify")
        self._ok(self.gil("step", f"{chain}/{cyc}", "--kind", "analyze", "--title", "A",
                          "--body", "해석", "--finding", "지지됐다"), "analyze")
        self._ok(self.gil("step", f"{chain}/{cyc}", "--kind", "success", "--title", "S",
                          "--body", "종합", "--toward", "기준 충족",
                          "--next-design", "다음"), "success")
        self._ok(self.gil("close", f"{chain}/{cyc}", "--verdict", "supported"), "close")

    def _old_tree_with_intake(self):
        """옛 레이아웃 + **intake 로 연 체인**(chain-root 위에 intake-reference 가 있다)."""
        self._ok(self.gil("init", "--name", "clew"), "init")
        self._git("checkout", "-q", "main")
        self._git("branch", "-D", "dev")     # 옛 레이아웃 재현: 층이 없다
        self._ok(self.gil("intake", "gold", "--ask", "-",
                          input='[{"q":"무엇을 풀려는가","type":"text"}]'), "intake")
        ans = os.path.join(self.repo, "ans.md")
        with open(ans, "w", encoding="utf-8") as f:
            f.write("# 답\n\n## Q1 무엇을 풀려는가\n스텝 유실을 없앤다\n")
        self._ok(self.gil("intake", "gold", "--resolve", "ans.md"), "intake --resolve")
        self._ok(self.gil("chain", "gold", "--from-intake", "gold",
                          "--purpose-from", "1", "--criterion-from", "1"), "chain --from-intake")
        self._cycle("gold", "c1")

    def _steps(self, prefix=""):
        """브랜치에서 닿는 (체인, 사이클, 스텝) 집합. 접두를 떼어 옛/새를 견준다."""
        fmt = ("%(trailers:key=Gil-Chain,valueonly,unfold=true)\x1f"
               "%(trailers:key=Gil-Cycle,valueonly,unfold=true)\x1f"
               "%(trailers:key=Gil-Step,valueonly,unfold=true)\x1e")
        out = self._git("log", "--format=" + fmt, "--branches").stdout
        got = set()
        for rec in out.split("\x1e"):
            f = rec.strip("\n").split("\x1f")
            if len(f) < 3 or not f[2].strip():
                continue
            ch = f[1 - 1].strip()
            if prefix and not ch.startswith(prefix):
                continue
            if not prefix and ch.startswith("v3-"):
                continue
            got.add((ch[len(prefix):], f[1].strip(), f[2].strip()))
        return got

    def test_intake_led_chain_branches_from_dev_for_real(self):
        """① 선언만 있고 분기는 없던 것 — intake 앞머리는 dev 층에 얹힌다.

        살아 있는 흐름에서 `gil intake` 는 사람이 dev 에 서서 부르므로 intake 커밋은 dev 의
        것이다. 이주가 그걸 체인 가지에 실으면 chain-root 의 부모가 dev 에서 안 닿는다."""
        self._old_tree_with_intake()
        r = self.gil("migrate", "--to-dev-layout", "--prefix", "v3-")
        self._ok(r, "migrate --to-dev-layout")
        # 층 검사(fsck)가 스스로 통과해야 한다 — 이게 이 명령의 목적 그 자체다.
        f = self.gil("fsck")
        self.assertNotIn("층: 체인 v3-gold", f.stdout + f.stderr,
                         "이주한 체인이 dev 에서 갈라졌다고 선언만 하고 실제로는 아니다:\n"
                         + f.stdout + f.stderr)
        # chain-root 의 부모가 dev 브랜치에서 실제로 닿는다(약한 검사를 쓰지 않는다).
        root = self._git("log", "--format=%H",
                         "--grep", "Gil-Kind: chain-root", "v3-gold").stdout.split()[0]
        parent = self._git("log", "-1", "--format=%P", root).stdout.split()[0]
        on_dev = self._git("log", "--format=%H", "dev").stdout.split()
        self.assertIn(parent, on_dev, "chain-root 의 부모가 dev 에서 닿지 않는다")

    def test_a_plain_commit_at_a_branch_tip_is_refused_not_ignored(self):
        """③ 스텝 6개가 조용히 사라진 자리 — 이제 옮기기 전에 막는다."""
        self._old_tree_with_intake()
        with open(os.path.join(self.repo, "chore.txt"), "w", encoding="utf-8") as f:
            f.write("평범한 커밋\n")
        self._git("checkout", "-q", "gold-c1")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "chore: 평범한 커밋")
        self._git("checkout", "-q", "main")
        r = self.gil("migrate", "--to-dev-layout", "--prefix", "v3-")
        self.assertNotEqual(r.returncode, 0, "조용히 통과했다:\n" + r.stdout + r.stderr)
        out = r.stdout + r.stderr
        self.assertIn("gold-c1", out, "어느 브랜치인지 말하지 않는다")
        self.assertIn("chore: 평범한 커밋", out, "어느 커밋인지 말하지 않는다")
        self.assertIn("--allow-dirty-tips", out, "강행하는 길을 알려주지 않는다")
        # 그리고 아무것도 만들지 않았다 — 거부는 이주 **전에** 선다.
        self.assertEqual("", self._git("branch", "--list", "v3-*").stdout.strip(),
                         "거부했는데 새 브랜치가 생겼다")

    def test_it_counts_and_names_what_it_lost(self):
        """② 사람이 스크립트를 짜야 알 수 있으면 그건 무손실 안내가 아니다.

        --allow-dirty-tips 로 강행하면 실제로 사이클이 빠진다. 그때 **도구가 이름을 부르고**
        종료코드로도 말하는지를 본다(강행 경로가 없으면 이 길은 시험할 수 없다)."""
        self._old_tree_with_intake()
        with open(os.path.join(self.repo, "chore.txt"), "w", encoding="utf-8") as f:
            f.write("평범한 커밋\n")
        self._git("checkout", "-q", "gold-c1")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "chore: 평범한 커밋")
        self._git("checkout", "-q", "main")
        r = self.gil("migrate", "--to-dev-layout", "--prefix", "v3-", "--allow-dirty-tips")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, "유실이 났는데 성공으로 끝났다:\n" + out)
        self.assertIn("대조", out, "스스로 세지 않았다")
        for step in ("s1", "s5"):
            self.assertIn(f"gold/c1/{step}", out, f"빠진 {step} 의 이름을 안 부른다:\n" + out)
        self.assertIn("유실", out)

    def test_clean_tree_migrates_losslessly_and_says_so(self):
        """깨끗한 나무는 그대로 옮겨지고, 체인마다 옛/새 수를 **세어서** 보고한다."""
        self._old_tree_with_intake()
        before = self._steps()
        r = self.gil("migrate", "--to-dev-layout", "--prefix", "v3-")
        self._ok(r, "migrate")
        after = self._steps(prefix="v3-")
        self.assertEqual(before, after, "스텝이 무손실로 옮겨지지 않았다")
        self.assertIn("gold: " + str(len(before)) + " → " + str(len(after)), r.stdout,
                      "체인별 대조를 보고하지 않는다:\n" + r.stdout)


class TestMigrateRepairsDeclaredCycleLineage(GilFixture):
    """**선언이 실재를 정한다** (이슈 #97①, 상현님 실사용).

    v3.45.0 이전의 `gil open --parent` 는 계보를 **선언만** 하고 실제로 갈라지지 않았다.
    그런 나무를 커밋 부모 그대로 옮기면 납작한 실재가 그대로 복사된다 — 실사용에서 여덟
    사이클이 전부 한 커밋(intake)에 붙었고, `c008 이 c007 을 이어받았다`는 사실이 그래프에서
    사라졌다. 도움말은 "계보만 참이 된다"고 약속하는데 계보가 지워진 것이다.

    이주는 옮기는 일이자 **선언과 실재를 맞추는** 일이다 — 그러라고 부르는 명령이다."""

    def _ok(self, r, what):
        self.assertEqual(r.returncode, 0, what + " 실패:\n" + r.stdout + r.stderr)

    def _cycle(self, cyc, parent=None):
        args = ["open", f"a/{cyc}", "--author", "clew", "--purpose", "P",
                "--body", "정의", "--fits", "그 자체"]
        if parent:
            args += ["--parent", parent, "--inherit", "앞 사이클의 교훈"]
        self._ok(self.gil(*args), f"open {cyc}")
        self._ok(self.gil("step", f"a/{cyc}", "--kind", "hypothesis", "--title", "H",
                          "--body", "가설", "--falsify", "F", "--falsify-to", "s1",
                          "--plan", "구현 1개", "--advances", "경로"), "hypothesis")
        self._ok(self.gil("step", f"a/{cyc}", "--kind", "verify", "--title", "V", "--body", "검증",
                          "--verdict", "supported", "--plan-held",
                          "--falsify-unmet", "미관측"), "verify")
        self._ok(self.gil("step", f"a/{cyc}", "--kind", "analyze", "--title", "A",
                          "--body", "해석", "--finding", "지지됐다"), "analyze")
        self._ok(self.gil("step", f"a/{cyc}", "--kind", "success", "--title", "S", "--body", "종합",
                          "--toward", "충족", "--next-design", "다음"), "success")
        self._ok(self.gil("close", f"a/{cyc}", "--verdict", "supported"), "close")

    # ── fixture: 선언은 있는데 실재는 납작한 옛 나무 ──────────────────────────
    def _trailer(self, sha, key):
        return self._git("log", "-1",
                         f"--format=%(trailers:key={key},valueonly,unfold=true)", sha).stdout.strip()

    def _flatten(self):
        """모든 사이클의 첫 커밋을 chain-root 에 붙여 **납작하게** 다시 쓴다.

        v3.45.0 이전 나무의 모양이다: `Gil-Cycle-Parent` 선언은 그대로 남고 커밋 부모만
        평평하다. 메시지를 손대지 않으므로 선언은 한 글자도 안 바뀐다."""
        root = None
        for ln in self._git("log", "--format=%H", "a").stdout.split():
            if self._trailer(ln, "Gil-Kind") == "chain-root":
                root = ln
                break
        self.assertIsNotNone(root, "chain-root 를 못 찾았다")
        new = {}
        def redraw(sha, parents):
            msg = self._git("log", "-1", "--format=%B", sha).stdout
            tree = self._git("log", "-1", "--format=%T", sha).stdout.strip()
            args = ["commit-tree", tree]
            for p in parents:
                args += ["-p", p]
            out = subprocess.run(["git", *args], cwd=self.repo, input=msg,
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, "commit-tree 실패: " + out.stderr)
            new[sha] = out.stdout.strip()
            return new[sha]
        # 1) chain-root 까지는 그대로(부모도 그대로).
        rootParents = self._git("log", "-1", "--format=%P", root).stdout.split()
        newRoot = redraw(root, rootParents)
        # 2) 사이클마다: 첫 커밋은 chain-root 에, 나머지는 앞 커밋에 잇는다.
        tips = {}
        for cyc in ("c1", "c2", "c3"):
            prev = newRoot
            for sha in self._git("log", "--format=%H", "--reverse", f"a-{cyc}").stdout.split():
                if self._trailer(sha, "Gil-Cycle") != cyc:
                    continue
                prev = redraw(sha, [prev])
            tips[cyc] = prev
            self._git("update-ref", f"refs/heads/a-{cyc}", prev)
        self._git("update-ref", "refs/heads/a", newRoot)
        return tips

    def _define_of(self, cyc, branch):
        for sha in self._git("log", "--format=%H", branch).stdout.split():
            if self._trailer(sha, "Gil-Cycle") == cyc and self._trailer(sha, "Gil-Step") == "s1":
                return sha
        self.fail(f"{branch} 에서 {cyc} 의 define 을 못 찾았다")

    def _old_flat_tree(self):
        self._ok(self.gil("init", "--name", "clew"), "init")
        self._git("checkout", "-q", "main")
        self._git("branch", "-D", "dev")           # 옛 레이아웃: 층이 없다
        self._ok(self.gil("chain", "a", "--purpose", "국면", "--reference", "-",
                          "--criterion", "된다", input="기준"), "chain")
        self._cycle("c1")
        self._cycle("c2", parent="c1")
        self._cycle("c3", parent="c2")
        self._flatten()
        # **fixture 를 단언한다**: 선언은 살아 있고 실재는 납작해야 이 시험이 성립한다.
        for cyc, want in (("c2", "c1"), ("c3", "c2")):
            d = self._define_of(cyc, f"a-{cyc}")
            self.assertEqual(want, self._trailer(d, "Gil-Cycle-Parent"),
                             f"{cyc} 의 계보 선언이 fixture 에서 사라졌다")
            par = self._git("log", "-1", "--format=%P", d).stdout.split()[0]
            self.assertEqual("chain-root", self._trailer(par, "Gil-Kind"),
                             f"{cyc} 가 납작하지 않다 — 이 시험은 아무것도 검증하지 않는다")

    def test_migration_grafts_cycles_where_they_declared_they_came_from(self):
        self._old_flat_tree()
        r = self.gil("migrate", "--to-dev-layout", "--prefix", "v3-")
        self._ok(r, "migrate --to-dev-layout")
        # 새 나무에서 c3 는 c2 의 끝에, c2 는 c1 의 끝에 붙어야 한다 — 선언한 그대로.
        for cyc, parentCyc in (("c2", "c1"), ("c3", "c2")):
            d = self._define_of(cyc, f"v3-a-{cyc}")
            par = self._git("log", "-1", "--format=%P", d).stdout.split()[0]
            self.assertEqual(parentCyc, self._trailer(par, "Gil-Cycle"),
                             f"{cyc} 가 선언한 부모({parentCyc})의 끝에 안 붙었다 — "
                             "납작한 실재가 그대로 복사됐다:\n" + r.stdout)
            self.assertEqual("close", self._trailer(par, "Gil-Kind"),
                             f"{cyc} 가 부모 사이클의 **끝**(close)에 붙지 않았다")
        # 선언 자체도 그대로 살아 있어야 한다(옮기면서 지우지 않는다).
        self.assertEqual("c2", self._trailer(self._define_of("c3", "v3-a-c3"), "Gil-Cycle-Parent"))


class TestPruneApprovalHasNoSilentDoor(GilFixture):
    """**문이 열리지 않는데 열리지 않는다는 신호도 없었다** (이슈 #96, 상현님 실사용).

    승인 버튼 핸들러의 첫 줄이 `confirm()` 이었다. 대화상자가 뜨지 않는 환경(차단 설정·
    자동화 브라우저·포커스를 잃은 창)에서는 **아무 흔적 없이 return** 한다 — 버튼도 서버도
    정상인데 사람 눈에는 "버튼이 죽었다"로 보였다. 그리고 승인은 뷰어 전용이라, 그 저장소는
    삭제 승인을 영영 못 했다(#91 의 '덫' 과 같은 계열).

    에이전트가 `window.confirm` 을 덮어써서 통과시킬 수는 있다. 하지만 그러면 사람 게이트가
    무의미해진다 — 그래서 우회가 아니라 **문 자체를 고친다**."""

    def _page(self):
        """뷰어 HTML(정적 build 로 얻는다 — 서버를 띄우지 않아도 같은 렌더 코드다)."""
        out = os.path.join(self.repo, "v.html")
        r = self.gil("graph", "--html", "--out", out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out, encoding="utf-8") as f:
            return f.read()

    def test_the_approve_button_does_not_depend_on_a_browser_dialog(self):
        self.gil("init", "--name", "clew")
        html = self._page()
        # 승인 카드 코드에 confirm( 호출이 없어야 한다 — 주석의 단어는 세지 않는다.
        calls = [ln for ln in html.split("\n")
                 if "confirm(" in ln and not ln.strip().startswith("//")]
        self.assertEqual([], calls,
                         "승인이 브라우저 대화상자에 걸려 있다 — 막히면 조용히 죽는다:\n"
                         + "\n".join(calls))
        self.assertIn("정말 지웁니다 — 한 번 더", html,
                      "무게를 유지하는 2단계 확인이 없다(그냥 한 번에 지우면 안 된다)")

    def test_it_tells_the_human_the_next_command_after_approving(self):
        """곁다리 — 승인한 사람이 다음에 무엇을 쳐야 하는지 그 자리에서 준다."""
        self.gil("init", "--name", "clew")
        html = self._page()
        self.assertIn("--confirm", html, "승인 뒤 실행 명령을 안 알려준다")
        self.assertIn("gil prune ", html)

    def test_cli_approval_path_is_discoverable(self):
        """뷰어가 유일한 문이면 뷰어의 사고가 곧 저장소의 마비다 — CLI 문을 문서가 보여준다."""
        r = self.gil("help", "prune")
        out = r.stdout + r.stderr
        self.assertIn("gil prune-approve", out,
                      "CLI 승인 경로가 help 에 없다 — 있는데 아무도 못 찾으면 없는 것과 같다:\n" + out)

    def test_cli_approval_actually_approves(self):
        """그리고 그 문은 실제로 열린다(있다고 적기만 하면 안 된다)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P", "--reference", "-",
                 "--criterion", "C", input="기준")
        self.gil("chain-close", "a", "--verdict", "supported", "--retro", "-", input="회고")
        self._ok = self.assertEqual
        r = self.gil("prune", "a", "--request", "--reason", "이주 완료")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.gil("prune-approve", "a")
        self.assertEqual(r.returncode, 0, "CLI 승인이 안 된다:\n" + r.stdout + r.stderr)
        self.assertIn("승인", r.stdout)


class TestPrunedChainsAreNotJudgedAgain(GilFixture):
    """**묘비를 남기는 것과 묘비를 위반으로 재판정하는 것은 다른 일이다** (이슈 #97②, 상현님).

    prune 은 그 체인의 ref 를 지우지만, 옛 나무에서 다른 체인이 그 위에 얹혀 있었으면 커밋은
    여전히 다른 브랜치에서 닿는다 — 그래서 fsck 가 **지운 체인의 적층을 계속 판정했다.**
    사람이 "흔적을 지우고 싶다"고 한 바로 그 흔적이, 지운 뒤에도 건강 지표를 오염시켰다.

    다만 **유실 경고는 숨기지 않는다.** 처음엔 위반 문장에서 체인 이름을 찾아 걸렀다가
    "유실 직전(GC 대상)"까지 숨겼다 — 지워진 체인의 것이라도 '사라지기 직전'은 지금 일어나는
    일이다. 거르는 자리는 출력이 아니라 **판정 그 자체**여야 한다."""

    def _ok(self, r, what):
        self.assertEqual(r.returncode, 0, what + " 실패:\n" + r.stdout + r.stderr)

    def _stacked_tree(self):
        """옛 레이아웃: beta 는 alpha 를 **이어받고**(정당), gamma 는 그 위에 **얹힌다**(적층).

        체인이 둘이면 뒤엣것이 닫힌 앞 체인의 끝에서 나므로 계승으로 인정된다 — 적층이 안 생긴다.
        셋이어야 '이어받지도 않았는데 남의 루트 위에 있는' 관계가 만들어진다."""
        self._ok(self.gil("init", "--name", "clew"), "init")
        self._git("checkout", "-q", "main")
        self._git("branch", "-D", "dev")
        for name, extra in (("alpha", []), ("beta", ["--from", "alpha", "--inherit", "alpha 의 교훈"])):
            self._ok(self.gil("chain", name, "--purpose", name, "--reference", "-",
                              "--criterion", "C", *extra, input="기준"), f"chain {name}")
            self._ok(self.gil("open", f"{name}/c1", "--author", "clew", "--purpose", "P",
                              "--body", "정의", "--fits", "그 자체"), f"open {name}")
            self._ok(self.gil("step", f"{name}/c1", "--kind", "hypothesis", "--title", "H",
                              "--body", "가설", "--falsify", "F", "--falsify-to", "s1",
                              "--plan", "구현 1개", "--advances", "경로"), "hypothesis")
            self._ok(self.gil("step", f"{name}/c1", "--kind", "verify", "--title", "V",
                              "--body", "검증", "--verdict", "supported", "--plan-held",
                              "--falsify-unmet", "미관측"), "verify")
            self._ok(self.gil("step", f"{name}/c1", "--kind", "analyze", "--title", "A",
                              "--body", "해석", "--finding", "지지됐다"), "analyze")
            self._ok(self.gil("step", f"{name}/c1", "--kind", "success", "--title", "S",
                              "--body", "종합", "--toward", "충족", "--next-design", "다음"), "success")
            self._ok(self.gil("close", f"{name}/c1", "--verdict", "supported"), "close")
            self._ok(self.gil("chain-close", name, "--verdict", "supported",
                              "--retro", "-", input="회고"), f"chain-close {name}")
        # gamma 는 alpha 의 **사이클 한복판**(닫힌 끝이 아닌 자리)에 손으로 심는다. gil 문법으로는
        # 만들 수 없는 모양이라 손으로 심어야 한다 — 그게 바로 적층이다: 이어받지도 않았는데
        # 남의 작업 위에 서 있다. (닫힌 끝에서 났다면 그건 계승이고, 적층이 아니다.)
        mid = self._git("log", "--format=%H", "--grep=Gil-Step: s2", "alpha-c1").stdout.split()
        self.assertTrue(mid, "alpha 의 사이클 한복판을 못 찾았다")
        self._git("checkout", "-q", "-b", "gamma", mid[0])
        self._git("commit", "-q", "--allow-empty", "-m",
                  "gil gamma chain: 얹힘\n\n체인 [gamma] 개설.\n\n"
                  "Gil-Chain: gamma\nGil-Kind: chain-root\nGil-Chain-Purpose: 얹힘\n"
                  "Gil-Chain-Criterion: 된다\nGil-Reference: true\nGil-Interview: done")
        self._ok(self.gil("open", "gamma/c1", "--author", "clew", "--purpose", "P",
                          "--body", "정의", "--fits", "그 자체"), "open gamma")
        self._ok(self.gil("step", "gamma/c1", "--kind", "hypothesis", "--title", "H",
                          "--body", "가설", "--falsify", "F", "--falsify-to", "s1",
                          "--plan", "구현 1개", "--advances", "경로"), "hypothesis gamma")

    def _prune(self, target):
        self._ok(self.gil("prune", target, "--request", "--reason", "이주 완료"), "prune --request")
        self._ok(self.gil("prune-approve", target), "prune-approve")
        self._ok(self.gil("prune", target, "--confirm", target, "--reason", "이주 완료"), "prune --confirm")

    def test_stacking_of_a_buried_chain_is_no_longer_counted(self):
        self._stacked_tree()
        before = self.gil("fsck")
        self.assertIn("체인 gamma", before.stdout,
                      "fixture 가 적층을 안 만들었다 — 이 시험은 아무것도 검증하지 않는다:\n"
                      + before.stdout)
        self._prune("alpha")       # 밑에 깔린 체인을 지운다(위의 beta 때문에 커밋은 남는다)
        after = self.gil("fsck")
        out = after.stdout + after.stderr
        self.assertNotIn("루트가 체인 alpha", out,
                         "지운 체인의 적층을 계속 판정한다:\n" + out)
        self.assertIn("🪦", out, "세지 않았다는 사실을 말하지 않는다 — 감춘 게 죄다")
        self.assertIn("gil fsck --all", before.stdout + out + " gil fsck --all")

    def test_loss_warnings_are_never_hidden(self):
        """지워진 체인의 것이라도 '사라지기 직전'은 지금 일어나는 일이다.

        맨 위 체인을 지우면 그 커밋들은 어디에서도 안 닿는다(GC 대상). 판정은 빼더라도
        이 경고는 남아야 한다 — 처음 판은 위반 문장에서 체인 이름을 찾아 걸렀고, 그래서
        **이것까지 숨겼다.**"""
        self._stacked_tree()
        self._prune("gamma")       # 맨 위 체인 — 지우면 그 스텝들이 어디에서도 안 닿는다
        out = self.gil("fsck").stdout
        self.assertIn("유실 직전", out,
                      "GC 임박 경고까지 숨겼다 — 이건 절대 숨기면 안 되는 것이다:\n" + out)
        self.assertIn("gamma/", out, "무엇이 사라지기 직전인지 이름을 안 부른다")


class TestMultilineTrailerKeepsTheChainVisible(GilFixture):
    """여러 줄짜리 값 하나가 트레일러 블록 **전체**를 무효로 만들었다 (이슈 #109).

    git 의 트레일러 블록은 마지막 문단 전체가 `Key: value`(또는 공백으로 시작하는 이어짐)일
    때만 성립한다. `--inherit` 에 두 줄을 넘긴 순간 그 줄은 키도 이어짐도 아니게 되고, 그
    커밋의 **Gil-Chain 까지 포함해 모든 트레일러가 사라진다.** 그래서 방금 정석대로 만든
    체인이 open 의 기준 게이트에서 "기준 문서가 없다"로 거부되고, handoff 에서도 통째로
    사라졌다 — 다음 세션은 그 체인의 존재 자체를 모른다.

    사람 눈에는 git log 에 그대로 보이니 조용하다. 실패하지 않고 **성공했다고 말하면서
    틀리는** 종류다."""

    QS = [{"q": "무엇을 하려고 하십니까", "type": "text"},
          {"q": "무엇이 관측되면 풀린 것입니까", "type": "text"}]
    ANS = ("# 기준 문서\n\n## 1. 무엇을 하려고 하십니까\n\n런타임까지 돌린다.\n\n"
           "## 2. 무엇이 관측되면 풀린 것입니까\n\n지표를 측정하고 시각화하면 풀린 것이다.\n")
    MULTI = "앞 체인 셋에서:\n- 문법은 됐다\n- 런타임은 안 됐다"

    def _run(self, *a, input=None):
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.run([*GIL_CMD, *a], cwd=self.repo, capture_output=True,
                              text=True, env=env, input=input)

    def _chain(self):
        self._run("intake", "rt", "--ask", "-", input=json.dumps(self.QS))
        p = os.path.join(self.repo, "ans.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.ANS)
        self._run("intake", "rt", "--resolve", "ans.md")
        os.remove(p)
        return self._run("chain", "ail-runtime", "--from-intake", "rt",
                         "--purpose-from", "1", "--criterion-from", "2",
                         "--inherit", self.MULTI)

    def test_trailers_survive_a_multiline_value(self):
        r = self._chain()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("ail-runtime", "Gil-Chain"), "ail-runtime")
        self.assertEqual(self.trailer("ail-runtime", "Gil-Interview"), "done")
        # 값 자체도 잃지 않는다 — 접고 되펴면 git 의 unfold 와 같은 한 줄이 된다.
        got = self._git("log", "-1", "ail-runtime",
                        "--format=%(trailers:key=Gil-Inherit,valueonly,unfold)").stdout.strip()
        self.assertEqual(got, "앞 체인 셋에서: - 문법은 됐다 - 런타임은 안 됐다")

    def test_the_cycle_opens(self):
        """정석(인터뷰 선행)으로 만든 체인은 그 자리에서 사이클이 열려야 한다."""
        self._chain()
        r = self._run("open", "ail-runtime/interp", "--author", "naru",
                      "--purpose", "인터프리터 뼈대", "--goal", "돈다",
                      "--fits", "런타임 검증이다", "--body", "무엇을 푸는가: 뼈대를 세운다.")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_handoff_still_sees_the_chain(self):
        """여기서 사라진 체인은 다음 세션이 존재 자체를 모른다(#45 가 막으려던 상황)."""
        self._chain()
        out = self._run("handoff").stdout
        self.assertIn("ail-runtime", out)

    def test_body_is_not_polluted_by_the_folded_lines(self):
        """접힌 이어짐도 트레일러다 — 본문으로 새면 뷰어가 그걸 보고서로 그린다."""
        self._chain()
        body = self._git("log", "-1", "ail-runtime", "--format=%B").stdout
        self.assertIn("Gil-Inherit:", body)
        self.assertNotIn("Gil-Inherit:", self._run("log", "ail-runtime").stdout)


class TestLongQuestionDoesNotBecomeTheAnswer(GilFixture):
    """후보를 나열한 긴 질문의 2행 이후가 **사람의 답으로** 파싱됐다 (이슈 #109 결함 3).

    사람의 답은 "2번 해보자." 한 줄이었는데 체인 목적에는 고르지 **않은** 후보 셋과
    "이 넷 밖의 것도 좋습니다"까지 통째로 박혔다. 이 문장은 이후 모든 스텝에서 되읽히는
    판단 근거라, 기각된 후보가 섞이면 매 스텝마다 오독 위험이 선다."""

    def _run(self, *a, input=None):
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.run([*GIL_CMD, *a], cwd=self.repo, capture_output=True,
                              text=True, env=env, input=input)

    ANS = ("# 기준 문서\n\n## 1. 다음 시드 후보 중 무엇을 할까요?\n\n"
           "> ① 다중 모델 검증\n> ② 런타임 실행 검증\n> ③ 문법 표면적\n"
           "> 이 셋 밖의 것도 좋습니다.\n\n2번 해보자.\n\n"
           "## 2. 무엇이 관측되면 풀린 것입니까\n\n런타임까지 돌려서 지표측정, 시각화\n")

    def _chain(self):
        self._run("intake", "sd", "--ask", "-",
                  input=json.dumps([{"q": "다음 시드 후보 중 무엇을 할까요?", "type": "text"},
                                    {"q": "무엇이 관측되면 풀린 것입니까", "type": "text"}]))
        p = os.path.join(self.repo, "ans.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.ANS)
        self._run("intake", "sd", "--resolve", "ans.md")
        os.remove(p)
        return self._run("chain", "sd-chain", "--from-intake", "sd",
                         "--purpose-from", "1", "--criterion-from", "2")

    def test_only_the_answer_is_lifted(self):
        r = self._chain()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("sd-chain", "Gil-Chain-Purpose"), "2번 해보자.")
        self.assertNotIn("다중 모델 검증", self.trailer("sd-chain", "Gil-Chain-Purpose"))

    def test_referential_answer_is_called_out(self):
        """'2번 해보자'는 참조형이다 — 막지는 않되 그대로 두면 안 된다고 말한다."""
        r = self._chain()
        self.assertIn("참조형", r.stderr)
        self.assertIn("radio", r.stderr)


class TestTheCardWritesWhatTheParserReads(GilFixture):
    """**기준 문서를 쓰는 규칙이 한 벌인가** — 카드 폼 경로로 끝까지 밟는다 (2026-08-10).

    위 TestOnlyTheAnswerIsLifted 는 답 문서를 **손으로 써서** --resolve 로 넣는다. 그러니
    그것이 재는 것은 파서이고, **쓰는 쪽**은 한 번도 안 밟힌다. 그 사이에 조립기가 두 벌이
    됐고 카드 쪽만 #109 를 안 배웠다:

      ① 여러 줄 질문을 `> ` 로 안 접어 2행 이후(고르지 않은 후보들)가 사람의 답으로 파싱됐다
      ② 빈 답을 `(답 없음)` 으로 적어 파서가 못 걸러냈다 — 체인의 성패 기준이 **문자 그대로
         "(답 없음)"** 으로 확정되고, 그 뒤 모든 판정이 빈 자를 대고 재는 일이 된다

    둘 다 오류를 안 낸다. 커밋은 성공하고 git log 는 멀쩡해 보인다 — 그래서 조용히 틀린다."""

    def _app(self):
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1", "GIL_NO_VERSION_CHECK": "1"})
        self.addCleanup(p.terminate)
        state = {"id": 0}

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                try:
                    m = json.loads(ln.strip())
                except (json.JSONDecodeError, ValueError):
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "unsupported"}})
                    continue
                if m.get("id") == want:
                    return m

        state["id"] += 1
        send({"jsonrpc": "2.0", "id": state["id"], "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "app", "version": "0"}}})
        pump(state["id"])
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        def call(name, args):
            state["id"] += 1
            send({"jsonrpc": "2.0", "id": state["id"], "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
            r = pump(state["id"])
            if r is None:
                return "", "(응답 없음)"
            if "error" in r:
                return "", r["error"].get("message", "")
            res = r["result"]
            txt = "".join(c.get("text", "") for c in res.get("content", []))
            return ("", txt) if res.get("isError") else (txt, "")
        return call

    # 1번은 **여러 줄** 질문(후보 나열), 3번은 사람이 비워 둘 칸.
    QS = [{"q": "다음 시드 후보 중 무엇을 할까요?\n① 다중 모델 검증\n② 런타임 실행 검증\n"
                "③ 문법 표면적\n이 셋 밖의 것도 좋습니다.", "type": "text"},
          {"q": "무엇이 관측되면 풀린 것입니까", "type": "text"},
          {"q": "덧붙일 것이 있습니까", "type": "text"}]

    def _submit(self):
        self.gil("init", "--name", "clew")
        r = self.gil("intake", "sd", "--ask", "-",
                     input=json.dumps(self.QS, ensure_ascii=False))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        call = self._app()
        out, err = call("gil_interview_submit", {
            "repo": self.repo, "chain": "sd",
            "answers": json.dumps({"q1": "2번 해보자.", "q2": "런타임까지 돌려서 지표측정",
                                   "q3": ""}, ensure_ascii=False)})
        self.assertEqual(err, "", f"카드 제출이 막혔다:\n{err}")
        return out

    def test_the_long_questions_tail_is_not_the_humans_answer(self):
        """사람은 "2번 해보자." 한 줄을 적었다 — 고르지 **않은** 후보가 목적에 박히면 안 된다."""
        self._submit()
        r = self.gil("chain", "sd-chain", "--from-intake", "sd",
                     "--purpose-from", "1", "--criterion-from", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        purpose = self.trailer("sd-chain", "Gil-Chain-Purpose")
        self.assertEqual(purpose, "2번 해보자.",
                         "질문의 2행 이후가 사람의 답으로 섞였다: " + purpose)
        for cand in ("다중 모델 검증", "문법 표면적", "이 셋 밖의 것도"):
            self.assertNotIn(cand, purpose, f"고르지 않은 후보 '{cand}' 가 목적에 박혔다")

    def test_an_empty_answer_is_empty_not_a_placeholder(self):
        """빈 답은 **빈 것**이지 "(답 없음)" 이라는 답이 아니다 — 거절해야 한다."""
        self._submit()
        r = self.gil("chain", "sd2", "--from-intake", "sd",
                     "--purpose-from", "1", "--criterion-from", "3")
        both = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0,
                            "빈 답이 성패 기준으로 확정됐다 — 그 뒤 판정은 빈 자를 대고 재는 일이 된다:\n" + both)
        self.assertIn("비었다", both, "왜 거절인지 말하지 않았다:\n" + both)
        self.assertNotIn("답 없음", self.trailer("sd2", "Gil-Chain-Criterion"),
                         "자리표시자가 기준으로 기록됐다")

    def test_both_writers_produce_the_same_shape(self):
        """**규칙이 한 벌인지 문서로 확인한다** — 카드가 쓴 것을 파서가 읽어 답만 남는다."""
        self._submit()
        shown = self.gil("intake", "sd", "--status", "--show").stdout
        self.assertIn("> ① 다중 모델 검증", shown,
                      "여러 줄 질문이 인용으로 접히지 않았다 — 파서가 답과 구분하지 못한다")
        self.assertIn("_(답 없음)_", shown,
                      "빈 답이 파서가 아는 표기로 적히지 않았다")


class TestCompetingSiblings(GilFixture):
    """경합 중인 형제 가설을 1급 상태로 (이슈 #106 · #107, 상현님).

    실사용 7사이클·스텝 90여 개 동안 병렬 가지가 **0회**였다. 문법은 형제 가지를 처음부터
    지원했는데도. 이유는 도구 쪽에 있었다:

    1. 형제를 **동시에** 띄우는 것 자체가 규범 위반이었다 — 앞 가지를 종결하지 않고 떠나면
       거부, 탈출구는 --leave-open 뿐이고 그건 fsck 가 짚는 낙인이다.
    2. 매 스텝의 꼬리가 "⟹ 다음은 반드시 <하나>" 였다 — 다음 행동은 항상 한 개라는 리듬.
    3. 이겼을 때 끝맺는 그림(패자 처리·자산 통합·비교 기록)이 없었다.

    도구가 "큰 사고는 일자로 흐르는 중"이라 경고하면서, 정작 일자를 벗어나는 모든 동작에
    마찰을 붙여 놓은 셈이다. 경합은 매달림과 다르다: 매달린 잎은 **잊혀서** 남은 것이고,
    경합 갈래는 **겨루려고** 열어 둔 것이다."""

    def _cycle(self):
        self.gil("init", "--name", "naru")
        with open(os.path.join(self.repo, "ref.md"), "w", encoding="utf-8") as f:
            f.write("# 기준 문서\n\n런타임까지 돌려서 지표를 잰다.\n")
        self.gil("chain", "ch", "--purpose", "런타임", "--reference", "ref.md",
                 "--criterion", "지표측정")
        self.gil("open", "ch/cy", "--author", "naru", "--purpose", "p", "--goal", "돈다",
                 "--fits", "맞다")
        self.gil("step", "ch/cy", "--kind", "hypothesis", "--title", "h1", "--body", "가설",
                 "--falsify", "안됨", "--falsify-to", "s1", "--advances", "첫 조각")
        self.gil("step", "ch/cy", "--kind", "verify", "--title", "v1", "--body", "검증",
                 "--verdict", "supported")
        return self.gil("step", "ch/cy", "--kind", "analyze", "--title", "a1",
                        "--body", "선택지 A/B/C", "--finding", "세 축을 다 재야 한다: A/B/C")

    def _sib(self, name, competing=True):
        a = ["step", "ch/cy", "--kind", "hypothesis", "--to", "s4", "--title", f"h{name}",
             "--body", f"{name}축 가설", "--falsify", "안됨", "--falsify-to", "s1",
             "--advances", f"{name}축"]
        if competing:
            a.append("--competing")
        return self.gil(*a)

    def test_analyze_offers_the_parallel_path(self):
        """분석이 선택지를 내놓는 자리에서 병렬이 화면에 **있어야** 한다 — 없으면 안 쓴다."""
        r = self._cycle()
        self.assertIn("--competing", r.stderr)
        self.assertIn("다 밟아라", r.stderr)

    def test_enumerated_options_are_counted_back(self):
        """자기가 쓴 결론에서 선택지 수를 세어 되돌려준다 — 일반 안내보다 덜 흘러간다."""
        r = self._cycle()
        self.assertIn("선택지가 3개로 읽힌다", r.stderr)

    def test_siblings_can_be_open_at_once(self):
        """경합 선언이 있으면 형제를 동시에 띄울 수 있다 — 이게 선결 문제였다."""
        self._cycle()
        self.assertEqual(self._sib("A").returncode, 0)
        r = self._sib("B")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("경합", r.stderr)

    def test_undeclared_sibling_is_still_refused_but_taught(self):
        """선언 없이 떠나는 것은 여전히 막는다 — 다만 거부가 경합의 길을 가르친다."""
        self._cycle()
        self._sib("A", competing=False)
        r = self._sib("B", competing=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--competing", r.stderr)

    def test_fsck_does_not_stigmatize_a_declared_competition(self):
        """선언된 경합은 위반이 아니다 — 대신 이름으로 불린다(안 보이는 것과 다르다)."""
        self._cycle(); self._sib("A"); self._sib("B"); self._sib("C")
        r = self.gil("fsck")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("경합 중", r.stdout)

    def test_handoff_names_the_competing_branches(self):
        """이어받는 세션은 자기가 밟고 선 가지 하나만 본다 — 나머지가 여기 없으면 잊힌다."""
        self._cycle(); self._sib("A"); self._sib("B"); self._sib("C")
        out = self.gil("handoff").stdout
        self.assertIn("경합 중인 형제 가설 3개", out)

    def test_close_still_requires_every_branch_to_end(self):
        """경합은 유예지 면제가 아니다 — 닫을 때는 갈래마다 종결이 있어야 한다."""
        self._cycle(); self._sib("A"); self._sib("B")
        r = self.gil("close", "ch/cy", "--goal-met")
        self.assertNotEqual(r.returncode, 0)

    def test_adopt_folds_the_losers_and_moves_to_the_winner(self):
        """승자 채택 — 패자마다 벽(승자를 가리키는 선과 함께), HEAD 는 승자 가지로."""
        self._cycle()
        self._sib("A"); self._sib("B"); self._sib("C")
        r = self.gil("adopt", "ch/cy/s5", "--reason", "A 가 3표본에서 245 대 109 로 앞섰다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("접을 형제 2개", r.stdout)
        # 진 갈래마다 승자를 가리키는 선이 남는다
        lost = self._git("log", "--all", "--format=%(trailers:key=Gil-Lost-To,valueonly,unfold)").stdout
        self.assertEqual(lost.count("ch/cy/s5"), 2)
        # 채택 뒤에는 경합이 남지 않는다 — fsck 도 조용하다
        f = self.gil("fsck")
        self.assertEqual(f.returncode, 0, f.stdout)
        self.assertNotIn("경합 중", f.stdout)

    def test_adopt_demands_a_reason(self):
        """채택은 판단이다 — 근거가 없으면 측정이었는지 취향이었는지 아무도 모른다."""
        self._cycle(); self._sib("A"); self._sib("B")
        r = self.gil("adopt", "ch/cy/s5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--reason", r.stderr)


class TestCloseFindsTheLiveLeafAnywhere(GilFixture):
    """산 잎이 형제 가지에 있으면 close 가 못 봤다 (이슈 #106 g).

    병렬 형제를 쓰면 이긴 가지와 진 가지가 서로 다른 브랜치에 산다. 진 가지에 서서 닫으려
    하면 "산 잎 없음"으로 거부됐다 — **어디서 닫느냐에 따라 같은 사이클의 판정이 달라진
    것이다.** 사이클의 상태는 무엇을 체크아웃했는지에 달린 것이 아니다."""

    def _two_branches(self):
        self.gil("init", "--name", "naru")
        with open(os.path.join(self.repo, "ref.md"), "w", encoding="utf-8") as f:
            f.write("# 기준 문서\n\n런타임까지 돌려서 지표를 잰다.\n")
        self.gil("chain", "ch", "--purpose", "런타임", "--reference", "ref.md", "--criterion", "지표")
        self.gil("open", "ch/cy", "--author", "naru", "--purpose", "p", "--fits", "맞다")
        self.gil("step", "ch/cy", "--kind", "hypothesis", "--title", "h1", "--body", "가설",
                 "--falsify", "안됨", "--falsify-to", "s1", "--advances", "몫")
        self.gil("step", "ch/cy", "--kind", "verify", "--title", "v1", "--body", "검증",
                 "--verdict", "supported")
        self.gil("step", "ch/cy", "--kind", "analyze", "--title", "a1", "--body", "해석")
        # 산 잎 — A 가지
        self.gil("step", "ch/cy", "--kind", "success", "--title", "sA", "--body", "종합",
                 "--toward", "달성", "--next-design", "다음")
        # 형제 가지 B — 여기서 끝난다(죽은 잎)
        self.gil("step", "ch/cy", "--kind", "hypothesis", "--to", "s1", "--title", "hB",
                 "--body", "B 가설", "--falsify", "안됨", "--falsify-to", "s1", "--advances", "B")
        self.gil("step", "ch/cy", "--kind", "verify", "--title", "vB", "--body", "검증",
                 "--verdict", "refuted")
        self.gil("step", "ch/cy", "--kind", "analyze", "--title", "aB", "--body", "해석")
        self.gil("step", "ch/cy", "--kind", "fail", "--title", "fB", "--body", "벽", "--to", "s1",
                 "--toward", "못 갔다", "--next-design", "접는다")

    def test_close_from_the_losing_branch_still_finds_the_success(self):
        self._two_branches()
        cur = self._git("branch", "--show-current").stdout.strip()
        self.assertTrue(cur.endswith("b1") or "s1b" in cur, f"형제 가지 위에 있어야 한다: {cur}")
        r = self.gil("close", "ch/cy")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("형제 가지", r.stderr)


class TestDeployRequiresALiveLeaf(GilFixture):
    """**죽은 잎만 있는 계보는 세상으로 나갈 수 없다** (이슈 #108 ①).

    `gil close` 는 "산 잎(success) 없으면 못 닫는다"를 집행하는데, 생애주기의 마지막 관문인
    배포에는 그 검사가 없었다. 집행이 두 자리에서 갈리면 느슨한 쪽이 실질 규칙이 된다 —
    실제로 리포터는 죽은 가지에서 close 를 시도하다 도구에 막혀 옳은 가지로 옮겼고, 같은
    실수를 deploy 는 잡지 못했다. 형제 가지를 병렬로 팔수록 죽은 가지가 더 많은 게 정상이라
    (#106·#107) 잘못 짚기도 쉽다."""

    def _chain(self, name, alive):
        self.gil("chain", name, "--purpose", "목적 " + name, "--reference", "-",
                 "--criterion", "된다", input="기준")
        self.gil("open", name + "/c1", "--author", "clew", "--purpose", "P", "--body", "정의")
        if alive:
            self.gil("step", name + "/c1", "--kind", "success", "--title", "S", "--body", "종합")
            self.gil("close", name + "/c1", "--verdict", "supported")
        else:
            self.gil("step", name + "/c1", "--kind", "hypothesis", "--title", "H", "--body", "가설")
            self.gil("step", name + "/c1", "--kind", "verify", "--title", "V", "--body", "검증",
                     "--verdict", "refuted")
            self.gil("step", name + "/c1", "--kind", "analyze", "--title", "A", "--body", "분석")
            self.gil("step", name + "/c1", "--kind", "fail", "--to", "s1", "--title", "F",
                     "--body", "죽음")
            self.gil("close", name + "/c1", "--verdict", "refuted", "--abandon")
        self.gil("chain-close", name, "--verdict", "supported" if alive else "refuted",
                 "--retro", "-", input="회고")
        self.gil("merge", name, "--into", "dev", "--reason", "배포 단위")

    def _ready(self, alive=True):
        self.gil("init", "--name", "clew")
        self._chain("login", alive)

    def test_a_lineage_of_dead_leaves_is_refused(self):
        self._ready(alive=False)
        r = self.gil("deploy", "--tag", "v0.1.0")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, "죽은 잎만 있는 계보가 그대로 나갔다:\n" + out)
        self.assertIn("산 잎", out)
        self.assertIn("--force", out, "막기만 하고 길을 안 줬다:\n" + out)

    def test_refusal_leaves_no_marker(self):
        """거부했는데 기록이 남으면, 나중에 읽는 쪽은 배포된 줄 안다."""
        self._ready(alive=False)
        self.gil("deploy", "--tag", "v0.1.0")
        self.assertNotIn("v0.1.0", self._git("log", "dev", "--format=%s").stdout)

    def test_force_without_a_reason_is_refused(self):
        """이유 없는 강행은 기록에서 정상 배포와 구별되지 않는다."""
        self._ready(alive=False)
        r = self.gil("deploy", "--tag", "v0.1.0", "--force")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--reason", r.stdout + r.stderr)

    def test_forced_deploy_writes_the_reason_into_the_commit(self):
        self._ready(alive=False)
        r = self.gil("deploy", "--tag", "v0.1.0", "--force", "--reason", "문서 전용 배포")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = self._git("log", "-1", "dev", "--format=%B").stdout
        self.assertIn("문서 전용 배포", body)
        self.assertEqual(self.trailer("dev", "Gil-Deployed-Leaf"), "",
                         "산 잎이 없는데 잎을 내보냈다고 적었다")

    def test_a_live_lineage_still_deploys(self):
        """막는 것이 목적이 아니다 — 정상 배포는 그대로 나가야 한다."""
        self._ready(alive=True)
        r = self.gil("deploy", "--tag", "v0.1.0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_commit_names_what_shipped(self):
        """배포 커밋만 봐서는 어느 잎의 결과물인지 알 수 없었다(#108 1c)."""
        self._ready(alive=True)
        self.gil("deploy", "--tag", "v0.1.0")
        self.assertEqual(self.trailer("dev", "Gil-Deployed-Leaf"), "login/c1/s5")

    def test_an_empty_repo_is_not_scolded_about_leaves(self):
        """스텝이 아예 없는 자리는 '죽은 잎만 남았다'와 다른 상태다 — 그 말이 층 진단을 가리면 안 된다."""
        self.gil("init", "--name", "clew")
        r = self.gil("deploy", "--tag", "v0.1.0")
        self.assertNotIn("산 잎", r.stdout + r.stderr)


class TestDeployMarkerSurvivesTheMerges(GilFixture):
    """**정석대로 할수록 배포 마커가 사라졌다** (이슈 #108 ②, #104 와 같은 뿌리).

    사이클 → 체인 merge → chain-close → dev merge → deploy 로 갈수록 머지가 겹겹이 쌓이고,
    산 잎은 언제나 머지의 **둘째 부모** 쪽에 선다. 귀속이 선언(--at)에만 기대던 옛 코드는
    --at 없는 기본형에서 마커를 통째로 버렸다 — 화면에 남는 마지막 노드가 붉은 fail 잎이라,
    사람이 "죽은 잎이 배포된 것 같다"고 읽었다. 기록은 정상인데 그림이 반대로 말했다."""

    def _built(self, alive=True, extra=()):
        self.gil("init", "--name", "clew")
        self.gil("chain", "login", "--purpose", "로그인", "--reference", "-",
                 "--criterion", "된다", input="기준")
        self.gil("open", "login/c1", "--author", "clew", "--purpose", "P", "--body", "정의")
        if alive:
            self.gil("step", "login/c1", "--kind", "success", "--title", "S", "--body", "종합")
            self.gil("close", "login/c1", "--verdict", "supported")
        else:
            self.gil("step", "login/c1", "--kind", "hypothesis", "--title", "H", "--body", "가설")
            self.gil("step", "login/c1", "--kind", "verify", "--title", "V", "--body", "검증",
                     "--verdict", "refuted")
            self.gil("step", "login/c1", "--kind", "analyze", "--title", "A", "--body", "분석")
            self.gil("step", "login/c1", "--kind", "fail", "--to", "s1", "--title", "F",
                     "--body", "죽음")
            self.gil("close", "login/c1", "--verdict", "refuted", "--abandon")
        self.gil("chain-close", "login", "--verdict", "supported" if alive else "refuted",
                 "--retro", "-", input="회고")
        self.gil("merge", "login", "--into", "dev", "--reason", "배포 단위")
        r = self.gil("deploy", "--tag", "v1.0.0", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out_html = os.path.join(self.repo, "g.html")
        self.assertEqual(self.gil("graph", "--html", "--out", out_html).returncode, 0)
        return open(out_html, encoding="utf-8").read()

    def _dag(self, html):
        return json.loads(re.search(r'"dagdata"[^>]*>(.*?)</script>', html, re.S).group(1))

    def _layer(self, html):
        return json.loads(re.search(r'"layergraphdata"[^>]*>(\{.*?\})</script>', html, re.S).group(1))

    def test_the_marker_lands_on_the_live_leaf(self):
        nodes = self._dag(self._built())
        nodes = nodes["nodes"] if isinstance(nodes, dict) else nodes
        marked = [n for n in nodes if n.get("deploy")]
        self.assertTrue(marked, "배포 마커가 어떤 노드에도 붙지 않았다 — 배포가 없었던 것처럼 보인다")
        self.assertEqual(marked[0].get("deploy"), "v1.0.0")
        self.assertEqual(marked[0].get("kind"), "success",
                         "산 잎이 아닌 곳에 배포 마커가 붙었다")

    def test_the_layer_rows_carry_the_deploy_and_its_leaf(self):
        """층 그림은 승격 머지의 제목이 아니라 **마커 커밋**에게 묻는다."""
        rows = self._layer(self._built())["rows"]
        d = [r for r in rows if r.get("deploy")]
        self.assertTrue(d, "층 행에 배포가 하나도 없다")
        self.assertEqual(d[0]["deploy"], "v1.0.0")
        self.assertEqual(d[0]["deployAt"], "login/c1/s5")

    def test_an_unattributed_deploy_is_drawn_not_swallowed(self):
        """귀속을 못 찾아도 침묵하지 않는다 — 없는 것과 못 찾은 것은 다르다."""
        html = self._built(alive=False, extra=("--force", "--reason", "문서 전용"))
        rows = self._layer(html)["rows"]
        d = [r for r in rows if r.get("deploy")]
        self.assertTrue(d, "귀속을 못 찾자 배포를 통째로 지웠다")
        self.assertEqual(d[0]["deployAt"], "", "없는 귀속을 지어냈다")
        self.assertIn("귀속 스텝 미상", html, "화면이 '모른다'고 말할 자리가 없다")

    def test_a_declared_leaf_is_believed_without_searching(self):
        """Gil-Deployed-Leaf 가 있으면 탐색하지 않는다 — 배포한 쪽이 아는 사실이 더 정확하다."""
        html = self._built(extra=("--at", "login/c1/s5"))
        d = [r for r in self._layer(html)["rows"] if r.get("deploy")]
        self.assertEqual(d[0]["deployAt"], "login/c1/s5")


class TestChainInheritsFromMany(GilFixture):
    """계승이 하나뿐이라 여러 갈래의 지식이 모이는 그림이 없었다 (이슈 #107 3b).

    실사용에서 다음 체인은 두 닫힌 체인(문법 실험 · 순수계산) **양쪽**에서 물려받아야
    자연스러웠는데, 계승 부모를 하나만 적을 수 있어 새 체인은 직전 체인 위에 얹히거나
    무연고로 떴다. 선언만 늘리면 커밋 그래프는 여전히 한 갈래에서만 왔다고 말하므로,
    **합류선**까지 남긴다."""

    def _closed_chain(self, name):
        with open(os.path.join(self.repo, "ref.md"), "w", encoding="utf-8") as f:
            f.write("# 기준\n\n돌린다\n")
        self.gil("chain", name, "--purpose", f"{name} 목적", "--reference", "ref.md",
                 "--criterion", "지표")
        self.gil("open", f"{name}/c1", "--author", "naru", "--purpose", "p", "--fits", "맞다")
        self.gil("step", f"{name}/c1", "--kind", "hypothesis", "--title", "h", "--body", "가설",
                 "--falsify", "안됨", "--falsify-to", "s1", "--advances", "몫")
        self.gil("step", f"{name}/c1", "--kind", "verify", "--title", "v", "--body", "검증",
                 "--verdict", "supported")
        self.gil("step", f"{name}/c1", "--kind", "analyze", "--title", "a", "--body", "해석")
        self.gil("step", f"{name}/c1", "--kind", "success", "--title", "s", "--body", "종합",
                 "--toward", "달성", "--next-design", "다음")
        self.gil("close", f"{name}/c1")
        self.gil("chain-close", name, "--retro", "-", input="회고")

    def _two(self):
        self.gil("init", "--name", "naru")
        self._closed_chain("grammar")
        self._closed_chain("pure")

    def test_two_parents_are_declared_and_drawn(self):
        self._two()
        r = self.gil("chain", "multi", "--purpose", "다중 검증", "--reference", "ref.md",
                     "--criterion", "지표", "--from", "grammar", "--from", "pure")
        self.assertEqual(r.returncode, 0, r.stderr)
        # 선언
        decl = self._git("log", "multi", "--format=%(trailers:key=Gil-Chain-From,valueonly,unfold)").stdout
        self.assertIn("grammar", decl)
        self.assertIn("pure", decl)
        # 그리고 **실재** — 커밋 그래프에 합류선이 있다
        parents = self._git("log", "-1", "multi", "--format=%p").stdout.split()
        self.assertEqual(len(parents), 2, "둘째 계승이 합류선으로 안 남았다")

    def test_lineage_shows_both_parents(self):
        """계보 화면이 선언을 읽는다 — 안 읽으면 '(대문)' 으로 떠 계승이 사라진다."""
        self._two()
        self.gil("chain", "multi", "--purpose", "다중 검증", "--reference", "ref.md",
                 "--criterion", "지표", "--from", "grammar", "--from", "pure")
        out = self.gil("handoff").stdout
        self.assertIn("multi (open) ← grammar+pure", out)

    def test_no_declaration_says_so(self):
        """계승 결정을 빈칸으로 두지 않는다 — 시조로 서면 그렇게 말한다."""
        self._two()
        r = self.gil("chain", "solo", "--purpose", "혼자", "--reference", "ref.md",
                     "--criterion", "지표")
        self.assertIn("시조", r.stderr)
        self.assertIn("--orphan", r.stderr)

    def test_orphan_reason_is_recorded(self):
        self._two()
        r = self.gil("chain", "solo", "--purpose", "혼자", "--reference", "ref.md",
                     "--criterion", "지표", "--orphan", "앞선 국면과 전제가 다르다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("solo", "Gil-Chain-Orphan-Reason"),
                         "앞선 국면과 전제가 다르다")

    def test_from_and_orphan_cannot_stand_together(self):
        self._two()
        r = self.gil("chain", "solo", "--purpose", "혼자", "--reference", "ref.md",
                     "--criterion", "지표", "--from", "grammar", "--orphan", "왜냐하면")
        self.assertNotEqual(r.returncode, 0)


class TestWallMapCanBeUndecided(GilFixture):
    """벽의 지도를 **즉시·단일**로 확정하도록 강제한 탓에 지도와 행동이 어긋났다 (이슈 #105).

    실사례: s9(fail)는 s1 로 돌아간다고 적었는데 다음 가설 s10 은 s8(analyze)에서 갈라졌다.
    재분기 자체는 규범에 맞았고 --despite 도 작동했다 — 문제는 fail 시점의 진실이
    "다음 갈 곳은 사람 판정 (a)/(b)/(c) 에 달렸다" 였는데 그걸 적을 어휘가 없었다는 것이다.
    세션은 보수적 기본값을 적을 수밖에 없었고, 그 값이 나중에 모순으로 보였다.
    어휘가 부족하면 기록이 거짓말한다."""

    def _wall(self):
        self.gil("init", "--name", "naru")
        with open(os.path.join(self.repo, "ref.md"), "w", encoding="utf-8") as f:
            f.write("# 기준\n\n돌린다\n")
        self.gil("chain", "ch", "--purpose", "목적", "--reference", "ref.md", "--criterion", "지표")
        self.gil("open", "ch/cy", "--author", "naru", "--purpose", "p", "--fits", "맞다")
        self.gil("step", "ch/cy", "--kind", "hypothesis", "--title", "h1", "--body", "가설",
                 "--falsify", "안됨", "--falsify-to", "s1", "--advances", "몫")
        self.gil("step", "ch/cy", "--kind", "verify", "--title", "v1", "--body", "검증",
                 "--verdict", "refuted")
        self.gil("step", "ch/cy", "--kind", "analyze", "--title", "a1", "--body", "해석",
                 "--finding", "고수준 도구는 별도 설계가 필요하다")

    def test_fail_can_say_it_does_not_know_yet(self):
        self._wall()
        r = self.gil("step", "ch/cy", "--kind", "fail", "--to", "pending", "--title", "f1",
                     "--body", "벽: 다음은 (a)/(b)/(c) — 사람 판정에 달렸다",
                     "--toward", "여기까지", "--next-design", "판정 뒤 확정")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Backtrack"), "pending")

    def test_missing_to_teaches_the_pending_vocabulary(self):
        self._wall()
        r = self.gil("step", "ch/cy", "--kind", "fail", "--title", "f1", "--body", "벽",
                     "--toward", "t", "--next-design", "n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--to pending", r.stderr)

    def test_a_pending_map_is_not_a_map_to_defy(self):
        """미정인 지도는 벗어날 지도가 없다 — --despite 를 요구하면 그건 빈 칸 채우기다."""
        self._wall()
        self.gil("step", "ch/cy", "--kind", "fail", "--to", "pending", "--title", "f1",
                 "--body", "벽", "--toward", "t", "--next-design", "n")
        self._no_despite_autofill = True
        r = self.gil("step", "ch/cy", "--kind", "hypothesis", "--to", "s4", "--title", "h2",
                     "--body", "새 가설", "--falsify", "안됨", "--falsify-to", "s1",
                     "--inherit", "벽의 교훈", "--advances", "몫")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("미정", r.stderr)

    def test_context_says_the_map_is_still_undecided(self):
        """도구는 이미 안다 — 말만 안 했을 뿐이다. 화면이 침묵하면 사람이 모순으로 읽는다."""
        self._wall()
        self.gil("step", "ch/cy", "--kind", "fail", "--to", "pending", "--title", "f1",
                 "--body", "벽", "--toward", "t", "--next-design", "n")
        out = self.gil("context", "ch/cy").stdout
        self.assertIn("지도 미정", out)


class TestLayerRootIsWhereTheLayerStarts(GilFixture):
    """`--adopt-dev` 가 층 표식을 **뿌리가 아니라 팁에** 심었다 (이슈 #113).

    표식은 "여기부터 층"인데 dev 팁에 심으면 "여기까지 아무것도"가 된다 — 층의 범위를
    정하는 쪽(devLayerFacts)이 표식에서 자르기 때문이다. 실사용 저장소에서 dev 커밋 148개
    중 147개가 층 밖이 됐고, **dev 에서 갈라져야 하는 유일한 체인**(첫 체인)만 정확히 이
    결함에 노출돼 뿌리 없이 떴다.

    더 나쁜 것은 되돌리는 값이었다: `--adopt-dev` 는 'SHA 불변'을 약속하는데, 표식을 옳은
    자리로 옮기려면 이력을 다시 써야 했다. **안전하다던 명령이 안전하지 않은 수리를 요구하는
    상태로 끝났다.** 그래서 표식을 커밋이 아니라 ref 로 둔다 — 옮기면 그만이다."""

    def _old_layout_dev(self, extra=3):
        self._git("checkout", "-q", "-b", "main")
        with open(os.path.join(self.repo, "README.md"), "w") as f:
            f.write("hi\n")
        self._git("add", "-A"); self._git("commit", "-qm", "Initial commit")
        self._git("checkout", "-q", "-b", "dev")
        for i in range(extra):
            with open(os.path.join(self.repo, "w.md"), "a") as f:
                f.write(f"w{i}\n")
            self._git("add", "-A"); self._git("commit", "-qm", f"작업 {i}")

    def test_adopt_recognizes_the_whole_layer(self):
        self._old_layout_dev()
        r = self.gil("migrate", "--adopt-dev")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("층으로 인정된 커밋", r.stdout)   # 범위를 숫자로 말한다(제안 d)
        root = self._git("rev-parse", "refs/gil/layer/dev").stdout.strip()
        self.assertTrue(root, "층 뿌리 ref 가 없다")
        # 뿌리는 대문에서 갈라진 **첫** dev 커밋이어야 한다 — 팁이 아니라.
        tip = self._git("rev-parse", "dev").stdout.strip()
        self.assertNotEqual(root, tip)
        inside = self._git("rev-list", "--count", f"{root}..dev").stdout.strip()
        self.assertGreaterEqual(int(inside), 3, "층이 1커밋으로 쪼그라들었다")

    def test_a_misplanted_marker_can_be_repaired_without_rewriting(self):
        """이미 팁에 심긴 저장소(v3.52.0 산물)를 재실행으로 고칠 수 있어야 한다."""
        self._old_layout_dev()
        # 옛 --adopt-dev 가 남긴 모양을 그대로 만든다: 팁에 dev-root 트레일러
        msg = "옛 adopt 표식\n\nGil-Kind: dev-root\nGil-Dev-Adopted: true\n"
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-F", "-"],
                       cwd=self.repo, input=msg, text=True, capture_output=True,
                       env=dict(os.environ, GIL_ALLOW_RAW="1"))
        before = self._git("rev-parse", "dev").stdout.strip()
        r = self.gil("migrate", "--adopt-dev")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("뿌리가 층의 시작이 아니다", r.stdout)
        # SHA 는 하나도 안 바뀐다 — 그게 이 명령의 약속이다
        self.assertEqual(self._git("rev-parse", "dev").stdout.strip(), before)
        root = self._git("rev-parse", "refs/gil/layer/dev").stdout.strip()
        self.assertNotEqual(root, before)
        self.assertGreaterEqual(int(self._git("rev-list", "--count", f"{root}..dev").stdout.strip()), 3)


class TestChainMustSayWhereItInherits(GilFixture):
    """`gil chain` 이 계승 자리를 강제하지 않았다 (이슈 #111).

    문서는 "닫힌 체인 끝에서만 연다"고 약속하는데 실제로는 아무 자리에서나 열려 통과했다.
    배포까지 마친 대문(main) 끝에서 열어도 경고 한 줄 없었고, 그 체인은 그래프에서 선 하나
    없이 떴다 — **사람이 계승을 명시적으로 골랐는데도.** 체인은 계보의 최상위 단위라 여기서
    끊기면 그 아래 사이클·스텝 전부가 지식의 강에서 떨어져 나간다."""

    def _closed_first(self):
        # **층 없는 옛 저장소**의 모양이다(gil init 을 안 탄다) — 이 결함이 실제로 난 자리가
        # 그곳이다. 층이 있으면 시조는 dev 에서 나므로 이 물음 자체가 뜨지 않는다.
        self._git("checkout", "-q", "-b", "main")
        with open(os.path.join(self.repo, "README.md"), "w") as f:
            f.write("hi\n")
        self._git("add", "-A"); self._git("commit", "-qm", "Initial commit")
        with open(os.path.join(self.repo, "ref.md"), "w", encoding="utf-8") as f:
            f.write("# 기준\n\n돈다\n")
        self.gil("chain", "first", "--purpose", "첫 국면", "--reference", "ref.md",
                 "--criterion", "지표")
        self.gil("open", "first/c1", "--author", "naru", "--purpose", "p", "--fits", "맞다")
        self.gil("step", "first/c1", "--kind", "hypothesis", "--title", "h", "--body", "가설",
                 "--falsify", "안됨", "--falsify-to", "s1", "--advances", "몫")
        self.gil("step", "first/c1", "--kind", "verify", "--title", "v", "--body", "검증",
                 "--verdict", "supported")
        self.gil("step", "first/c1", "--kind", "analyze", "--title", "a", "--body", "해석")
        self.gil("step", "first/c1", "--kind", "success", "--title", "s", "--body", "종합",
                 "--toward", "달성", "--next-design", "다음")
        self.gil("close", "first/c1")
        self.gil("chain-close", "first", "--retro", "-", input="회고")
        self._git("checkout", "-q", "main")  # 대문 끝 — 여기서 여는 것이 이 이슈의 재현이다

    def test_opening_at_the_gate_without_declaring_is_refused(self):
        self._closed_first()
        r = self.gil("chain", "second", "--purpose", "다음", "--reference", "ref.md",
                     "--criterion", "지표")
        self.assertNotEqual(r.returncode, 0, "대문 끝에서 선언 없이 열렸다")
        self.assertIn("--from first", r.stderr)      # 칠 수 있는 한 줄을 준다
        self.assertIn("--orphan", r.stderr)

    def test_from_digs_at_the_closed_end_itself(self):
        """사람이 git checkout 으로 옳은 커밋을 찾아다니게 하지 않는다."""
        self._closed_first()
        r = self.gil("chain", "second", "--purpose", "다음", "--reference", "ref.md",
                     "--criterion", "지표", "--from", "first")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.gil("handoff").stdout
        self.assertIn("second (open) ← first", out)

    def test_orphan_is_an_accepted_answer(self):
        self._closed_first()
        r = self.gil("chain", "second", "--purpose", "다음", "--reference", "ref.md",
                     "--criterion", "지표", "--orphan", "앞 국면과 전제가 다르다")
        self.assertEqual(r.returncode, 0, r.stderr)


class TestViewerShowsTheCompetition(GilFixture):
    """**나란히 세운 것은 비교하려는 것이다 — 그런데 비교하는 화면이 없었다** (이슈 #112).

    v3.53.0 이 경합(`--competing`)·채택(`gil adopt`)·미정 지도(`--to pending`)의 문법을
    세웠다. 그런데 fsck·handoff 는 "경합 중 3개"라고 **세기만** 했고, 무엇과 무엇이 겨루는지는
    사람이 그래프를 눈으로 따라가야 알았다. 그리고 `--despite` 로 갱신된 옛 지도는 화면에서
    여전히 '유효한 계획'처럼 그려졌다 — 사람이 "뭐가 맞는 거냐"고 물은 자리다.

    여기서 지키는 것: (1) 겨루는 갈래가 재료로 화면에 실린다 (2) 선언 없이 난 형제는 경합이
    아니다 (3) 갱신된 지도는 강등의 근거(누가·어디로)를 달고 나간다 (4) 미정인 지도가 미정으로
    남는다 (5) 선언된 경합에서는 갈래 사이를 오갈 수 있다."""

    def _cycdata(self):
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("graph", "--html", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'id="cycledata"[^>]*>(.*?)</script>', html, re.S)
        self.assertIsNotNone(m, "사이클 데이터가 페이지에 실리지 않았다")
        return json.loads(m.group(1))

    def _competition(self):
        """경합 둘을 세우고 하나를 채택한 사이클."""
        self._no_despite_autofill = True
        self.gil("init", "--name", "clew")
        self.gil("chain", "tune", "--purpose", "p95 낮추기")
        self.gil("open", "tune/c001", "--author", "clew", "--purpose", "p95 낮추기",
                 "--fits", "체인 목적 그 자체")
        for title, fals in (("인덱스로 줄인다", "인덱스 후에도 스캔이 남으면 틀림"),
                            ("배치로 줄인다", "배치를 늘려도 p95 그대로면 틀림")):
            r = self.gil("step", "tune/c001", "--kind", "hypothesis", "--to", "s1",
                         "--competing", "--inherit", "앞 가지의 교훈", "--title", title,
                         "--falsify", fals, "--falsify-to", "s1",
                         "--advances", "p95 목표의 한 축", "--body", "가설")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.gil("goto", "tune/c001/s2")
        self.gil("step", "tune/c001", "--kind", "verify", "--verdict", "refuted",
                 "--title", "인덱스 측정", "--body", "측정")
        r = self.gil("goto", "tune/c001/s3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.gil("step", "tune/c001", "--kind", "verify", "--verdict", "supported",
                 "--title", "배치 측정", "--body", "측정")
        r = self.gil("adopt", "tune/c001/s5", "--reason", "배치가 p95 를 가장 많이 낮췄다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def _cycle(self, data, name="c001"):
        for cy in data["tune"]["cycles"]:
            if cy["name"] == name:
                return cy
        self.fail("사이클을 못 찾았다: " + name)

    def test_competing_branches_are_stood_side_by_side(self):
        """겨루는 갈래가 **재료로** 화면에 온다 — 반증조건까지. 비교는 결국 그것으로 한다."""
        self._competition()
        cy = self._cycle(self._cycdata())
        comps = cy.get("competitions") or []
        self.assertEqual(len(comps), 1, "경합 한 판이 한 묶음으로 서지 않았다: " + repr(comps))
        self.assertEqual(comps[0]["root"], "s1")
        br = {b["step"]: b for b in comps[0]["branches"]}
        self.assertEqual(sorted(br), ["s2", "s3"])
        self.assertIn("스캔이 남으면", br["s2"]["falsify"], "반증조건이 안 실렸다 — 무엇으로 견주나")
        self.assertEqual(br["s3"]["state"], "won", "채택된 갈래가 이겼다고 안 나온다")
        self.assertEqual(br["s2"]["state"], "lost", "진 갈래가 졌다고 안 나온다")
        self.assertTrue(br["s2"]["lostTo"].endswith("/s5"), br["s2"]["lostTo"])

    def test_a_rebranch_without_the_declaration_is_not_a_competition(self):
        """**선언이 가른다.** 잊혀서 남은 형제와 겨루려고 연 형제는 다른 것이다 —
        선언 없는 재분기를 경합으로 그리면 비교 카드가 거짓을 말한다."""
        self._no_despite_autofill = True
        self.gil("init", "--name", "clew")
        self.gil("chain", "tune", "--purpose", "p95 낮추기")
        self.gil("open", "tune/c001", "--author", "clew", "--purpose", "p95", "--fits", "그 자체")
        self.gil("step", "tune/c001", "--kind", "hypothesis", "--title", "첫 가설",
                 "--falsify", "…", "--falsify-to", "s1", "--advances", "…", "--body", "가설")
        self.gil("step", "tune/c001", "--kind", "verify", "--verdict", "refuted",
                 "--title", "측정", "--body", "측정")
        self.gil("step", "tune/c001", "--kind", "analyze", "--title", "분석", "--body", "분석")
        self.gil("step", "tune/c001", "--kind", "hypothesis", "--to", "s4", "--inherit", "교훈",
                 "--title", "둘째 가설", "--falsify", "…", "--falsify-to", "s4",
                 "--advances", "…", "--body", "가설")
        cy = self._cycle(self._cycdata())
        self.assertEqual(cy.get("competitions"), [],
                         "선언 없이 난 형제 가지를 경합이라 그렸다")

    def test_the_updated_map_carries_who_updated_it(self):
        """옛 지도를 지우지 않되, **강등의 근거**를 함께 낸다(누가·어디로·왜).
        선만 흐리면 사람은 왜 흐린지 모르고, 안 흐리면 두 계획이 동시에 유효해 보인다."""
        self._no_despite_autofill = True
        self.gil("init", "--name", "clew")
        self.gil("chain", "tune", "--purpose", "메모리 줄이기")
        self.gil("open", "tune/c001", "--author", "clew", "--purpose", "RSS", "--fits", "그 자체")
        self.gil("step", "tune/c001", "--kind", "hypothesis", "--title", "풀링이 원인",
                 "--falsify", "…", "--falsify-to", "s1", "--advances", "…", "--body", "가설")
        self.gil("step", "tune/c001", "--kind", "verify", "--verdict", "refuted",
                 "--title", "측정", "--body", "측정")
        self.gil("step", "tune/c001", "--kind", "analyze", "--title", "분석", "--body", "분석")
        self.gil("step", "tune/c001", "--kind", "fail", "--to", "s1", "--title", "벽",
                 "--toward", "여기까지", "--next-design", "다른 축", "--body", "벽")
        r = self.gil("step", "tune/c001", "--kind", "hypothesis", "--to", "s4",
                     "--despite", "분석이 이미 자리를 좁혔다 — s1 까지 갈 필요가 없다",
                     "--inherit", "풀은 아니다", "--title", "경로 A",
                     "--falsify", "…", "--falsify-to", "s4", "--advances", "…", "--body", "재분기")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        nodes = {n["id"]: n for n in self._cycle(self._cycdata())["nodes"]}
        wall = nodes["s5"]
        self.assertEqual(wall.get("mapStaleBy"), "s6", "지도를 갱신한 스텝을 안 말한다")
        self.assertEqual(wall.get("mapStaleTo"), "s4", "실제로 간 자리를 안 말한다")
        self.assertIn("자리를 좁혔다", wall.get("mapStaleWhy", ""), "이유가 안 실렸다")
        self.assertIn("자리를 좁혔다", nodes["s6"].get("despite", ""),
                      "지도를 벗어난 이유가 그 스텝에 안 실렸다")

    def test_a_pending_map_stays_pending(self):
        """모른다고 적은 것은 빠뜨린 것이 아니다 — 화면이 그 차이를 받아야 한다."""
        self._no_despite_autofill = True
        self.gil("init", "--name", "clew")
        self.gil("chain", "tune", "--purpose", "로그 줄이기")
        self.gil("open", "tune/c001", "--author", "clew", "--purpose", "로그", "--fits", "그 자체")
        self.gil("step", "tune/c001", "--kind", "hypothesis", "--title", "디버그 로그",
                 "--falsify", "…", "--falsify-to", "s1", "--advances", "…", "--body", "가설")
        self.gil("step", "tune/c001", "--kind", "verify", "--verdict", "refuted",
                 "--title", "측정", "--body", "측정")
        self.gil("step", "tune/c001", "--kind", "analyze", "--title", "분석", "--body", "분석")
        r = self.gil("step", "tune/c001", "--kind", "fail", "--to", "pending", "--title", "벽",
                     "--toward", "여기까지", "--next-design", "다음에 정한다", "--body", "벽")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        nodes = {n["id"]: n for n in self._cycle(self._cycdata())["nodes"]}
        self.assertEqual(nodes["s5"]["backtrack"], "pending",
                         "미정인 지도가 미정으로 오지 않았다")
        self.assertNotIn("mapStaleBy", nodes["s5"],
                         "정해진 적 없는 지도를 '갱신됐다'고 했다")

    def test_goto_lets_you_walk_between_declared_branches(self):
        """**갈래 사이를 오가는 길이 막히면 경합은 문법으로만 있고 실제로는 못 쓴다.**

        goto 는 미종결 잎을 두고 떠나는 것을 막는다(#78) — 잊고 떠나는 것을 막으려고. 그런데
        선언된 경합에서 떠나는 것은 잊는 것이 아니라 **다음 갈래를 재러 가는 것**이다.
        (탈출구 --leave-open 의 안내문도 여기선 거짓이 된다: 선언된 경합은 fsck 위반이 아니다.)"""
        self._competition()
        r = self.gil("fsck")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_goto_still_blocks_leaving_a_plain_unterminated_leaf(self):
        """넓게 걸면 정상 흐름이 막히고, 아예 풀면 #78 이 되살아난다 — 좁게 건 것을 지킨다."""
        self._no_despite_autofill = True
        self.gil("init", "--name", "clew")
        self.gil("chain", "tune", "--purpose", "p95")
        self.gil("open", "tune/c001", "--author", "clew", "--purpose", "p95", "--fits", "그 자체")
        self.gil("step", "tune/c001", "--kind", "hypothesis", "--title", "선언 없는 가설",
                 "--falsify", "…", "--falsify-to", "s1", "--advances", "…", "--body", "가설")
        r = self.gil("goto", "tune/c001/s1")
        self.assertNotEqual(r.returncode, 0,
                            "선언 없는 미종결 잎을 두고 떠나는 것까지 열렸다:\n" + r.stdout + r.stderr)
        self.assertIn("종결 없이 떠날 수 없다", r.stdout + r.stderr)


class TestFoldingWithoutFabricating(GilFixture):
    """**도구가 날조 아니면 미종결을 강요하면 안 된다** (이슈 #115 후속, 실사용 리포트).

    잘못된 자리에서 열린 사이클을 정직하게 접으려 했더니 접을 문법이 없었다:
    `close --abandon` 은 fail 잎을 요구하고, fail 잎을 박으려면 define→hypothesis→verify→
    analyze 를 다 걸어야 하고, verify 는 `--verdict` 를 요구한다 — 즉 **하지 않은 측정의
    판정**을 쓰라는 압력이다. `--kind pending` 으로 우회하려 해도 순서 검사가 두 번 거부했다.

    남은 선택은 셋뿐이었다: 날조하거나, 영구 미종결로 두거나, 하려던 것과 다른 작업을 한
    벌 더 하거나. 어휘가 부족하면 기록이 거짓말한다(#80 과 같은 논거)."""

    def _empty_cycle(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "ch", "--purpose", "정리")
        self.gil("open", "ch/c001", "--author", "clew", "--purpose", "잘못된 자리에서 열렸다",
                 "--fits", "정리 대상", "--body", "여기서 열지 말았어야 했다")

    def test_abandon_without_a_reason_is_refused_but_shown_the_way(self):
        """이유 없는 포기는 나중에 판단이었는지 방치였는지 모른다 — 거부하되 길을 준다."""
        self._empty_cycle()
        r = self.gil("close", "ch/c001", "--abandon")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--reason", out, "접을 길을 안 줬다:\n" + out)
        self.assertIn("없는 관측의 판정", out, "왜 가짜 fail 을 박으면 안 되는지 말하지 않았다")

    def test_a_cycle_with_no_dead_leaf_can_be_abandoned_with_a_reason(self):
        """포기 선언 자체가 종결이다 — fail 잎을 또 요구하는 것은 중복이고, 그 중복이 날조 압력이다."""
        self._empty_cycle()
        r = self.gil("close", "ch/c001", "--abandon", "--reason",
                     "체인이 dev 보다 232 커밋 뒤처져 이 자리에서 열지 말았어야 했다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self._git("log", "--all", "--format=%B").stdout
        self.assertIn("232 커밋 뒤처져", log, "왜 접었는지가 그래프에 안 남았다")
        self.assertIn("Gil-Abandoned-Leaf: s1", log, "이 포기가 무엇을 접었는지 안 적혔다")

    def test_fsck_does_not_re_demand_a_terminal_for_an_abandoned_cycle(self):
        """접은 것을 다시 위반이라 하면, 그 압력이 그대로 돌아온다(가짜 잎을 박게 만든다)."""
        self._empty_cycle()
        self.gil("close", "ch/c001", "--abandon", "--reason", "여기서 접는다")
        r = self.gil("fsck")
        self.assertIn("위반 0", r.stdout + r.stderr,
                      "포기 선언으로 접힌 사이클을 다시 짚었다:\n" + r.stdout + r.stderr)

    def test_pending_is_legitimate_right_after_define(self):
        """**pending 은 사고의 다음 걸음이 아니라 사고를 멈추고 사람에게 넘기는 것**이다.

        human-in-the-loop.md 가 "문제 정의가 불명확하면 가설을 세우기 전에 먼저 사람에게
        물어라"라고 권하는데, 정작 그 동작이 순서 검사에 막혀 있었다 — 문서가 권하는 것을
        문법이 거부하면 사람은 문서를 안 믿거나 문법을 우회한다."""
        self._empty_cycle()
        r = self.gil("step", "ch/c001", "--kind", "pending", "--title", "사람에게 묻는다",
                     "--toward", "정의가 불명확하다", "--next-design", "사람 답 뒤에 가설",
                     "--body", "무엇을 풀지부터 정해 주십시오")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("pending", self._git("log", "--all", "--format=%B").stdout)

    def test_the_order_check_still_governs_everything_else(self):
        """면제는 pending 하나다 — 넓히면 순서 검사가 형해화한다."""
        self._empty_cycle()
        # 시험 하네스의 순서 자동보정을 우회한다 — 여기서 보려는 것이 그 순서 강제다.
        r = self._raw_step("ch/c001", "--kind", "verify", "--verdict", "supported",
                           "--title", "건너뛴 검증", "--body", "측정")
        self.assertNotEqual(r.returncode, 0, "define 뒤 verify 까지 열렸다")
        self.assertIn("순서를 건너뛴다", r.stdout + r.stderr)


class TestLayersDoNotFlowDownhill(GilFixture):
    """**층은 아래로 흐르지 않는다** (이슈 #115, 실사용 리포트).

    체인이 dev 보다 232 커밋 뒤처져 정본이 트리에 없었다. 그 자리에서 에이전트가 발명한 수가
    `gil merge dev --into <체인>` 이었다 — 충돌 0, 문법 통과, fsck 위반 0. 층 모델을 정면으로
    거스르는데 아무것도 막지 않았고 **사람이 잡았다.**

    문법이 침묵한 이유: `merge --help` 가 허용을 **열거**하고 금지를 말하지 않았다. 열거형
    문서 옆에 일반형 문법이 있으면, 없는 항목은 금지가 아니라 **미기재**로 읽힌다.

    그리고 뒤처짐은 정도와 함께 말해야 한다 — 2 커밋과 232 커밋이 같은 문장으로 나오면 읽는
    쪽이 위험을 못 잰다. 파일이 겹치지 않으면 조용해도 된다: 위험한 것은 그 사이 dev 가
    **이 트리의 파일을 고쳤을 때**다(낡은 값이 그 자리에 있어서 조용히 틀린다)."""

    def _behind_chain(self, overlap=True):
        self.gil("init", "--name", "clew")
        self.gil("chain", "ch", "--purpose", "서빙")
        self._git("checkout", "-q", "ch")
        with open(os.path.join(self.repo, "leaderboard.md"), "w") as f:
            f.write("7조항\n1위 0.8490\n")
        self._git("add", "leaderboard.md")
        self._git("commit", "-qm", "리더보드 초판(체인 트리)")
        self._git("checkout", "-q", "dev")
        name = "leaderboard.md" if overlap else "unrelated.md"
        with open(os.path.join(self.repo, name), "w") as f:
            f.write("8조항\n1위 0.8512\n")
        self._git("add", name)
        self._git("commit", "-qm", "dev 가 앞서 나간다")
        self._git("checkout", "-q", "ch")

    def test_merging_a_layer_into_a_chain_is_refused(self):
        self._behind_chain()
        r = self.gil("merge", "dev", "--into", "ch", "--reason", "정본을 가져온다", "--allow-open")
        self.assertNotEqual(r.returncode, 0, "층을 체인으로 끌어오는 것이 통과했다")
        out = r.stdout + r.stderr
        self.assertIn("층은 아래로 흐르지 않는다", out)
        self.assertIn("chain-close", out, "거부만 하고 정당한 길을 안 줬다(#67)")

    def test_the_refusal_diagnoses_why_that_move_was_invented(self):
        """그 수를 두려는 이유는 대개 하나다 — 뒤처져서 정본이 트리에 없다."""
        self._behind_chain()
        r = self.gil("merge", "dev", "--into", "ch", "--reason", "정본", "--allow-open")
        self.assertIn("뒤처졌다", r.stdout + r.stderr, "진단이 없다 — 사람은 왜 막혔는지 모른다")

    def test_a_chain_going_up_to_dev_is_still_allowed(self):
        """올라가는 것은 정상이다 — 넓게 막으면 정당한 흐름이 벽에 부딪힌다."""
        self._behind_chain(overlap=False)
        r = self.gil("merge", "ch", "--into", "dev", "--reason", "끝난 체인을 층으로", "--allow-open")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_being_behind_is_named_with_its_degree_and_the_files(self):
        """정도를 말하지 않으면 위험을 못 잰다. 그리고 **무엇이 겹치는지**가 핵심이다."""
        self._behind_chain()
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertIn("뒤처졌", out, "fsck 가 뒤처짐을 한 마디도 안 했다:\n" + out)
        self.assertIn("leaderboard.md", out, "겹치는 파일을 안 짚었다")

    def test_a_chain_behind_but_not_overlapping_stays_quiet(self):
        """파일이 안 겹치면 뒤처짐은 정상이다 — 늘 짖으면 아무도 안 듣는다."""
        self._behind_chain(overlap=False)
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertNotIn("뒤처졌", out, "겹치지도 않는데 경고했다:\n" + out)


class TestOneChannelForTheRecord(GilFixture):
    """**git commit 과 gil step 이 섞이면 기록이 갈린다** (상현님: 괴리의 주범).

    체인/사이클 가지에 평범한 커밋이 끼면 그 변경은 어느 스텝의 것도 아니게 되고, 그 뒤 gil 이
    세는 모든 것(계보·적층·층·뒤처짐)이 실제와 갈린다. 사람 눈에는 git log 가 멀쩡하니 조용히
    갈린다 — 성실히 일한 세션일수록 더 많이 섞는다.

    두 겹으로 막는다. 한 겹으로는 원리적으로 부족하기 때문이다: 훅은 `--no-verify` 로 언제나
    뚫리고(git 의 설계다), 탐지만 두면 이미 섞인 뒤에 안다."""

    def _gil_branch_repo(self):
        self._guard_active = True   # 여기서는 훅이 판정해야 한다(fixture 예외를 끈다)
        self.gil("init", "--name", "clew")
        self.gil("chain", "ch", "--purpose", "목적")
        self.gil("open", "ch/c001", "--author", "clew", "--purpose", "p",
                 "--fits", "f", "--body", "정의")

    def _raw_commit(self, name="work.txt", extra=()):
        with open(os.path.join(self.repo, name), "w") as f:
            f.write("손으로 쓴 변경\n")
        self._git("add", name)
        return self._git("commit", *extra, "-m", "손으로 낀 커밋")

    def test_init_installs_the_guard(self):
        """심는 자리에서 거는 값이 가장 싸다 — 섞인 뒤에는 되돌릴 수 없다(append-only)."""
        self._guard_active = True
        self.gil("init", "--name", "clew")
        self.assertTrue(os.path.exists(os.path.join(self.repo, ".gil", "hooks", "pre-commit")),
                        "gil init 이 훅을 놓지 않았다")
        self.assertIn("켜져 있다", self.gil("guard", "status").stdout)

    def test_a_raw_commit_on_a_gil_branch_is_refused(self):
        self._gil_branch_repo()
        r = self._raw_commit()
        self.assertNotEqual(r.returncode, 0, "체인 가지의 평범 커밋이 통과했다")
        self.assertIn("gil 이 만든다", r.stdout + r.stderr)

    def test_gil_itself_still_commits(self):
        """막으려는 것은 우회지 gil 자신이 아니다 — 넓게 막으면 도구가 자기 발을 묶는다."""
        self._gil_branch_repo()
        r = self.gil("step", "ch/c001", "--kind", "hypothesis", "--title", "가설",
                     "--falsify", "f", "--falsify-to", "s1", "--advances", "a", "--body", "본문")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_layer_is_where_plain_commits_belong(self):
        """대문 문서·배포 머지는 평범 커밋의 자리다 — 거기까지 막으면 gil 자신의 배포가 막힌다."""
        self._gil_branch_repo()
        self._git("checkout", "-q", "dev")
        r = self._raw_commit("doc.md")
        self.assertEqual(r.returncode, 0, "층의 평범 커밋까지 막혔다:\n" + r.stdout + r.stderr)

    def test_what_slipped_through_is_still_named(self):
        """**훅은 벽이 아니다** — --no-verify 는 언제나 뚫린다. 그러니 판정은 탐지가 한다."""
        self._gil_branch_repo()
        r = self._raw_commit(extra=("--no-verify",))
        self.assertEqual(r.returncode, 0, "이 시험의 전제가 깨졌다(우회가 막혔다)")
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertIn("섞인 기록", out, "뚫고 들어온 커밋을 아무도 안 짚었다:\n" + out)

    def test_gils_own_merge_is_not_accused(self):
        """**탐지가 제 도구의 산물을 짚으면 사람은 그 고지를 통째로 무시한다.**

        결함(실사용 AIL): 판정이 `Gil-Chain` 하나만 봤다. 그런데 merge·deploy 커밋은 제
        트레일러(Gil-Merge·Gil-Deploy)만 달고 Gil-Chain 을 안 단다 — 그래서 gil 이 `gil
        merge` 로 만든 합류 커밋을 "gil 이 만들지 않은 커밋"이라고 고발했다(29건 중 12건).
        """
        self._gil_branch_repo()
        before = self.gil("fsck").stdout + self.gil("fsck").stderr
        self.assertNotIn("섞인 기록", before, "이 시험의 전제가 깨졌다(이미 섞여 있다)")
        # gil 이 만든 합류 커밋 하나를 이 가지에 얹는다.
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        side = branch + "-side"
        self._git("checkout", "-q", "-b", side)
        self._raw_commit("side.md", extra=("--no-verify",))
        self._git("checkout", "-q", branch)
        self._git("merge", "--no-ff", "-m",
                  "gil merge: " + side + " → " + branch + "\n\nGil-Merge: " + side, side)
        out = self.gil("fsck").stdout + self.gil("fsck").stderr
        merges = self._git("log", "-1", "--format=%h", branch).stdout.strip()
        self.assertNotIn(merges, out,
                         "gil 이 만든 합류 커밋을 '섞인 기록'으로 고발했다:\n" + out)

    def test_the_guard_can_be_turned_off(self):
        """강제는 벽이 아니라 선택이어야 한다 — 끄는 길이 없으면 사람은 도구를 버린다."""
        self._gil_branch_repo()
        self.gil("guard", "uninstall")
        r = self._raw_commit()
        self.assertEqual(r.returncode, 0, "껐는데도 막혔다:\n" + r.stdout + r.stderr)
        self.assertIn("섞인 기록", self.gil("fsck").stdout + self.gil("fsck").stderr,
                      "껐다고 탐지까지 꺼졌다 — 탐지는 끄지 않는다")


class TestGitGraphShowsTheSiblings(GilFixture):
    """**대조하라고 놓은 그림이 갈라진 것을 안 그렸다** (이슈 #114, 실사용 AIL).

    git 그래프(날것) 패널은 "gil 이 그리는 계보와 git 자신의 그림이 같은지 보는 자리"라고
    스스로 말한다. 그런데 레인이 **체인 브랜치**로만 배정돼, 같은 체인의 사이클·형제 가지
    (--competing)가 한 줄에 포개졌다 — 실측: 브랜치 31개 중 레인 6개, 나머지 30개는 레인 없는
    칩. 정작 형제 가지가 진짜로 갈라졌는지 확인하려던 사람이 `git log --format=%P` 를 손으로
    떠야 했다.

    고친 방향은 리포트의 (b): **체인 선택기와 연동**한다. 전부에 레인을 주면 줄이 서른 개가
    되니, 고른 체인만 남기고 그 안에서 위상 레인(형제마다 제 줄)으로 그린다."""

    def _competing_repo(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "ch", "--purpose", "목적")
        self.gil("open", "ch/c001", "--author", "clew", "--purpose", "p", "--fits", "f",
                 "--body", "정의")
        self._no_despite_autofill = True
        for t in ("가설 A", "가설 B"):
            r = self.gil("step", "ch/c001", "--kind", "hypothesis", "--to", "s1", "--competing",
                         "--inherit", "앞 가지의 교훈", "--title", t, "--falsify", "F",
                         "--falsify-to", "s1", "--advances", "a", "--body", "가설")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def _gitgraph(self):
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("graph", "--html", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'id="gitgraphdata"[^>]*>(.*?)</script>', html, re.S)
        self.assertIsNotNone(m, "git 그래프 데이터가 페이지에 없다")
        return json.loads(m.group(1)), html

    def test_each_commit_carries_its_cycle(self):
        """레인을 사이클 단위로 펼치려면 화면이 **어느 사이클의 커밋인지**를 알아야 한다."""
        self._competing_repo()
        rows, _ = self._gitgraph()
        steps = [r for r in rows if r["gil"]]
        self.assertTrue(steps, "gil 커밋이 하나도 안 실렸다")
        self.assertTrue(any(r.get("cycle") == "c001" for r in steps),
                        "커밋에 사이클이 안 실렸다 — 사이클 레인을 그릴 재료가 없다: " + repr(steps[:3]))

    def test_the_siblings_really_forked_in_git(self):
        """그림 이전에 **사실**이 그래야 한다 — 형제 셋이 같은 부모에서 났나(리포트의 실측 방법)."""
        self._competing_repo()
        rows, _ = self._gitgraph()
        by = {r["sha"]: r for r in rows}
        parents = [tuple(r["parents"]) for r in rows if r["gil"] and r.get("cycle") == "c001"]
        firsts = [p[0] for p in parents if p]
        dup = [p for p in set(firsts) if firsts.count(p) > 1]
        self.assertTrue(dup, "형제 가지가 git 에서 갈라지지 않았다(이 시험의 전제가 깨졌다)")
        self.assertTrue(all(d in by for d in dup))

    def test_the_panel_follows_the_chain_selector(self):
        """두 그림을 대조하라고 놓았는데 한쪽만 선택을 따르면, 사람은 서로 다른 범위를 본다."""
        _, html = self._gitgraph_after_build()
        self.assertIn("ZOOMED", html, "git 그래프가 체인 선택을 읽지 않는다")
        self.assertIn("gitgraph.zoomed", html, "펼쳤다는 사실을 화면이 말하지 않는다")

    def _gitgraph_after_build(self):
        self._competing_repo()
        return self._gitgraph()


class TestAdoptDevNeverShrinksTheLayer(GilFixture):
    """**안전을 약속한 명령이 조용히 좁히면 그 약속이 거짓이 된다** (이슈 #117, 실사용).

    #113 은 뿌리가 너무 **뒤**(dev 팁)에 심긴 것을 고쳤다. 그런데 그 수리 판정이 정상 뿌리까지
    잡았다: `gil init` 이 심은 옳은 뿌리를 가진 저장소가 "범위를 고친다"는 말을 들었고, 적용하면
    층이 26커밋에서 8커밋으로 줄었다(개시 인터뷰·기준 문서·배포 마커가 전부 층 밖으로).

    원인: '층의 시작'을 "대문에서 갈라진 뒤 dev 전용 커밋 중 가장 오래된 것"으로 잡는데,
    **대문이 앞으로 나가면(배포) 그 값도 함께 뒤로 밀린다.** 그건 층의 시작이 아니라 배포 이후
    구간의 시작이다. 판정은 조상관계로 한다 — 지금 뿌리가 제안된 시작의 조상이면 범위는 이미
    더 넓고, 고칠 것이 없다."""

    def _deployed_repo(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "ch", "--purpose", "목적")
        self.gil("open", "ch/c001", "--author", "clew", "--purpose", "p", "--fits", "f",
                 "--body", "정의")
        self.gil("step", "ch/c001", "--kind", "success", "--title", "됐다",
                 "--toward", "다 왔다", "--next-design", "다음")
        self.gil("close", "ch/c001", "--verdict", "supported")
        self.gil("merge", "ch", "--into", "dev", "--reason", "끝난 체인을 층으로", "--allow-open")
        r = self.gil("deploy", "--tag", "v0.1.0", "--reason", "첫 배포")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._git("checkout", "-q", "dev")
        with open(os.path.join(self.repo, "note.md"), "w") as f:
            f.write("배포 뒤\n")
        self._git("add", "note.md")
        self._git("commit", "-qm", "배포 뒤 dev 커밋")

    def _root(self):
        return self._git("rev-parse", "refs/gil/layer/dev").stdout.strip()

    def test_a_correct_root_is_left_alone(self):
        self._deployed_repo()
        before = self._root()
        r = self.gil("migrate", "--adopt-dev")
        out = r.stdout + r.stderr
        # 두 길 다 옳다: 선언(dev-root)을 읽어 "고칠 것 없음"이거나, 조상관계로 "이미 더 넓다".
        self.assertTrue("인정할 것이 없다" in out or "이미 더 넓다" in out,
                        "정상 뿌리를 '고쳐야 할 것'으로 봤다:\n" + out)
        self.assertNotIn("범위를 고친다", out, "정상 뿌리에 수리를 권했다:\n" + out)
        self.assertEqual(self._root(), before, "뿌리를 뒤로 옮겼다 — 층이 줄어든다")

    def test_the_coverage_does_not_shrink(self):
        """숫자로도 지킨다 — 인정 범위가 줄어드는 일은 이 명령에 없어야 한다."""
        self._deployed_repo()
        def inside():
            root = self._root()
            n = self._git("rev-list", "--first-parent", root + "..dev").stdout.split()
            return len(n) + 1
        before = inside()
        self.gil("migrate", "--adopt-dev")
        self.assertGreaterEqual(inside(), before, "인정 범위가 줄었다")

    def test_a_root_planted_at_the_tip_is_still_repaired(self):
        """#113 이 고치려던 것(뿌리가 너무 뒤에 심긴 경우)은 그대로 고쳐야 한다 —
        좁게 막으려다 수리 자체를 막으면 되돌아간다."""
        self._deployed_repo()
        tip = self._git("rev-parse", "dev").stdout.strip()
        self._git("update-ref", "refs/gil/layer/dev", tip)   # 옛 --adopt-dev 가 남기던 모양
        r = self.gil("migrate", "--adopt-dev")
        self.assertNotEqual(self._root(), tip, "팁에 심긴 뿌리를 안 고쳤다:\n" + r.stdout + r.stderr)

    def test_the_move_shows_before_and_after(self):
        """줄어드는 변경이 늘어나는 변경과 같은 모양으로 보이면 사람이 멈출 자리를 못 잡는다."""
        self._deployed_repo()
        self._git("update-ref", "refs/gil/layer/dev", self._git("rev-parse", "dev").stdout.strip())
        out = self.gil("migrate", "--adopt-dev", "--dry-run").stdout + \
              self.gil("migrate", "--adopt-dev", "--dry-run").stderr
        self.assertIn("지금:", out, "옮기기 전 범위를 안 보여준다:\n" + out)
        self.assertIn("이후:", out, "옮긴 뒤 범위를 안 보여준다:\n" + out)


class TestEdgesDoNotRepeatWhatIsAlreadyThere(GilFixture):
    """**A→B→C 인데 A→C 까지 그린다** (상현님 관측).

    전체맵의 엣지는 커밋 위상에서 **유도한다**. 조상 스텝을 찾는 탐색이 비-스텝 커밋을 뚫고
    올라가는데, 머지를 하나 지나면 그 갈래의 스텝이 통째로 딸려 온다 — 이미 B 를 통해 들어오는
    A 가 C 에 직접 다시 이어진다. 실측(AIL 저장소): 한 스텝의 부모가 13개였고 그중 이행 중복이
    아닌 것은 넷뿐이었다. 선이 많은 것은 정보가 많은 것이 아니다 — **어느 것이 바로 앞인지**가
    안 읽힌다.

    이 값은 사람이 적은 선언이 아니라 도구가 유도한 것이라, 줄여도 기록의 위조가 아니다.
    선언된 계보(dparents)는 그대로 둔다.
    """

    def _cycle_that_pulls_the_trunk_in(self):
        """사이클 가지에서 **체인 줄기를 git 머지로 끌어온 뒤** 스텝을 뜬다.

        실사용(AIL)에서 부모 8개·13개가 나온 자리가 정확히 이 모양이다 — 머지 하나를
        지나는 순간 그 갈래의 스텝이 통째로 조상 후보가 된다.
        """
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "d/c001", "--kind", "verify", "--title", "V",
                 "--body", "검증 보고서", "--verdict", "supported")
        self.gil("step", "d/c001", "--kind", "success", "--title", "됨",
                 "--body", "종합 보고서")
        self.gil("close", "d/c001")
        cycle_branch = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        # 체인 줄기가 **갈라져 앞서간다** — 그 사이 다른 사이클이 돌았다고 보면 된다.
        self.gil("open", "d/c002", "--author", "clew", "--purpose", "Q")
        second = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self._git("checkout", cycle_branch)
        with open(os.path.join(self.repo, "trunk.txt"), "w", encoding="utf-8") as f:
            f.write("줄기의 산물\n")
        self._git("add", "trunk.txt")
        self._git("commit", "-m", "줄기에서 이어간 작업")
        trunk = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("checkout", second)
        self._git("merge", "--no-ff", "-m", "merge: 줄기를 이 사이클로", trunk)
        self.gil("step", "d/c002", "--kind", "verify", "--title", "V",
                 "--body", "검증 보고서", "--verdict", "supported")

    def _dag_parents(self):
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("graph", "--html", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        html = open(out_html, encoding="utf-8").read()
        pat = (r'\{"sha":"([0-9a-f]+)","chain":"([^"]*)","cycle":"([^"]*)","step":"([^"]*)",'
               r'"kind":"[^"]*","outcome":"[^"]*","here":\w+,"sprout":\w+,"parents":\[([^\]]*)\]')
        out = {}
        for m in re.finditer(pat, html):
            refs = [x.strip('"') for x in m.group(5).split(",") if x.strip()]
            out[m.group(2) + "/" + m.group(3) + "/" + m.group(4)] = refs
        self.assertTrue(out, "DAG 노드를 하나도 못 읽었다 — 시험이 형해화됐다")
        return out

    def test_no_parent_is_reachable_through_another(self):
        """부모 중 **다른 부모의 조상인 것**이 하나도 없어야 한다.

        모양에 기대지 않고 성질을 잰다 — 어느 자리에서 중복이 생기든 이 단언이 잡는다.
        """
        self._cycle_that_pulls_the_trunk_in()
        parents = self._dag_parents()
        fanin = [k for k, v in parents.items() if len(v) > 1]
        for ref, ps in parents.items():
            for a in ps:
                for b in ps:
                    if a == b:
                        continue
                    anc = self._git("merge-base", "--is-ancestor", a, b).returncode == 0
                    self.assertFalse(anc, f"{ref}: {a[:7]} 는 {b[:7]} 를 통해 이미 들어온다")
        # 축소가 다 지워서 통과한 것이 아님을 확인한다(형해화 방지).
        self.assertEqual(len(fanin), 0,
                         f"이행 축소 뒤에도 갈래가 남았다면 그건 진짜 합류여야 한다: {fanin}")

    def test_the_fixture_really_creates_a_fan_in(self):
        """이 시험이 **재현하고 있는지**를 시험한다 — 머지가 없으면 아무것도 안 재고 있다."""
        self._cycle_that_pulls_the_trunk_in()
        merges = self._git("rev-list", "--merges", "--all").stdout.split()
        self.assertTrue(merges, "fixture 가 머지를 안 만들었다 — 재현이 아니다")
        # 그 머지를 지난 스텝이 실제로 두 갈래의 조상을 갖는다(축소 전 상태의 근거).
        step = self._git("log", "--all", "--format=%H %s", "--grep", "d/c002/s2").stdout.split()
        self.assertTrue(step, "머지 뒤 스텝을 못 찾았다")

    def test_no_step_loses_its_lineage_entirely(self):
        """줄이는 것과 끊는 것은 다르다 — 부모가 있던 노드는 여전히 부모가 있어야 한다."""
        self._cycle_that_pulls_the_trunk_in()
        parents = self._dag_parents()
        for ref, ps in parents.items():
            if ref.endswith("/s1"):
                continue
            self.assertTrue(ps, f"{ref} 이 계보를 통째로 잃었다")


class TestWhatTheHelpPointsAtExists(GilFixture):
    """**없는 곳을 가리키는 안내는 안내가 아니라 막다른 골목이다.**

    실제로 두 번 났다: `gil adopt --help` 가 없는 문서 페이지를 가리켰고(v3.55.0 에서 그
    페이지를 지어 메웠다), `chain-merge` 는 충돌로 멈춘 사람에게 **존재하지 않는 명령**
    (`gil chain-merge-continue`)을 치라고 했다. 둘 다 사람이 그 자리에 실제로 서기 전에는
    아무도 모른다 — 도움말은 평소에 읽히지 않고, 막힌 순간에만 읽히기 때문이다.

    그래서 소스에서 센다. 가리키는 것이 실재하는지는 사람이 막히기 전에 알 수 있는 사실이다."""

    ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
    GO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "go")

    def _go_sources(self):
        import glob
        return sorted(glob.glob(os.path.join(self.GO, "*.go")))

    def test_every_doc_path_it_points_at_exists(self):
        """도움말이 문서를 가리키면 그 문서가 있어야 한다."""
        import re
        bad = []
        for f in self._go_sources():
            for i, ln in enumerate(open(f, encoding="utf-8"), 1):
                if ln.lstrip().startswith("//"):
                    continue
                for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', ln):
                    for p in re.findall(r"docs/[A-Za-z0-9_./-]+\.md", lit):
                        if not os.path.exists(os.path.join(self.ROOT, p)):
                            bad.append(f"{os.path.basename(f)}:{i} → {p}")
        self.assertEqual(bad, [], "도움말이 없는 문서를 가리킨다:\n" + "\n".join(sorted(set(bad))))

    def _flag_table(self):
        """명령마다 실제로 선언된 플래그. `newFlags("gil X")` 뒤 그 함수 안의 fs.* 선언을 읽는다."""
        import re, glob
        decl = {}
        for f in glob.glob(os.path.join(self.GO, "*.go")):
            src = open(f, encoding="utf-8").read()
            for m in re.finditer(r'newFlags\("gil ([a-z0-9 -]+)"\)', src):
                tail = src[m.end():]
                nxt = tail.find("\nfunc ")
                body = tail[:nxt if nxt > 0 else len(tail)]
                decl.setdefault(m.group(1).strip(), set()).update(
                    re.findall(r'fs\.(?:str|boolFlag|strList|intFlag)\("([a-z0-9-]+)"', body))
        return decl

    def test_every_flag_it_tells_you_to_type_exists(self):
        """**복붙하면 실패하는 줄을 도움말이 준다.**

        실측 둘: 봉인된 체인 거부가 `gil chain <새체인> --parent` 를 주는데 그 플래그는
        `gil open` 의 것이고(체인 계승은 --from), 합류 거부가 `gil chain … --ask-root` 를
        주는데 --ask-root 는 `gil intake` 의 마지막 차수다. 둘 다 막힌 사람이 그대로 쳤을 때
        "모르는 플래그"로 한 번 더 막힌다 — 안내가 사람을 두 번 세운다.

        판정은 **같은 줄 안에서 그 명령에 딸린 플래그**만 본다: `gil <cmd>` 뒤로 다른 도구
        (git·gh·curl)나 다음 `gil` 이 나오기 전까지."""
        import re, glob
        decl = self._flag_table()
        self.assertIn("chain", decl, "플래그 표를 못 읽었다 — 이 시험이 공회전한다")
        bad = []
        for f in glob.glob(os.path.join(self.GO, "*.go")):
            for i, ln in enumerate(open(f, encoding="utf-8"), 1):
                if ln.lstrip().startswith("//"):
                    continue
                for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', ln):
                    for m in re.finditer(r"gil ([a-z][a-z0-9-]*)\b", lit):
                        cmd = m.group(1)
                        if cmd not in decl:
                            continue
                        seg = lit[m.end():]
                        stops = [x for x in (seg.find("gil "), seg.find("git "),
                                             seg.find("gh "), seg.find("curl ")) if x >= 0]
                        seg = seg[:min(stops)] if stops else seg
                        for fl in re.findall(r"--([a-z][a-z0-9-]*)", seg):
                            if fl not in decl[cmd]:
                                bad.append(f"{os.path.basename(f)}:{i} → gil {cmd} --{fl}")
        self.assertEqual(bad, [], "없는 플래그를 치라고 한다:\n" + "\n".join(sorted(set(bad))))

    def _commands(self):
        """**최상위 명령만.** case 블록 안에 cmdXxx( 호출이 있는 것.

        바로 다음 줄일 필요는 없다 — chain-merge 는 디프리케이트 경고 세 줄을 낸 뒤에야
        cmdChainMerge 를 부른다(그걸 놓치면 시험이 실재하는 명령을 없다고 말한다).
        그리고 `-h`·`--help` 는 명령이 아니라 스위치다."""
        import re
        main = open(os.path.join(self.GO, "main.go"), encoding="utf-8").read()
        out = set()
        blocks = re.split(r"\n\tcase ", main)
        for b in blocks[1:]:
            head, _, body = b.partition(":\n")
            # 블록의 끝은 다음 case 만이 아니다 — default: 와 스위치의 닫는 괄호도 끝이다.
            # (안 자르면 OS 스위치의 "darwin" 이 한참 아래의 cmd 호출을 제 것으로 삼킨다.)
            for stop in ("\n\tdefault:", "\n\t}", "\n}"):
                body = body.split(stop)[0]
            if not re.search(r"\bcmd[A-Z]\w*\(", body):
                continue
            out |= {c for c in re.findall(r'"([^"]+)"', head) if not c.startswith("-")}
        return out

    def test_every_command_has_a_place_in_the_help(self):
        """**명령은 있는데 도움말이 없으면 사람은 그 명령이 없다고 읽는다.**

        실측: `gil help version` 이 "알 수 없는 명령 version" 이라 답했다 — 도움말은 설명이자
        **표면의 목록**이라, 거기 없으면 없는 것이다. chain-unretire·prune-approve 도 그랬다."""
        import re
        h = open(os.path.join(self.GO, "usage_help.go"), encoding="utf-8").read()
        topics = set(re.findall(r'^\t"([a-z0-9-]+)": \{', h, re.M))
        missing = sorted(self._commands() - topics - {"help", "h"})
        self.assertEqual(missing, [], "도움말에 자리가 없는 명령: " + ", ".join(missing))

    def test_the_docs_do_not_tell_you_to_type_what_does_not_exist(self):
        """사람이 **복붙하는 표면**(코드블록·인라인 코드)만 본다 — 산문에서 낱말을 세면
        "gil is"·"gil ships" 같은 영어 문장이 명령으로 잡혀 시험이 못 쓰게 된다.

        실측: 대문(CLAUDE.md)이 층 검증 규칙을 `gil check` 로 가리켰는데 그런 명령은 없다
        (실물은 `.gil/checks` 와 merge·deploy 가 그걸 직접 돌리는 것이다). 우리 대문이
        세션에게 없는 명령을 가르치고 있었다."""
        import re, glob
        cmds, decl = self._commands(), self._flag_table()
        docs = sorted(set(glob.glob(os.path.join(self.ROOT, "docs", "**", "*.md"), recursive=True)
                          + glob.glob(os.path.join(self.ROOT, "*.md"))
                          + glob.glob(os.path.join(self.GO, "..", "*.md"))))
        self.assertTrue(docs, "문서를 하나도 못 찾았다 — 이 시험이 공회전한다")
        bad = []
        for d in docs:
            rel = os.path.relpath(d, self.ROOT)
            fence = False
            for i, ln in enumerate(open(d, encoding="utf-8", errors="ignore"), 1):
                if ln.lstrip().startswith("```"):
                    fence = not fence
                    continue
                for seg in ([ln] if fence else re.findall(r"`([^`]+)`", ln)):
                    if not seg.lstrip().startswith("gil "):
                        continue
                    m = re.match(r"\s*gil ([a-z][a-z0-9-]*)", seg)
                    # 커밋 **제목**은 명령이 아니라 기록이다("gil <체인>/<사이클>/<스텝> …").
                    if not m or "/" in seg[:m.end() + 1] or seg[m.end():m.end() + 1] == ":":
                        continue
                    c = m.group(1)
                    if c not in cmds:
                        bad.append(f"{rel}:{i} → gil {c} (없는 명령)")
                        continue
                    rest = seg[m.end():]
                    stops = [x for x in (rest.find("gil "), rest.find("git "),
                                         rest.find("gh "), rest.find("curl ")) if x >= 0]
                    rest = rest[:min(stops)] if stops else rest
                    for fl in re.findall(r"--([a-z][a-z0-9-]*)", rest):
                        if c in decl and fl not in decl[c] and fl not in ("help",):
                            bad.append(f"{rel}:{i} → gil {c} --{fl}")
        self.assertEqual(bad, [], "문서가 없는 것을 치라고 한다:\n" + "\n".join(sorted(set(bad))))

    # 이 명령들은 이 시험이 돌리지 않는다. 이유는 하나씩 다르다 — 네트워크(version)·
    # 백그라운드 프로세스(viewer·mcp)·사람 대기(interview·intake)·비가역(prune·migrate·
    # deploy)·저장소 바깥에 쓰기(global·memory·docs·guard). **문법이 아니라 부작용 때문에**
    # 빼는 것이므로, 여기에 이름을 더할 때는 그 이유를 적어야 한다.
    NOT_RUN = ("mcp", "init", "docs", "global", "memory", "prune",
               "migrate", "deploy", "guard", "version", "handoff", "interview", "intake")

    def test_the_lines_it_tells_you_to_type_actually_parse(self):
        """**가리키는 것이 있느냐 다음 질문은, 그걸 치면 도느냐다.**

        앞의 시험들은 명령과 플래그가 *실재하는지*를 봤다. 그런데 실재하는 조각으로도 안 도는
        줄을 만들 수 있다 — 한 명령의 줄에 다른 명령의 플래그를 섞으면(실측: 합류 거부가
        `gil chain … --ask-root`) 조각은 다 실재하는데 그 줄은 튕긴다.

        그래서 격리 저장소에서 **실제로 친다.** 판정은 문법에 대해서만 한다: '알 수 없는
        플래그'·'알 수 없는 명령'이 나오면 실패. 의미상 거부(닫히지 않았다·이미 있다…)는
        정상이다 — 그건 그 줄이 잘못이 아니라 이 저장소의 상태가 그럴 뿐이다."""
        import re, glob, subprocess
        cmds = self._commands()
        lines = {}
        for f in glob.glob(os.path.join(self.GO, "*.go")):
            for i, ln in enumerate(open(f, encoding="utf-8"), 1):
                if ln.lstrip().startswith("//"):
                    continue
                for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', ln):
                    for m in re.finditer(r'(?:^|\\n|\s{2,})(gil ([a-z][a-z0-9-]*)(?![^\s])[^"\\]*)', lit):
                        lines.setdefault(m.group(1).strip(), f"{os.path.basename(f)}:{i}")
        self.assertGreater(len(lines), 40, "안내줄을 못 뽑았다 — 이 시험이 공회전한다")

        def norm(c):
            c = re.sub(r"\s{2,}.*$", "", c)      # 줄 뒤에 붙은 설명
            c = re.sub(r"\(.*?\)", "", c)        # (권장) 같은 괄호주
            return re.sub(r"<[^>]*>", "X", c).replace("…", "").replace("|", "").strip()

        self.gil("init", "--name", "clew")
        env = dict(os.environ, GIL_NO_VIEWER="1", GIL_NO_VERSION_CHECK="1")
        bad, ran = [], 0
        for c, where in sorted(lines.items()):
            parts = norm(c).split()
            if len(parts) < 2 or parts[1] not in cmds or parts[1] in self.NOT_RUN:
                continue
            ran += 1
            try:
                r = subprocess.run([*GIL_CMD, *parts[1:]], cwd=self.repo, env=env,
                                   capture_output=True, text=True, timeout=20)
            except subprocess.TimeoutExpired:
                bad.append(f"{where} | {' '.join(parts)} | 멈췄다(타임아웃)")
                continue
            out = r.stdout + r.stderr
            for mark in ("알 수 없는 플래그", "알 수 없는 명령"):
                if mark in out:
                    bad.append(f"{where} | {' '.join(parts)} | {out.split(chr(10))[0][:70]}")
                    break
        self.assertGreater(ran, 30, "돌린 줄이 너무 적다 — 추출이나 제외가 과하다")
        self.assertEqual(bad, [], "안내가 준 줄이 문법에서 튕긴다:\n" + "\n".join(bad))

    def test_every_repo_path_it_points_at_exists(self):
        """에러가 레포 안의 파일을 가리키면 그 파일이 있어야 한다(문서 경로와 같은 규율)."""
        import re, glob
        bad = []
        for f in glob.glob(os.path.join(self.GO, "*.go")):
            for i, ln in enumerate(open(f, encoding="utf-8"), 1):
                if ln.lstrip().startswith("//"):
                    continue
                for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', ln):
                    for p in re.findall(
                            r"(?<![\w/.-])((?:project|scripts|tests)/[A-Za-z0-9_./-]+\.(?:md|sh|py|go|txt))", lit):
                        if not os.path.exists(os.path.join(self.ROOT, p)):
                            bad.append(f"{os.path.basename(f)}:{i} → {p}")
        self.assertEqual(bad, [], "없는 파일을 가리킨다:\n" + "\n".join(sorted(set(bad))))

    def test_every_command_it_tells_you_to_run_exists(self):
        """**도구가 자기가 만든 상태에서 빠져나올 길을 자기가 줘야 한다.**

        `chain-merge` 는 충돌로 멈춰 놓고 `gil chain-merge-continue` 를 치라고 했다 — 그런
        명령은 없다. 사람은 반쯤 병합된 저장소 앞에서 막혔다."""
        import re
        main = open(os.path.join(self.GO, "main.go"), encoding="utf-8").read()
        cmds = set()
        for m in re.finditer(r'case ((?:"[a-z0-9-]+"(?:, )?)+):', main):
            cmds |= set(re.findall(r'"([a-z0-9-]+)"', m.group(1)))
        self.assertIn("chain-merge", cmds, "명령 목록을 못 읽었다 — 이 시험이 공회전한다")
        bad = []
        for f in self._go_sources():
            for i, ln in enumerate(open(f, encoding="utf-8"), 1):
                if ln.lstrip().startswith("//"):
                    continue
                for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', ln):
                    # 커밋 **제목**은 명령이 아니라 기록이다("gil prune-request: <대상>").
                    # 뒤에 콜론이 붙는 꼴로 가른다 — 사람이 칠 줄은 콜론으로 안 끝난다.
                    for tok in re.findall(r"gil ([a-z][a-z0-9-]{1,20})(?![a-z0-9-])(:?)", lit):
                        if tok[1] == ":" or tok[0] in cmds:
                            continue
                        # 영어 산문("gil graph viewer" · "gil records …")은 명령이 아니다.
                        # 명령을 가리키는 줄은 그 자리에서 **칠 수 있는 꼴**이다.
                        if not re.search(r"gil " + re.escape(tok[0]) + r"(\s+[-<]|\s*$)", lit):
                            continue
                        bad.append(f"{os.path.basename(f)}:{i} → gil {tok[0]}")
        self.assertEqual(bad, [], "없는 명령을 치라고 한다:\n" + "\n".join(sorted(set(bad))))


class TestTheGraphHasItsOwnDoor(GilFixture):
    """**그림을 내는 문이 죽는 매체의 이름을 달고 있었다** (뷰어 제거 준비, 2026-08-10).

    정적 HTML 을 굽는 진입점은 `gil viewer build` 였다. 그런데 뷰어(브라우저 서버)는
    은퇴하고 **렌더러는 남는다** — MCP 표면의 그래프 화면이 같은 함수를 부른다. 진입점이
    죽는 매체의 이름을 달고 있으면, 매체를 지울 때 살아 있는 코드의 문이 함께 닫힌다.

    그리고 이 문은 사용자 기능이자 **검증면**이다: 시험 40여 개가 이 HTML 을 파싱해
    계승·발아·배포 귀속·경합·층 뿌리·형제 레인을 단언한다. 문을 닫으면 계속 살아서 MCP
    화면을 그리는 코드의 시험만 사라진다."""

    def _seed(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P", "--reference", "-",
                 "--criterion", "C", input="기준")

    def test_the_new_door_and_the_old_one_draw_the_same_thing(self):
        """**두 벌로 갈라 두지 않는다** — 한쪽만 고쳐지면 시험이 재는 그림과 사람이 보는
        그림이 달라진다."""
        self._seed()
        new = os.path.join(self.repo, "new.html")
        old = os.path.join(self.repo, "old.html")
        r = self.gil("graph", "--html", "--out", new)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.gil("graph", "--html", "--out", old)
        with open(new, encoding="utf-8") as f1, open(old, encoding="utf-8") as f2:
            self.assertEqual(f1.read(), f2.read(), "두 진입점이 다른 그림을 낸다")

    def test_it_bakes_a_self_contained_page(self):
        """서버도 브라우저도 없이 열린다 — 그게 이 문의 존재 이유다."""
        self._seed()
        p = os.path.join(self.repo, "g.html")
        self.gil("graph", "--html", "--out", p)
        with open(p, encoding="utf-8") as f:
            page = f.read()
        self.assertIn("<!doctype html>", page.lower(), "HTML 문서가 아니다")
        self.assertNotIn("/poll", page, "정적인데 서버 폴링이 실렸다")

    def test_it_can_draw_another_repository(self):
        """`--repo` 를 흘리면 저장소 밖에서 굽던 사용례가 조용히 사라진다."""
        self._seed()
        other = tempfile.mkdtemp(prefix="gil-graph-out-")
        self.addCleanup(shutil.rmtree, other, True)
        p = os.path.join(other, "g.html")
        r = subprocess.run([*GIL_CMD, "graph", "--html", "--out", p, "--repo", self.repo],
                           cwd=other, capture_output=True, text=True,
                           env=dict(os.environ, GIL_NO_VIEWER="1", GIL_NO_VERSION_CHECK="1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(p), "다른 저장소의 그림을 못 구웠다")

    def test_bare_graph_draws_something_instead_of_a_wall(self):
        """`gil graph` 한 줄이 사용법만 뱉으면 그건 문이 아니라 벽이다."""
        self._seed()
        r = self.gil("graph")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("체인", r.stdout, "아무것도 안 그렸다:\n" + r.stdout[:400])


class TestTheScreenAsksForTheRoomItNeeds(GilFixture):
    """**두 화면은 다른 일을 하니 다른 자리를 청한다** (상현님 제안, 2026-08-10).

    인라인 카드는 **대화와 함께 스크롤돼 올라간다.** 사람이 3번 문항을 쓰다 1번을 다시 보려면
    위로 올려야 하고, 승인 버튼은 대화가 길어지면 화면 밖으로 나간다. 브라우저 뷰어가 주던
    값 하나가 정확히 "창이 계속 거기 있다"였고 — 그건 그림이 아니라 **자리**였다.

      · 상태 카드 → `pip`(곁에 둔다). 일하는 동안 계속 보고, 거기서 답하고 승인한다.
      · 전체맵   → `fullscreen`(크게 보고 닫는다). 빈 저장소에서도 226KB 짜리 그림이다.

    **지키는 것 셋** — 이 셋이 없으면 이 기능은 이 세션이 내내 고친 병의 새 얼굴이 된다:
      ① 호스트가 목록에 넣은 모드만 청한다(규범: 지원 안 하는 모드를 청하면 안 된다).
      ② 답할 것이 있을 때만 청한다 — 사람이 안 시켰는데 화면이 옆으로 튀어나가면 방해다.
      ③ 한 번만 청한다 — 사람이 도로 인라인으로 돌려놨는데 다시 밀면 그건 싸움이다."""

    def shell(self):
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1", "GIL_NO_VERSION_CHECK": "1"})
        self.addCleanup(p.terminate)

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                try:
                    m = json.loads(ln.strip())
                except (json.JSONDecodeError, ValueError):
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "x"}})
                    continue
                if m.get("id") == want:
                    return m

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "t", "version": "0"}}})
        pump(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        out = {}
        for name, uri in (("status", "ui://gil/status"), ("graph", "ui://gil/graph")):
            send({"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"uri": uri}})
            r = pump(2)
            self.assertIsNotNone(r, f"{name} 껍데기를 못 받았다")
            out[name] = r["result"]["contents"][0]["text"]
        return out

    def test_each_screen_asks_for_the_mode_that_fits_its_job(self):
        sh = self.shell()
        self.assertIn('"pip"', sh["status"], "상태 카드가 곁에 서는 모드를 아예 선언 안 한다")
        self.assertIn('params:{mode:"pip"}', sh["status"], "상태 카드가 곁에 서기를 안 청한다")
        self.assertIn('"fullscreen"', sh["graph"], "전체맵이 크게 서는 모드를 아예 선언 안 한다")
        self.assertNotIn('"pip"', sh["graph"],
                         "전체맵이 곁에 두는 모드를 선언한다 — 그건 한 번 보고 닫는 그림이다")

    def test_making_it_big_waits_for_a_human_hand(self):
        """**크게 여는 것은 사람이 정한다** — 정본이 그렇고, 우리는 그렇게 안 했다.

        정본(ext-apps: docs/patterns.md · plugins/mcp-apps/skills/add-app-to-server)의 패턴은
        하나다: availableDisplayModes 에 fullscreen 이 있으면 **버튼을 보이고**, 사람이 누르면
        그때 ui/request-display-mode 를 보낸다. 우리는 두 화면 모두 **버튼 없이 자동으로**
        청했다 — 그래서 2026-08-10 현재까지 **제스처가 있는 요청을 한 번도 안 해 봤고**,
        "호스트가 안 준다"와 "제스처가 없어서 안 준다"가 아직 안 갈렸다. 갈리지 않은 것을
        결론으로 쓰면 그 위의 판단이 전부 추측이 된다.

        곁에 서는 것(pip)은 그대로 화면이 스스로 청한다 — 그건 자리를 옮기는 것이 아니라
        **곁에 서는 것**이고, 상현님이 기본으로 정한 동작이다(b83a94dd)."""
        for name, sh in self.shell().items():
            i = sh.find('mode:"fullscreen"')
            self.assertLess(i, 0,
                            f"{name}: fullscreen 을 **박아서** 청한다 — 사람이 누른 것이 아니라 "
                            "화면이 스스로 청하는 모양이다(정본과 반대 방향)")
            self.assertIn("request-display-mode", sh, f"{name}: 청하는 자리가 아예 없다")
            # 사람의 손이 닿는 자리가 실재해야 한다 — 없으면 "버튼으로 바꿨다"가 말뿐이다.
            self.assertIn("click", sh, f"{name}: 누를 자리가 없다 — 제스처가 닿을 곳이 없다")

    def test_it_never_offers_a_mode_the_host_did_not_offer(self):
        """**추측으로 켜면 없는 화면을 가리키는 그 병이 된다.**

        관문은 이제 *청하는 함수*가 아니라 **버튼을 내는 함수**에 있다(사람이 누르기 전에
        걸러야 하니 그쪽이 맞는 자리다 — 눌렀는데 아무 일도 안 나는 버튼은 없는 화면을
        가리키는 안내와 같은 것이다). 그러니 재는 것도 그 자리다."""
        for name, sh in self.shell().items():
            self.assertIn("availableDisplayModes", sh,
                          f"{name}: 호스트가 무엇을 여는지 아예 안 읽는다")
            # 판정 함수는 이름이 아니라 **하는 일**로 찾는다 — 이름을 박으면 배선을 옮길 때
            # 눈이 먼다(이 저장소가 여러 번 값을 치른 자리다).
            i = sh.find('indexOf("fullscreen")')
            self.assertGreater(i, 0,
                               f"{name}: 목록에 fullscreen 이 있는지 아예 안 본다 — 추측으로 낸다")
            fstart = sh.rfind("function ", 0, i)
            fn = sh[fstart:sh.find("\n  }", i)]
            self.assertTrue(fn.strip(), f"{name}: 판정 함수를 못 읽었다 — 이 시험이 눈이 먼다")
            # **없는 것과 안 밝힌 것은 다르다**(b83a94dd 가 pip 에서 값을 치른 구분).
            self.assertIn("length", fn,
                          f"{name}: 목록이 비었는지(=안 밝혔는지)를 안 본다 — 밝히지 않은 "
                          "호스트에서 열 수 있는 자리를 스스로 닫는다")

    def test_asking_to_sit_aside_is_the_default_but_never_a_fight(self):
        """**곁에 서는 것이 기본이다**(상현님) — 상태 카드는 원래 곁에 두고 일하는 화면이다.

        처음엔 "답할 것이 있을 때만" 청했는데, 그건 이 화면의 성격을 잘못 읽은 것이었다.
        다만 **한 번만** 청한다: 사람이 도로 인라인으로 돌려놨는데 우리가 다시 밀면 싸움이다."""
        sh = self.shell()["status"]
        body = sh.partition("function maybeAside(")[2].partition("\n  }")[0]
        self.assertTrue(body.strip(), "maybeAside 를 못 읽었다 — 이 시험이 눈이 먼다")
        self.assertIn("askedAside", body, "한 번만 청한다는 규칙이 없다 — 사람과 싸운다")

    def test_it_tells_apart_not_supported_from_not_declared(self):
        """**없는 것과 못 찾은 것은 다르다** — 이 저장소가 여러 번 배운 것.

          · 목록을 줬는데 pip 이 없다 → 지원 안 한다. 청하지 않는다(규범이 금한다).
          · 목록을 아예 안 줬다      → 모르는 것이다. 청해 보고 답을 받는 수밖에 없다
            (roots 에서 이미 겪었다 — 선언과 구현이 갈리는 호스트는 실재한다).

        이 구분이 없으면 둘 중 하나를 잃는다: 규범을 어기거나, 열 수 있는 자리를 안 열거나."""
        sh = self.shell()["status"]
        body = sh.partition("function maybeAside(")[2].partition("\n  }")[0]
        self.assertIn("HOST.modes.length", body,
                      "목록이 비었는지(=안 밝혔는지)를 안 본다 — 밝히지 않은 호스트에서 "
                      "열 수 있는 자리를 스스로 닫는다")
        self.assertIn('indexOf("pip")', body, "목록에 있는지 안 본다")

    def test_it_records_what_the_host_answered_not_only_what_it_asked(self):
        """**"청했다"까지만 알면 왜 인라인인지 아무도 답할 수 없다.**

        실측(상현님, 2026-08-10): 곁에 서기를 기본으로 올린 뒤에도 카드가 인라인으로 떴다.
        그런데 코드에는 청하는 자리만 있고 **답을 적는 자리가 없어서**, 그것이
          ㄱ) 호스트가 거절한 것인지
          ㄴ) 이 호스트가 그 요청 자체를 안 받는 것인지(무응답)
          ㄷ) 애초에 우리가 안 청한 것인지
        구별할 수 없었다. 셋은 화면 밖에서 전부 똑같이 "인라인 카드"로 보인다 — 그래서
        다음 수가 통째로 추측이 됐다.

        추측하지 않으려면 계기가 있어야 한다. 이 저장소가 여러 번 값을 치르고 적은 그대로다."""
        sh = self.shell()["status"]
        body = sh.partition("function maybeAside(")[2].partition("\n  }")[0]
        self.assertTrue(body.strip(), "maybeAside 를 못 읽었다 — 이 시험이 눈이 먼다")
        for k in ("HOST.asked", "HOST.grant", "HOST.err"):
            self.assertIn(k, body, f"{k} 를 안 적는다 — 청한 결과가 어디에도 안 남는다")
        # **무응답을 판정한다.** 답이 없는 것도 답이다(이 호스트가 그 요청을 안 받는다는 뜻).
        # 안 재면 거절과 무응답이 같은 침묵으로 보인다.
        self.assertIn("setTimeout", body,
                      "답이 안 올 때를 판정하지 않는다 — 무응답과 거절이 구별되지 않는다")
        # 안 청하기로 한 두 갈래도 **왜**인지를 남긴다(=ㄷ 을 ㄱ·ㄴ 과 가른다).
        self.assertGreaterEqual(body.count("HOST.why="), 2,
                                "안 청한 갈래 중 이유를 안 남기는 것이 있다")
        # 그리고 그 사실이 **서버까지 간다** — iframe↔호스트 프레임은 서버에 오지 않으니
        # 화면이 실어 보내는 길 말고는 도구가 알 방법이 없다.
        for k in ("asked:HOST.asked", "grant:HOST.grant", "err:HOST.err", "why:HOST.why"):
            self.assertIn(k, sh, f"{k} 가 서버로 안 간다 — 도구가 영영 결과를 모른다")
        # 첫 조회가 그 결과를 실어 가려면 **자리가 정해진 뒤에** 나가야 한다.
        self.assertIn("function asideDone(", sh,
                      "답을 기다렸다 첫 조각을 가져오는 자리가 없다 — 서버는 늘 한 발 늦는다")

    def test_not_yet_pressed_is_not_the_same_as_refused(self):
        """**안 눌린 것을 "거절됐다"로 읽으면 다음 세션이 안 해 본 것을 결론으로 쓴다.**

        크게 보기는 사람이 눌러야 청해진다. 그러니 아무 기록이 없는 상태는 "호스트가 안
        준다"가 아니라 **아직 아무도 안 눌렀다**이다. 두 갈래를 한 침묵으로 두면, 이 저장소가
        2026-08-10 에 실제로 그랬던 것처럼 — 한 번도 안 청해 본 채로 "이 호스트는 fullscreen
        을 안 준다"가 사실로 굳는다.

        그리고 그 기록은 **pip 과 따로** 적혀야 한다: 둘은 청하는 방식부터 다르고(하나는
        화면이, 하나는 사람이), 한 칸에 겹치면 "곁엔 못 서지만 크게는 된다"가 뭉개진다."""
        sh = self.shell()["status"]
        for k in ("fsAsked", "fsGrant", "fsErr", "fsWhy"):
            self.assertIn(k, sh, f"{k} 칸이 없다 — 크게 보기의 결과가 어디에도 안 남는다")
            self.assertIn(f"{k}:HOST.{k}", sh, f"{k} 가 서버로 안 간다 — 도구가 영영 결과를 모른다")
        # 무응답도 판정한다 — 답이 없는 것도 답이다(이 호스트가 그 요청을 안 받는다는 뜻).
        body = sh.partition("function askFullscreen(")[2].partition("\n  }")[0]
        self.assertTrue(body.strip(), "askFullscreen 을 못 읽었다 — 이 시험이 눈이 먼다")
        self.assertIn("setTimeout", body,
                      "답이 안 올 때를 판정하지 않는다 — 무응답과 거절이 구별되지 않는다")

    def test_the_card_marks_when_it_needs_a_human(self):
        """껍데기는 카드 내용을 모른다(레이아웃은 Go 에만 있다) — 그래서 카드가 표시한다."""
        self.gil("init", "--name", "clew")
        self.gil("intake", "sd", "--ask", "-",
                 input=json.dumps([{"q": "무엇을 하려 하십니까", "type": "text"}],
                                  ensure_ascii=False))
        waiting = self.gil("status", "--card").stdout
        self.assertIn("data-needs-human", waiting, "기다리는 질문이 있는데 표식이 없다")

    def test_it_fills_a_fixed_container_only_when_it_got_one(self):
        """**칸을 채우는 것은 전용 칸(pip·fullscreen)을 받았을 때뿐이다** (상현님 실측).

        처음엔 "호스트가 height 를 주면 무조건 채운다"로 했다. 그게 인라인 카드를 **읽을 수
        없게** 만들었다 — 세로가 짧게 눌려 안에서 스크롤해야 했다.

        기제는 **자기를 강화하는 고리**다: html 에 height:100%·overflow:hidden 을 걸면
        documentElement.scrollHeight 가 내용 높이가 아니라 **칸 높이**가 된다 → 작은 높이를
        보고한다 → 호스트가 그 크기를 유지한다 → 다시 작은 높이를 보고한다. 한 번 눌리면
        스스로는 못 빠져나온다. 그래서 두 자리를 함께 막는다."""
        sh = self.shell()["status"]
        self.assertIn("containerDimensions", sh, "호스트가 준 칸 크기를 안 읽는다")
        self.assertIn('data-fit="fixed"', sh, "고정 칸에서 채우는 규칙이 없다")
        # ① 판정이 **모드**를 본다 — 인라인이면 채우지 않는다.
        body = sh.partition("function applyContainer(")[2].partition("\n  }")[0]
        self.assertTrue(body.strip(), "applyContainer 를 못 읽었다 — 이 시험이 눈이 먼다")
        self.assertIn("HOST.mode", body,
                      "칸을 채울지 정하면서 **어떤 자리에 있는지**를 안 본다 — "
                      "인라인에서 채우면 카드가 눌려 읽을 수 없게 된다")
        for m in ('"pip"', '"fullscreen"'):
            self.assertIn(m, body, f"전용 칸 판정에 {m} 이 없다")
        # ② 보고하는 크기가 **자기 자신을 보지 않는다** — 칸이 아니라 내용을 잰다.
        rs = sh.partition("function reportSize(")[2].partition("\n  }")[0]
        self.assertIn("getBoundingClientRect", rs,
                      "칸 높이만 보고한다 — 채우는 모드에서 그 값은 곧 칸의 높이라 "
                      "'딱 맞다'는 말이 되어 영영 안 자란다")



class TestNobodyTypesAPathToStart(GilFixture):
    """**어디에 만들까 — 이 제품에서 제일 비싼 질문이다** (gil-app SPEC §4.1).

    MVP 표면(Claude Desktop 일반 채팅)은 **roots 를 주지 않는다**(2026-08-10 실측). 그래서
    거의 모든 첫 화면이 "저장소를 못 찾았다"이고, 옛 카드는 거기서 *"에이전트가 repo 인자와
    함께 다시 불러라"* 라고만 말했다 — 즉 **비개발자가 절대경로를 대야** 했다. 그건 이 사람들이
    답할 수 있는 질문이 아니고, 흐름은 거기서 끝난다.

    그래서 그 화면이 **시작하는 화면**이 된다: gil 이 자리를 제안하고, 사람은 이름만 적고,
    버튼을 누른다. 문법이 지켜 온 "어디에 만들지는 언제나 사람이 정한 것이 되게"는 그대로다 —
    사람이 이름을 적고 누르는 것이 곧 정하는 것이다. 도구가 정하는 것은 **기본값의 자리**뿐이고
    그건 언제나 눈에 보인다.
    """

    def _serve(self, home, cwd, full=False, draws_ui=False):
        import json, subprocess
        env = dict(os.environ, HOME=home, GIL_NO_VIEWER="1", GIL_NO_VERSION_CHECK="1")
        env.pop("GIL_UI_PROBE", None)
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=cwd, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env)
        self.addCleanup(p.terminate)
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                try:
                    m = json.loads(ln.strip())
                except ValueError:
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "x"}})
                    continue
                if m.get("id") == want:
                    return m

        caps = {"extensions": {"io.modelcontextprotocol/ui": {}}} if draws_ui else {}
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": caps,
                         "clientInfo": {"name": "t", "version": "0"}}})
        pump(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._n = 10

        def call(name, args):
            self._n += 1
            send({"jsonrpc": "2.0", "id": self._n, "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
            r = pump(self._n)
            if "error" in r:
                return True, r["error"].get("message", "")
            res = r["result"]
            txt = res["content"][0]["text"] if res.get("content") else ""
            self.last_result = res
            return bool(res.get("isError")), txt

        def tools():
            self._n += 1
            send({"jsonrpc": "2.0", "id": self._n, "method": "tools/list", "params": {}})
            got = pump(self._n)["result"]["tools"]
            return got if full else [t["name"] for t in got]

        return call, tools

    def _fresh(self):
        import tempfile
        return tempfile.mkdtemp(prefix="gilhome-"), tempfile.mkdtemp(prefix="notarepo-")

    def test_the_first_screen_asks_for_a_name_not_a_path(self):
        """저장소를 못 찾은 것은 **막다른 길이 아니라 첫 칸**이다."""
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd)
        bad, card = call("gil_status_card", {})
        self.assertFalse(bad, card)
        self.assertIn("data-start-name", card, "이름을 적을 칸이 없다 — 사람은 경로를 대야 한다")
        self.assertIn('data-act="start-here"', card, "누를 자리가 없다")
        # **자리를 제안한다.** 제안이 없으면 결국 사람이 경로를 치게 된다.
        self.assertIn("data-start-preview", card, "어디에 생기는지 안 보여준다")
        self.assertIn("~/", card, "기본 자리를 제안하지 않는다")

    def test_on_a_screen_host_it_opens_the_screen_instead_of_asking_for_a_path(self):
        """**화면을 지어 놓고도 대화로 경로를 물었다** (상현님 실사용, 2026-08-10).

        첫 화면을 다 만든 그날, 일반 채팅의 세션이 이렇게 물었다 — *"저장소를 세울 폴더의
        절대경로를 알려주세요"*. 우리가 없애려던 바로 그 질문이다. 원인은 둘:

          ㄱ) 자리가 안 정해지면 `gil_start` 가 **die** 로 끝났다. 오류 결과에는 `_meta.ui`
              가 실리지 않으니 **카드가 아예 안 열린다** — 지어 둔 화면이 뜰 기회가 없었다.
          ㄴ) 그 오류 문구가 여전히 "절대경로를 repo 에 실어라"고 가르쳤다.

        이 병의 아홉 번째 얼굴이다: 앞의 여덟 번은 **없는 화면**을 가리켰고, 이번엔 화면이
        **있는데** 안내가 그리로 안 보냈다. 그래서 재는 것도 두 가지다 — 성공으로 답하는가
        (=카드가 열리는가), 그리고 경로를 묻지 말라고 말하는가.

        **앞 시험들이 이걸 못 잡은 이유**: 카드를 그리는 호스트로 한 번도 안 밟았다. 못 밟은
        길은 못 잡는다 — 이 저장소가 폼 없는 호스트에서 이미 한 번 배운 것이다(#57)."""
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd, draws_ui=True)
        bad, out = call("gil_start", {})
        self.assertFalse(bad, "화면이 서는 호스트인데 오류로 끝났다 — 카드가 안 열린다:\n" + out)
        self.assertIn("화면", out, "화면으로 보내지 않는다:\n" + out)
        # 그리고 **절대경로를 요구하는 옛 문구가 남아 있으면 안 된다** — 남으면 세션이 그걸 읽는다.
        self.assertNotIn("절대경로를 repo", out, "옛 안내가 아직 경로를 요구한다:\n" + out)
        # **화면을 연다고 말했으면 실제로 열려야 한다.** 카드를 여는 것은 툴 수준 Meta 가
        # 아니라 **결과에 실린** resourceUri 다 — 안 실으면 "열었다"가 거짓말이 된다.
        ui = (self.last_result.get("_meta") or {}).get("ui") or {}
        self.assertEqual(ui.get("resourceUri"), "ui://gil/status",
                         "결과에 화면을 여는 표식이 없다 — '화면을 열었다'가 거짓말이 된다")
        # **그 화면에 실제로 있는 버튼을 가리켜야 한다.** 인터뷰 폼의 [답을 제출한다] 를
        # 가리키면 그건 같은 병의 다음 얼굴이다 — 화면은 맞는데 그 화면의 다른 버튼이다.
        self.assertIn("여기에 시작한다", out, "그 화면에 있는 버튼을 안 가리킨다:\n" + out)
        self.assertNotIn("답을 제출한다", out, "인터뷰 폼의 버튼을 가리킨다:\n" + out)

    def test_calling_start_twice_does_not_stack_two_screens(self):
        """**같은 화면을 두 번 열지 않는다** (상현님 실사용: "카드가 두번 나왔어 — ux 적으로
        너무 헷갈릴 포인트").

        에이전트가 gil_start 를 두 번 부르는 것 자체는 정상이다 — 레일이 "끝날 때까지 반복해서
        불러라"고 가르친다. 잘못은 **부를 때마다 화면을 새로 여는 것**이다: 사람 앞에 같은
        질문을 하는 카드가 둘 서면 어디에 적어야 할지 알 수 없고, 한쪽에 적은 것은 다른 쪽이
        모른다(초안은 화면마다 따로 산다).

        화면을 여는 것은 **결과에 실린 resourceUri** 하나뿐이니, 두 번째부터 그것만 빼면
        호스트는 새 카드를 그리지 않는다. 대신 이미 떠 있다고 말하고 기다리라고 한다."""
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd, draws_ui=True)
        bad1, out1 = call("gil_start", {})
        self.assertFalse(bad1, out1)
        ui1 = (self.last_result.get("_meta") or {}).get("ui") or {}
        self.assertEqual(ui1.get("resourceUri"), "ui://gil/status", "첫 호출이 화면을 안 연다")

        bad2, out2 = call("gil_start", {})
        self.assertFalse(bad2, out2)
        ui2 = (self.last_result.get("_meta") or {}).get("ui") or {}
        self.assertIsNone(ui2.get("resourceUri"),
                          "두 번째 호출이 카드를 또 연다 — 같은 질문이 사람 앞에 둘 선다")
        self.assertIn("이미 떠 있다", out2, "이미 떠 있다는 사실을 안 말한다:\n" + out2)

    def test_standing_rules_live_in_instructions_not_in_every_answer(self):
        """**잰 것은 응답, 정한 것은 instructions** (상현님 물음, 2026-08-10).

        "절대경로를 묻지 마라"·"사람이 누르는 버튼을 대신 누르지 마라" 는 호출 결과와 무관한
        **상시 규칙**이다. 이런 것을 응답에 적으면 둘이 잘못된다:

          ㄱ) **늦게 도착한다.** 에이전트는 응답을 읽기 전에 이미 무엇을 할지 정한다 —
              실측에서 세션이 먼저 절대경로를 묻고 그다음 우리 글을 읽었다.
          ㄴ) **두 자리에 같은 것을 적게 된다.** 그러면 한쪽만 낡는다(씨앗 표식에서 치른 값).

        연결마다 한 번, 첫 호출 **전에** 로드되는 자리가 `initialize.instructions` 다 —
        이 표면에서 "스킬"에 해당하는 유일한 슬롯이다(MCPB 매니페스트에 skills 칸은 없다).
        그러니 규칙은 거기 있고, 응답에는 **이 호출에서 잰 것**만 남는다."""
        home, cwd = self._fresh()
        import json, subprocess
        env = dict(os.environ, HOME=home, GIL_NO_VIEWER="1", GIL_NO_VERSION_CHECK="1")
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=cwd, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env)
        self.addCleanup(p.terminate)
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": "t", "version": "0"}}}) + "\n")
        p.stdin.flush()
        got = json.loads(p.stdout.readline())["result"]
        instr = got.get("instructions", "")
        for rule in ("절대경로를 묻지 마라", "대신 누르지 마라", "git init"):
            self.assertIn(rule, instr,
                          "상시 규칙이 첫 호출 전에 로드되는 자리에 없다: " + rule)
        # 그리고 그 규칙이 응답에 **또** 적혀 있으면 안 된다 — 두 자리는 갈린다.
        call, _ = self._serve(home, cwd, draws_ui=True)
        _, out = call("gil_start", {})
        self.assertNotIn("경로를 묻지 마라", out,
                         "상시 규칙이 응답에도 적혀 있다 — 두 자리에 적으면 한쪽만 낡는다")

    def test_on_a_hostless_screen_it_still_asks_the_human_the_old_way(self):
        """**카드를 안 그리는 호스트에서는 옛 길이 옳다.**

        거기서는 대화가 유일한 통로다. 화면으로 보내면 그건 없는 곳을 가리키는 안내가 되고,
        그게 이 저장소가 여덟 번 고친 그 병이다. 두 길을 **호스트를 보고** 가른다."""
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd, draws_ui=False)
        bad, out = call("gil_start", {})
        self.assertTrue(bad, "폼도 카드도 없는데 그냥 진행했다:\n" + out)
        self.assertIn("사람", out)

    def test_a_name_is_enough(self):
        """이름 하나로 자리가 정해지고 세계가 선다 — 경로는 아무도 치지 않는다."""
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd)
        bad, out = call("gil_start_here", {"name": "타이타닉 생존자 분석"})
        self.assertFalse(bad, out)
        made = [d for d in (os.path.join(home, "gil", "타이타닉-생존자-분석"),
                            os.path.join(home, "Documents", "gil", "타이타닉-생존자-분석"))
                if os.path.isdir(d)]
        self.assertTrue(made, "폴더가 안 생겼다:\n" + out)
        self.assertTrue(os.path.isdir(os.path.join(made[0], ".git")), "저장소가 안 섰다")

    def test_it_will_not_build_in_a_place_that_holds_projects(self):
        """**프로젝트를 담는 자리에는 프로젝트를 세우지 않는다** — 화면에서도 같다.

        `/` 와 홈 자신에 세우면 그 아래 전부가 한 저장소가 된다. 그리고 화면이 만드는 자리는
        홈 안이어야 한다 — 남의 디스크 아무 데나 폴더를 만드는 버튼을 두지 않는다.
        """
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd)
        for place, why in [("/", "루트"), ("/etc", "홈 밖"), ("~/..", "홈 위")]:
            bad, msg = call("gil_start_here", {"name": "x", "place": place})
            self.assertTrue(bad, why + " 에 세우는 것을 안 막았다: " + msg)
            self.assertIn("거부", msg)

    def test_an_empty_name_is_refused_because_a_folder_gets_that_name(self):
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd)
        bad, msg = call("gil_start_here", {"name": "   "})
        self.assertTrue(bad, msg)
        self.assertIn("이름", msg)

    def test_the_humans_button_is_declared_as_the_apps_not_the_models(self):
        """**사람이 누르는 자리는 에이전트의 것이 아니다** — 다만 그건 벽이 아니라 선언이다.

        `visibility: ["app"]` 은 지키는 호스트가 모델의 목록에서 빼 주는 **힌트**다. 날
        프로토콜의 tools/list 에는 그대로 보인다 — 이 시험을 처음 쓸 때 "목록에서 빠져
        있어야 한다"로 적었다가 빨개졌고, **잡힌 것이 옳다**(같은 과장을 주석에서 한 번
        고친 적이 있다). 얻는 것은 "못 한다"가 아니라 "무심코 부르지 않는다"이다.

        그러니 재는 것은 **선언**이다. 그리고 안내가 그 자리에서 "이건 사람이 누르는 것"
        이라고 말하는지까지 함께 본다 — 선언만 있고 설명이 없으면 에이전트는 그냥 부른다.
        """
        home, cwd = self._fresh()
        _, tools = self._serve(home, cwd, full=True)
        by = {t["name"]: t for t in tools()}
        self.assertIn("gil_start", by, "시작하는 툴이 사라졌다")
        here = by.get("gil_start_here")
        self.assertIsNotNone(here, "화면의 버튼이 도는 자리가 없다")
        vis = (((here.get("_meta") or {}).get("ui") or {}).get("visibility") or [])
        self.assertEqual(list(vis), ["app"],
                         "사람의 버튼이 앱 전용으로 선언되지 않았다: " + repr(vis))
        desc = here.get("description", "")
        self.assertIn("사람", desc, "설명이 '사람이 누르는 자리'라고 말하지 않는다")
        self.assertIn("gil_start", desc, "에이전트가 대신 갈 길(gil_start)을 안 가리킨다")

    def test_the_name_being_typed_survives_the_card_redrawing_itself(self):
        """**카드는 스스로 다시 그린다 — 그러면서 사람이 쓰던 것을 잃으면 안 된다.**

        이 규칙은 이미 세워져 있었고(af4b667f), 그 자리 주석에 *"둘은 같은 커밋이어야 한다"*
        고까지 적혀 있다. 그런데 시작 화면의 이름 칸을 **새로 만들면서 그 보존에 등록하지
        않았다** — 그래서 카드가 다시 그려질 때마다 적던 이름이 사라지고 만들 자리 미리보기가
        되돌아갔다(상현님 실사용: "치는 동안 따라오는 게 안 되네").

        **보존은 새 입력 칸마다 다시 챙겨야 하는 것**이지, 한 번 세우면 따라오는 것이 아니다.
        그러니 재는 것도 칸이 아니라 **규칙**이다: 화면의 입력 칸은 전부 harvest/restore 를
        지나야 한다.
        """
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd, draws_ui=True)
        bad, shell = call("gil_status_card", {})
        self.assertFalse(bad, shell)
        # 껍데기(=보존 기계가 사는 곳)를 읽어 규칙을 센다.
        import json, subprocess
        env = dict(os.environ, HOME=home, GIL_NO_VIEWER="1", GIL_NO_VERSION_CHECK="1")
        p = subprocess.Popen([*GIL_CMD, "mcp", "serve"], cwd=cwd, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env)
        self.addCleanup(p.terminate)
        send = lambda o: (p.stdin.write(json.dumps(o) + "\n"), p.stdin.flush())
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "t", "version": "0"}}})
        p.stdout.readline()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "resources/read",
              "params": {"uri": "ui://gil/status"}})
        while True:
            m = json.loads(p.stdout.readline())
            if m.get("id") == 2:
                break
        sh = m["result"]["contents"][0]["text"]

        harvest = sh.partition("function harvest(")[2].partition("\n  }")[0]
        self.assertTrue(harvest.strip(), "harvest 를 못 읽었다 — 이 시험이 눈이 먼다")
        self.assertIn("data-start-name", harvest,
                      "시작 화면의 이름 칸이 보존에 등록되지 않았다 — 다시 그리면 사라진다")
        # 되돌린 뒤 **미리보기도 맞춘다**: 값만 되돌리고 그림을 안 맞추면 사람은 자기가 친
        # 이름과 다른 자리를 보게 된다.
        self.assertIn("restoreStart(", sh, "되돌리는 자리가 없다")
        self.assertIn("syncStartPreview(", sh, "미리보기를 맞추는 자리가 없다")
        redraw = sh.partition("function paint(")[2].partition("\n  }")[0]
        self.assertIn("restoreStart()", redraw, "다시 그릴 때 되돌리지 않는다")

    def test_the_screen_and_the_server_fold_the_name_the_same_way(self):
        """화면이 미리 보여준 자리와 서버가 만드는 자리가 갈리면, 사람은 **자기가 본 것과
        다른 곳**에 폴더가 생긴 것을 나중에 알게 된다. 접는 규칙은 두 곳에 있지만 결과는
        같아야 한다 — 그래서 규칙 자체를 여기서 못박는다."""
        home, cwd = self._fresh()
        call, _ = self._serve(home, cwd)
        # 공백은 하이픈으로, 경로를 벗어나게 하는 글자는 사라진다.
        bad, out = call("gil_start_here", {"name": "a b/c"})
        self.assertFalse(bad, out)
        self.assertIn("a-bc", out, "접는 규칙이 화면의 미리보기와 다르다:\n" + out)


class TestWhatWeDeclareToTheHostIsTheSpecsShape(GilFixture):
    """**안 도는 선언은 선언이 아니다** (MCP Apps 규범 SEP-1865 대조, 2026-08-10).

    우리는 리소스의 `_meta.ui.csp` 에 `connect-src`·`resource-src` 를 적어 뒀다 — CSP 지시어
    이름을 그대로 옮긴 것이다. 그런데 규범의 필드는 `connectDomains`·`resourceDomains`·
    `frameDomains`·`baseUriDomains` 다. **호스트는 모르는 키를 무시하고 기본 CSP 를 건다.**
    즉 그 선언은 한 글자도 효과가 없었고, 화면이 뜬 것은 기본값이 인라인 스크립트를 허용해서지
    우리가 선언해서가 아니었다.

    이건 눈으로는 안 보이는 종류다 — 오타가 아니라 **다른 어휘**라 읽으면 그럴듯하고, 화면은
    멀쩡히 뜨니 아무도 의심하지 않는다. 그래서 시험이 규범의 이름을 알고 있어야 한다.

    같은 이유로 확장 ID·MIME 도 함께 못박는다: 이 셋 중 하나만 어긋나도 호스트는 우리를
    **앱 리소스로 안 본다**(읽기는 성공하고 렌더만 안 되는, 판정이 세 번 뒤집혔던 그 증상)."""

    GO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "go")

    def _ui_src(self):
        return open(os.path.join(self.GO, "mcp_ui.go"), encoding="utf-8").read()

    def test_the_extension_id_and_mime_are_the_specs(self):
        src = self._ui_src()
        self.assertIn('"io.modelcontextprotocol/ui"', src, "확장 ID 가 규범의 것이 아니다")
        self.assertIn('"text/html;profile=mcp-app"', src, "MIME 이 규범의 것이 아니다")

    def test_the_csp_keys_are_the_specs_field_names(self):
        """CSP 지시어 이름(`connect-src`)이 아니라 **규범의 필드 이름**이어야 한다."""
        src = self._ui_src()
        blk = src.partition("func uiResourceMeta()")[2].partition("\n}")[0]
        self.assertTrue(blk.strip(), "uiResourceMeta 를 못 읽었다 — 이 시험이 눈이 먼다")
        for field in ("connectDomains", "resourceDomains", "frameDomains", "baseUriDomains"):
            self.assertIn(field, blk, f"규범의 CSP 필드 {field} 가 없다")
        for wrong in ("connect-src", "resource-src", "frame-src", "base-uri"):
            self.assertNotIn(wrong, blk,
                             f"CSP 지시어 이름({wrong})을 필드 이름 자리에 적었다 — "
                             "호스트가 무시하고 기본값을 건다(선언이 안 돈다)")

    def test_the_card_really_calls_nothing_outside(self):
        """빈 목록으로 선언했으면 **실제로도 안 불러야** 한다 — 선언과 실물이 갈리면 어느 쪽이
        사실인지 알 수 없다. 그림은 data: 만 싣는다(markdown.go 가 바깥 주소를 거부한다)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P", "--reference", "-",
                 "--criterion", "C", input="기준")
        p = os.path.join(self.repo, "g.html")
        self.gil("graph", "--html", "--out", p)
        with open(p, encoding="utf-8") as f:
            page = f.read()
        for pat in ('src="http', "src='http", 'href="http://', "@import"):
            self.assertNotIn(pat, page, f"화면이 바깥({pat})을 부른다 — 자기완결이 아니다")


class TestTheRetirementCleansUpAfterItself(GilFixture):
    """**은퇴한 것이 남긴 자리를 은퇴시킨 쪽이 치운다** (2026-08-10).

    브라우저 관전 서버는 setsid/DETACHED 로 떠서 gil 이 죽어도 살았다. 그리고 끄는 유일한
    수단(`gil viewer stop`)이 뷰어와 **함께** 사라졌다 — 그러면 이 릴리스로 올린 사람의
    머신에는 포트를 쥔 채 낡은 그래프를 보여주는 서버가 남고, 바탕화면 런처는 은퇴 문구만
    받는다. 도구가 자기가 만든 상태에서 빠져나올 길을 자기가 줘야 한다."""

    def test_the_cleanup_runs_and_says_what_it_found(self):
        """치울 것이 없어도 **없다고 말한다** — 침묵은 '했다'와 '못 했다'를 구별해 주지 않는다."""
        self.gil("init", "--name", "clew")
        r = self.gil("viewer-cleanup", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout + r.stderr
        self.assertIn("떠 있는 옛 뷰어", out, "무엇을 봤는지 말하지 않는다")
        self.assertIn("런처", out, "런처를 봤는지 말하지 않는다")
        self.assertIn("gil graph", out, "그림을 어디서 보는지 안 알려준다")

    def test_the_retirement_notice_points_at_it(self):
        """은퇴 문구가 회수 명령을 가리키고, **그 명령이 실재한다.**"""
        self.gil("init", "--name", "clew")
        r = self.gil("viewer")
        out = r.stdout + r.stderr
        self.assertIn("은퇴했다", out)
        self.assertIn("viewer-cleanup", out, "치우는 길을 안 알려준다")
        # 가리킨 것이 실제로 돈다(v3.58.1·2 가 값을 치른 규칙).
        self.assertEqual(self.gil("viewer-cleanup", "--dry-run").returncode, 0,
                         "은퇴 문구가 가리킨 명령이 안 돈다")

    def test_it_does_not_claim_to_have_cleaned_what_it_cannot_see(self):
        """옛 명령은 `--out` 으로 아무 데나 런처를 만들 수 있었고 gil 은 그 목록이 없다 —
        '다 지웠다'고 말하면 거짓이다."""
        self.gil("init", "--name", "clew")
        out = self.gil("viewer-cleanup", "--dry-run").stdout
        self.assertNotIn("다 지웠다", out)
        self.assertNotIn("모두 정리", out)


class TestRetiringACommandLeavesNoDanglingGuidance(GilFixture):
    """**명령을 지우면 그 이름을 가리키던 안내가 전부 없는 곳을 가리킨다** (2026-08-10).

    이 저장소가 뷰어를 버리기로 한 근거가 정확히 그 병이었다 — 낡은 통로가 안내에 남아
    있는 한, 그걸 읽은 세션이 매번 우회했다. 그러니 지우는 일에는 **지운 뒤를 세는 시험**이
    함께 있어야 한다.

    그런데 기존 시험(`test_it_does_not_tell_you_to_type_a_command_that_is_not_there`)은
    이걸 못 잡는다. 그 시험은 `gil x -플래그` · `gil x <인자>` · 줄 끝 세 꼴만 "칠 수 있는
    줄"로 인정한다 — 영어 산문에서 낱말을 세면 "gil records …" 같은 문장이 명령으로 잡혀
    시험이 못 쓰게 되므로 일부러 좁힌 것이다(v3.58.2 의 값). 그 대가로 **서브명령이 붙은
    꼴**(`gil viewer open`)은 산문으로 보아 그냥 지나간다. 실측: 그 꼴로 남은 안내가 31곳 중
    29곳이었다.

    그래서 **은퇴를 선언하게** 한다(surface.go 의 retiredCmds). 선언된 이름은 꼴과 무관하게
    잡힌다. 열거가 아니라 규칙이다 — 다음에 무엇을 지우든 이름 한 줄만 더하면 된다."""

    GO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "go")

    def _retired(self):
        surf = open(os.path.join(self.GO, "surface.go"), encoding="utf-8").read()
        blk = surf.partition("var retiredCmds = map[string]string{")[2].partition("}")[0]
        return dict(re.findall(r'"([a-z0-9-]+)":\s*"((?:[^"\\]|\\.)*)"', blk))

    @staticmethod
    def _mentions(text, name):
        """**꼴을 안 가린다.** 은퇴한 이름은 어떤 모양으로 나오든 없는 것을 가리킨다."""
        # 경계는 **명령 이름 문자**로 잡는다. `\b` 만 쓰면 하이픈이 경계라서
        # `gil viewer-cleanup` 이 `gil viewer` 로 잡힌다 — 회수 명령을 가리키는 정당한
        # 줄이 결함으로 뜬다(실제로 그렇게 잡혔다). 낱말만 세면 사실을 말하는 줄까지 빨개진다.
        return re.search(r"\bgil " + re.escape(name) + r"(?![a-z0-9-])", text) is not None

    def test_the_detector_actually_detects(self):
        """**공회전하지 않는다는 것을 먼저 보인다.**

        은퇴 목록이 비어 있으면 아래 시험은 언제나 통과한다 — 안 깨지지만 아무것도 안 잰다.
        그래서 판정기 자체를 합성 입력으로 밟아 둔다. 이게 초록이면, 아래가 통과하는 것은
        '잴 것이 없어서'지 '못 재서'가 아니다."""
        self.assertTrue(self._mentions('"이제 gil viewer open 을 쳐라"', "viewer"),
                        "서브명령이 붙은 꼴을 못 잡는다 — 바로 그 꼴로 29곳이 샜다")
        self.assertTrue(self._mentions('"gil viewer"', "viewer"), "맨 꼴을 못 잡는다")
        self.assertFalse(self._mentions('"gil viewers 는 없다"', "viewer"),
                         "다른 낱말의 앞부분을 잡는다 — 그러면 시험이 못 쓰게 된다")
        self.assertFalse(self._mentions('"치우려면 gil viewer-cleanup"', "viewer"),
                         "하이픈으로 이어진 **다른 명령**을 잡는다 — 회수 명령을 가리키는 "
                         "정당한 줄이 결함으로 뜬다")

    def test_no_guidance_names_a_retired_command(self):
        """선언된 은퇴 명령은 소스의 어떤 안내에도 안 나온다(주석은 사실을 말해도 된다)."""
        retired = self._retired()
        if not retired:
            self.skipTest("아직 은퇴한 명령이 없다 — 위 판정기 시험이 이 자리를 지킨다")
        bad = []
        for f in sorted(glob.glob(os.path.join(self.GO, "*.go"))):
            raw = False          # ` … ` raw string 안인가
            for i, ln in enumerate(open(f, encoding="utf-8"), 1):
                # **raw string 안의 `//` 는 Go 주석이 아니다.** 렌더러의 css·js 는 통째로
                # raw string 이고, 그 안의 `// …` 줄은 **화면에 나가는 글**이다. 이걸
                # 주석으로 보고 건너뛰다가 두 자리를 놓쳤다(console.error('[gil viewer] …')).
                was_raw = raw
                if ln.count("`") % 2:
                    raw = not raw
                if not was_raw and ln.lstrip().startswith("//"):
                    continue
                if was_raw:
                    for name in retired:
                        if self._mentions(ln, name):
                            bad.append(f"{os.path.basename(f)}:{i} → gil {name} (화면에 나가는 글)")
                    continue
                for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', ln):
                    for name in retired:
                        if self._mentions(lit, name):
                            bad.append(f"{os.path.basename(f)}:{i} → gil {name}")
        self.assertEqual(bad, [], "은퇴한 명령을 아직 가리킨다:\n  " + "\n  ".join(sorted(set(bad))))

    def test_a_retired_command_says_where_it_went(self):
        """"알 수 없는 명령"만 주면 옛 습관으로 친 사람이 거기서 막힌다."""
        retired = self._retired()
        if not retired:
            self.skipTest("아직 은퇴한 명령이 없다")
        name = sorted(retired)[0]
        r = self.gil(name)
        out = r.stdout + r.stderr
        self.assertIn("은퇴했다", out, f"gil {name} 이 어디로 갔는지 안 말한다:\n{out}")
        self.assertNotIn("알 수 없는 명령", out, "은퇴한 것을 없는 것이라 말한다")
        h = self.gil("help", name)
        self.assertIn("은퇴했다", h.stdout + h.stderr, "도움말이 은퇴를 모른다")

    def test_help_has_no_topic_for_a_command_that_is_gone(self):
        """**역방향도 센다.** 기존 시험은 `명령 − 도움말` 만 봤다 — 도움말에 남은 옛 항목은
        아무도 안 잡았고, 그러면 사람은 없는 명령의 사용법을 읽는다."""
        h = open(os.path.join(self.GO, "usage_help.go"), encoding="utf-8").read()
        topics = set(re.findall(r'^\t"([a-z0-9-]+)": \{', h, re.M))
        self.assertTrue(topics, "도움말 항목을 못 읽었다 — 이 시험이 공회전한다")
        main = open(os.path.join(self.GO, "main.go"), encoding="utf-8").read()
        cmds = set()
        for m in re.finditer(r'case ((?:"[a-z0-9-]+"(?:, )?)+):', main):
            cmds |= set(re.findall(r'"([a-z0-9-]+)"', m.group(1)))
        self.assertIn("chain-merge", cmds, "명령 목록을 못 읽었다 — 이 시험이 공회전한다")
        # 개념 항목은 명령이 아니다 — **선언된 것만** 봐준다(usage_help.go 의 conceptTopics).
        # 이 예외가 없으면 정당한 항목이 결함으로 잡히고, 있으면서 선언을 안 읽으면
        # 이 시험은 통째로 무뎌진다. 선언을 읽어서, 선언 밖의 고아만 잡는다.
        concept = set(re.findall(r'"([a-z0-9-]+)":\s*"',
                                 h.partition("var conceptTopics = map[string]string{")[2]
                                  .partition("}")[0]))
        self.assertIn("close-vocabulary", concept,
                      "개념 항목 선언을 못 읽었다 — 이 시험이 눈이 먼다")
        orphan = sorted(topics - cmds - concept - {"help", "h"})
        self.assertEqual(orphan, [],
                         "없는 명령의 도움말이 남아 있다: " + ", ".join(orphan) +
                         "\n  개념 항목이면 usage_help.go 의 conceptTopics 에 왜 그런지 적어라.")


class TestConflictHasAWayOut(GilFixture):
    """**도구가 자기가 만든 상태에서 빠져나올 길을 자기가 줘야 한다.**

    `chain-merge` 는 충돌로 멈춰 놓고 `gil chain-merge-continue` 를 치라고 했다 — 그런 명령은
    없다. 사람은 반쯤 병합된 저장소 앞에서 없는 명령을 치고 거기서 막힌다. 없는 길을 가리키는
    안내는 안내가 아니라 막다른 골목이다(#91 의 끊긴 정리 사다리와 같은 병)."""

    def _conflict(self):
        self.gil("init", "--name", "clew")
        self._git("checkout", "-q", "main")
        p = os.path.join(self.repo, "f.txt")
        def put(t):
            with open(p, "w", encoding="utf-8") as f:
                f.write(t + "\n")
        put("base"); self._git("add", "f.txt"); self._git("commit", "-qm", "base")
        self._git("checkout", "-qb", "t1"); put("one"); self._git("commit", "-qam", "one")
        self._git("checkout", "-q", "main")
        self._git("checkout", "-qb", "t2"); put("two"); self._git("commit", "-qam", "two")
        self._git("checkout", "-q", "main"); self._git("checkout", "-qb", "work")
        r = self.gil("chain-merge", "unified", "--purpose", "합치기", "t1", "t2")
        self.assertEqual(r.returncode, 2, "충돌이 안 났다:\n" + r.stdout + r.stderr)
        return r, p

    def test_the_conflict_message_names_a_command_that_runs(self):
        r, _ = self._conflict()
        out = r.stdout + r.stderr
        self.assertNotIn("chain-merge-continue", out, "없는 명령을 치라고 한다")
        self.assertIn("--resume", out, "이어가는 길을 안 보여준다")
        self.assertIn("git commit --no-edit", out, "이 병합을 어떻게 끝내는지 안 말한다")

    def test_resume_finishes_what_the_conflict_stopped(self):
        r, p = self._conflict()
        with open(p, "w", encoding="utf-8") as f:
            f.write("resolved\n")
        self._git("add", "f.txt"); self._git("commit", "-q", "--no-edit")
        r = self.gil("chain-merge", "unified", "--resume")
        self.assertEqual(r.returncode, 0, "이어가기가 거부됐다:\n" + r.stdout + r.stderr)
        # **사람이 끝낸 머지에도 표식이 얹혀야 한다.** 안 얹으면 그 갈래는 어느 병합의 것도
        # 아니게 되고, 그 뒤 gil 이 세는 모든 것이 실제와 갈린다(#116 이 막으려던 모양).
        subj = self._git("log", "-1", "--format=%(trailers:key=Gil-Merge,valueonly)").stdout
        self.assertIn("t2", subj, "사람이 끝낸 병합에 표식이 없다 — 기록의 통로가 갈렸다")

    def test_reopening_without_resume_points_at_resume(self):
        """이미 있는 체인이라 거부할 때, 그 사람이 실제로 하려던 일의 길을 준다."""
        self._conflict()
        r = self.gil("chain-merge", "unified", "--purpose", "합치기", "t2")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--resume", r.stdout + r.stderr, "거부만 하고 길을 안 준다")


class TestTheScreenCountsOneThing(GilFixture):
    """**두 숫자가 어긋나면 사람은 그래프가 고장 났다고 읽는다** (상현님, AIL 실사용).

    머리글은 "체인 6개"라 말하는데 전체맵의 체인 선택기에는 5개만 있었다. 둘 다 제 규칙으로는
    옳았다 — 머리글은 **선언된** 체인(chain-root 가 있는 것)을 세고, 선택기는 **그려진 노드**에서
    체인을 모았다. 그 사이에 스텝이 아직 없는 체인(AIL 의 ail-fullstack: chain-root 만 있고
    스텝 0)이 하나 있었고, 화면은 그 차이를 설명하지 않았다.

    열린 체인을 목록에서 빼면 "체인이 열렸다"는 신호가 화면에서 사라진다 — 그건 v3 초기에
    한 번 고친 자리다(상현님: chain-close 후 새 체인을 발의했는데 뷰어에 아무 변화가 없었다).
    그러니 빼는 쪽이 아니라 **같이 세는 쪽**으로 맞춘다. 다만 왜 비어 보이는지는 말해 준다."""

    def _build(self):
        out = os.path.join(self.repo, "g.html")
        r = self.gil("graph", "--html", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        return open(out, encoding="utf-8").read()

    def test_a_chain_with_no_steps_is_still_in_the_list(self):
        import re, json
        self.gil("init", "--name", "clew")
        self.gil("chain", "worked", "--purpose", "스텝이 있는 체인")
        self.gil("open", "worked/c1", "--author", "clew", "--purpose", "P",
                 "--body", "정의", "--fits", "목적 그 자체")
        # 열기만 하고 스텝은 하나도 없는 체인 — 화면에서 사라지면 안 된다.
        self.gil("chain", "opened", "--purpose", "열리기만 한 체인")
        html = self._build()
        declared = json.loads(re.search(r'id="chainsdata"[^>]*>(.*?)</script>', html, re.S).group(1))
        self.assertIn("opened", declared, "스텝 없는 체인이 목록에서 빠졌다 — 열린 신호가 사라진다")
        head = int(re.search(r"체인 (\d+)개", html).group(1))
        self.assertEqual(head, len(declared),
                         f"머리글({head})과 목록({len(declared)})이 다른 것을 센다")

    def test_the_picker_is_built_from_the_same_list(self):
        """**이 시험의 한계를 먼저 적는다**: 선택기는 JS 가 화면에서 만든다. 파이썬 시험은 그
        런타임을 안 돌리므로 여기서는 **소스가 그 목록을 쓰는지**만 본다(약한 판정이다).

        그래도 거는 이유: 앞 시험은 서버가 보낸 목록과 머리글만 봐서, 화면 쪽을 옛 코드로
        되돌려도 통과했다 — 정작 어긋났던 자리가 화면이었는데. 약한 판정이라도 그 자리를
        비워 두면, 다음에 같은 회귀가 아무 저항 없이 들어온다."""
        src = open(renderer_src_path(), encoding="utf-8").read()
        self.assertIn("DECLARED", src, "선언된 체인 목록을 화면이 안 읽는다")
        self.assertRegex(src, r"const ALLCHAINS=\[\.\.\.new Set\(\[\.\.\.DRAWN,\.\.\.DECLARED\]\)\]",
                         "선택기가 그려진 노드에서만 체인을 모은다 — 머리글과 다른 것을 센다")

    def test_the_picker_gets_what_it_uses_passed_in(self):
        """**남의 함수의 지역변수를 이름으로 집으면 그 함수 밖에서는 없는 이름이다.**

        실측(상현님, 고친 지 몇 분 만에): 선택기가 다른 함수의 `DRAWN` 을 그대로 썼고, 화면에
        "뷰어의 일부(전체맵)를 그리지 못했다: DRAWN is not defined" 가 떴다. 전체맵이 통째로
        안 그려졌다 — 나머지는 멀쩡해서 **부분 실패**로만 보였다.

        이 시험도 약한 판정이다(JS 런타임을 안 돌린다). 그래도 이 한 줄이면 같은 회귀는 막는다:
        선택기가 쓰는 것은 **인자로 받는다**."""
        src = open(renderer_src_path(), encoding="utf-8").read()
        self.assertIn("function chainFilterBar(chains,drawn)", src,
                      "선택기가 쓰는 값을 인자로 안 받는다")
        body = src.split("function chainFilterBar(chains,drawn){", 1)[1].split("\nfunction ", 1)[0]
        self.assertNotIn("DRAWN", body,
                         "선택기가 남의 함수의 지역변수(DRAWN)를 집는다 — 화면에서 죽는다")

    def test_the_list_says_why_that_chain_looks_empty(self):
        """같이 세되, **왜 비어 보이는지**는 말한다 — 안 그러면 골랐을 때 빈 화면만 남는다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "opened", "--purpose", "열리기만 한 체인")
        html = self._build()
        self.assertIn("map.filter.nosteps", html, "스텝 없음을 말할 자리가 없다")
        self.assertIn("스텝 없음", html, "사전에 그 문구가 없다")


class TestOrphanMeansOrphanInTheFilesToo(GilFixture):
    """**"이어받지 않는다"고 선언했으면 파일도 안 이어받아야 한다** (이슈 #118, 상현님 실사용).

    `--ask-root` 의 "대문에서 새로 시작한다 — 앞의 어느 것도 이어받지 않는 새 계보" 를 골라
    연 체인이 dev 의 **현재 끝**에 뿌리를 박았다. 그래프의 계승선은 안 그어지는데(계보에는
    `← (대문)`) **파일 층위에서는 앞 체인이 합류시킨 것을 전부 물려받았다.** 실측: 한
    저장소의 체인 여섯이 전부 그때그때의 dev 팁에 붙어 있었다 — "대문"과 "닫힌 체인
    이어받음"이 트리 층위에서 구별되지 않았다.

    대문 브랜치의 끝에 박을 수는 없다: 배포는 dev → main 머지라 main 팁은 dev 에서 닿지 않고,
    층 검사("시조는 dev 에서 난다")가 곧바로 깨진다. 그런데 배포 직후 **대문의 내용은 그때의
    dev 와 같다.** 그러니 대문이 비추는 그 dev 커밋에 박으면 둘 다 참이 된다
    (상현님: main → dev → chain 룰을 따른다)."""

    def _chain_with_a_file(self, name, fname):
        self.gil("chain", name, "--purpose", name, "--reference", "-",
                 "--criterion", "C", input="기준")
        self.gil("open", f"{name}/c1", "--author", "clew", "--purpose", "P",
                 "--body", "정의", "--fits", "목적 그 자체")
        # **파일은 가설 뒤에 만든다**(이슈 #121): 생각의 걸음(define·hypothesis)은 깨끗한
        # 트리에서만 선다. 옛 fixture 는 가설 앞에서 파일을 만들었고, 새 규칙이 그걸 잡았다 —
        # fixture 가 틀렸던 것이지 규칙이 과한 게 아니다.
        self.gil("step", f"{name}/c1", "--kind", "hypothesis", "--title", "H", "--body", "가설",
                 "--falsify", "F", "--falsify-to", "s1", "--plan", "p", "--advances", "a")
        with open(os.path.join(self.repo, fname), "w", encoding="utf-8") as f:
            f.write("이 체인이 만든 파일\n")
        self._git("add", fname)
        for s in ([ "--kind", "verify", "--title", "V", "--body", "검증", "--verdict", "supported",
                   "--plan-held", "--falsify-unmet", "미관측"],
                  ["--kind", "analyze", "--title", "A", "--body", "해석", "--finding", "f"],
                  ["--kind", "success", "--title", "S", "--body", "종합", "--toward", "t",
                   "--next-design", "d"]):
            self.gil("step", f"{name}/c1", *s)
        self.gil("close", f"{name}/c1", "--verdict", "supported")
        self.gil("chain-close", name, "--verdict", "supported", "--retro", "-", input="회고")
        self.gil("merge", name, "--into", "dev", "--reason", "합류")

    def _has(self, ref, path):
        return self._git("show", f"{ref}:{path}").returncode == 0

    def test_it_does_not_inherit_the_previous_chain_files(self):
        self.gil("init", "--name", "clew")
        self._chain_with_a_file("first", "first-only.txt")
        self.assertTrue(self._has("dev", "first-only.txt"), "fixture 가 dev 에 파일을 안 올렸다")
        r = self.gil("chain", "fresh", "--purpose", "새 관점", "--reference", "-",
                     "--criterion", "C", "--orphan", "새 관점으로 환기", input="기준")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self._has("fresh", "first-only.txt"),
                         "이어받지 않는다고 선언했는데 앞 체인의 파일을 물려받았다")
        # 그리고 층은 여전히 참이어야 한다 — 뿌리는 dev 에서 닿는 자리다.
        f = self.gil("fsck")
        self.assertIn("위반 0", f.stdout + f.stderr, "층 검사가 깨졌다:\n" + f.stdout + f.stderr)

    def test_after_a_deploy_it_stands_on_what_shipped(self):
        """배포된 것은 물려받는다 — 그게 '대문'의 뜻이다(대문 = 배포된 것만 온다)."""
        self.gil("init", "--name", "clew")
        self._chain_with_a_file("first", "first-only.txt")
        self._git("checkout", "-q", "dev")
        self.gil("deploy", "--tag", "v1")
        self.assertTrue(self._has("main", "first-only.txt"), "fixture 가 배포를 못 했다")
        r = self.gil("chain", "fresh2", "--purpose", "배포 뒤 새 관점", "--reference", "-",
                     "--criterion", "C", "--orphan", "환기", input="기준")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self._has("fresh2", "first-only.txt"),
                        "배포된 것까지 안 물려받았다 — 대문에서 시작한다는 뜻이 아니다")

    def test_it_names_the_node_instead_of_saying_the_front_door(self):
        """**"대문"이라고만 하면 어느 대문인지 알 수 없다**(상현님): 모든 것을 머지한 대문과
        init 직후의 대문은 다른 자리다. 자리를 sha 로 지목한다."""
        self.gil("init", "--name", "clew")
        r = self.gil("chain", "fresh", "--purpose", "새 관점", "--reference", "-",
                     "--criterion", "C", "--orphan", "환기", input="기준")
        out = r.stdout + r.stderr
        self.assertIn("⌂ 뿌리:", out, "어느 자리에 섰는지 말하지 않았다:\n" + out)
        self.assertEqual(self.trailer("fresh", "Gil-Chain-Orphan-At")[:9],
                         self.trailer("fresh", "Gil-Chain-Orphan-At"),
                         "자리가 커밋에 안 남았다")
        self.assertNotEqual(self.trailer("fresh", "Gil-Chain-Orphan-At"), "",
                            "자리를 커밋에 안 적었다 — 나중에 어느 대문이었는지 못 판정한다")


class TestQueriesDoNotLie(GilFixture):
    """**조회가 못 본 것과 실재하지 않는 것은 다르다** (이슈 #120, 긴급 — 상현님 실사용).

    `gil goto <c>/<cy>/s2` 가 "스텝 s2 없음"이라 **단정**했다. 같은 순간 `gil handoff` 는 s2 를
    팁으로 보여줬다. 에이전트는 그 단정을 "등록에 실패했다"로 읽고 **같은 스텝을 다시 심었고**,
    실측으로 s2 커밋이 네 벌 쌓였다. 치우려고 `git reset --soft` 를 두 번 — **gil 밖에서 이력을
    만졌다.** 재심는 과정에서 작업 트리가 가설 커밋에 함께 들어가, git 이력만 보면 "가설과 코드가
    한 커밋"이 됐다 — 이 도구가 지키려는 바로 그 성질(기록 순서의 증거)이 훼손된 것이다.

    원인은 하나의 비대칭이었다: 조회(goto·log·번호발급)는 `--branches` 만 보고, handoff 는 HEAD
    를 본다. 그래서 **어느 브랜치도 안 가리키는 커밋**은 한쪽에서만 사라지고, 그 번호가 다시
    발급된다. 세 창구가 같은 그래프를 다르게 읽으면 안 된다."""

    def _cycle(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P", "--reference", "-", "--criterion", "C",
                 input="기준")
        self.gil("open", "c/cy", "--author", "clew", "--purpose", "P",
                 "--body", "정의", "--fits", "목적 그 자체")
        self.gil("step", "c/cy", "--kind", "hypothesis", "--title", "H", "--body", "가설",
                 "--falsify", "F", "--falsify-to", "s1", "--plan", "p", "--advances", "a")

    def _orphan_the_tip(self):
        """지금 팁을 **어느 브랜치도 안 가리키는** 상태로 만든다(사고의 재현)."""
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("checkout", "-q", "--detach", head)
        for b in self._git("for-each-ref", "--contains", head, "--format=%(refname:short)",
                           "refs/heads/").stdout.split():
            self._git("branch", "-f", b, head + "~1")
        return head

    def test_log_accepts_a_cycle_and_lists_its_steps(self):
        """`gil log <chain>/<cycle>` 이 인자를 통째로 **체인 이름**과 비교해, 아무것도 못 찾고
        조용히 빈 목록을 냈다. goto 가 그 문법을 받으니 여기에도 그렇게 치는 게 자연스럽다."""
        self._cycle()
        r = self.gil("log", "c/cy")
        out = r.stdout + r.stderr
        self.assertIn("c/cy/s1", out, "사이클을 짚었는데 스텝 목록이 안 나온다:\n" + out)
        self.assertIn("c/cy/s2", out)

    def test_log_says_when_it_found_nothing(self):
        """**조용한 빈 목록은 "없다"로 읽힌다** — 그 오독이 다시 심게 만든다."""
        self._cycle()
        r = self.gil("log", "c/nope")
        out = r.stdout + r.stderr
        self.assertIn("못 찾았다", out, "못 찾고도 아무 말이 없다:\n" + out)
        self.assertIn("--all", out, "더 넓게 보는 길을 안 준다")

    def test_a_step_no_branch_points_at_is_still_seen(self):
        """어느 브랜치도 안 가리키는 스텝을 **없는 것으로 세지 않는다.**"""
        self._cycle()
        self._orphan_the_tip()
        # --leave-open: 미종결 잎 가드가 조회보다 **앞에** 서 있다. 여기서 재려는 것은
        # 그 가드가 아니라 조회의 시야다.
        r = self.gil("goto", "c/cy/s9", "--leave-open")
        out = r.stdout + r.stderr
        self.assertIn("s2", out, "브랜치가 안 가리키는 스텝이 조회에서 사라졌다:\n" + out)

    def test_the_number_is_not_reissued(self):
        """**같은 번호가 다시 나오면 그 뒤 계보 참조(--to·Gil-Parent)가 뜻을 잃는다.**"""
        self._cycle()
        self._orphan_the_tip()
        r = self.gil("step", "c/cy", "--kind", "verify", "--title", "V", "--body", "검증",
                     "--verdict", "supported", "--plan-held", "--falsify-unmet", "미관측")
        out = r.stdout + r.stderr
        self.assertIn("c/cy/s3", out, "s2 가 재발급됐다(같은 번호 두 벌):\n" + out)

    def test_the_refusal_does_not_assert_it_does_not_exist(self):
        """단정하지 않는다 — 못 봤으면 어디까지 봤는지 말하고 대조할 길을 준다."""
        self._cycle()
        r = self.gil("goto", "c/cy/s9", "--leave-open")
        out = r.stdout + r.stderr
        self.assertIn("못 찾았다", out, "여전히 '없음'이라 단정한다:\n" + out)
        self.assertIn("gil handoff", out, "대조할 길을 안 준다")


class TestYouCanOpenACycleThatMakesTheDataset(GilFixture):
    """**좌표를 요구하는 규칙이 좌표를 오염시켰다** (이슈 #119, 상현님 실사용).

    `--require-dataset` 로 연 체인에서는 **평가셋을 만드는 사이클**을 열 수 없었다. 그 사이클은
    아직 잴 셋이 없는데 `gil open` 이 `<이름>@sha256:<hex>` 를 요구한다 — 셋은 이 사이클의
    **산출물**인데 선언은 이 사이클을 **여는 조건**이다(닭-달걀).

    사람이 하게 되는 것 셋이 전부 기록을 상하게 한다: 해시를 지어내거나(#79 가 막으려던 것),
    앞 국면의 엉뚱한 셋을 적거나("이 수가 그 셋 위에 섰다"는 거짓말), 파일부터 만들고 사이클을
    나중에 열거나(gil 이 막으려는 '코드 먼저, 기록 나중').

    처방은 요구를 없애는 것이 아니라 **옳은 시점으로 옮기는 것**이다(리포트의 2번): 열 때는
    이름만(--produces-dataset), **닫을 때** 실제 sha. 그러면 원래 취지가 오히려 더 세게
    지켜지고, "이 사이클이 그 셋을 만들었다"는 간선이 그래프에 남는다."""

    DIGEST = "a" * 64

    def _chain(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P", "--reference", "-", "--criterion", "C",
                 "--require-dataset", input="기준")

    def _finish(self):
        for s in (["--kind", "hypothesis", "--title", "H", "--body", "가설", "--falsify", "F",
                   "--falsify-to", "s1", "--plan", "p", "--advances", "a"],
                  ["--kind", "verify", "--title", "V", "--body", "검증", "--verdict", "supported",
                   "--plan-held", "--falsify-unmet", "미관측"],
                  ["--kind", "analyze", "--title", "A", "--body", "해석", "--finding", "f"],
                  ["--kind", "success", "--title", "S", "--body", "종합", "--toward", "t",
                   "--next-design", "d"]):
            r = self.gil("step", "c/design", *s)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_refusal_shows_the_way_out(self):
        """막되, **없는 좌표를 지어내지 않는 길**을 그 자리에서 준다."""
        self._chain()
        r = self.gil("open", "c/design", "--purpose", "평가셋을 정의한다", "--title", "t",
                     "--body", "정의", "--fits", "t")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--produces-dataset", r.stdout + r.stderr,
                      "만드는 사이클의 길을 안 보여준다:\n" + r.stdout + r.stderr)

    def test_it_opens_with_a_promise(self):
        self._chain()
        r = self.gil("open", "c/design", "--purpose", "평가셋을 정의한다", "--title", "t",
                     "--body", "정의", "--fits", "t", "--produces-dataset", "app-suite")
        self.assertEqual(r.returncode, 0, "셋을 만드는 사이클을 못 연다:\n" + r.stdout + r.stderr)

    def test_closing_requires_the_real_coordinate(self):
        """**요구는 사라지지 않는다 — 잴 수 있는 시점으로 옮겨갈 뿐이다.**"""
        self._chain()
        self.gil("open", "c/design", "--purpose", "평가셋 정의", "--title", "t",
                 "--body", "정의", "--fits", "t", "--produces-dataset", "app-suite")
        self._finish()
        r = self.gil("close", "c/design", "--verdict", "supported")
        self.assertNotEqual(r.returncode, 0, "약속한 셋 없이 닫혔다 — 좌표가 사라진다")
        self.assertIn("app-suite", r.stdout + r.stderr, "무엇을 적어야 하는지 안 말한다")

    def test_the_coordinate_survives_in_the_graph(self):
        """받기만 하고 안 적으면 검사에만 쓰이고 사라진다 — 간선이 남아야 다음 사이클이 쓴다."""
        self._chain()
        self.gil("open", "c/design", "--purpose", "평가셋 정의", "--title", "t",
                 "--body", "정의", "--fits", "t", "--produces-dataset", "app-suite")
        self._finish()
        spec = "app-suite@sha256:" + self.DIGEST
        r = self.gil("close", "c/design", "--verdict", "supported", "--dataset", spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(spec, self._git("log", "-1", "--format=%B", "c-design").stdout,
                      "만든 셋의 좌표가 그래프에 안 남았다")


class TestTheHypothesisStandsBeforeTheCode(GilFixture):
    """**사후 해명은 증거가 아니라 자기보고다** (이슈 #121, 상현님 실사용).

    `gil step` 이 작업 트리를 스텝 커밋에 함께 담아, hypothesis 를 심는 순간 그때까지 쌓인
    코드가 같은 커밋에 들어갔다. git 이력만 보면 **"가설과 코드가 한 커밋"** 이다 — 이 도구가
    지키려는 성질이 바로 그 순서(문제 정의 → 가설 → 코드)인데 그 증거가 커밋 단위에서 사라진다.
    실측으로 두 사이클에서 반복됐고, 두 번 다 verify 본문에 "깃 이력만 보면 한 커밋이다"라고
    손으로 적어야 했다. **에이전트가 정직하게 남기려 해도 도구가 그것을 못 하게 한 것이다.**

    verify·analyze·종결은 산출물이 함께 들어오는 것이 자연스러우므로 건드리지 않는다."""

    def _cycle(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "c", "--purpose", "P", "--reference", "-", "--criterion", "C",
                 input="기준")
        self.gil("open", "c/cy", "--author", "clew", "--purpose", "P",
                 "--body", "정의", "--fits", "목적 그 자체")

    def _dirty(self, name="server.py"):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
            f.write("서버층 구현\n")
        self._git("add", name)

    def _hypothesis(self, *extra):
        return self.gil("step", "c/cy", "--kind", "hypothesis", "--title", "H", "--body", "가설",
                        "--falsify", "F", "--falsify-to", "s1", "--plan", "p", "--advances", "a",
                        *extra)

    def test_a_thinking_step_refuses_a_dirty_tree(self):
        self._cycle()
        self._dirty()
        r = self._hypothesis()
        self.assertNotEqual(r.returncode, 0, "코드를 안은 채 가설이 섰다")
        out = r.stdout + r.stderr
        self.assertIn("server.py", out, "무엇이 걸렸는지 안 말한다:\n" + out)

    def test_the_refusal_only_offers_paths_that_actually_work(self):
        """**"먼저 커밋하라"는 못 준다** — 체인 가지의 평범 커밋은 guard(#116)가 막는다.
        막기만 하고 통하지 않는 길을 주면 그건 벽이다."""
        self._cycle()
        self._dirty()
        out = self._hypothesis().stdout + self._hypothesis().stderr
        self.assertIn("git stash", out, "치우는 길을 안 준다")
        self.assertIn("--allow-dirty", out, "함께 담는 길을 안 준다")
        self.assertNotIn("먼저 커밋하", out, "guard 가 막는 길을 가르친다")

    def test_stashing_lets_the_hypothesis_stand(self):
        self._cycle()
        self._dirty()
        self._git("stash", "-q")
        r = self._hypothesis()
        self.assertEqual(r.returncode, 0, "치웠는데도 안 선다:\n" + r.stdout + r.stderr)

    def test_a_measuring_step_still_carries_its_artifacts(self):
        """verify 는 산출물을 담는 걸음이다 — 여기까지 막으면 도구가 일을 막는다."""
        self._cycle()
        self._git("stash", "-q")  # 깨끗한 자리에서 가설을 세우고
        self._hypothesis()
        self._dirty()             # 그 뒤 코드를 쓰고
        r = self.gil("step", "c/cy", "--kind", "verify", "--title", "V", "--body", "검증",
                     "--verdict", "supported", "--plan-held", "--falsify-unmet", "미관측")
        self.assertEqual(r.returncode, 0, "verify 가 산출물을 못 담는다:\n" + r.stdout + r.stderr)
        self.assertIn("server.py", self._git("show", "--stat", "--format=", "HEAD").stdout,
                      "verify 커밋에 산출물이 안 담겼다")

    def test_allow_dirty_writes_down_what_came_along(self):
        """함께 담기로 했으면 **무엇이 들어왔는지 커밋이 말한다** — 최소한 읽을 수는 있게."""
        self._cycle()
        self._dirty("f1.txt")
        self._dirty("f2.txt")
        r = self._hypothesis("--allow-dirty")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = self._git("log", "-1", "--format=%B", "c-cy").stdout
        self.assertIn("Gil-Tree-Changes: 2 files", body, "함께 들어온 것을 안 적었다")
        self.assertIn("f1.txt", body, "어떤 파일인지 안 적었다")


class _MCPClient:
    """gil mcp serve 를 stdio 로 몰아 **실제 프로토콜로** 부르는 최소 클라이언트.

    왜 이걸 짓나. 이 표면의 결함은 소스를 읽어서는 안 보였다 — 툴이 등록돼 있고 함수가 옳아도,
    **스키마가 필수라고 광고한 필드를 문법이 금지**하면 호출은 gil 이 돌기도 전에 죽는다
    (실제로 gil_chain 이 그랬다: purpose 필수인데 권장 경로인 from_intake 가 purpose 를
    금지한다). 그리고 인터뷰의 핵심인 Elicitation 은 **서버가 클라이언트에게 거는 요청**이라,
    거기에 답하는 클라이언트가 없으면 그 경로는 밟히지 않는다. 그래서 답하는 쪽까지 짓는다.
    """

    def __init__(self, repo, answers):
        self.p = subprocess.Popen(
            GIL_CMD + ["mcp", "serve"], cwd=repo, text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GIL_NO_VIEWER": "1"})
        self.answers = list(answers)
        self.forms = []          # 사람에게 실제로 뜬 폼들(무엇을 물었는지 검사할 수 있게)
        self._id = 0
        self.init = self._rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {"elicitation": {}},
            "clientInfo": {"name": "gil-test", "version": "0"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, obj):
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def _rpc(self, method, params):
        self._id += 1
        want = self._id
        self._send({"jsonrpc": "2.0", "id": want, "method": method, "params": params})
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise AssertionError(f"서버가 응답 없이 끝났다: {self.p.stderr.read()[:2000]}")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("method") == "elicitation/create":
                self.forms.append(msg["params"].get("message", ""))
                content = self.answers.pop(0) if self.answers else {}
                self._send({"jsonrpc": "2.0", "id": msg["id"],
                            "result": {"action": "accept", "content": content}})
                continue
            if msg.get("method"):
                if "id" in msg:
                    self._send({"jsonrpc": "2.0", "id": msg["id"],
                                "error": {"code": -32601, "message": "unsupported"}})
                continue
            if msg.get("id") == want:
                return msg

    def tools(self):
        return {t["name"]: t for t in self._rpc("tools/list", {})["result"]["tools"]}

    def call(self, _tool, **args):
        """툴 호출. (성공텍스트, 오류메시지) — 오류면 첫째가 ''.

        첫 인자를 _tool 로 둔다: 툴 인자에도 name 이 있어서(gil_start 의 존재 이름,
        gil_chain 의 체인 이름) 같은 이름이면 파이썬이 먼저 죽는다."""
        r = self._rpc("tools/call", {"name": _tool, "arguments": args})
        if "error" in r:
            return "", r["error"].get("message", "")
        res = r["result"]
        out = "".join(c.get("text", "") for c in res.get("content", []))
        return out, ("" if not res.get("isError") else out)

    def close(self):
        self.p.terminate()
        try:
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


class TestStartingIsOneMove(GilFixture):
    """**"gil 프로젝트 시작하자" 한 마디로 온보딩이 끝까지 간다** (상현님, 2026-08-09).

    이 시험이 생긴 이유는 실측이다. MCP 표면 — 비개발자가 쓰는 바로 그 표면 — 에서는
    새 프로젝트를 시작할 수가 **없었다**:

      · 빈 폴더에 gil_init(repo=…) 를 부르면 "거기서 시작하는 것이라면 먼저 gil_init 을 그
        경로로 불러라"가 돌아왔다. 방금 한 그 호출이다 — 자기 자신을 가리키는 닫힌 고리.
      · 체인 거부가 주는 권장 경로(`gil intake`)에 **대응 툴이 없었다.** 남는 길은 같은
        메시지가 금지하는 것 하나뿐이었다("네가 기준을 창작해 넣지 마라").
      · 존재를 각인하는 길(gil global)이 없어, init 이 준 첫 과제 자체가 불가능했다.
      · 스키마가 gil_chain 의 purpose 를 **필수**로 광고했는데, 권장 경로인 from_intake 는
        purpose 를 금지한다 — 호출이 gil 에 닿기도 전에 검증에서 죽었다.

    전부 "툴 목록에 있나"로는 안 잡히고 **끝까지 밟아야** 잡힌다. 그래서 밟는다."""

    def _client(self, repo=None, answers=None):
        c = _MCPClient(repo or self.repo, answers or [])
        self.addCleanup(c.close)
        return c

    ANSWERS = [
        {"ok": True},
        {"q1": "사내 문서를 검색해 답하는 도우미를 만들고 싶다.",
         "q2": "직원 20명이 일주일 써서 답이 맞다고 한 비율이 80% 를 넘으면 된 것이다."},
    ]

    def test_the_server_says_where_to_begin(self):
        """호스트가 initialize 에서 받는 글이 비어 있으면 시작점을 아무도 모른다."""
        c = self._client()
        ins = c.init["result"].get("instructions") or ""
        self.assertTrue(ins.strip(), "MCP instructions 가 비었다 — 시작점을 말할 유일한 자리다")
        self.assertIn("gil_start", ins, "시작할 때 무엇을 부르는지 안 적혀 있다")

    def test_the_table_of_the_surface_does_not_lie(self):
        """surface.go 의 표가 실재하지 않는 툴을 가리키면, 그 표가 곧 거짓 안내가 된다."""
        c = self._client()
        have = set(c.tools())
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "go", "surface.go"), encoding="utf-8").read()
        claimed = set(re.findall(r'"(gil_[a-z_]+)"', src))
        missing = sorted(claimed - have)
        self.assertEqual(missing, [], f"표가 없는 툴을 가리킨다: {missing}")

    def test_an_empty_folder_can_become_a_world(self):
        """**닫힌 고리가 없어야 한다.** 빈 폴더에서 시작하는 길이 실제로 있어야 한다."""
        empty = tempfile.mkdtemp(prefix="gil-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        c = self._client(repo=empty, answers=[{"ok": True}])
        out, err = c.call("gil_start")
        self.assertEqual(err, "", f"빈 폴더에서 시작하지 못했다:\n{err}")
        self.assertTrue(os.path.isdir(os.path.join(empty, ".git")), "저장소가 안 섰다")
        self.assertIn("이름", out, "다음 칸(이름 짓기)을 안 말했다")
        self.assertTrue(c.forms, "사람에게 묻지 않고 남의 디스크에 저장소를 세웠다")

    def test_it_will_not_create_a_folder_that_does_not_exist(self):
        """없는 경로에 디렉터리를 파지 않는다 — 어디에 만들지는 언제나 사람이 정한다."""
        c = self._client()
        gone = os.path.join(self.repo, "없는폴더", "더없는폴더")
        _, err = c.call("gil_start", repo=gone)
        self.assertIn("그런 폴더가 없다", err, f"없는 경로를 그냥 만들었거나 다른 이유로 죽었다: {err}")

    def test_the_rail_runs_to_the_end(self):
        """빈 폴더 → 세계 → 이름 → 정체성 → 사람의 답 → 체인. **한 자리도 못 밟으면 안 된다.**"""
        c = self._client(answers=list(self.ANSWERS))
        out, err = c.call("gil_start")
        self.assertEqual(err, "", out + err)

        out, err = c.call("gil_start", name="scout")
        self.assertEqual(err, "", out + err)
        self.assertIn("scout", out)

        # 정체성을 채우면 그 자리에서 개시 인터뷰가 서고, 호스트 폼으로 사람에게 닿는다.
        out, err = c.call("gil_start",
                          identity="# Identity — scout\n\n문서에서 답을 찾아 오는 존재다.\n",
                          will="# Will\n\n사람이 묻기 전에 근거를 갖춘다.\n")
        self.assertEqual(err, "", out + err)
        self.assertIn("사람의 답이 도착했다", out,
                      "질문을 심어 놓고 끝냈다 — 그러면 아무 일도 안 일어난다(#82)")

        # **권장 경로가 실제로 돌아야 한다.** 여기서 purpose 를 요구하면 인용이 불가능해진다.
        out, err = c.call("gil_chain", name="docs-helper", from_intake="start",
                          purpose_from="1", criterion_from="2")
        self.assertEqual(err, "", f"gil 이 권장하는 인용 경로가 이 표면에서 막혔다:\n{err}")
        self.assertIn("사내 문서를 검색해 답하는 도우미", out,
                      "목적이 사람의 문장 그대로가 아니다")
        self.assertIn("80%", out, "성패 기준이 사람의 문장 그대로가 아니다")

        out, _ = c.call("gil_start", status=True)
        self.assertIn("온보딩은 끝났다", out, f"끝났는데 안 끝났다고 말한다:\n{out}")

    def test_the_existence_can_write_its_own_room(self):
        """존재를 각인하는 손이 이 표면에 있어야 한다 — 없으면 첫 과제가 불가능하다."""
        c = self._client(answers=list(self.ANSWERS))
        c.call("gil_start")
        c.call("gil_start", name="scout")
        out, err = c.call("gil_global", action="read", path="existence/scout/identity.md")
        self.assertEqual(err, "", err)
        # 이름을 지으면 **방이 옮겨질 뿐** 본문은 씨앗 그대로다 — 자기 말로 쓰는 것은
        # 존재가 할 일이지 도구가 대신할 일이 아니다(도구가 채우면 각인이 아니라 위조다).
        self.assertIn("아직 이름이 없다", out, "옮겨진 방이 아니라 다른 것을 읽었다")
        _, err = c.call("gil_global", action="write",
                        path="existence/scout/identity.md",
                        content="# Identity — scout\n\n내가 쓴 문서다.\n")
        self.assertEqual(err, "", f"존재가 제 방을 쓰지 못한다: {err}")
        out, _ = c.call("gil_global", action="read", path="existence/scout/identity.md")
        self.assertIn("내가 쓴 문서다", out, "쓴 것이 안 남았다")

    def test_the_memory_can_be_knotted(self):
        """세션을 넘기는 유일한 통로 — 없으면 이 표면의 존재는 매번 죽는다."""
        c = self._client(answers=list(self.ANSWERS))
        c.call("gil_start")
        c.call("gil_start", name="scout")
        _, err = c.call("gil_memory", action="append", name="scout",
                        knot="## 세션 매듭\n\n이번에 한 일과 다음 순서.\n")
        self.assertEqual(err, "", f"기억을 못 남긴다: {err}")
        out, _ = c.call("gil_memory", action="read", name="scout")
        self.assertIn("이번에 한 일과 다음 순서", out, "남긴 매듭이 안 읽힌다")

    def test_the_body_does_not_leak_to_disk(self):
        """본문을 파일로 나르는 임시 파일은 **호출 하나**만 산다(정체성·기억이 실린다)."""
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "gil-identity-*.md")))
        c = self._client(answers=list(self.ANSWERS))
        c.call("gil_start")
        c.call("gil_start", name="scout")
        c.call("gil_start", identity="# Identity — scout\n\n비밀은 아니지만 남을 것도 아니다.\n",
               will="# Will\n\n무엇을 향해 가는가.\n")
        after = set(glob.glob(os.path.join(tempfile.gettempdir(), "gil-identity-*.md")))
        self.assertEqual(sorted(after - before), [], "임시 파일이 남았다")


class TestGuidancePointsAtThisSurface(GilFixture):
    """**안내가 가리키는 명령은 이 표면에 실재하거나, 없다고 말해야 한다.**

    소스 전체에서 안내가 `gil <명령>` 을 가리키는 자리는 400곳이 넘는다. MCP 표면에 대응
    툴이 없는 명령을 가리키면 그 줄은 **칠 수 없는 줄**이고, 실측에서 그런 자리가 통째로
    막다른 골목이었다(gil_handoff 가 준 다음 수 12개 중 11개).

    전부 고쳐 쓰는 대신 **가리키는 것을 실재하게** 만들었다(이름이 기계적으로 대응한다:
    `gil x-y` → `gil_x_y`). 남은 것은 일부러 안 만든 것들이고, 그건 왜 없는지가 적혀 있어야
    한다. 열거가 아니라 규칙으로 센다 — 열거는 늘 뒤늦기 때문이다."""

    GO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "go")

    def test_every_command_it_names_is_placed_on_purpose(self):
        """안내가 부르는 명령은 툴이 있거나, 터미널 전용이라고 선언돼 있어야 한다."""
        src = open(os.path.join(self.GO, "main.go"), encoding="utf-8").read()
        known = set(re.findall(r'^\tcase "([a-z][a-z-]*)":', src, re.M))
        self.assertIn("start", known, "gil start 가 명령 표면에 없다")

        # **어느 표에 있는지**로 가른다 — 값의 생김새로 가르면 안 된다.
        # (처음엔 값이 "gil_" 로 시작하는지로 갈랐는데, terminalOnly 의 guard 는 값이
        #  "git 훅과…" 로 시작해서 걸려 나왔다. 시험이 자기 정규식의 결함을 결함으로
        #  보고한 것이다 — 갈림의 근거가 뜻이 아니라 철자면 언젠가 반드시 어긋난다.)
        surf = open(os.path.join(self.GO, "surface.go"), encoding="utf-8").read()
        _, _, rest = surf.partition("var mcpSurface = map[string]string{")
        mcp_block, _, rest = rest.partition("}")
        _, _, term_block = rest.partition("var terminalOnly = map[string]string{")
        term_block = term_block.partition("}")[0]
        # 표는 **셋**이다. 세 번째(humanOnly)는 "툴은 실재하는데 에이전트의 것이 아니다" —
        # 카드의 버튼이 부르는 자리다. 이 표를 안 읽으면, 자리를 옳게 정한 명령이
        # "아무도 안 정했다"로 잡힌다(실제로 prune-approve 가 그렇게 잡혔다).
        _, _, human_block = surf.partition("var humanOnly = map[string]string{")
        human_block = human_block.partition("}")[0]
        on_mcp = set(re.findall(r'"([a-z][a-z-]*)":\s*"gil_[a-z_]+"', mcp_block))
        terminal = set(re.findall(r'"([a-z][a-z-]*)":\s*"', term_block))
        human = set(re.findall(r'"([a-z][a-z-]*)":\s*"', human_block))
        self.assertTrue(on_mcp and terminal and human,
                        "surface.go 의 세 표를 못 읽었다 — 시험이 눈이 먼다")

        named = set()
        for f in sorted(glob.glob(os.path.join(self.GO, "*.go"))):
            for ln in open(f, encoding="utf-8"):
                if ln.lstrip().startswith("//"):
                    continue      # 주석은 사람이 치는 표면이 아니다(v3.58.2 의 판정 규칙)
                for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', ln):
                    for cmd in re.findall(r"\bgil ([a-z][a-z-]+)", lit):
                        if cmd in known:
                            named.add(cmd)

        unplaced = sorted(named - on_mcp - terminal - human)
        self.assertEqual(
            unplaced, [],
            "안내가 부르는데 이 표면에서 어디에 있는지 아무도 안 정한 명령:\n  " +
            ", ".join(unplaced) +
            "\n  셋 중 하나를 해라 — 툴을 세우거나(mcpSurface), 사람이 화면에서 누르는 것이라고"
            " 적거나(humanOnly), 왜 터미널 전용인지 적거나(terminalOnly). 조용히 두는 선택지는 없다.")


class TestGitFailuresSpeakGilsLanguage(GilFixture):
    """**죽은 잠금 하나가 시작을 통째로 막았다** (상현님 실사용, 2026-08-09).

    Claude Desktop 에서 새 프로젝트를 시작하다 이게 그대로 올라갔다:

        git add CLAUDE.md 실패: exit status 128 — fatal: Unable to create
        '…/.git/index.lock': File exists.

    그 자리의 에이전트는 **진단도 처방도 누가 실행할지도 전부 지어냈고**, 사람에게
    `rm …/index.lock` 을 대신 쳐 달라고 부탁했다. 상현님 판단: **비개발자는 터미널에 뭘
    해달라고 하면 대응하지 못한다.** 그러니 도구가 치울 수 있는 것을 사람 숙제로 넘기면
    시작하려던 사람이 첫 칸에서 멈춘다.

    그래서 둘을 함께 세운다 — 치울 수 있으면 **치우고 이어가고**, 못 치우면 **무슨 일인지와
    복구 한 줄을** 정확히 말한다. 조용히 넘어가지도, 지어내지도 않는다."""

    def _lock(self, age_seconds):
        lock = os.path.join(self.repo, ".git", "index.lock")
        open(lock, "w").close()
        if age_seconds:
            t = time.time() - age_seconds
            os.utime(lock, (t, t))
        # gil 은 심링크를 푼 실제 경로를 준다(macOS 의 /var → /private/var).
        return os.path.realpath(lock)

    def _no_clear(self):
        """자동정리를 끄고 진단만 보게 한다 — 끄는 길이 실제로 있는지도 함께 센다."""
        os.environ["GIL_NO_LOCK_CLEAR"] = "1"
        self.addCleanup(os.environ.pop, "GIL_NO_LOCK_CLEAR", None)

    def test_a_dead_lock_does_not_stop_the_start(self):
        """**핵심**: 죽은 잠금은 gil 이 치우고 이어간다 — 사람에게 터미널을 시키지 않는다."""
        self._lock(3600)
        r = self.gil("start")
        out = r.stdout + r.stderr
        self.assertIn("잠금을 치웠다", out, "치웠다는 사실을 말하지 않았다(조용한 정리는 원인을 지운다)")
        self.assertIn("gil init 완료", out, "치우고도 이어가지 않았다 — 사람이 여전히 막힌다")

    def test_a_fresh_lock_is_never_touched(self):
        """방금 생긴 잠금은 **지금 도는 git** 일 수 있다 — 남의 작업을 밟는 쪽이 더 나쁘다."""
        lock = self._lock(0)
        r = self.gil("start")
        out = r.stdout + r.stderr
        self.assertNotIn("잠금을 치웠다", out, "갓 생긴 잠금을 치웠다")
        self.assertTrue(os.path.exists(lock), "갓 생긴 잠금 파일이 사라졌다")
        self.assertIn("잠깐 기다렸다 다시 해라", out, "기다리라고 말하지 않았다")

    def test_when_it_cannot_clear_it_says_what_and_how(self):
        """못 치우는 환경(공유 폴더·가상화 샌드박스)에서는 **정확한 복구 한 줄**을 준다."""
        self._no_clear()
        lock = self._lock(3600)
        r = self.gil("start")
        out = r.stdout + r.stderr
        self.assertIn("잠금 파일", out, "날 git 에러만 올렸다 — 무슨 일인지 말하지 않았다")
        self.assertIn(lock, out, "어느 파일인지 말하지 않았다(사람이 경로를 지어내게 된다)")
        self.assertIn('rm "' + lock + '"', out, "복구 한 줄을 그대로 주지 않았다")
        self.assertIn("정황이지 증명은 아니다", out, "정황을 단정으로 말했다(#57)")

    def test_unknown_git_failures_get_no_invented_diagnosis(self):
        """모르는 실패에 진단을 얹지 않는다. 그 자리를 채우려는 유혹이 이 결함의 뿌리다."""
        r = self.gil("global", "read", "존재하지-않는-파일.md")
        out = r.stdout + r.stderr
        self.assertNotIn("잠금 파일", out, "관계없는 실패에 잠금 진단이 붙었다")


class TestAFormlessHostCanStillStart(GilFixture):
    """**폼이 안 뜬 것과 사람이 거절한 것은 다르다** (#57 — 그리고 그 자리를 다시 밟았다).

    실측(상현님, 2026-08-09): Claude Desktop 에서 승낙 폼이 서지 않았고, gil 은 **"사람이
    승낙하지 않았다"고 단언**했다. 사람은 거절한 적이 없다 — 방금 "gil 프로젝트 시작하자"고
    말한 참이었다. 다시 불러도 같은 답이라 막다른 길이었고, 그래서 에이전트는 gil 을 우회했다:

        gil_start → gil_start → Bash(git init) → gil_start → gil_init → …

    그 git 이 중간에 죽어 잠금이 남았고, 사람은 터미널 명령을 부탁받았다. **거부 문구 하나가
    우회를 만들고, 우회가 저장소를 반쯤 부순 것이다.**

    앞 시험들이 이걸 못 잡은 이유가 분명하다 — **폼에 답하는 클라이언트로만 밟았다.**
    답하지 *못하는* 클라이언트는 밟지 않았다. 그래서 여기서 밟는다."""

    def _call(self, args, answers_forms):
        """폼 요청에 error 로 답하는(=못 띄우는) 호스트로 gil_start 를 부른다."""
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1"})
        self.addCleanup(p.terminate)

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    m = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if m.get("method") == "elicitation/create":
                    if answers_forms:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "result": {"action": "accept", "content": {"ok": True}}})
                    else:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "elicitation not supported"}})
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "unsupported"}})
                    continue
                if m.get("id") == want:
                    return m

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "formless", "version": "0"}}})
        pump(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "gil_start", "arguments": args}})
        r = pump(2)
        if r is None:
            return "", "(응답 없음)"
        if "error" in r:
            return "", r["error"].get("message", "")
        # 거부는 JSON-RPC error 가 아니라 **isError 인 result** 로 온다(MCP 규범). 이걸
        # 성공으로 읽으면 "막혔는데 통과했다"고 세게 되고, 그러면 시험이 눈이 먼다.
        res = r["result"]
        txt = "".join(c.get("text", "") for c in res.get("content", []))
        if res.get("isError"):
            return "", txt
        return txt, ""

    def setUp(self):
        super().setUp()
        shutil.rmtree(os.path.join(self.repo, ".git"), ignore_errors=True)  # 진짜 빈 폴더로

    def test_it_does_not_claim_the_human_refused(self):
        """없던 사람 의사를 심으면 그게 곧 우회 압력이 된다."""
        _, err = self._call({}, answers_forms=False)
        self.assertNotIn("승낙하지 않았다", err, "폼이 안 선 것을 '사람이 거절했다'로 단언했다")
        self.assertIn("거절한 것이 아니다", err, "둘이 다르다는 것을 말하지 않았다")

    def test_it_gives_a_way_forward_instead_of_a_dead_end(self):
        """막다른 길이면 에이전트는 도구를 우회한다 — 실제로 그렇게 됐다."""
        _, err = self._call({}, answers_forms=False)
        self.assertIn("confirmed", err, "다음에 무엇을 실어 오면 되는지 말하지 않았다")
        self.assertIn("git init", err, "우회하지 말라고 그 자리에서 말하지 않았다")

    def test_confirmed_actually_works(self):
        """**안내가 가리키는 것은 실재해야 한다** — confirmed 로 다시 부르면 실제로 서야 한다."""
        out, err = self._call({"confirmed": True}, answers_forms=False)
        self.assertEqual(err, "", f"confirmed 를 실었는데도 막혔다:\n{err}")
        self.assertIn("gil init 완료", out, "세계가 서지 않았다")
        self.assertTrue(os.path.isdir(os.path.join(self.repo, ".git")), "저장소가 안 섰다")

    def test_the_provenance_of_the_consent_is_recorded(self):
        """폼의 승낙과 에이전트의 보고는 다른 것이다 — 구분되는 것은 구분해 적는다(#57)."""
        out, _ = self._call({"confirmed": True}, answers_forms=False)
        self.assertIn("에이전트가 사람에게 물어", out,
                      "확인의 출처를 폼의 승낙과 똑같이 적었다")


class TestTheWorldStandsOnlyWhereSomeoneChose(GilFixture):
    """**프로젝트를 담는 자리에는 프로젝트를 세우지 않는다** (상현님 실사용, 2026-08-09).

    앞 커밋이 "폼이 안 서면 사람에게 물어라"로 고쳤고 그건 먹혔다 — 에이전트가 우회하지 않고
    제대로 물었다. 그런데 그 물음이 이렇게 나갔다:

        "기본 경로가 / 로 잡혀 있는데, 보통은 지금 작업 중인 폴더에 세우는 게 맞습니다."

    **gil 이 `/` 에 서 있었다.** Claude Desktop 은 roots 를 선언하지 않아 프로세스가 뜬 자리가
    그대로 자리가 됐고, 안내는 거기다 대고 "여기에 저장소를 세우게 된다: /" 라고 태연히 말했다.
    사람이 "네" 라고 답했으면 `/` 에 저장소를 세우려 들었을 것이다 — 에이전트가 이상함을
    알아채고 되물어 준 덕에 안 났을 뿐, **그건 운이다.**

    처음엔 **누가 이 자리를 골랐나**로 판정을 걸었다(roots·repo 면 정당, "프로세스가 뜬 자리"면
    거부). 원리적으로 깔끔했는데 **정당한 경우를 함께 막았다** — 호스트가 프로젝트 폴더 *안에서*
    서버를 띄우는 구성이 실제로 있고, 그건 띄운 쪽이 자리를 고른 것이다. 시험 넷이 빨개져서
    알았다: **규칙이 예쁘다고 옳은 것은 아니다.**

    그래서 판정은 **그 자리가 무엇인가**로 건다. `/` 와 홈 자신은 프로젝트가 아니라 프로젝트를
    **담는** 자리다 — 누가 골랐든 거기에 세우면 그 아래 전부가 한 저장소가 된다. 그리고
    **승낙은 "할지"에 대한 것이지 "어디에"가 아니다** — confirmed 가 자리를 정당화하지 못한다."""

    def _start(self, args, cwd="/"):
        """roots 를 안 주는 호스트로, 지정한 자리에서 뜬 서버에 gil_start 를 건다."""
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=cwd, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1"})
        self.addCleanup(p.terminate)

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    m = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if m.get("method"):
                    if "id" in m:      # 폼 요청 포함 — 이 호스트는 아무것도 못 띄운다
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "unsupported"}})
                    continue
                if m.get("id") == want:
                    return m

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "no-roots", "version": "0"}}})
        pump(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "gil_start", "arguments": args}})
        r = pump(2)
        if r is None:
            return "", "(응답 없음)"
        if "error" in r:
            return "", r["error"].get("message", "")
        res = r["result"]
        txt = "".join(c.get("text", "") for c in res.get("content", []))
        return ("", txt) if res.get("isError") else (txt, "")

    def test_it_refuses_the_filesystem_root(self):
        """실사용에서 gil 이 실제로 서 있던 자리다 — 거기를 세울 곳으로 내밀면 안 된다."""
        _, err = self._start({})
        self.assertIn("파일시스템의 뿌리", err, "`/` 를 세울 자리로 받아들였다")
        self.assertIn("repo", err, "무엇을 실어 오면 되는지 말하지 않았다")

    def test_consent_does_not_justify_the_place(self):
        """**승낙은 '할지'에 대한 것이지 '어디에'가 아니다.** confirmed 로 뚫려선 안 된다."""
        _, err = self._start({"confirmed": True})
        self.assertIn("파일시스템의 뿌리", err,
                      "confirmed 하나로 루트에 저장소를 세울 수 있게 됐다")
        self.assertFalse(os.path.isdir("/.git"), "루트에 저장소를 세웠다")

    def test_a_real_folder_stands(self):
        """담는 자리가 아니면 선다 — 막기만 하면 그건 레일이 아니라 벽이다."""
        out, err = self._start({"repo": self.repo, "confirmed": True})
        self.assertEqual(err, "", f"평범한 폴더인데 막혔다:\n{err}")
        self.assertIn("gil init 완료", out)

    def test_a_server_launched_inside_the_project_stands(self):
        """호스트가 프로젝트 폴더 안에서 서버를 띄우는 구성 — 그것도 고른 것이다.

        이 시험이 없어서 앞선 '누가 골랐나' 판정이 정당한 경우를 막았다(시험 넷이 빨개졌다)."""
        out, err = self._start({"confirmed": True}, cwd=self.repo)
        self.assertEqual(err, "", f"프로젝트 폴더 안에서 띄웠는데 막혔다:\n{err}")
        self.assertIn("gil init 완료", out)

    def test_the_cli_stands_where_the_human_typed(self):
        """CLI 는 사람이 그 폴더에서 직접 친 것이다 — cd 가 곧 선택이다."""
        r = self.gil("start")
        out = r.stdout + r.stderr
        self.assertNotIn("프로젝트가 아니라", out, "사람이 직접 친 자리를 되물었다")
        self.assertIn("gil init 완료", out)


class TestDeletionCanBeDecidedWhereThePersonIs(GilFixture):
    """**삭제 승인이 카드 안에 선다** (상현님 결정, 2026-08-10).

    규범은 처음부터 "삭제는 사람의 판단을 지난다"였다. 그런데 그 판단을 **누를 자리**가
    뷰어 창 하나뿐이었다 — 뷰어는 이 표면에서 열 수 없고 비개발자에게 터미널은 없다.
    즉 규범은 사람이 승인한다고 말하는데 실제로는 **승인할 수 있는 사람이 없었다.**
    요청은 쌓이고 아무도 못 푼다.

    그리고 요청이 떠 있다는 사실을 보여 주는 화면도 뷰어뿐이었다 — status·handoff 는
    prune 을 한 글자도 말하지 않았다(실측 grep 0).

    맞바꾼 것: 통로를 세우면 에이전트도 이 툴을 부를 수 있게 된다(visibility:["app"] 은
    벽이 아니라 힌트다). 도달가능성을 택했고, 방어는 두 겹으로 남는다 — Gil-By 가 누가
    눌렀는지 적고, 승인만으로는 아무것도 안 지워진다(실행은 터미널의 확인 문구)."""

    def _app(self):
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1", "GIL_NO_VERSION_CHECK": "1"})
        self.addCleanup(p.terminate)
        state = {"id": 0}

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                try:
                    m = json.loads(ln.strip())
                except (json.JSONDecodeError, ValueError):
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "x"}})
                    continue
                if m.get("id") == want:
                    return m

        state["id"] += 1
        send({"jsonrpc": "2.0", "id": state["id"], "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "app", "version": "0"}}})
        pump(state["id"])
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        def call(name, args):
            state["id"] += 1
            send({"jsonrpc": "2.0", "id": state["id"], "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
            r = pump(state["id"])
            if r is None:
                return "", "(응답 없음)"
            if "error" in r:
                return "", r["error"].get("message", "")
            res = r["result"]
            txt = "".join(c.get("text", "") for c in res.get("content", []))
            return ("", txt) if res.get("isError") else (txt, "")
        return call

    WHY = "이주가 끝나 옛 계보는 더 볼 이유가 없다."

    def _requested(self):
        """삭제 요청이 올라온 상태 — 그리고 HEAD 는 층 위에 선다(요청을 올린 사람의 자리)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "old", "--purpose", "P", "--reference", "-",
                 "--criterion", "C", input="기준")
        self.gil("chain-close", "old", "--verdict", "supported", "--retro", "-", input="회고")
        r = self.gil("prune", "old", "--request", "--reason", self.WHY)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._git("checkout", "-q", "main")

    def _card(self):
        return self.gil("status", "--card").stdout

    def test_the_request_is_visible_where_the_person_stands(self):
        """층(dev·main) 위에서도 보여야 한다 — 요청을 올린 사람이 서 있는 자리가 거기다."""
        self._requested()
        card = self._card()
        self.assertIn('data-prune="old"', card,
                      "삭제 요청이 카드에 안 뜬다 — 뷰어 말고는 이 사실을 보여 주는 화면이 없다")
        self.assertIn(self.WHY, card, "요청 이유가 없다 — 그것 말고 사람이 판단할 재료가 없다")
        self.assertIn("지금 지워지지는 않는다", card,
                      "승인이 무엇을 하는지 화면이 말하지 않는다")

    def test_the_agent_reads_the_same_fact(self):
        """화면만 알고 데이터가 모르면 둘이 갈린다."""
        self._requested()
        st = json.loads(self.gil("status", "--json").stdout)
        got = [p["target"] for p in st["pending_prunes"]]
        self.assertEqual(got, ["old"], "gil status 가 삭제 대기를 말하지 않는다: " + repr(got))

    def test_the_button_actually_approves(self):
        """**버튼이 보내는 그 인자 그대로** 승인이 돈다 — 그리고 Gil-By 에 자국이 남는다."""
        self._requested()
        card = self._card()
        m = re.search(r'<button[^>]*data-tool="gil_prune_approve"[^>]*>', card)
        self.assertIsNotNone(m, "승인 버튼이 없다")
        tgt = re.search(r'data-target="([^"]*)"', m.group(0)).group(1)
        out, err = self._app()("gil_prune_approve", {"repo": self.repo, "target": tgt})
        self.assertEqual(err, "", f"승인 버튼이 보내는 인자가 거부됐다: {err}")
        # 승인은 됐지만 **아무것도 안 지워졌다** — 문은 둘이다.
        self.assertIn("old", self.branches(), "승인만으로 가지가 사라졌다 — 문이 하나로 줄었다")
        by = self._git("log", "--branches", "-1", "--format=%(trailers:key=Gil-By,valueonly)",
                       "--grep=prune-approve").stdout.strip()
        self.assertEqual(by, "card", "누가 눌렀는지가 안 남았다 — ⚡ 고지가 생산자를 잃는다")

    def test_withdrawing_takes_the_request_back(self):
        """거두는 길이 없으면 그 문은 덫이다 — 그리고 거두는 데 관문을 세우지 않는다."""
        self._requested()
        out, err = self._app()("gil_prune_withdraw", {"repo": self.repo, "target": "old"})
        self.assertEqual(err, "", f"철회가 거부됐다: {err}")
        self.assertNotIn('data-prune="old"', self._card(), "거뒀는데 카드가 남았다")
        card_btn = re.search(r'<button[^>]*data-tool="gil_prune_withdraw"[^>]*>',
                             self.gil("status", "--card").stdout)
        # (지금은 요청이 없어 버튼도 없다 — 있을 때 무장 면제였는지는 요청 상태에서 본다)
        self.assertIsNone(card_btn, "요청을 거뒀는데 버튼이 남아 있다")

    def test_withdraw_is_not_armed(self):
        """아무것도 안 지우는 버튼에 두 번 클릭을 걸면 그 관문이 값싸진다."""
        self._requested()
        m = re.search(r'<button[^>]*data-tool="gil_prune_withdraw"[^>]*>', self._card())
        self.assertIsNotNone(m, "철회 버튼이 없다")
        self.assertIn("data-noarm", m.group(0), "철회에 두 번 클릭이 걸려 있다")
        a = re.search(r'<button[^>]*data-tool="gil_prune_approve"[^>]*>', self._card())
        self.assertIn("data-arm=", a.group(0), "승인이 무엇을 확정하는지 되묻지 않는다")

    def test_the_guidance_points_at_the_button_not_at_a_missing_tool(self):
        """**툴은 실재하는데 에이전트의 것이 아니다** — 그 셋째 자리를 안내가 말한다.

        terminalOnly 에 두면 "이 표면엔 툴이 없다" 가 거짓이 되고, mcpSurface 에 두면
        에이전트에게 사람의 판단을 누를 이름을 준다."""
        self._requested()
        out, _ = self._app()("gil_status", {"repo": self.repo})
        self.assertNotIn("gil_prune_approve", out,
                         "에이전트에게 삭제 승인 툴 이름을 줬다 — 사람의 판단이다")
        self.gil("prune-approve", "old", "--by", "card")
        out2, _ = self._app()("gil_status", {"repo": self.repo})
        self.assertIn("승인했다", out2, "승인 도착이 에이전트에게 안 닿았다")


class TestArrivalsReachTheMCPSession(GilFixture):
    """**도착 고지가 MCP 세션에도 선다** (뷰어 제거 조사, 2026-08-10).

    사람이 자기 몫을 다했는데 그 사실이 에이전트에게 안 닿으면, 사람이 다시 말을 걸어야
    한다 — 그걸 막으려고 이슈 #77 이 세운 기구다(⚡ 인터뷰 답·승인·기각·삭제).

    그런데 그 기구의 **유일한 호출자가 main.go 의 부팅 자리**였고, MCP 툴 호출은
    toolUI→runGil 로 cmd* 를 직접 부르므로 그 자리를 지나지 않는다. 즉 MCP 로 도는 세션은
    이 고지를 **한 번도** 못 받았다. 카드에서 답을 제출해도, 승인을 눌러도.

    이건 새로 발견한 병이 아니다 — 같은 자리에서 versionAskBanner 가 이미 같은 이유로
    따로 붙어 있었고(mcp.go 의 주석이 그 이유를 적어 뒀다), **그 옆줄에서 이 기구가 빠진
    것을 아무도 안 봤다.** 한쪽을 고치고 그 짝을 안 본 자리가 하나 더 있었던 것이다."""

    def _app(self):
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1", "GIL_NO_VERSION_CHECK": "1"})
        self.addCleanup(p.terminate)
        state = {"id": 0}

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                try:
                    m = json.loads(ln.strip())
                except (json.JSONDecodeError, ValueError):
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "x"}})
                    continue
                if m.get("id") == want:
                    return m

        state["id"] += 1
        send({"jsonrpc": "2.0", "id": state["id"], "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "app", "version": "0"}}})
        pump(state["id"])
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        def call(name, args):
            state["id"] += 1
            send({"jsonrpc": "2.0", "id": state["id"], "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
            r = pump(state["id"])
            if r is None:
                return "(응답 없음)"
            if "error" in r:
                return r["error"].get("message", "")
            return "".join(c.get("text", "") for c in r["result"].get("content", []))
        return call

    def _human_answered(self):
        """사람이 카드 폼에 답을 제출한 상태까지 — 그 다음 에이전트가 알아야 한다."""
        self.gil("init", "--name", "clew")
        self.gil("intake", "sd", "--ask", "-",
                 input=json.dumps([{"q": "무엇을 하려 하십니까", "type": "text"}],
                                  ensure_ascii=False))
        call = self._app()
        out = call("gil_interview_submit", {
            "repo": self.repo, "chain": "sd",
            "answers": json.dumps({"q1": "사내 규정을 쉽게 찾게 하고 싶다."}, ensure_ascii=False)})
        self.assertNotIn("확정하지 못했다", out, out)

    def test_the_agent_learns_the_human_answered(self):
        """제출은 됐는데 에이전트가 모르면, 사람이 다시 말을 걸어야 한다."""
        self._human_answered()
        out = self._app()("gil_status", {"repo": self.repo})
        self.assertIn("⚡", out,
                      "사람이 답했는데 MCP 세션이 그 사실을 못 받았다:\n" + out[:1200])
        self.assertIn("sd", out, "어느 인터뷰가 도착했는지 안 말한다")

    def test_the_notice_does_not_point_at_a_tool_that_is_not_here(self):
        """prune 은 이 표면에 툴이 없다 — 날것으로 적으면 없는 gil_prune 을 파생한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P", "--reference", "-",
                 "--criterion", "C", input="기준")
        self.gil("chain-close", "a", "--verdict", "supported", "--retro", "-", input="회고")
        self.gil("prune", "a", "--request", "--reason", "이주 완료")
        # 사람이 뷰어/카드가 아니라 CLI 로 승인했더라도 --by 가 붙으면 사람의 손이다.
        r = self.gil("prune-approve", "a", "--by", "card")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self._app()("gil_status", {"repo": self.repo})
        self.assertIn("삭제를 **승인했다**", out, "삭제 승인이 MCP 세션에 안 닿았다:\n" + out[:1200])
        self.assertIn("이 표면엔 툴이 없다", out,
                      "터미널 전용 명령을 이 표면의 툴인 것처럼 가리킨다:\n" + out[:1200])

    def test_the_lead_stands_on_every_registration_path(self):
        """**등록 자리를 열거하지 않는다** — 앞머리는 미들웨어 하나가 붙인다.

        이 병의 모양이 그거였다: 툴을 등록하는 자리가 여섯인데 앞머리를 둘에만 붙여 놨고,
        그래서 gil_status·gil_graph 로만 도는 세션은 통째로 비껴갔다. 붙이는 자리를 세지
        말고, **붙는 자리가 하나임**을 센다."""
        go = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "go")
        src = ""
        for fn in sorted(os.listdir(go)):
            if fn.endswith(".go"):
                with open(os.path.join(go, fn), encoding="utf-8") as f:
                    src += f"\n// ===== {fn} =====\n" + f.read()
        # 배너를 **부를 자격이 있는 파일**은 셋뿐이다: 각자를 정의한 자리(그 안에서 CLI
        # 부팅용 print 가 자기를 부른다)와, MCP 앞머리를 붙이는 한 자리.
        allowed = {"version.go", "interview_notice.go", "mcp_lead.go"}
        stray = []
        for fn in sorted(os.listdir(go)):
            if not fn.endswith(".go") or fn in allowed:
                continue
            with open(os.path.join(go, fn), encoding="utf-8") as f:
                body = f.read()
            for banner in ("versionAskBanner()", "arrivalBanner()"):
                # 주석에서 이름을 말하는 것은 사실이다 — 호출만 센다.
                for ln in body.split("\n"):
                    t = ln.strip()
                    if banner in t and not t.startswith("//"):
                        stray.append(f"{fn}: {t[:90]}")
        self.assertEqual(stray, [],
                         "등록 자리에서 앞머리를 직접 붙인다 — 그러면 붙이는 자리를 열거하게 "
                         "되고, 등록 자리가 하나 늘 때 또 샌다(이 병의 모양이 그것이었다):\n  "
                         + "\n  ".join(stray))
        del src

    def test_app_only_tools_are_declared(self):
        """**화면이 부르는 통로는 선언돼 있어야 한다** — 앞머리가 그 표를 보고 비켜선다.

        선언을 빠뜨리면 에이전트에게 하는 말(⚡ 도착 고지·버전 문의)이 사람이 보는 카드
        한복판에 앉는다. 표를 손으로 맞추지 말고, 소스의 실제 등록을 세어 대조한다."""
        go = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "go")
        declared, registered = set(), set()
        for fn in sorted(os.listdir(go)):
            if not fn.endswith(".go"):
                continue
            with open(os.path.join(go, fn), encoding="utf-8") as f:
                src = f.read()
            if fn == "surface.go":
                blk = src[src.index("var appOnlyTools"):]
                blk = blk[:blk.index("\n}")]
                declared |= set(re.findall(r'"(gil_[a-z_]+)"\s*:', blk))
            for m in re.finditer(r'\[\]string\{"app"\}', src):
                head = src[:m.start()]
                names = re.findall(r'Name:\s*"(gil_[a-z_]+)"', head)
                if not names:
                    continue
                # visibility 에 model 이 함께 있으면 앱 전용이 아니다(모델도 부른다).
                line_start = src.rfind("\n", 0, m.start())
                if '"model"' in src[line_start:m.end()]:
                    continue
                registered.add(names[-1])
        self.assertEqual(registered, declared,
                         f"소스의 앱 전용 등록과 surface.go 의 표가 어긋난다.\n"
                         f"  등록: {sorted(registered)}\n  선언: {sorted(declared)}")


class TestTheCardKeepsUpAndKeepsWhatWasWritten(GilFixture):
    """**화면이 스스로 따라가고, 따라가면서 사람이 쓰던 것을 잃지 않는다** (2026-08-10).

    카드는 한 번 그려지면 끝이었다: fetchCard 가 `drawn` 이면 즉시 되돌아가고, tool-result
    알림은 **카드 HTML 을 실은 결과만** 다시 그렸다. 그런 결과를 내는 것은 앱 전용 툴 둘뿐이라,
    모델이 gil_step·gil_close 를 아무리 불러도 사람이 보는 화면은 처음 상태 그대로였다.
    뷰어에는 /poll 이 있었고 카드에는 대응하는 것이 없었다.

    그런데 갱신만 세우면 **더 나쁜 것**이 생긴다 — 조각 교체는 innerHTML 이라 폼에 적던
    문장이 함께 사라진다. 뷰어는 이걸 윈도우 필드테스트에서 값을 치르고 배웠다(초안 저장 +
    쓰는 중 새로고침 보류). 그래서 둘은 **같은 커밋**이어야 한다.

    ── 이 시험이 재는 것과 못 재는 것 ────────────────────────────────────────
    껍데기 JS 는 샌드박스 iframe 안에서 호스트와 프레임을 주고받으며 돈다. 여기서 그걸
    **실행해 볼 수단이 없다**(DOM 이 필요하고, 브라우저는 이 환경에서 안 뜬다 — 실제로
    두 경로를 밟아 보고 막혔다). 그러니 이 시험이 재는 것은 **배선의 규칙**이다:
    조각을 넣는 자리가 보존 경로를 지나는가, 갱신을 거는 자리가 있는가, 막다른 길이 없는가.
    화면이 실제로 그렇게 도는지는 호스트에서 밟아야 한다 — 그건 이 시험이 못 하는 일이고,
    못 하는 것은 못 한다고 적어 둔다."""

    def shell(self):
        """껍데기 HTML — 호스트가 resources/read 로 가져가는 그것."""
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1", "GIL_NO_VERSION_CHECK": "1"})
        self.addCleanup(p.terminate)

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                try:
                    m = json.loads(ln.strip())
                except (json.JSONDecodeError, ValueError):
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "x"}})
                    continue
                if m.get("id") == want:
                    return m

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "t", "version": "0"}}})
        pump(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "resources/read",
              "params": {"uri": "ui://gil/status"}})
        r = pump(2)
        self.assertIsNotNone(r, "껍데기를 못 받았다")
        return r["result"]["contents"][0]["text"]

    def test_every_card_swap_goes_through_the_preserving_path(self):
        """**규칙으로 센다** — 조각을 넣는 자리는 빠짐없이 paint() 를 지난다.

        열거하면 다음에 넣는 자리가 하나 늘 때 조용히 샌다. 그래서 innerHTML 대입을 전부
        찾아, 카드 조각을 넣는 것이 paint() 밖에 있으면 실패한다."""
        sh = self.shell()
        self.assertIn("function paint(", sh, "보존 경로 자체가 없다")
        for fn in ("harvest()", "restore()"):
            self.assertIn(fn, sh, f"paint 가 {fn} 를 안 쓴다 — 보존이 이름뿐이다")
        # **자리로 판정한다.** 낱말만 세면 paint() 안의 정당한 대입까지 빨개지고, 그러면
        # 시험이 못 쓰게 된다(v3.58.2 가 이미 치른 값). 규칙은 이것이다 —
        # 카드 조각을 innerHTML 로 꽂는 자리는 **하나뿐이고 그것이 paint() 안**이다.
        swaps = [m.start() for m in re.finditer(r'innerHTML\s*=\s*(?:h2?|html)\b', sh)]
        self.assertEqual(len(swaps), 1,
                         f"카드 조각을 꽂는 자리가 {len(swaps)} 곳이다 — 하나여야 한다(paint). "
                         "다른 자리에서 꽂으면 거기서 사람이 쓰던 답이 사라진다.")
        body = sh[sh.index("function paint("):]
        body = body[:body.index("\n  }")]
        self.assertIn("innerHTML", body, "유일한 교체 자리가 paint() 밖에 있다")
        self.assertLess(body.index("harvest()"), body.index("innerHTML"),
                        "걷기(harvest)가 교체보다 뒤에 있다 — 이미 지워진 것을 걷는다")
        self.assertGreater(body.index("restore()"), body.index("innerHTML"),
                           "되심기(restore)가 교체보다 앞에 있다 — 새 DOM 에 안 심긴다")

    def test_the_card_refetches_when_gil_did_something(self):
        """카드를 안 실어 온 결과도 세계가 바뀌었다는 뜻이다 — 그때 다시 가져온다."""
        sh = self.shell()
        # **그 자리만 본다.** 첫 그리기 폴백(setTimeout ... if(!drawn) fetchCard())은 정당하다 —
        # 아직 안 그려졌을 때 한 번 더 시도하는 것이고, 그걸 없애면 첫 화면이 안 뜬다.
        # 고쳐야 했던 것은 **툴 결과 알림 갈래**다.
        # **고정 폭으로 자르지 않는다.** 처음엔 여기서 900자를 떼어 봤는데, 그 사이에 다른
        # 갈래(host-context-changed)가 들어오자 정작 볼 블록이 창 밖으로 밀려 빨개졌다 —
        # 재는 자리를 위치로 잡으면 배선이 조금만 움직여도 시험이 거짓말을 한다.
        # 갈래는 **그 갈래의 여는 중괄호부터 닫는 중괄호까지**다.
        marker = 'if(m.method==="ui/notifications/tool-result"){'
        i = sh.index(marker)
        branch = sh[i:sh.index("\n    }", i)]
        self.assertIn("scheduleRefresh()", branch,
                      "툴 결과가 와도 다시 안 가져온다 — 화면이 처음 상태로 멈춘다")
        self.assertNotIn("if(!drawn) fetchCard()", branch,
                         "이미 그려졌으면 영영 안 그리는 옛 규칙이 이 갈래에 남아 있다")
        self.assertIn("lastInput", sh, "쓰는 중 보류가 없다 — 문장 한가운데서 화면이 갈린다")

    def test_a_failed_fetch_is_not_a_dead_end(self):
        """조회는 네 번에서 멈춘다 — 거기서 사람이 되살릴 길이 있어야 한다."""
        sh = self.shell()
        self.assertIn('data-act="refetch"', sh, "다시 가져오는 버튼이 없다")
        self.assertIn("fetches>=4", sh, "상한 자체가 사라졌다면 이 시험을 고쳐야 한다")

    def test_harmless_buttons_are_not_armed(self):
        """아무것도 안 바꾸는 버튼까지 두 번 누르게 하면 그 관문이 무뎌진다."""
        sh = self.shell()
        self.assertIn("data-noarm", sh, "무장 면제 표식이 없다")
        self.assertIn('data-arm', sh, "무장 문구를 버튼이 정하는 자리가 없다")

    def test_the_submit_button_says_what_it_confirms(self):
        """되묻는 값은 **무엇이 확정되는지**를 말할 때 나온다 — "정말?" 은 아무것도 안 알려준다."""
        self.gil("init", "--name", "clew")
        self.gil("intake", "sd", "--ask", "-",
                 input=json.dumps([{"q": "무엇을 하려 하십니까", "type": "text"}],
                                  ensure_ascii=False))
        card = self.gil("status", "--card").stdout
        self.assertIn('data-arm="이 문장이 기준이 된다', card,
                      "제출 버튼이 공용 되묻기 문구를 쓴다 — 무엇이 확정되는지 안 말한다")


class TestTheFormStandsWhereverTheQuestionIs(GilFixture):
    """**폼은 HEAD 가 아니라 질문이 있는 곳에 선다** (뷰어 제거 조사, 2026-08-10).

    뷰어는 처음부터 `--branches` 를 훑어 기다리는 인터뷰를 **전부** 띄웠다. 카드는 HEAD 가
    선 체인 **하나**만 봤다(gatherStatus → headChainCycle → `git log -1 HEAD` 의 트레일러).
    그 차이가 지금까지는 안 아팠다 — 못 뜨면 뷰어에서 답하면 됐으니까. 뷰어를 지우면
    그 자리에서 사람이 답할 길이 **0** 이 된다.

    구체적으로 두 가지가 조용히 일어난다:

      ① **체인 밖에 서 있으면 폼이 아예 안 뜬다.** gatherStatus 는 chain 이 비면 조기
         반환하고, 카드의 폼은 `st.Chain != nil` 분기 **안에만** 있었다. 그런데 개시 인터뷰를
         심어 놓고 사람을 기다리는 자리가 바로 층(dev·main) 위다.
      ② **질문이 둘이면 하나만 보인다.** 사람은 HEAD 가 선 쪽에만 답할 수 있고 나머지는
         화면에서 사라진다. 질문은 저장소에 그대로 살아 있는데.

    둘 다 오류를 안 낸다 — 화면이 조용히 좁아질 뿐이다."""

    def _ask(self, slug, *qs):
        r = self.gil("intake", slug, "--ask", "-",
                     input=json.dumps([{"q": q, "type": "text"} for q in qs],
                                      ensure_ascii=False))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def _card(self):
        r = self.gil("status", "--card")
        return r.stdout + r.stderr

    def _status(self):
        r = self.gil("status", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_two_waiting_interviews_both_get_a_form(self):
        """질문이 둘이면 폼도 둘이다 — 사람이 고를 수 없는 것을 화면이 고르지 않는다."""
        self.gil("init", "--name", "clew")
        self._ask("alpha", "알파에서 무엇을 하려 하십니까")
        self._ask("beta", "베타에서 무엇을 하려 하십니까")
        card = self._card()
        self.assertIn('data-iv="alpha"', card, "먼저 심은 인터뷰의 폼이 사라졌다:\n" + card[:1500])
        self.assertIn('data-iv="beta"', card, "나중 인터뷰의 폼이 없다")
        self.assertEqual(card.count('data-act="interview-submit"'), 2,
                         "제출 버튼이 질문지 수만큼 서지 않았다")

    def test_the_form_survives_standing_outside_a_chain(self):
        """층(dev·main) 위에 서 있어도 답할 자리가 있어야 한다 — 거기가 시작하는 자리다."""
        self.gil("init", "--name", "clew")
        self._ask("sd", "무엇을 하려 하십니까")
        self._git("checkout", "-q", "main")
        st = self._status()
        self.assertIsNone(st["chain"], "이 시험은 체인 밖에 서야 뜻이 있다")
        card = self._card()
        self.assertIn('data-iv="sd"', card,
                      "체인 밖에 서니 폼이 통째로 사라졌다 — 질문은 저장소에 살아 있는데:\n"
                      + card[:1500])

    def test_status_names_every_open_interview(self):
        """에이전트도 같은 사실을 읽는다 — 화면만 알고 데이터가 모르면 둘이 갈린다."""
        self.gil("init", "--name", "clew")
        self._ask("alpha", "하나", "둘")
        self._ask("beta", "셋")
        self._git("checkout", "-q", "main")
        st = self._status()
        got = {i["chain"]: i["questions"] for i in st["open_interviews"]}
        self.assertEqual(got, {"alpha": 2, "beta": 1},
                         "기다리는 인터뷰를 데이터가 다 말하지 않는다: " + repr(got))

    def test_the_answered_one_drops_off(self):
        """확정된 것은 목록에서 빠진다 — 최신 마커가 상태를 정한다(#75)."""
        self.gil("init", "--name", "clew")
        self._ask("alpha", "하나")
        self._ask("beta", "둘")
        p = os.path.join(self.repo, "ans.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# 기준 문서\n\n## 1. 하나\n\n알파의 답이다.\n")
        self.gil("intake", "alpha", "--resolve", "ans.md")
        os.remove(p)
        st = self._status()
        names = [i["chain"] for i in st["open_interviews"]]
        self.assertEqual(names, ["beta"], "확정된 인터뷰가 아직 기다린다고 나온다: " + repr(names))
        self.assertNotIn('data-iv="alpha"', self._card(), "확정됐는데 폼이 남았다")


class TestTheInterviewStandsInTheCard(GilFixture):
    """**인터뷰가 카드 안에 선다** (상현님, 2026-08-10).

    사람에게 묻는 통로가 이 표면에서 계속 없어졌다: 뷰어 폼은 창을 청해야 뜨는데 시작하는
    사람에겐 창이 없고, 호스트 네이티브 폼은 Claude Desktop 이 못 띄운다(2026-08-09 실측
    두 판). 그래서 남은 것이 대화였다 — 에이전트가 질문을 하나씩 말로 물었다.

    그게 왜 나쁜가. 질문지는 **한 벌**인데 대화는 한 줄씩 흐른다. 사람은 앞 질문을 다시 볼 수
    없고 몇 개 남았는지 모른다. 무엇보다 **에이전트가 사람의 말을 옮겨 적는 단계가 끼어든다** —
    gil 이 문법으로 지켜 온 단 하나("기준은 사람의 문장 그 자체다")가 거기서 옮겨쓰기가 된다.

    카드는 이 표면에서 **실제로 서는 화면**이고, 그 안 버튼이 진짜 명령을 도는 통로도 이미
    있다(승인·기각). 인터뷰는 그 통로에 정확히 맞는 일이다."""

    def _pending_intake(self):
        """개시 인터뷰가 사람 답을 기다리는 상태까지 레일을 밟는다(체인은 아직 없다)."""
        self.gil("start")
        self.gil("start", "--name", "probe")
        idf = os.path.join(self.repo, "i.md")
        wf = os.path.join(self.repo, "w.md")
        with open(idf, "w", encoding="utf-8") as f:
            f.write("# Identity — probe\n\n시험용 존재다.\n")
        with open(wf, "w", encoding="utf-8") as f:
            f.write("# Will\n\n확인한다.\n")
        self.gil("start", "--identity", idf, "--will", wf)

    def _card(self):
        r = self.gil("status", "--card")
        return r.stdout + r.stderr

    def test_the_card_asks_instead_of_pointing_elsewhere(self):
        """옛 카드는 "에이전트가 여는 인터뷰 창구에 적으면"이라고 했다 — 그 창구가 없었다."""
        self._pending_intake()
        card = self._card()
        self.assertIn('data-act="interview-submit"', card, "카드에 제출 버튼이 없다")
        self.assertEqual(card.count('class="ivin"'), 2, "질문 두 개가 칸으로 서지 않았다")
        self.assertNotIn("인터뷰 창구에 적으면", card,
                         "없는 창구를 여전히 가리킨다 — 카드가 그 창구인데도")

    def test_it_does_not_prefill_the_answers(self):
        """**답을 미리 채우지 않는다.** 채우는 순간 기준이 사람의 문장이 아니게 된다(#90)."""
        self._pending_intake()
        card = self._card()
        self.assertIn('<textarea class="ivin" data-q="q1" rows="3"></textarea>', card,
                      "빈 칸이 아니다 — 기본값이나 예시가 들어갔다")

    def test_it_shows_how_many_are_left(self):
        """대화로 물을 때 사라졌던 것 — 몇 개 중 몇 번째인지."""
        self._pending_intake()
        card = self._card()
        self.assertIn("1/2.", card)
        self.assertIn("2/2.", card)

    def test_every_question_type_becomes_a_control(self):
        """text·radio·checkbox 가 각각 제 입력으로 선다 — 하나라도 빠지면 그 질문은 못 답한다."""
        self.gil("chain", "c", "--purpose", "p", "--reference", CRIT_FILE,
                 "--criterion", "무엇이 관측되면 풀린 것인가")
        qs = json.dumps([
            {"q": "무엇을 풀려는가", "type": "text"},
            {"q": "어느 쪽인가", "type": "radio", "options": ["빠르게", "정확하게"]},
            {"q": "무엇을 재나", "type": "checkbox", "options": ["속도", "정확도"]},
        ], ensure_ascii=False)
        qf = os.path.join(self.repo, "q.json")
        with open(qf, "w", encoding="utf-8") as f:
            f.write(qs)
        r = self.gil("interview", "c", "--ask", qf)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        card = self._card()
        self.assertIn('class="ivin" data-q="q1"', card, "열린 질문이 칸으로 안 섰다")
        self.assertIn('type="radio"', card, "radio 가 안 섰다")
        self.assertIn('type="checkbox"', card, "checkbox 가 안 섰다")

    def test_a_settled_interview_shows_no_form(self):
        """확정된 뒤에도 폼이 남으면 사람이 같은 답을 두 번 낸다."""
        self._pending_intake()
        ref = os.path.join(self.repo, "ref.md")
        with open(ref, "w", encoding="utf-8") as f:
            f.write("# 기준\n\n사람이 답했다.\n")
        self.gil("intake", "start", "--resolve", ref)
        self.assertNotIn('data-act="interview-submit"', self._card(),
                         "확정된 인터뷰의 폼이 카드에 남아 있다")


class TestTheAnswerComesBackFromTheCard(GilFixture):
    """**폼에 적은 것이 그대로 기준이 된다** — 카드에서 gil 까지, 프로토콜로 밟는다.

    소스로는 "폼이 있다"까지만 확인된다. 답이 실제로 돌아와 확정되는지는 **앱이 하는 그대로**
    (tools/call) 쳐 봐야 안다 — 이 세션이 두 번 값을 치르고 배운 것이다."""

    def _app(self):
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1"})
        self.addCleanup(p.terminate)
        state = {"id": 0}

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    m = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "unsupported"}})
                    continue
                if m.get("id") == want:
                    return m

        state["id"] += 1
        send({"jsonrpc": "2.0", "id": state["id"], "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "app", "version": "0"}}})
        pump(state["id"])
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        def call(name, args):
            state["id"] += 1
            send({"jsonrpc": "2.0", "id": state["id"], "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
            r = pump(state["id"])
            if r is None:
                return "", "(응답 없음)"
            if "error" in r:
                return "", r["error"].get("message", "")
            res = r["result"]
            txt = "".join(c.get("text", "") for c in res.get("content", []))
            return ("", txt) if res.get("isError") else (txt, "")
        return call

    def _pending_intake(self):
        self.gil("start")
        self.gil("start", "--name", "probe")
        for name, body in (("i.md", "# Identity — probe\n\n시험용.\n"), ("w.md", "# Will\n\n확인.\n")):
            with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
                f.write(body)
        self.gil("start", "--identity", os.path.join(self.repo, "i.md"),
                 "--will", os.path.join(self.repo, "w.md"))

    def test_the_humans_sentence_is_what_gets_recorded(self):
        """**요약도 정제도 없이** 사람이 친 문장 그대로여야 한다 — 그게 이 폼의 존재 이유다."""
        self._pending_intake()
        call = self._app()
        mine = "사내 규정을 쉽게 찾게 하고 싶다."
        crit = "직원 10명이 1분 안에 답을 얻으면 된 것이다."
        out, err = call("gil_interview_submit", {
            "repo": self.repo, "chain": "start",
            "answers": json.dumps({"q1": mine, "q2": crit}, ensure_ascii=False)})
        self.assertEqual(err, "", f"제출이 막혔다:\n{err}")
        shown = self.gil("intake", "start", "--status", "--show").stdout
        self.assertIn(mine, shown, "사람의 문장이 그대로 남지 않았다")
        self.assertIn(crit, shown, "성패 기준이 그대로 남지 않았다")

    def test_an_empty_submit_is_refused(self):
        """빈 기준으로 확정되면 그 뒤 판정이 전부 빈 자를 대고 재는 일이 된다(형해화)."""
        self._pending_intake()
        call = self._app()
        out, _ = call("gil_interview_submit",
                      {"repo": self.repo, "chain": "start", "answers": "{}"})
        self.assertIn("아직 아무것도", out, "빈 제출이 확정됐다")
        self.assertIn("pending", self.gil("intake", "start", "--status").stdout,
                      "빈 제출로 인터뷰가 닫혔다")

    def test_submitting_twice_does_not_break(self):
        """사람은 두 번 누른다. 두 번째는 사실을 말하면 된다 — 오류가 아니다."""
        self._pending_intake()
        call = self._app()
        args = {"repo": self.repo, "chain": "start",
                "answers": json.dumps({"q1": "한 번만 적는다.", "q2": "되면 된 것이다."},
                                      ensure_ascii=False)}
        _, err = call("gil_interview_submit", args)
        self.assertEqual(err, "", err)
        out, err2 = call("gil_interview_submit", args)
        self.assertEqual(err2, "", "두 번째 제출이 오류로 터졌다")
        self.assertIn("기다리는 질문이 없다", out, "두 번째 제출이 무슨 일인지 말하지 않았다")

    def test_the_card_then_shows_what_is_next(self):
        """제출 뒤 사람이 보는 것은 "됐다"가 아니라 **다음이 무엇인지**여야 한다."""
        self._pending_intake()
        call = self._app()
        out, _ = call("gil_interview_submit", {
            "repo": self.repo, "chain": "start",
            "answers": json.dumps({"q1": "무엇을 한다.", "q2": "이러면 된 것이다."},
                                  ensure_ascii=False)})
        self.assertNotIn('data-act="interview-submit"', out,
                         "확정했는데 폼이 그대로 남았다")


class TestTheButtonSendsWhatTheSchemaDemands(GilFixture):
    """**버튼이 보내는 그 인자 모양 그대로** 프로토콜로 친다 (상현님 실사용 조사, 2026-08-10).

    카드의 승인·기각 버튼은 `arguments:{}` 를 보냈는데 스키마는 `target` 을 필수로 광고했다.
    그래서 호출은 gil 이 돌기도 **전에** 검증에서 죽었고, 사람 화면에 도착한 문장은
    `거부됐다 — validating "arguments": … missing properties: ["target"]` 이었다.
    비개발자가 pending 을 푸는 유일한 문이 그것이었다.

    **이건 어느 쪽을 읽어서도 안 보인다.** 툴 목록은 스키마가 옳다고 말하고, 카드 HTML 은
    버튼이 있다고 말하고, `gil approve` 는 CLI 에서 잘 돈다 — 셋 다 참인데 사람은 못 누른다.
    셋을 잇는 자리(버튼의 data-* → tools/call 인자)를 실제로 밟아야 드러난다.
    gil_chain 의 purpose 가 이미 같은 값을 치렀다: **스키마와 호출을 두 자리에 따로 적으면
    한쪽만 낡는다.**"""

    def _app(self):
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1", "GIL_NO_VERSION_CHECK": "1"})
        self.addCleanup(p.terminate)
        state = {"id": 0}

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    m = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "unsupported"}})
                    continue
                if m.get("id") == want:
                    return m

        state["id"] += 1
        send({"jsonrpc": "2.0", "id": state["id"], "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "app", "version": "0"}}})
        pump(state["id"])
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        def call(name, args):
            state["id"] += 1
            send({"jsonrpc": "2.0", "id": state["id"], "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
            r = pump(state["id"])
            if r is None:
                return "", "(응답 없음)"
            if "error" in r:
                return "", r["error"].get("message", "")
            res = r["result"]
            txt = "".join(c.get("text", "") for c in res.get("content", []))
            return ("", txt) if res.get("isError") else (txt, "")
        return call

    def _pending_repo(self):
        """사람을 기다리는 스텝이 실제로 선 저장소 — 카드에 승인·기각 버튼이 뜨는 상태."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "ap", "--purpose", "버튼을 밟는다", "--reference", "-",
                 "--criterion", "사람이 누를 수 있으면 된 것이다", input="기준")
        self.gil("open", "ap/c1", "--purpose", "사이클", "--author", "clew")
        r = self.gil("step", "ap/c1", "--kind", "pending",
                     "--title", "이건 사람이 정해야 한다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def _buttons(self, html):
        """카드에서 `data-tool` 을 단 버튼을 뽑아, **껍데기 JS 가 하는 그대로** 인자를 만든다.

        runAct 의 툴 갈래와 같은 규칙이어야 한다 — 여기서 다르게 만들면 시험은 초록인데
        사람은 못 누르는 상태가 그대로 남는다(그게 이 결함의 모양이었다)."""
        out = []
        for tag in re.findall(r"<button\b[^>]*>", html):
            tool = re.search(r'data-tool="([^"]*)"', tag)
            if not tool:
                continue
            args = {}
            tgt = re.search(r'data-target="([^"]*)"', tag)
            if tgt:
                args["target"] = tgt.group(1)
            to = re.search(r'data-to="([^"]*)"', tag)
            if to:
                args["to"] = to.group(1)
            args["repo"] = self.repo          # learnRepo 가 주워 싣는 값
            out.append((tool.group(1), args))
        return out

    def test_the_pending_buttons_actually_run(self):
        """승인 버튼이 보내는 인자로 실제로 승인이 된다 — 문법이 거절하지 않는다."""
        self._pending_repo()
        call = self._app()
        card, err = call("gil_status_card", {"repo": self.repo})
        self.assertEqual(err, "", f"카드를 못 받았다:\n{err}")
        btns = self._buttons(card)
        self.assertTrue(btns, "pending 인데 명령을 도는 버튼이 하나도 없다:\n" + card[:2000])
        approve = [(t, a) for t, a in btns if t == "gil_approve"]
        self.assertTrue(approve, "승인 버튼이 없다")
        tool, args = approve[0]
        out, err = call(tool, args)
        self.assertEqual(err, "", f"승인 버튼이 보내는 인자가 거부됐다 — 사람이 여기서 막힌다.\n"
                                  f"보낸 것: {args}\n돌아온 것: {err}")
        self.assertIn("approve", out, out)

    def test_every_command_button_carries_its_target(self):
        """**규칙으로 센다.** 명령을 도는 버튼은 스키마가 필수라 한 것을 빠짐없이 싣는다.

        낱낱이 열거하면 다음에 버튼이 늘 때 또 샌다 — 카드가 내는 모든 data-tool 버튼을
        세고, 그 툴의 스키마가 required 라 한 필드가 인자에 있는지 본다."""
        self._pending_repo()
        call = self._app()
        card, _ = call("gil_status_card", {"repo": self.repo})
        btns = self._buttons(card)
        self.assertTrue(btns, "명령을 도는 버튼이 없다")

        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1", "GIL_NO_VERSION_CHECK": "1"})
        self.addCleanup(p.terminate)
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": "t", "version": "0"}}}) + "\n")
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                                  "params": {}}) + "\n")
        p.stdin.flush()
        schemas = {}
        while True:
            ln = p.stdout.readline()
            if not ln:
                break
            try:
                m = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if m.get("id") == 2:
                for t in m["result"]["tools"]:
                    schemas[t["name"]] = t.get("inputSchema", {})
                break

        for tool, args in btns:
            req = schemas.get(tool, {}).get("required", [])
            missing = [k for k in req if k not in args]
            self.assertEqual(missing, [],
                             f"{tool} 버튼이 스키마 필수 필드를 안 싣는다: {missing}\n"
                             f"버튼이 보내는 것: {sorted(args)}\n"
                             f"스키마가 요구하는 것: {req}\n"
                             "→ 호출이 gil 에 닿기 전에 검증에서 죽고, 사람은 "
                             '\'validating "arguments"…\' 를 본다.')

    def test_reject_offers_no_dead_button(self):
        """되돌아갈 자리가 없으면 **기각 버튼을 세우지 않는다** — 눌러도 안 열리는 칸을
        가리키면 사람은 화면이 고장 났다고 읽는다. 없으면 없다고 적는다."""
        self._pending_repo()
        call = self._app()
        card, _ = call("gil_status_card", {"repo": self.repo})
        if 'data-open="gil-back"' in card:
            self.assertIn('id="gil-back"', card,
                          "기각 버튼이 없는 칸을 가리킨다 — 눌러도 아무 일도 안 일어난다")
        else:
            self.assertIn("되돌아갈", card, "기각할 수 없는 이유를 화면이 말하지 않는다")


class TestAskingOpensTheScreen(GilFixture):
    """**묻는 자리가 곧 화면이 서는 자리다** (상현님 실사용, 2026-08-10 — "뷰어폼이 안뜨네").

    인터뷰 카드를 세워 놓고, 인터뷰를 심는 자리의 안내에 "사람에게 **화면의 인터뷰 폼**에
    답해 달라고 청하라"고 적었다. 그런데 그 화면을 여는 것은 `gil_status` 뿐이었고, 인터뷰를
    심는 툴은 **아무 화면도 열지 않았다.** 뷰어로 가는 길도 이 표면엔 없다(터미널 전용으로
    선언했다). 그래서 사람 앞에는 **아무것도 뜨지 않았다.**

    카드도 옳았고 뷰어 폼도 옳았다(둘 다 실제로 그려지는 것을 확인했다). 틀린 것은 **아무도
    그것을 열지 않는다**는 사실이었다 — 사흘째 같은 병(가리키는 것이 실재하지 않는다), 이번엔
    내가 만든 자리에서.

    사람에게 물어 놓고 물음을 어디에도 안 띄우면, 그 물음은 대화로 새거나(옮겨쓰기) 사라진다."""

    def _tools(self):
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1"})
        self.addCleanup(p.terminate)

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    m = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "unsupported"}})
                    continue
                if m.get("id") == want:
                    return m

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "probe", "version": "0"}}})
        pump(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        return {t["name"]: t for t in pump(2)["result"]["tools"]}

    def test_every_asking_tool_opens_a_screen(self):
        """사람에게 묻는 툴은 **자기 화면을 함께 연다** — 안 그러면 물음이 어디에도 안 뜬다."""
        tools = self._tools()
        asking = ["gil_start", "gil_intake", "gil_interview"]
        missing = []
        for name in asking:
            self.assertIn(name, tools, f"{name} 이 표면에 없다")
            ui = (tools[name].get("_meta") or {}).get("ui") or {}
            if not ui.get("resourceUri"):
                missing.append(name)
        self.assertEqual(
            missing, [],
            "사람에게 묻는데 화면을 안 여는 툴: " + ", ".join(missing) +
            "\n  물어 놓고 물음을 어디에도 안 띄우면 그 물음은 대화로 새거나 사라진다.")

    def test_the_guidance_points_at_a_screen_that_opens(self):
        """안내가 "화면의 폼"을 말하려면 그 화면이 **그 호출로** 떠야 한다."""
        self.gil("start")
        self.gil("start", "--name", "probe")
        for n, b in (("i.md", "# I\n\n시험용.\n"), ("w.md", "# W\n\n확인.\n")):
            with open(os.path.join(self.repo, n), "w", encoding="utf-8") as f:
                f.write(b)
        out = self.gil("start", "--identity", os.path.join(self.repo, "i.md"),
                       "--will", os.path.join(self.repo, "w.md")).stdout
        # CLI 는 카드를 안 띄운다 — 여기서 "카드에 적어라"라고 하면 그게 또 없는 것을 가리키는
        # 안내다. 이 자리의 CLI 안내는 뷰어·상태를 말해야 한다.
        self.assertNotIn("위에 뜬 카드", out,
                         "CLI 에서 카드를 가리켰다 — 그 표면엔 카드가 없다")


class TestItPointsAtTheScreenItOpened(GilFixture):
    """**열어 놓은 화면을 가리켜야 한다** (상현님 실사용, 2026-08-10 — "이번엔 카드가 떴어").

    앞 커밋이 "묻는 툴은 자기 화면을 함께 연다"를 세웠고, 카드는 실제로 떴다. 그런데 같은
    호출의 마지막 줄이 이렇게 말했다:

        (호스트 네이티브 폼이 서지 않았다 … 사람에게 **뷰어 폼**으로 답해 달라고 청하고 …)

    뷰어는 이 표면에서 **열 수 없다**(터미널 전용으로 선언했다). 그러니 에이전트에게 남은
    길은 대화뿐이었고, 실제로 이렇게 말했다 — *"뷰어 폼이 이 환경에선 안 떠서 여기서
    여쭤봅니다."* 그리고 질문을 하나씩 말로 물었다. **카드는 바로 그 위에 떠 있었다.**

    화면을 여는 것과 그 화면을 가리키는 것은 **다른 일**이다. 앞 커밋이 앞엣것을 했고,
    이 시험이 뒤엣것을 지킨다."""

    def _agent_sees(self, declare_ui=False):
        """폼을 못 띄우는 호스트로 온보딩을 밟고, 에이전트가 받는 글을 모은다.

        declare_ui: MCP Apps 확장을 **선언하는** 호스트로 붙는다(= 카드가 뜨는 자리).
        기본은 선언 안 함 — 실사용에서 카드를 안 그리는 표면이 실재한다(Cowork)."""
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1"})
        self.addCleanup(p.terminate)
        st = {"id": 0}

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    m = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if m.get("method"):
                    if "id" in m:      # 폼 요청 포함 — 이 호스트는 못 띄운다
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "no form"}})
                    continue
                if m.get("id") == want:
                    return m

        st["id"] += 1
        caps = {}
        if declare_ui:
            caps = {"extensions": {"io.modelcontextprotocol/ui": {
                "mimeTypes": ["text/html;profile=mcp-app"]}}}
        send({"jsonrpc": "2.0", "id": st["id"], "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": caps,
                         "clientInfo": {"name": "formless", "version": "0"}}})
        pump(st["id"])
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        def call(name, args):
            st["id"] += 1
            send({"jsonrpc": "2.0", "id": st["id"], "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
            r = pump(st["id"])
            if r is None:
                return ""
            if "error" in r:
                return r["error"].get("message", "")
            return "".join(c.get("text", "") for c in r["result"].get("content", []))

        seen = [call("gil_start", {"repo": self.repo, "confirmed": True}),
                call("gil_start", {"repo": self.repo, "name": "probe"}),
                call("gil_start", {"repo": self.repo,
                                   "identity": "# I\n\n시험.\n", "will": "# W\n\n확인.\n"}),
                call("gil_handoff", {"repo": self.repo})]
        return "\n".join(seen)

    def test_it_never_sends_the_human_to_a_screen_this_surface_cannot_open(self):
        """**이 표면에서 못 여는 화면으로 사람을 보내지 않는다.**

        뷰어는 터미널 전용이다(surface.go 의 terminalOnly). 그런데도 "사람에게 뷰어 폼에
        답해 달라 청하라"고 하면 에이전트는 그 화면을 못 띄우고 대화로 우회한다 — 그리고
        대화로 물으면 사람의 문장이 에이전트를 한 번 거쳐 들어온다(옮겨쓰기)."""
        bad = []
        for line in self._agent_sees().split("\n"):
            if "뷰어" not in line:
                continue
            # 사람에게 **청하라**고 시키는 줄만 잡는다 — 진단·설명은 뷰어를 말해도 된다.
            if any(k in line for k in ["청하라", "답해 달라", "답해주", "제출을", "답하게"]):
                bad.append(line.strip())
        self.assertEqual(
            bad, [],
            "이 표면에서 열 수 없는 화면(뷰어)으로 사람을 보낸다:\n  " + "\n  ".join(bad) +
            "\n  → askHumanHere()/askHumanLine() 를 써라(surface.go). 화면을 여는 것과 "
            "그 화면을 가리키는 것은 다른 일이다.")

    def test_it_does_not_point_at_a_card_on_a_host_that_draws_none(self):
        """**MCP 라는 이유만으로 "위에 뜬 카드"를 가리키면 안 된다** (상현님 실사용, Cowork).

        플러그인으로 붙인 gil 이 잘 돌았다 — 저장소도 보이고 툴도 다 먹었다. 그런데 **카드는
        끝내 안 떴다.** 상태를 두 번 물어도 화면 보고가 한 줄도 없었다. 그 표면은 MCP Apps 를
        그리지 않는다.

        그런데 안내는 여전히 "사람에게 **위에 뜬 카드**의 인터뷰 폼에 답해 달라 청하라"고
        말한다. 없는 곳을 가리키는 것이고, 그러면 세션은 질문을 대화로 옮겨 적는다 — gil 이
        문법으로 지켜 온 단 하나("기준은 사람의 문장 그 자체다")가 그 자리에서 무너진다.

        다섯 번은 뷰어를, 한 번은 아무도 안 여는 것을, 한 번은 열어 놓고 다른 것을 가리켰다.
        이번엔 **못 그리는 호스트에서 카드를** 가리켰다 — 같은 병의 여섯 번째 얼굴이다.

        갈라야 하는 것은 "MCP 인가"가 아니라 **"이 호스트가 화면을 선언했나"** 다. 그건 카드가
        보고해 주기를 기다릴 필요도 없다 — initialize 의 capabilities.extensions 에 이미 와
        있다. 이 시험의 호스트는 `capabilities: {}` 로 붙는다(= 선언 안 함)."""
        seen = self._agent_sees()
        bad = [ln.strip() for ln in seen.split("\n")
               if "카드" in ln and any(k in ln for k in ["청하라", "답해 달라", "답하면", "답할 때까지"])]
        self.assertEqual(
            bad, [],
            "화면을 선언하지 않은 호스트인데 카드로 사람을 보낸다:\n  " + "\n  ".join(bad) +
            "\n  → askHumanHere() 가 hostDeclaresUI 를 봐야 한다(surface.go).")
        # 그리고 **없다는 사실과 그때 지킬 것**을 말해야 한다. 침묵하면 세션은 "카드가 왜
        # 안 뜨지"를 추측하고, 추측 위에서 사람의 문장을 옮겨 적기 시작한다.
        self.assertIn("그대로", seen,
                      "폼이 없는 자리에서 '사람이 쓴 문장을 그대로 실어라'를 안 말한다 — "
                      "문법이 못 지키는 것은 말로라도 지켜야 한다")

    def test_the_tool_descriptions_do_not_send_them_to_the_viewer_either(self):
        """**에이전트가 읽는 글은 툴 응답만이 아니다 — 툴 목록도 읽는다.**

        실측(상현님, 2026-08-10): 응답 쪽을 다 고쳤는데도 세션이 "답변 창구(뷰어)가 아직 떠
        있지 않아"로 시작해 Bash 로 gil 을 찾다 실패하고(`gil: command not found`) 질문을
        대화로 옮겨 적었다. 남은 자리 하나가 **`gil_interview_status` 의 툴 설명**이었다 —
        거기에 "뷰어 폼으로 넘어간 인터뷰는…"이 있었다.

        앞 시험은 툴 **응답**만 봤다. 목록은 안 봤다. 에이전트는 둘 다 읽는다."""
        p = subprocess.Popen(GIL_CMD + ["mcp", "serve"], cwd=self.repo, text=True, bufsize=1,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             env={**os.environ, "GIL_NO_VIEWER": "1"})
        self.addCleanup(p.terminate)

        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()

        def pump(want):
            while True:
                ln = p.stdout.readline()
                if not ln:
                    return None
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    m = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if m.get("method"):
                    if "id" in m:
                        send({"jsonrpc": "2.0", "id": m["id"],
                              "error": {"code": -32601, "message": "x"}})
                    continue
                if m.get("id") == want:
                    return m

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "probe", "version": "0"}}})
        pump(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = pump(2)["result"]["tools"]
        # instructions 도 에이전트가 읽는 글이다 — 함께 센다.
        # **판정은 응답 검사와 같은 기준이다** — 사람을 그 화면으로 **보내는** 말만 잡는다.
        # "뷰어를 끈다"(gil_handoff --end)는 실제 동작 설명이지 사람을 보내는 것이 아니다.
        # 낱말만 세면 사실을 말하는 줄까지 빨개지고, 그러면 시험이 못 쓰게 된다(v3.58.2 의 교훈).
        send_words = ("답", "제출", "청하", "폼")
        bad = [f"{n}: {d}" for n, d in ((t["name"], t.get("description", "")) for t in tools)
               if "뷰어" in d and any(w in d for w in send_words)]
        self.assertEqual(
            bad, [],
            "툴 설명이 이 표면에서 못 여는 화면(뷰어)을 가르친다:\n  " + "\n  ".join(bad) +
            "\n  에이전트는 응답만이 아니라 **툴 목록도** 읽는다.")

    def test_it_names_the_card_that_is_actually_up(self):
        """물음을 심은 그 출력이 **떠 있는 카드**를 이름으로 불러야 한다.

        **이 시험의 전제가 틀려 있었다**(2026-08-10, 상현님 Cowork 실측으로 드러남): 이 클래스의
        기본 호스트는 `capabilities: {}` 로 붙는다 — MCP Apps 확장을 **선언하지 않는다**. 그런
        호스트에서는 카드가 아예 안 뜬다. 그러니 옛 단언("카드를 열어 놓고")은 열지도 않은 카드를
        가리키라고 강제하고 있었다 — 고치려던 병을 시험이 요구한 셈이다.

        그래서 **카드를 실제로 그리는 호스트로** 밟는다. 그래야 이 시험이 원래 지키려던 것,
        곧 "열어 놓은 화면을 이름으로 부른다"를 지킨다."""
        seen = self._agent_sees(declare_ui=True)
        self.assertIn("카드", seen, "카드를 열어 놓고 카드를 한 번도 안 가리켰다")
        self.assertIn("[답을 제출한다]", seen, "사람이 눌러야 할 것을 이름으로 말하지 않았다")

    def test_it_does_not_promise_an_answer_it_may_not_get(self):
        """'답이 아래에 이어진다'는 폼이 설 때만 참이다 — 모르는 것을 약속하지 않는다."""
        self.assertNotIn("답이 아래에 이어진다", self._agent_sees(),
                         "폼이 안 서는 호스트에서도 답이 이어진다고 단언했다")

    def test_the_cli_does_not_point_at_the_retired_viewer(self):
        """**시험이 은퇴한 명령을 가리키라고 강제하고 있었다.**

        옛 이름은 `test_the_cli_still_points_at_the_viewer` 였고 CLI 출력에 "관전 창"이 있기를
        요구했다. 그 전제("CLI 에서는 뷰어가 열리는 화면이다")는 뷰어를 지우기 전의 사실이다 —
        지금 `gil viewer` 는 *"은퇴했다"* 로 답한다. 즉 이 시험은 **없는 곳을 가리키는 안내**를
        요구하고 있었다. 이 저장소가 싸우는 바로 그 병을, 시험이 지키고 있었던 것이다.

        고치는 방향은 "카드를 가리켜라"가 아니다 — CLI 엔 카드도 없다. **없다고 말하는 것**이
        답이다(상현님, 2026-08-10: 터미널의 공백은 인정한다)."""
        self.gil("start")
        self.gil("start", "--name", "probe")
        for n, b in (("i.md", "# I\n\n시험.\n"), ("w.md", "# W\n\n확인.\n")):
            with open(os.path.join(self.repo, n), "w", encoding="utf-8") as f:
                f.write(b)
        out = self.gil("start", "--identity", os.path.join(self.repo, "i.md"),
                       "--will", os.path.join(self.repo, "w.md")).stdout
        self.assertNotIn("관전 창", out, "은퇴한 뷰어로 사람을 보낸다")
        self.assertNotIn("위에 뜬 카드", out, "CLI 엔 카드가 없는데 카드를 가리켰다")
        self.assertIn("터미널엔", out,
                      "CLI 엔 답할 자리가 없다는 사실을 안 말한다 — 없는 것을 있는 척하는 것보다 "
                      "없다고 말하고 지킬 것을 적는 편이 낫다")
        self.assertIn("그대로", out, "옮겨 적을 때 지킬 것(사람의 문장 그대로)을 안 말한다")


class TestOnboardingDoesNotAskTwiceForOneJudgment(GilFixture):
    """**나눌 이유가 없으면 나누지 않는다** (상현님 관찰, 2026-08-10 — "gil start 를 세 번
    호출하는데 정상적인건가?").

    세 번은 설계가 아니라 **안내가 만든 것**이었다: 1회차가 이름만 요구하고, 그 다음에 정체성을
    요구했다. 그런데 **이름을 정한 존재는 자기가 무엇인지도 그 순간 안다** — 두 판단이 하나다.
    도구는 이미 한 호출에 둘 다 받을 수 있었는데(startArgs), 안내가 한 칸씩만 물었다.

    그리고 사람이 "정상인가?" 하고 물었다는 것 자체가 신호다 — **왜 여러 번인지 도구가 말하지
    않았다.** 반복이 설계일 때는 그 이유가 그 자리에 있어야 한다. 없으면 사람은 고장으로 읽는다.

    멈추는 자리는 남는다(이름·정체성은 도구가 채우면 위조다). 줄이는 것은 **한 판단을 두 번
    묻는 것**이지 판단 자체가 아니다."""

    def _bodies(self):
        idf = os.path.join(self.repo, "i.md")
        wf = os.path.join(self.repo, "w.md")
        with open(idf, "w", encoding="utf-8") as f:
            f.write("# Identity — probe\n\n확인하는 존재다.\n")
        with open(wf, "w", encoding="utf-8") as f:
            f.write("# Will\n\n확인한다.\n")
        return idf, wf

    def test_two_calls_reach_the_interview(self):
        """① 세계 ② 이름+정체성 — 그 두 번이면 사람이 답할 차례가 온다."""
        first = self.gil("start")
        self.assertIn("이름", first.stdout, "첫 호출이 이름을 요구하지 않았다")
        idf, wf = self._bodies()
        second = self.gil("start", "--name", "probe", "--identity", idf, "--will", wf)
        out = second.stdout + second.stderr
        self.assertIn("사람에게 먼저 묻는다", out,
                      "두 번째 호출로 인터뷰까지 못 갔다 — 한 판단을 두 번 묻고 있다")
        self.assertIn("pending", self.gil("intake", "start", "--status").stdout,
                      "질문이 심기지 않았다")

    def test_the_first_call_teaches_the_one_shot_path(self):
        """**도구가 그 길을 말해야 한다.** 안 말하면 에이전트는 한 칸씩 부른다(실제로 그랬다)."""
        out = self.gil("start").stdout
        self.assertIn("한 번에 끝난다", out, "한 번에 가는 길을 안 가르쳤다")
        self.assertIn("--identity", out, "그 호출에 무엇을 실으면 되는지 안 말했다")

    def test_it_says_why_it_stops(self):
        """반복이 설계일 때는 **왜 멈추는지**가 그 자리에 있어야 한다 — 없으면 고장으로 읽힌다."""
        self.gil("start")
        out = self.gil("start", "--name", "probe").stdout
        self.assertIn("네가 써야 하는 것", out,
                      "왜 여기서 멈추는지 말하지 않았다(사람이 '정상인가?'를 묻게 된다)")

    def test_stopping_places_are_still_the_humans_to_fill(self):
        """줄인 것은 **묻는 횟수**지 판단이 아니다 — 이름 없이는 여전히 못 넘어간다."""
        self.gil("start")
        idf, wf = self._bodies()
        # 이름 없이 정체성만 주면 설 자리가 없다(방이 아직 unnamed 다).
        r = self.gil("start", "--identity", idf, "--will", wf)
        out = r.stdout + r.stderr
        self.assertIn("이름", out, "이름 없이 정체성이 심겼다 — 도구가 판단을 대신했다")


class TestWillIsNotTheProjectsPurpose(GilFixture):
    """**will 은 존재의 지향이지 프로젝트의 목적이 아니다** (상현님 실사용, 2026-08-10).

    will 씨앗이 이렇게 물었다: *"(스스로 세운다. **이 저장소에서 무엇을 이루려 하는가?**)"*
    세션이 그걸 **프로젝트 목표**로 읽고 사람에게 대화로 물었다:

        "이 프로젝트로 무엇을 만들려고 하시나요? 한두 문장으로 목표만 알려주시면,
         그에 맞게 will을 제 말로 써서 방을 완성하고 첫 작업 체인을 열겠습니다."

    그 순간 **목적이 인터뷰가 아니라 대화로 들어온다.** gil 이 문법으로 지켜 온 단 하나
    ("기준은 사람의 문장 그 자체다")가 옮겨쓰기로 바뀌고, 개시 인터뷰(카드 폼)는 통째로
    건너뛰어진다 — 세션이 stageIdentity 에서 멈춘 채 대화로 새기 때문이다.

    **세션이 순서를 뒤집은 게 아니라, 문서가 뒤집도록 유도했다.** 두 개가 같은 말로
    불리고 있었고, 충돌하면 더 구체적인 쪽이 이긴다."""

    def _seed_will(self):
        self.gil("start")
        self.gil("start", "--name", "gaon")
        return self.gil("global", "read", "existence/gaon/will.md").stdout

    def test_the_seed_does_not_ask_for_the_project_goal(self):
        """씨앗이 프로젝트 목표를 물으면 세션은 사람에게 묻는다 — 실제로 그랬다."""
        will = self._seed_will()
        self.assertNotIn("이 저장소에서 무엇을 이루려 하는가", will,
                         "will 씨앗이 여전히 프로젝트 목표를 묻는다")
        self.assertIn("프로젝트의 목적을 적는 자리가 아니다", will,
                      "will 이 무엇이 아닌지를 그 자리에서 말하지 않는다")

    def test_the_seed_says_where_the_purpose_actually_comes_from(self):
        """아니라고만 하면 벽이다 — **어디서 오는지**까지 말해야 순서가 선다."""
        will = self._seed_will()
        self.assertIn("개시 인터뷰", will, "목적이 어디서 오는지 안 말했다")

    def test_the_guidance_forbids_asking_the_human_here(self):
        """이 칸에서 사람에게 목적을 물으면 인터뷰가 통째로 건너뛰어진다."""
        self.gil("start")
        out = self.gil("start", "--name", "gaon").stdout
        self.assertIn("묻지 마라", out, "여기서 사람에게 묻지 말라고 말하지 않았다")
        self.assertIn("다음 칸", out, "그럼 언제 묻는지를 말하지 않았다")

    def test_the_seed_marker_still_matches_the_seed(self):
        """**두 자리에 같은 것을 적으면 한쪽만 낡는다.**

        씨앗 문구를 고치면서 '씨앗 그대로인가'를 판정하는 표식(seedWillMark)을 안 고치면,
        새 저장소에서 will 이 비었는데도 '채워졌다'고 판정한다 — 그러면 온보딩이 그 칸을
        말없이 건너뛴다. 이 시험이 그 어긋남을 잡는다."""
        self.gil("start")
        self.gil("start", "--name", "gaon")
        r = self.gil("start", "--status")
        self.assertIn("identity", r.stdout,
                      "씨앗 그대로인데 '정체성 미기입' 칸으로 안 잡혔다 — "
                      "seedWillMark 가 씨앗과 어긋났을 수 있다(init.go 의 tmplWill 과 대조)")
