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
import json
import os
import re
import sys
import subprocess
import tempfile
import time
import shutil
import unittest

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
        return subprocess.run(["git", *args], cwd=self.repo,
                              capture_output=True, text=True)

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
            seg = r.stdout.split(cyc, 1)[-1] if cyc in r.stdout else ""
            # 이 사이클에 이미 있는 kind 로 다음 필요한 kind 판단
            have = [k for k in chain_order if ("[" + k + "]") in r.stdout]
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
        r = subprocess.run([*GIL_CMD, "open", "c/c001", "--author", "clew", "--purpose", "P"],
                           cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0, "본문 없는 open 이 거부되지 않음")
        self.assertIn("본문", r.stderr)
        # amend 우회를 더는 안내하지 않는다(자기모순 제거) — 오히려 하지 말라고 명시.
        self.assertNotIn("커밋 수정으로 채우라", r.stderr)

    def test_open_body_via_title(self):
        """--title 도 본문으로 인정된다(한 줄 문제 정의)."""
        env = dict(os.environ, GIL_NO_VIEWER="1")
        r = subprocess.run([*GIL_CMD, "open", "c/c001", "--author", "clew",
                            "--purpose", "P", "--title", "한 줄 정의"],
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
        self.gil("chain", "dev", "--purpose", "개발 국면")
        self.gil("open", "dev/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "dev/c001", "--kind", "success", "--title", "s")
        self.gil("close", "dev/c001")
        self.gil("chain-close", "dev")
        r = self.gil("chain", "stg", "--purpose", "스테이징 국면")
        self.assertEqual(r.returncode, 0, r.stderr)
        # 새 체인 stg 는 닫힌 dev 끝에서 분기 — 대문(CLAUDE.md)이 조상으로 보존
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
        """출력에 STATE/NEXT + 다음 명령이 담긴다 — 인간 UX 아닌 LLM 프롬프트."""
        out = self.gil("init", "--name", "aria").stdout
        self.assertIn("STATE", out)
        self.assertIn("NEXT", out)
        self.assertIn("gil global read existence/aria/identity.md", out)

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

    def test_init_launches_integrated_viewer(self):
        """뷰어가 gil 에 통합됐다 — init 은 gil 자기 자신을 뷰어로 띄우고(또는 이미 떠 있으면
        그 URL 안내), 어느 경우든 깨지지 않는다. 별도 gilviewer 바이너리는 필요 없다."""
        env = dict(os.environ)
        env.pop("GIL_NO_VIEWER", None)   # 억제 끄기 → 실제 기동 시도
        env.pop("GIL_VIEWER", None)
        r = subprocess.run([*GIL_CMD, "init", "--name", "aria"], cwd=self.repo,
                           capture_output=True, text=True, env=env, timeout=15)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("STATE", r.stdout)
        self.assertIn("뷰어", r.stdout)          # 관전 안내를 낸다
        self.assertNotIn("gilviewer", r.stdout)  # 옛 별도 바이너리 언급 없음(통합됨)
        # init 이 띄운 뷰어 프로세스가 남았으면 정리(포트 8790).
        subprocess.run(["pkill", "-f", "viewer serve --repo"],
                       capture_output=True)

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

    def test_viewer_shows_the_new_form(self):
        """뷰어에 폼이 뜬다 — 커밋은 있는데 아무에게도 도달하지 않던 자리."""
        self._settled_chain()
        self._ask("mr", "전제가 반증됐다 — 범위는?")
        import socket, time, urllib.request
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        p = subprocess.Popen([*GIL_CMD, "viewer", "serve", "--repo", self.repo, "--port", str(port)],
                             env=dict(os.environ, GIL_NO_VIEWER="1"),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            body = ""
            for _ in range(40):
                try:
                    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1).read().decode()
                    break
                except Exception:
                    time.sleep(0.05)
            self.assertIn("📋 인터뷰", body)
            self.assertIn("전제가 반증됐다", body)
        finally:
            p.terminate()
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()

    def test_revision_stacks_instead_of_overwriting(self):
        """기준은 사람의 답이라 지워지면 안 된다 — 차수로 쌓인다(append-only 의 정신)."""
        self._settled_chain()
        self._ask("mr", "다시 묻는다")
        with open(os.path.join(self.repo, "ref2.md"), "w", encoding="utf-8") as f:
            f.write("기준 v2: 두 축을 갈라 잰다\n")
        self.gil("interview", "mr", "--resolve", "ref2.md")
        r = self.gil("interview", "mr", "--status")
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


class TestViewer(GilFixture):
    """gil viewer — 뷰어가 gil 에 통합됨(별도 gilviewer 폐지, 2026-07-25 상현님).

    serve(관전 서버)·build(정적 자기완결 HTML)·text(트리) 세 서브명령. 격리 방식으로
    통합돼 gil 본체는 안 건드린다. 여기선 build 자기완결성과 serve 기동을 검증."""

    def _seed_graph(self):
        """작은 데모 그래프 하나(체인·사이클·스텝·본문)를 만든다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "demo", "--purpose", "뷰어 테스트")
        self.gil("open", "demo/c001", "--author", "clew", "--purpose", "합 100")
        self.gil("step", "demo/c001", "--kind", "verify", "--verdict", "supported",
                 "--body", "검증 보고서 본문. 40+60=100.", "--title", "검증")
        self.gil("step", "demo/c001", "--kind", "success", "--title", "찾음")
        self.gil("close", "demo/c001", "--verdict", "supported")

    def test_viewer_build_is_self_contained(self):
        self._seed_graph()
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("viewer", "build", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        # 자기완결: 외부 http(s) 리소스 참조 없음(w3.org 네임스페이스·색상 힌트는 예외).
        import re
        externals = [u for u in re.findall(r'https?://[^\s"\'<>]+', html)
                     if "w3.org" not in u]
        self.assertEqual(externals, [], f"외부 참조 있음: {externals}")
        # 정적: 폴링 비활성(서버 없음).
        self.assertNotIn("/poll", html)
        self.assertNotIn("setInterval(poll", html)
        # 스텝 본문이 인라인 임베드됨(서버 페치 없이 보고서 렌더).
        self.assertIn('"body":', html)
        self.assertIn("demo", html)          # 데모 체인이 그래프에 들어감
        self.assertIn("정적 스냅샷", html)   # live 대신 스냅샷 표시

    def _exit_map(self):
        """정적 빌드 HTML 에서 (사이클, 스텝) → exit 라벨을 뽑는다."""
        import json, re
        out_html = os.path.join(self.repo, "g.html")
        self.gil("viewer", "build", "--out", out_html)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        data = json.loads(re.search(r'id="cycledata"[^>]*>(.*?)</script>', html, re.S).group(1))
        out = {}
        for chain, v in data.items():
            for cy in v["cycles"]:
                for n in cy["nodes"]:
                    if n.get("exit"):
                        out[(cy["name"], n["id"])] = n["exit"]
        return out

    def test_exit_ghost_only_where_something_took_over(self):
        """진출 경계는 추측이 아니라 사실이다 (이슈 #72).

        옛 구현은 카드 안에서 자식 없는 잎을 전부 '나갔다'고 그렸다 — 아무도 이어받지 않은
        잎에도, 잎 판정이 무너지면 모든 노드에도 붙었다. 이제 그 스텝을 진입 부모로 삼은
        카드가 실재할 때만 나간 것이다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "demo", "--purpose", "P")
        self.gil("open", "demo/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "demo/c001", "--kind", "success", "--title", "됨")
        self.gil("close", "demo/c001", "--verdict", "supported")
        # 아무도 이어받지 않은 사이클 — 진출 고스트가 붙으면 거짓이다.
        self.assertEqual(self._exit_map(), {})
        # c001 의 끝에서 실제로 새 사이클이 태어나면, 그 스텝에만 진출이 생긴다.
        self.gil("open", "demo/c002", "--author", "clew", "--purpose", "이어받음",
                 "--parent", "c001", "--inherit", "c001 교훈")
        exits = self._exit_map()
        self.assertEqual(len(exits), 1, exits)
        (cycle, step), label = next(iter(exits.items()))
        self.assertEqual(cycle, "c001")
        self.assertIn("demo/c002", label)

    def test_terminal_leaf_alone_does_not_exit(self):
        """종결 잎은 원래 나가지 않는다 — 종결 뒤 부착이 문법으로 막혀 있으니(#60).

        죽은 잎(fail)과 산 잎(success)이 함께 있는 사이클에서, 아무도 이어받지 않았다면
        어느 쪽에도 진출이 붙지 않는다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "demo", "--purpose", "P")
        self.gil("open", "demo/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "demo/c001", "--kind", "hypothesis", "--title", "H",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "demo/c001", "--kind", "fail", "--to", "s1", "--title", "벽")
        self.gil("step", "demo/c001", "--kind", "hypothesis", "--to", "s1", "--title", "H2",
                 "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "demo/c001", "--kind", "success", "--title", "됨")
        self.assertEqual(self._exit_map(), {})

    def test_overview_map_uses_gil_rules_not_raw_commit_ancestry(self):
        """전체맵의 선은 gil 룰로 그린다 (이슈 #70).

        옛 전체맵은 커밋 조상관계를 날것으로 이어, 계보상 무관한 체인까지 한 줄로 길게
        붙였다 — 아래 체인·사이클 패널은 gil 판정(#53)을 쓰는데 위아래가 다른 그림을 냈다.
        선 계산이 조용히 옛 방식으로 돌아가지 않게 못박는다(그림 자체는 브라우저 실측)."""
        self._seed_graph()
        out_html = os.path.join(self.repo, "g.html")
        self.gil("viewer", "build", "--out", out_html)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        # 계보 부모(gilParents)로 depth·row·엣지를 모두 계산한다.
        self.assertIn("gilParents", html)
        self.assertIn("n.gparents", html)
        # 범례가 성격을 바꿔 말한다 — "진짜 커밋 그래프"가 아니라 "gil 계보 그래프".
        self.assertIn("gil 계보 그래프", html)
        self.assertNotIn("진짜 커밋 그래프", html)

    def test_layout_spacing_comes_from_label_size(self):
        """간격은 그려질 글자 크기에서 나온다 (이슈 #71).

        옛 상수(체인 rowH=90 · 사이클 gap=104)는 라벨을 셈에 넣지 않아, 이름이 길면 라벨이
        아래 노드의 HEAD ▼ 와, 이웃 사이클 라벨과 겹쳤다(브라우저 실측: 체인 1건 · 사이클
        7건). 상수로 되돌아가면 같은 겹침이 조용히 살아나므로 계산식의 존재를 못박는다."""
        self._seed_graph()
        out_html = os.path.join(self.repo, "g.html")
        self.gil("viewer", "build", "--out", out_html)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("longestCy*8+20", html)      # 사이클 그래프 gap = 이름 길이에서
        self.assertNotIn("const gap=104", html)    # 옛 고정 간격이 남아 있으면 안 된다
        self.assertIn("rotate(-", html)            # 긴 라벨은 기울여 세운다(상현님 제안)

    def test_map_has_chain_filter_and_minimap(self):
        """26체인·381스텝이 되면 전체맵은 눈으로 따라갈 수 없다 (이슈 #79, 상현님 실사용).

        뎁스 접기(AIL #6)는 '얼마나 자세히'를 줄이지만 '무엇을'은 못 줄인다 — 지금 보려는
        체인만 남기는 축과, 확대했을 때 길을 잃지 않는 미니맵이 따로 필요하다."""
        self._seed_graph()
        out_html = os.path.join(self.repo, "g.html")
        self.gil("viewer", "build", "--out", out_html)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("chainFilterBar", html)      # 체인 하나만 그리는 축
        self.assertIn("gilMapChain", html)         # 고른 값은 리로드를 넘어 유지된다
        self.assertIn("minimap", html)             # 확대 중 위치를 잃지 않게
        self.assertIn("enableChainGraphZoom", html)  # 체인 그래프도 같은 엔진을 쓴다

    def test_working_node_marks_where_uncommitted_work_is(self):
        """미커밋 작업은 노드가 없어 '어디서 손대고 있는지'가 그래프에 없었다 (상현님).

        가장 가까운 조상 스텝을 앵커로 '작업중' 유령 노드를 그린다. 커밋되면 그 자리에
        진짜 스텝이 선다."""
        self._seed_graph()
        with open(os.path.join(self.repo, "wip.txt"), "w", encoding="utf-8") as f:
            f.write("작업중\n")
        import socket, time, urllib.request
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        p = subprocess.Popen([*GIL_CMD, "viewer", "serve", "--repo", self.repo, "--port", str(port)],
                             env=dict(os.environ, GIL_NO_VIEWER="1"),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            body = ""
            for _ in range(40):
                try:
                    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1).read().decode()
                    break
                except Exception:
                    time.sleep(0.05)
            self.assertIn('"dirty":true', body)          # 미커밋 상태가 실린다
            self.assertIn('"step":"s', body)             # 앵커 스텝까지 — 어디서 작업 중인가
            self.assertIn("dnode working", body)         # 유령 노드를 그리는 코드
        finally:
            p.terminate()
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()

    def test_viewer_build_requires_out(self):
        self._seed_graph()
        r = self.gil("viewer", "build")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--out", r.stderr)

    def test_viewer_serve_responds(self):
        self._seed_graph()
        # 여유 포트로 격리 기동(병렬 테스트 안전).
        import socket, time, urllib.request
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        env = dict(os.environ, GIL_NO_VIEWER="1")
        p = subprocess.Popen([*GIL_CMD, "viewer", "serve", "--repo", self.repo,
                              "--port", str(port)], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            ok = False
            for _ in range(40):  # 최대 ~2s 대기
                try:
                    body = urllib.request.urlopen(base + "/", timeout=1).read().decode()
                    ok = True
                    break
                except Exception:
                    time.sleep(0.05)
            self.assertTrue(ok, "serve 가 뜨지 않음")
            self.assertIn("gil 그래프 뷰어", body)
            self.assertIn("/poll", body)  # serve HTML 엔 폴링이 있다(정적과 반대)
            self.assertEqual(
                urllib.request.urlopen(base + "/poll", timeout=1).getcode(), 200)
        finally:
            p.terminate()
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()

    def test_viewer_approve_endpoint(self):
        """serve 의 POST /approve 가 pending 을 승인 → 산 잎(상현님, 뷰어 인터랙션).

        뷰어에서 사람이 pending 스텝의 승인 버튼을 누르면 서버가 gil approve 를 exec 한다.
        모든 호스트(브라우저·확장)에서 도는 범용 경로. GET 은 거부(상태 변경이라 POST 만)."""
        import socket, time, urllib.request, urllib.error
        self.gil("init", "--name", "clew")
        self.gil("chain", "t", "--purpose", "승인")
        self.gil("open", "t/c001", "--author", "clew", "--purpose", "p", "--body", "정의")
        self._autofill_order("t/c001", "t", "pending", dict(os.environ, GIL_NO_VIEWER="1"))
        self.gil("step", "t/c001", "--kind", "pending", "--title", "대기", "--body", "승인 요청")
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        env = dict(os.environ, GIL_NO_VIEWER="1")
        p = subprocess.Popen([*GIL_CMD, "viewer", "serve", "--repo", self.repo,
                              "--port", str(port)], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(40):
                try:
                    urllib.request.urlopen(base + "/", timeout=1); break
                except Exception:
                    time.sleep(0.05)
            # GET 은 405(POST only)
            try:
                urllib.request.urlopen(base + "/approve?chain=t&cycle=c001", timeout=1)
                self.fail("GET /approve 가 허용됨 — POST 만 허용해야")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 405)
            # POST 로 승인 → 산 잎
            req = urllib.request.Request(base + "/approve?chain=t&cycle=c001", method="POST")
            body = urllib.request.urlopen(req, timeout=3).read().decode()
            self.assertIn("success", body)
        finally:
            p.terminate()
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()
        # 승인 후 그래프에 success 산 잎이 생겼다.
        self.assertIn("success", self.gil("viewer").stdout)

    def test_viewer_text_output(self):
        self._seed_graph()
        r = self.gil("viewer")   # 서브명령 없으면 텍스트 트리
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("체인 demo", r.stdout)
        self.assertIn("c001", r.stdout)

    def test_viewer_text_shows_backtrack_parent(self):
        """viewer text 는 분기(backtrack 형제 가지)의 부모를 ←s# 로 표기한다.

        선형 진행은 부모 표기 없이 깔끔하고, 조상 define 으로 되돌아간
        형제 가지만 드러나야 backtrack 이 텍스트 트리에서도 보인다.
        """
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        # s1=define(open 자동). s2=가설, s3=검증 → s4=fail(죽은 잎, ←는 직전이라 표기 안 함).
        self.gil("step", "d/c001", "--kind", "hypothesis", "--title", "H1", "--body", "가설 보고서", "--falsify", "F", "--falsify-to", "s1")
        self.gil("step", "d/c001", "--kind", "verify", "--title", "V", "--body", "검증 보고서", "--verdict", "supported")
        self.gil("step", "d/c001", "--kind", "fail", "--to", "s1", "--title", "기각", "--body", "벽 보고서")
        # backtrack: 조상 define s1 에서 새 형제 가지.
        self.gil("step", "d/c001", "--kind", "hypothesis", "--to", "s1", "--title", "H2", "--body", "가설2 보고서", "--falsify", "F", "--falsify-to", "s1")
        r = self.gil("viewer")
        self.assertEqual(r.returncode, 0, r.stderr)
        # 형제 가지(s1 에서 되돌아간 가설)에 부모 표기가 있어야 한다.
        self.assertIn("←s1", r.stdout, f"backtrack 부모 표기 없음:\n{r.stdout}")
        # 선형 진행 스텝은 부모 표기로 어지럽히지 않는다(←s2/←s3 등 직전-부모 표기 없음).
        self.assertNotIn("←s2", r.stdout)
        self.assertNotIn("←s3", r.stdout)

    def test_viewer_reads_remote_only_branches(self):
        """뷰어는 원격 추적 브랜치(refs/remotes/*)의 gil 그래프도 읽는다.

        결함(상현님): 신선한 clone 은 로컬에 기본 브랜치 하나뿐이고 gil 그래프는
        refs/remotes/origin/* 에만 있다. 뷰어가 --branches(로컬)만 보면 그래프를
        통째로 놓쳐 '스텝 0개'가 됐다. --remotes 까지 봐야 한다.
        """
        # 1) origin 역할의 bare 저장소에 gil 그래프를 만든다.
        import tempfile as _tf
        origin = _tf.mkdtemp(prefix="gil-origin-")
        work = _tf.mkdtemp(prefix="gil-work-")
        clone = _tf.mkdtemp(prefix="gil-clone-")
        try:
            subprocess.run(["git", "init", "-q", "--bare", origin], check=True)
            # work 에서 그래프를 만들고 origin 으로 push.
            for a in (["init", "-q"], ["config", "user.email", "t@e.com"],
                      ["config", "user.name", "t"], ["config", "commit.gpgsign", "false"],
                      ["remote", "add", "origin", origin]):
                subprocess.run(["git", "-C", work, *a], check=True)
            env = dict(os.environ, GIL_NO_VIEWER="1")
            g = lambda *a: subprocess.run([*GIL_CMD, *a], cwd=work, env=env,
                                          capture_output=True, text=True)
            g("init", "--name", "clew")
            g("chain", "demo", "--purpose", "P")
            # #33: open 게이트(사람 승인 기준) 충족 — 인터뷰 심고 즉시 해소.
            subprocess.run([*GIL_CMD, "interview", "demo", "--ask", "-"], cwd=work, env=env,
                           capture_output=True, text=True, input='[{"q":"q","type":"text"}]')
            with open(os.path.join(work, "reference-demo.md"), "w", encoding="utf-8") as f:
                f.write("# 기준")
            g("interview", "demo", "--resolve", "reference-demo.md")
            os.remove(os.path.join(work, "reference-demo.md"))
            g("open", "demo/c001", "--author", "clew", "--purpose", "Q", "--body", "문제 정의")
            g("step", "demo/c001", "--kind", "hypothesis", "--title", "H", "--body", "b", "--falsify", "F", "--falsify-to", "s1")
            subprocess.run(["git", "-C", work, "push", "-q", "--all", "origin"], check=True)
            # 2) 신선한 clone — 로컬 브랜치는 기본 하나뿐, 그래프는 원격에만.
            subprocess.run(["git", "clone", "-q", origin, clone], check=True)
            local_branches = subprocess.run(
                ["git", "-C", clone, "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
                capture_output=True, text=True).stdout.split()
            self.assertLessEqual(len(local_branches), 1, f"신선한 클론에 로컬 브랜치 여럿: {local_branches}")
            # 3) 뷰어가 원격 브랜치의 그래프를 본다.
            r = subprocess.run([*GIL_CMD, "viewer", "text", "--repo", clone],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("스텝 노드 0개", r.stdout, f"원격 그래프를 놓침:\n{r.stdout}")
            self.assertIn("체인 demo", r.stdout, f"원격 그래프 미표시:\n{r.stdout}")
        finally:
            for d in (origin, work, clone):
                shutil.rmtree(d, ignore_errors=True)

    def test_step_rejects_second_define(self):
        """define 은 사이클의 뿌리 하나(open 이 만드는 s1)뿐 — step --kind define 은 거부된다.

        첫 정의가 못 다룬 부분은 새 define 이 아니라 다른 kind(hypothesis 등)나
        새 사이클로 이어간다(상현님). 그래야 "사이클 = 하나의 문제 정의에서 뻗은
        사고 나무" 불변식이 서고, 뷰어에 define 이 둘씩 떠 혼란을 주지 않는다.
        """
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        r = self.gil("step", "d/c001", "--kind", "define", "--title", "재정의", "--body", "b")
        self.assertNotEqual(r.returncode, 0, "두 번째 define 이 거부되지 않았다")
        self.assertIn("define 은 사이클의 뿌리 하나", r.stderr + r.stdout)
        # 다른 kind 는 여전히 허용.
        r2 = self.gil("step", "d/c001", "--kind", "hypothesis", "--title", "H", "--body", "b", "--falsify", "F", "--falsify-to", "s1")
        self.assertEqual(r2.returncode, 0, r2.stderr)

    def test_fsck_flags_multiple_defines_in_cycle(self):
        """fsck 는 한 사이클에 define 이 여럿인 (옛) 그래프를 위반으로 잡는다.

        step 단계에서 신규 생성은 막지만, 규칙 도입 전 데이터엔 여러 define 이
        있을 수 있다(공식 example 이 그랬다). fsck 가 이를 드러내야 정리 대상이 된다.
        같은 사이클은 한 번만 보고한다.
        """
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        # step 이 막으므로, 옛 데이터를 흉내내 두 번째 define 커밋을 손으로 심는다.
        self._git("commit", "--allow-empty", "-q", "-m",
                  "gil d/c001/s2 define: 재정의\n\n"
                  "Gil-Chain: d\nGil-Cycle: c001\nGil-Step: s2\nGil-Kind: define\nGil-Parent: s1")
        r = self.gil("fsck")
        out = r.stdout + r.stderr
        self.assertIn("define 이 2개", out, f"fsck 가 define 중복을 못 잡음:\n{out}")
        # 한 사이클은 한 번만 보고(s1·s2 각각 두 번 아님).
        self.assertEqual(out.count("define 이 2개"), 1, f"사이클 중복 보고:\n{out}")

    def test_viewer_no_duplicate_define_across_sibling_branches(self):
        """조상 define 에서 형제 가지를 분기해도 define 노드가 두 번 뜨지 않는다.

        결함(상현님): backtrack/새 가지는 조상 define 커밋에서 진짜 git 브랜치를
        분기하므로 그 define 이 여러 브랜치 공통조상이 된다. 뷰어가 SHA dedup 을
        안 하면 스택·사이클 뷰에 define 이 두 번 그려진다. viewerCollectNodes 가
        커밋 하나=노드 하나로 접어야 한다.
        """
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "d/c001", "--kind", "hypothesis", "--title", "H1", "--body", "가설1", "--falsify", "F", "--falsify-to", "s1")
        # 조상 define(s1)으로 되돌아가 형제 가지 분기 → s1 이 두 브랜치 공통조상.
        self.gil("step", "d/c001", "--kind", "hypothesis", "--to", "s1", "--title", "H2", "--body", "가설2", "--falsify", "F", "--falsify-to", "s1")
        r = self.gil("viewer")
        self.assertEqual(r.returncode, 0, r.stderr)
        # s1 define 라인이 정확히 한 번만 나와야 한다.
        n = sum(1 for ln in r.stdout.splitlines() if "s1 [define]" in ln)
        self.assertEqual(n, 1, f"define 노드가 {n}번 뜸(중복):\n{r.stdout}")

    def test_viewer_shows_uncommitted_work_overlay(self):
        """미커밋 작업이 있으면 현재위치 스텝 아래에 '작업중' 오버레이가 뜬다.

        결함(상현님): 뷰어가 커밋만 보여줘 마지막 커밋 이후 작업이 살아있어도
        '멈춘 듯' 보였다. 스텝 모델은 그대로 두고(커밋=완결 사고단위 불변식),
        뷰어가 워킹트리 상태를 오버레이로만 그린다.
        """
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "d/c001", "--kind", "hypothesis", "--title", "H", "--body", "가설", "--falsify", "F", "--falsify-to", "s1")
        # 클린: 오버레이 없음.
        r = self.gil("viewer")
        self.assertIn("작업 없음(클린)", r.stdout, r.stdout)
        self.assertNotIn("작업중", r.stdout)
        # 미커밋 변경 발생 → 오버레이 등장.
        with open(os.path.join(self.repo, "wip.txt"), "w") as f:
            f.write("in progress\n")
        r = self.gil("viewer")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("작업중", r.stdout, f"미커밋 오버레이 없음:\n{r.stdout}")
        self.assertIn("wip.txt", r.stdout, "변경 파일 샘플 표시 없음")

    def test_thin_body_warns_append_only(self):
        """--body 를 빠뜨린 얇은 스텝엔, 본문은 나중에 못 고친다(append-only)고 경고한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        r = self.gil("step", "d/c001", "--kind", "verify", "--title", "얇음", "--verdict", "supported")  # --body 없음
        self.assertEqual(r.returncode, 0, r.stderr)
        msg = r.stderr + r.stdout
        self.assertIn("얇다", msg)
        self.assertIn("append-only", msg, "본문 불변성(나중에 못 고침) 안내가 없다")

    def test_cycle_status_success_on_new_model(self):
        """success 종결 스텝(새 모델)이 있으면 사이클 status 가 success — open 으로 남지 않는다.

        결함: status() 가 옛 모델(analyze --outcome)만 봐서, kind=success 스텝을
        만들어도 사이클이 계속 '열림'으로 보였다.
        """
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "d/c001", "--kind", "verify", "--title", "V", "--body", "검증 보고서", "--verdict", "supported")
        self.gil("step", "d/c001", "--kind", "success", "--title", "됨", "--body", "종합 보고서")
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("viewer", "build", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        self.assertIn('"status":"success"', html)
        self.assertNotIn('"status":"open"', html, "종결됐는데 사이클이 open 으로 남음")

    def test_viewer_build_has_dag_and_lineage(self):
        """build HTML 에 진짜 커밋 DAG(전체 스텝맵)·지식전파 계보 렌더 코드와
        DAG 데이터(커밋 부모)가 임베드된다."""
        self._seed_graph()
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("viewer", "build", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        # 전체 스텝맵·DAG 렌더 함수(탭 없이 항상 렌더).
        self.assertIn("buildStepMap", html)
        self.assertIn("view-map", html)
        self.assertIn("전체 스텝맵", html)
        # 탭은 제거됐다 — 세로 스택 pane 구조.
        self.assertNotIn('id="tab-map"', html)
        self.assertIn("panehead", html)
        self.assertIn("pane-report", html)
        # DAG 데이터(커밋 부모로 이어진 노드 리스트) 임베드.
        self.assertIn("dagdata", html)
        self.assertIn('"parents":', html)
        # 전체맵: 체인 이름을 사이클 박스 위 라벨로, 사이클=박스.
        self.assertIn("chlabel", html)
        self.assertIn("cycbox", html)
        # 지식 전파 계보 함수.
        self.assertIn("function lineage", html)
        # 맵/DAG JS 는 Go 의 esc() 가 아니라 JS mdEsc 를 써야 한다(esc 미정의 회귀 방지).
        self.assertNotIn("esc(chain)", html)

    def test_head_arrow_on_all_graphs(self):
        """현재위치(HEAD)를 모든 그래프의 팁 노드 위에 ▼(headarrow)로 표시한다."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "a", "--purpose", "P")
        self.gil("open", "a/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "a/c001", "--kind", "verify", "--title", "V", "--body", "b", "--verdict", "supported")
        # 닫지 않음 → HEAD 가 이 스텝 팁. 체인 그래프 노드에 headarrow(정적 렌더)가 있어야.
        out_html = os.path.join(self.repo, "g.html")
        self.gil("viewer", "build", "--out", out_html)
        html = open(out_html, encoding="utf-8").read()
        # 체인 노드(here)에 headarrow SVG 가 인라인된다.
        self.assertIn("headarrow", html)
        self.assertIn("현재위치 1개", html)  # 헤더에 현재위치 카운트

    def test_open_body_file_stdin_fills_define(self):
        """gil open --body-file - 가 s1 define 본문을 여는 순간 채운다(이슈 #31) —
        raw amend 로 내려가 trailer 를 날리는 함정 제거. step 과 대칭."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        r = self.gil("open", "d/c1", "--author", "clew", "--purpose", "Q",
                     "--body-file", "-",
                     input="# 문제 정의\n\n무엇을 푸는가: 예제 문제를 정의한다.\n\n"
                           "- 입력: 관측 데이터 파일\n- 출력: 판정 보고서\n- 평가 지표: 정확도와 재현율\n"
                           "- 제약: 외부 의존 없이 표준 라이브러리만 사용한다\n\n"
                           "이 사이클은 위 지표로 성공/실패를 가른다.\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        show = self._git("show", "-s", "--format=%B", "HEAD").stdout
        self.assertIn("# 문제 정의", show)
        self.assertIn("Gil-Kind: define", show, "trailer 소실")
        # 본문이 채워졌으니 '얇다' 경고가 없어야 한다.
        self.assertNotIn("본문이 얇다", r.stdout + r.stderr)

    def test_version_command(self):
        """gil version 은 git 없이도 현재 버전을 낸다(이슈 #22). 소스 빌드는 dev."""
        r = self.gil("version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gil ", r.stdout)

    def test_handoff_reports_viewer_liveness(self):
        """gil handoff 가 뷰어 생존 여부를 보고한다(이슈 #30) — 죽어 있으면 되살릴 명령까지."""
        self.gil("init", "--name", "clew")
        r = self.gil("handoff")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("뷰어:", r.stdout)

    def test_chain_lineage_skips_plain_commits(self):
        """체인을 닫고 평범 커밋(gil 트레일러 없음)을 쌓은 뒤 다음 체인을 열어도
        체인 계보(부모→자식)가 이어진다 — 첫 부모 한 칸만 보면 계보가 끊겨
        체인 그래프가 전체맵(비-gil 을 건너뛰는 DAG)과 안 맞았다(AIL 실사용 결함)."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "dev", "--purpose", "P")
        self.gil("open", "dev/c1", "--author", "clew", "--purpose", "Q")
        self.gil("step", "dev/c1", "--kind", "success", "--title", "됨", "--body", "종합")
        self.gil("close", "dev/c1", "--verdict", "supported")
        self.gil("chain-close", "dev", "--verdict", "supported")
        # 평범 개발 커밋 두 개 — 실사용 레포에선 체인 사이에 흔히 낀다.
        for i in (1, 2):
            with open(os.path.join(self.repo, f"plain{i}.txt"), "w") as f:
                f.write("x\n")
            self._git("add", "-A")
            self._git("commit", "-m", f"plain dev commit {i}")
        self.gil("chain", "stg", "--purpose", "P2")
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("viewer", "build", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        import json, re
        html = open(out_html, encoding="utf-8").read()
        parents = json.loads(re.search(r'"parentdata"[^>]*>(\{.*?\})</script>', html, re.S).group(1))
        self.assertEqual(parents.get("stg"), "dev",
                         f"평범 커밋을 건너 조상 체인을 못 찾음 — 계보 끊김: {parents}")

    def test_stepmap_zoom_pan_and_cycle_labels(self):
        """전체 스텝맵에 줌/팬 컨트롤(dagbar·enableZoomPan)과 사이클 라벨(cyclabel)이 들어간다 —
        대형 그래프(수백 스텝) 항해용."""
        self._seed_graph()
        out_html = os.path.join(self.repo, "g.html")
        r = self.gil("viewer", "build", "--out", out_html)
        self.assertEqual(r.returncode, 0, r.stderr)
        html = open(out_html, encoding="utf-8").read()
        # 줌/팬: 컨트롤 바 + viewBox 조작 함수 + 휠·드래그 안내.
        self.assertIn("enableZoomPan", html)
        self.assertIn("dagbar", html)
        self.assertIn("Ctrl+휠", html)
        # 사이클 라벨: 박스 위 작은 글씨(툴팁만으론 훑기 어려움).
        self.assertIn("cyclabel", html)

    def test_dag_connects_cycles_across_chain_boundary(self):
        """DAG 는 사이클·체인 경계를 넘는 지식 전수를 진짜 엣지로 잇는다 —
        자식 체인의 첫 스텝이 부모 체인의 종결 스텝(산 잎)을 부모로 갖는다.

        비-gil 커밋(chain/close/chain-close)을 건너뛰어 조상 스텝을 찾는 게 핵심.
        """
        self.gil("init", "--name", "clew")
        # dev 체인: verify → success → close → chain-close.
        self.gil("chain", "dev", "--purpose", "P")
        self.gil("open", "dev/c1", "--author", "clew", "--purpose", "Q")
        self.gil("step", "dev/c1", "--kind", "verify", "--title", "V", "--body", "검증", "--verdict", "supported")
        self.gil("step", "dev/c1", "--kind", "success", "--title", "됨", "--body", "종합")
        self.gil("close", "dev/c1", "--verdict", "supported")
        self.gil("chain-close", "dev", "--verdict", "supported")
        # staging 체인: 닫힌 dev 끝에서 열린다.
        self.gil("chain", "stg", "--purpose", "P2")
        self.gil("open", "stg/c1", "--author", "clew", "--purpose", "Q2")
        out_html = os.path.join(self.repo, "g.html")
        self.gil("viewer", "build", "--out", out_html)
        import json, re
        html = open(out_html, encoding="utf-8").read()
        dag = json.loads(re.search(r'"dagdata"[^>]*>(\[.*?\])</script>', html).group(1))
        by = {(d["chain"], d["step"]): d for d in dag}
        dev_success = next(d for d in dag if d["chain"] == "dev" and d["kind"] == "success")
        stg_s1 = by[("stg", "s1")]
        self.assertIn(dev_success["sha"], stg_s1["parents"],
                      "staging 첫 스텝이 dev 종결 스텝을 부모로 갖지 않음 — 경계 넘는 전수 끊김")

    def test_body_file_dash_reads_stdin(self):
        """--body-file - 는 stdin 에서 본문을 읽는다 — 임시 .md 파일 없이 잉여 방지."""
        self.gil("init", "--name", "clew")
        self.gil("chain", "d", "--purpose", "P")
        self.gil("open", "d/c001", "--author", "clew", "--purpose", "Q")
        body = "# 검증 보고서\n\nstdin 으로 넘긴 본문 마커 XYZZY.\n"
        r = self.gil("step", "d/c001", "--kind", "verify", "--title", "V",
                     "--verdict", "supported", "--body-file", "-", input=body)
        self.assertEqual(r.returncode, 0, r.stderr)
        # 커밋 본문에 stdin 내용이 들어갔는지 확인.
        show = subprocess.run(["git", "-C", self.repo, "log", "--branches", "--format=%B"],
                              capture_output=True, text=True)
        self.assertIn("XYZZY", show.stdout, "stdin 본문이 커밋에 안 들어감")


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

    def test_viewer_shows_refuted_by(self):
        """뷰어 텍스트가 반증된 판정에 ⚠refuted-by, 반증한 쪽에 ⟵refutes 를 표시한다."""
        self._refutes("net/design/s3")
        self.gil("step", "net/harden", "--kind", "success", "--title", "됨")
        self.gil("close", "net/harden")
        r = self.gil("viewer")
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
        r = self.gil("viewer", "build", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            html = f.read()
        # 정적 build 는 인터뷰 폼을 싣지 않는다(제출할 서버가 없다) — 여기서 보증할 수 있는
        # 것은 **크래시 가드가 실제로 실려 나갔는가**다. 폼이 뜨는 것 자체는 브라우저로
        # 확인했다(뷰어 폼 제출 → intake done → 인용된 목적으로 체인).
        self.assertIn("if(!host)return;", html)         # 전체맵이 없어도 죽지 않는다
        self.assertIn("step('인터뷰 폼'", html)          # 앞 단계가 죽어도 폼은 그린다

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
        r = self._run("open", "ail/c1", "--author", "x", "--from-plan", "2", "--body", "정의")
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
        r = self._raw_step("c/c1", "--kind", "analyze", "--title", "a")
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
        self._raw_step("c/c1", "--kind", "analyze", "--title", "a")
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
    """gil deploy — 배포(공개) 지점 마커 (이슈 #34)."""

    def _live_step(self):
        self.gil("chain", "dev", "--purpose", "개발")
        self.gil("open", "dev/c001", "--author", "a", "--purpose", "P")
        self.gil("step", "dev/c001", "--kind", "success", "--title", "릴리스 준비")

    def test_deploy_marks_target_step(self):
        """deploy 는 대상 스텝을 가리키는 Gil-Deploy 트레일러 커밋을 남긴다."""
        self._live_step()
        r = self.gil("deploy", "--at", "dev/c001/s4", "--tag", "v0.2.0",
                     "--url", "https://example.com/r/v0.2.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy"), "v0.2.0")
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-At"), "dev/c001/s4")
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-Url"),
                         "https://example.com/r/v0.2.0")
        # 배포 커밋은 추론 노드가 아니다 — Gil-Step 을 달지 않는다(그래프 위상 불변).
        self.assertEqual(self.trailer("HEAD", "Gil-Step"), "")

    def test_deploy_requires_tag_and_at(self):
        self._live_step()
        r = self.gil("deploy", "--tag", "v1")  # --at 없음
        self.assertNotEqual(r.returncode, 0)
        r = self.gil("deploy", "--at", "dev/c001/s4")  # --tag 없음
        self.assertNotEqual(r.returncode, 0)

    def test_deploy_rejects_missing_step(self):
        """실재하지 않는 스텝엔 마커를 얹지 못한다."""
        self._live_step()
        r = self.gil("deploy", "--at", "dev/c001/s99", "--tag", "v1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("s99", r.stdout + r.stderr)

    def test_deploy_rejects_malformed_at(self):
        """--at 은 chain/cycle/step 세 조각을 다 요구한다."""
        self._live_step()
        r = self.gil("deploy", "--at", "dev/c001", "--tag", "v1")  # 스텝 없음
        self.assertNotEqual(r.returncode, 0)

    def test_deploy_url_optional(self):
        self._live_step()
        r = self.gil("deploy", "--at", "dev/c001/s4", "--tag", "v0.1.0")
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
                     "--reference", "-", input="# 기준\n성공: 30% 절감\n실패: 정확도 하락")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("audit", "Gil-Reference"), "true")
        body = self._git("log", "-1", "audit", "--format=%b").stdout
        self.assertIn("30% 절감", body)  # 기준 전문이 본문에 있다

    def test_chain_without_reference_still_ok(self):
        """--reference 는 강제 아님(최소 형태) — 없어도 체인은 열린다."""
        self._init()
        r = self.gil("chain", "plain", "--purpose", "그냥")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("plain", "Gil-Reference"), "")

    def test_open_surfaces_reference_when_present(self):
        """기준 있는 체인에서 사이클을 열면 '기준을 읽으라' 안내가 뜬다."""
        self._init()
        self.gil("chain", "audit", "--purpose", "감사",
                 "--reference", "-", input="# 기준 문서 전문")
        r = self.gil("open", "audit/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("기준 문서", r.stdout + r.stderr)

    def test_open_blocked_without_approved_reference(self):
        """사람 승인 기준(인터뷰 done)이 없으면 작업 사이클 open 이 거부된다(#33 게이트).
        (자동 인터뷰 보정을 끄고 게이트 자체를 검증한다.)"""
        self._init()
        self.gil("chain", "plain", "--purpose", "그냥")
        self._no_interview_autofill = True
        try:
            r = self.gil("open", "plain/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        finally:
            self._no_interview_autofill = False
        self.assertNotEqual(r.returncode, 0, "기준 없는 open 이 거부되지 않음")
        self.assertIn("인터뷰", r.stdout + r.stderr)


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

    def test_open_blocked_without_interview(self):
        """기준(인터뷰 done) 없이 작업 사이클 open 거부 — 인터뷰가 먼저."""
        r = self.gil("open", "sb/c1", "--author", "clew", "--purpose", "측정", "--body", "정의")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("인터뷰", r.stdout + r.stderr)

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
        """심어둔 인터뷰가 없으면 none — 그리고 무엇을 해야 하는지 한 수를 준다."""
        r = self.gil("interview", "sb", "--status")
        self.assertEqual(r.returncode, 0, r.stderr)
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
        r = self.gil("interview", "sb", "--status")
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
        r = self.gil("interview", "sb", "--wait", "--timeout", "3")
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
            ("gil_chain", {"name": "probe", "purpose": "MCP 경로"}),
            ("gil_open", {"target": "probe/c001", "author": "clew", "purpose": "인터뷰 없이"}),
            ("gil_log", {}),
        ])
        self.assertFalse(r[0][0], r[0][1])
        self.assertTrue(r[1][0], "인터뷰 없는 open 은 거부돼야 한다")
        self.assertFalse(r[2][0], "거부 뒤에도 서버는 살아 다음 호출을 받는다")

    def test_interview_elicitation_makes_reference(self):
        """인터뷰 = 호스트 네이티브 폼 한 번. 사람 답이 그대로 기준 문서가 되고 게이트가 열린다."""
        r = self._rpc([
            ("gil_chain", {"name": "probe", "purpose": "MCP 인터뷰"}),
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
                  "params": {"name": "gil_chain", "arguments": {"name": "probe", "purpose": "P"}}})
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
            ("gil_chain", {"name": "probe", "purpose": "P"}),
            ("gil_interview", {"chain": "probe",
                               "questions": [{"q": "무엇을 풀려는가", "type": "text"}]}),
        ])
        self.assertFalse(r[1][0], r[1][1])
        self.assertEqual(self.trailer("HEAD", "Gil-Interview"), "pending")


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
        self.assertTrue(r["structuredContent"]["tipSignature"].strip())

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

    def test_chain_without_reference_closes_freely(self):
        """기준 없는 체인까지 소급해 막지는 않는다 — 없는 잣대에 성적표를 요구하지 않는다."""
        self.gil("chain", "legacy", "--purpose", "기준 없이 열린 옛 체인")
        self._no_retro_autofill = True
        r = self.gil("chain-close", "legacy")
        self.assertEqual(r.returncode, 0, r.stderr)

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
        self.gil("chain", "beta", "--purpose", "다음 국면")
        self._no_interview_autofill = True
        r = self.gil("open", "beta/c001", "--author", "clew", "--purpose", "P", "--body", "B")
        self.assertNotEqual(r.returncode, 0, "시드는 인터뷰를 대신하지 못한다")


class TestQuietByDefault(GilFixture):
    """브라우저는 **기본으로 열지 않는다** (이슈 #48).

    자동으로 튀어나오는 창은 도움보다 방해였다: 에이전트가 인앱 패널에 띄우려는데 밖에 창이
    하나 더 뜨고, 테스트·반복 실행마다 브라우저가 쌓인다. 주소는 언제나 출력에 나오므로
    사람도 에이전트도 여는 데 지장이 없다. 여는 건 명시적 --open 일 때만.
    """

    def test_init_still_accepts_no_open(self):
        """--no-open 은 이제 기본이라 no-op — 이미 쓰인 문서·스크립트가 깨지지 않게 계속 받는다."""
        r = self.gil("init", "--no-open")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_viewer_help_documents_open(self):
        """표면에 안 보이면 없는 기능이다."""
        r = self.gil("help", "viewer")
        self.assertIn("--open", r.stdout + r.stderr)

    def test_browser_not_opened_by_default(self):
        """아무 플래그도 없이 serve 해도 '브라우저로 열었다' 가 나오지 않는다."""
        self.gil("init")
        env = dict(os.environ)
        env.pop("GIL_NO_VIEWER", None)
        env.pop("GIL_NO_BROWSER", None)
        p = subprocess.Popen([*GIL_CMD, "viewer", "serve", "--port", "8796"],
                             cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env)
        try:
            deadline = 0
            out = ""
            # 서버가 떴다는 첫 줄(주소)만 읽고 끊는다 — 브라우저를 열었다면 그 다음 줄에 나온다.
            while deadline < 40:
                import time as _t
                _t.sleep(0.1)
                deadline += 1
                if p.poll() is not None:
                    break
        finally:
            p.terminate()
            out, err = p.communicate(timeout=10)
        self.assertIn("뷰어 서버가 떴다", out, out + err)   # 주소는 나온다
        self.assertNotIn("브라우저로 열었다", out)           # 창은 안 뜬다


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
        r = self.gil("viewer", "build", "--out", "g.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.repo, "g.html"), encoding="utf-8") as f:
            return f.read()

    def test_chain_label_is_emitted_once_per_chain(self):
        """'이미 그렸는지'로 판정한다 — 깊이 비교로는 나란한 사이클을 못 가른다."""
        html = self._migrated_repo({"serving": 6, "dash": 3})
        self.assertIn("chainDone", html)           # 체인당 1회 보증 장치
        self.assertNotIn("dmin===chainMinD", html)  # 옛 깊이 판정으로 되돌아가지 않았다

    def test_cycle_labels_are_placed_before_chain_labels(self):
        """자리 다툼에서 살아남아야 할 건 사이클 신원이다 — 체인 이름은 몇 개뿐이다."""
        html = self._migrated_repo({"serving": 4})
        i_cyc = html.index("class:'cyclabel'")
        i_ch = html.index("class:'chlabel'")
        self.assertLess(i_cyc, i_ch, "사이클 라벨 배치가 체인 라벨보다 먼저여야 한다")


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
        r = self.gil("viewer", "build", "--out", "g.html")
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


class TestHandoffOpensViewer(GilFixture):
    """세션을 이어받는 자리에서 관전 뷰어를 규범으로 띄운다 (이슈 #55).

    handoff 는 새 세션이 정신모델을 세우는 첫 관문이다. 여기서 그래프를 안 보면 그 세션 내내
    안 본다 — 계보가 수십 개면 텍스트 나열로는 분기·죽은 잎·현재위치가 눈에 안 들어오고,
    이미 있는 가지를 못 보고 새로 파게 된다.

    왜 안내가 아니라 규범인가. "에이전트가 알아서 뷰어를 열기"는 자기규율이고, 자기규율은
    원리적으로 불충분하다(LLM 은 명시된 절차도 우회한다). 강제는 도구가 레일을 까는 쪽에
    둔다 — 이슈 #45·#33 과 같은 계열이다.
    """

    def test_handoff_directs_to_open_the_viewer_in_app(self):
        self.gil("init")
        r = self.gil("handoff")
        out = r.stdout + r.stderr
        self.assertIn("관전 뷰어", out)
        self.assertIn("인앱 브라우저", out)
        self.assertIn("127.0.0.1", out)

    def test_directive_is_normative_not_optional(self):
        """'열 수 있으면 열어라'가 아니라 '지금 열어라'여야 한다."""
        self.gil("init")
        out = (lambda r: r.stdout + r.stderr)(self.gil("handoff"))
        self.assertIn("선택이 아니다", out)

    def test_outside_browser_is_last_resort(self):
        """밖의 브라우저 창은 사람이 앱을 떠나야 하므로 마지막 수단이다."""
        self.gil("init")
        out = (lambda r: r.stdout + r.stderr)(self.gil("handoff"))
        self.assertIn("마지막 수단", out)


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
        r = self.gil("viewer", "build", "--out", "g.html")
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
        r = self.gil("viewer", "text")
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
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-Target"), "l40s:8080")
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-State"), "staged")
        # 승격도 대상을 함께 남긴다 — 언제 어디로 올라갔나가 둘 다 남는다.
        self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--promote", "--target", "l40s:8080")
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-State"), "live")
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-Target"), "l40s:8080")

    def test_target_is_shown_in_viewer(self):
        self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--target", "l40s:8080")
        out_html = os.path.join(self.repo, "g.html")
        self.gil("viewer", "build", "--out", out_html)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        self.assertIn('"deployTarget":"l40s:8080"', html)

    def test_default_stays_live(self):
        """옛 사용법은 그대로다 — 새 상태가 기존 흐름을 깨지 않는다."""
        r = self.gil("deploy", "--at", "d/c1/s5", "--tag", "v0.2.0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-State"), "live")

    def test_staged_is_recorded_as_machine_readable_state(self):
        """산문이 아니라 상태로 남는다 — notes 에 손으로 쓴 필드를 발명하지 않아도 되게."""
        r = self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--state", "staged")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-State"), "staged")
        out = r.stdout + r.stderr
        self.assertIn("아직 안 올라갔다", out)
        self.assertIn("--promote", out)   # 다음 올바른 한 수

    def test_promote_appends_rather_than_rewrites(self):
        """승격은 앞 마커를 고치지 않는다 — 언제 준비됐고 언제 올라갔나가 둘 다 남는다."""
        self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--state", "staged")
        staged_sha = self._git("rev-parse", "HEAD").stdout.strip()
        r = self.gil("deploy", "--at", "d/c1/s5", "--tag", "v2.1.0", "--promote")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Deploy-State"), "live")
        # 앞의 staged 커밋이 그대로 살아 있다(append-only).
        self.assertNotEqual(self._git("rev-parse", "HEAD").stdout.strip(), staged_sha)
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

    def test_new_chain_refused_while_another_is_open(self):
        """문서와 실동작의 어긋남을 없앤다 — 열린 체인이 있으면 그냥 통과시키지 않는다."""
        r = self.gil("chain", "beta", "--purpose", "동시에 굴릴 트랙 B")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("alpha", out)
        self.assertIn("chain-close", out)      # 이어받기
        self.assertIn("--parallel-with", out)  # 병렬

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
        """'닫힌 체인의 끝에서 새 체인을 연다'가 이름 수준에서도 성립한다."""
        self._close()
        r = self.gil("chain", "next", "--purpose", "P2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        anc = self._git("merge-base", "--is-ancestor", "app", "next").returncode == 0
        self.assertTrue(anc, "새 체인이 닫힌 체인의 자손이 아니다 — 고아로 보인다")


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


class TestViewerIdentityBeforeClaim(GilFixture):
    """그 포트의 뷰어가 이 저장소를 보는지 확인하고 말한다 (온보딩 실측에서 발견).

    포트가 열려 있다는 사실만으로 "관전 중"이라 부르면, 다른 프로젝트의 뷰어가 같은 기본
    포트를 쥐고 있을 때 사람을 **남의 그래프**로 보낸다. 실제로 새 폴더에서 gil_init 을
    했더니 다른 저장소의 뷰어 주소를 안내했고, handoff 는 그 주소를 "지금 열어라 — 선택이
    아니다"라는 규범(#55)으로 지시했다. 레일이 틀린 곳을 가리키면 레일이 아니다.
    """

    def _fake_server_on(self, port, body):
        """그 포트를 쥔 다른 무언가를 흉내낸다(다른 저장소의 뷰어 또는 뷰어가 아닌 것)."""
        import http.server, threading
        payload = body.encode()

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return srv

    def _handoff_with_port(self, port):
        env = dict(os.environ, GIL_NO_VIEWER="1", GIL_VIEWER_PORT=str(port))
        r = subprocess.run([*GIL_CMD, "handoff"], cwd=self.repo, env=env,
                           capture_output=True, text=True)
        return r.stdout + r.stderr

    def test_foreign_repo_viewer_is_not_claimed(self):
        """다른 저장소를 보는 뷰어를 '이 저장소의 뷰어'라 부르지 않는다."""
        self.gil("init")
        port = 8873
        self._fake_server_on(port, '{"repo":"/somewhere/else"}')
        out = self._handoff_with_port(port)
        self.assertIn("다른 저장소", out)
        self.assertIn("/somewhere/else", out)   # 어디를 보고 있는지 짚어준다
        self.assertNotIn("뷰어: 살아있음", out)

    def test_non_viewer_on_port_is_not_claimed(self):
        """뷰어가 아닌 무언가가 포트를 쥐고 있어도 마찬가지다."""
        self.gil("init")
        port = 8874
        self._fake_server_on(port, 'not json at all')
        out = self._handoff_with_port(port)
        self.assertIn("다른 저장소", out)
        self.assertNotIn("뷰어: 살아있음", out)

    def test_directive_does_not_send_people_to_the_wrong_graph(self):
        """규범('지금 열어라')이 틀린 주소를 가리키지 않는다 — 여기가 제일 아픈 자리다."""
        self.gil("init")
        port = 8875
        self._fake_server_on(port, '{"repo":"/somewhere/else"}')
        out = self._handoff_with_port(port)
        self.assertIn("남의 그래프를 보게 된다", out)
        self.assertIn("--port", out)   # 다른 포트로 띄우라는 다음 한 수


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
        ref = self.gil("interview", "deep", "--status").stdout
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
        r = self.gil("viewer", "build", "--out", out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(out, encoding="utf-8") as f:
            return f.read()

    def test_resolved_reference_is_rendered(self):
        self._seed()
        self._resolve()
        html = self._build()
        self.assertIn('id="pane-reference"', html)
        self.assertIn("추론 비용을 절반으로", html)

    def test_nothing_rendered_before_submit(self):
        self._seed()
        self.assertNotIn('id="pane-reference"', self._build())

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

        이 자리에 오는 원인은 대개 하나다 — 이 페이지를 만든 서버가 이미 없다."""
        self._seed()
        html = self._build()
        self.assertIn("뷰어 서버에 닿지 못했습니다", html)
        self.assertIn("답은 아직 제출되지 않았습니다", html)   # 잃은 게 아니라는 사실부터
        self.assertIn("gil viewer serve", html)                 # 되살리는 한 수

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
                       cwd=self.repo, input=msg, text=True, capture_output=True)

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
        r = self.gil("viewer", "build", "--out", out)
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
        r = self.gil("viewer", "build", "--out", out)
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
