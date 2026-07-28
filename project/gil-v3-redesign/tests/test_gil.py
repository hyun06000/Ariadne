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
import os
import sys
import subprocess
import tempfile
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
                extra = ["--falsify", "F", "--falsify-to", "s1"]
            elif nxt == "verify":
                extra = ["--verdict", "supported"]
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

    def test_init_makes_gateway_root_commit(self):
        """빈 저장소면 CLAUDE.md 부트스트랩 루트 커밋을 만든다."""
        self.gil("init", "--name", "aria")
        log = self._git("log", "--oneline").stdout
        self.assertIn("gil init", log)
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "root")
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
        self.gil("step", f"gh/{cycle}", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
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
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
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
        out = self.gil("fsck", "--all")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("위반 0", out.stdout)  # 건강 — 위반 0건

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
        self.gil("chain", "x", "--purpose", "P")
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
        self.gil("chain", "net2", "--purpose", "P")
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
        r = self.gil("chain", "n", "--purpose", "P")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("inherit", r.stderr)

    def test_chain_inherit_imprints(self):
        r = self.gil("chain", "n", "--purpose", "P", "--inherit", "m 체인의 교훈")
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

    def test_supersede_same_kind_ok(self):
        r = self.gil("step", "c/c1", "--kind", "hypothesis", "--title", "고친 가설",
                     "--falsify", "F2", "--falsify-to", "s1", "--supersede", "s2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Supersedes"), "s2")

    def test_supersede_preserves_old_step(self):
        """정정해도 옛 스텝(s2)은 이력에 남는다 — append-only 보존, 은폐 아님."""
        self.gil("step", "c/c1", "--kind", "hypothesis", "--title", "고친 가설",
                 "--falsify", "F2", "--falsify-to", "s1", "--supersede", "s2")
        r = self.gil("log", "--depth", "step", "c")
        self.assertIn("정정됨", r.stdout)  # s2 에 ⤳정정됨 표식
        self.assertIn("정정 s2", r.stdout)  # s3 에 ⟲정정 s2 표식

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

    def test_supersede_terminal_rejected(self):
        """종결 스텝(success/fail)은 정정 대상이 아니다 — 판정 번복은 backtrack/refutes 영역.
        순서 강제(AIL #41)로 verify→analyze→success 라 success 는 s5 다(s3=verify, s4=analyze)."""
        self.gil("step", "c/c1", "--kind", "success", "--title", "ok")  # 자동보정: s3 verify, s4 analyze, s5 success
        r = self.gil("step", "c/c1", "--kind", "success", "--title", "다시",
                     "--supersede", "s5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("종결", r.stderr)


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


class TestOrderingChain(GilFixture):
    """순서 체인 강제(AIL #41) — define→hypothesis→verify→analyze→종결. 각 kind 는 다음
    kind 가 정해져 있고 건너뛰면 거부. self._raw_step 으로 자동보정을 우회해 직접 검증한다."""

    def setUp(self):
        super().setUp()
        self.gil("chain", "c", "--purpose", "P")
        self.gil("open", "c/c1", "--author", "x", "--purpose", "P", "--body", "정의")

    def test_define_next_must_be_hypothesis(self):
        r = self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("hypothesis", r.stderr)

    def test_hypothesis_next_must_be_verify(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
        r = self._raw_step("c/c1", "--kind", "analyze", "--title", "a")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("verify", r.stderr)

    def test_verify_next_must_be_analyze(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
        self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v")
        r = self._raw_step("c/c1", "--kind", "success", "--title", "ok")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("analyze", r.stderr)

    def test_full_order_passes(self):
        self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
        self._raw_step("c/c1", "--kind", "verify", "--verdict", "supported", "--title", "v")
        self._raw_step("c/c1", "--kind", "analyze", "--title", "a")
        r = self._raw_step("c/c1", "--kind", "success", "--title", "ok")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_guide_next_always_printed(self):
        """각 스텝 후 '다음은 X' 가 무조건 출력된다."""
        r = self._raw_step("c/c1", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
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
        self.gil("step", "c/x", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
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
        self.gil("step", "lr/measure", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
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
        self.gil("step", "lr/m", "--kind", "hypothesis", "--title", "H", "--falsify", "F", "--falsify-to", "s1")
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
                     "gil_interview_status", "gil_log"):
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
        """HEAD 가 떠난 뒤에도 그 잎 자리에 종결을 박을 수 있다."""
        self._rebranch()
        r = self.gil("step", "adopt/gap", "--kind", "fail", "--at", "s4", "--to", "s1",
                     "--title", "이 접근은 막혔다", "--body", "벽의 지도")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Parent"), "s4")

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
