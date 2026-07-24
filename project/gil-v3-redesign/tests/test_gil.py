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

    def gil(self, *args):
        """gil 명령 실행. 반환: CompletedProcess(returncode, stdout, stderr)."""
        return subprocess.run([*GIL_CMD, *args], cwd=self.repo,
                              capture_output=True, text=True)

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

    def test_open_requires_purpose(self):
        r = self.gil("open", "c/c001", "--author", "clew")
        self.assertNotEqual(r.returncode, 0)

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
        r = self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "가설")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Step"), "s2")
        self.assertEqual(self.trailer("HEAD", "Gil-Kind"), "hypothesis")

    def test_analyze_requires_outcome(self):
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "P")
        r = self.gil("step", "c/c001", "--kind", "analyze")
        self.assertNotEqual(r.returncode, 0)

    def test_close_requires_live_leaf(self):
        """산 잎(analyze/success) 없으면 close 거부."""
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "P")
        r = self.gil("close", "c/c001")
        self.assertNotEqual(r.returncode, 0)

    def test_full_cycle(self):
        """open → hypothesis → analyze success → close 전 주기."""
        self.gil("open", "c/c001", "--author", "clew", "--purpose", "P")
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "h")
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
        self.gil("step", "c/c001", "--kind", "analyze", "--outcome", "success",
                 "--title", "s")
        self.gil("close", "c/c001")
        # chain-close 커밋 모사
        self._git("commit", "-q", "--allow-empty", "-F", "-",
                  ) if False else None
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-F", "-"],
                       cwd=self.repo, text=True,
                       input="gil c 체인 닫힘\n\nGil-Chain: c\nGil-Kind: chain-close\n")
        r = self.gil("open", "c/c002", "--author", "a", "--purpose", "P")
        self.assertNotEqual(r.returncode, 0, "닫힌 부모 체인 사이클은 거부돼야")


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
        self.gil("step", "appr/c001", "--kind", "verify", "--title", "검증")
        self.gil("step", "appr/c001", "--kind", "pending", "--title", "승인 요청")
        r = self.gil("handoff")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("사이클 c001", r.stdout)
        self.assertIn("PENDING", r.stdout)

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
        self.gil("step", "viewer/c001", "--kind", "verify", "--title", "검사")
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

    def test_no_args_prints_usage(self):
        """인자 없는 gil 은 침묵이 아니라 명령 표면(프롬프트)을 낸다."""
        r = self.gil()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gil init", r.stdout)
        self.assertIn("gil handoff", r.stdout)


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
        self.gil("step", "greenhouse/c001", "--kind", "hypothesis", "--title", "가설 A")
        self.gil("step", "greenhouse/c001", "--kind", "verify", "--title", "검증 A")
        self.gil("step", "greenhouse/c001", "--kind", "analyze",
                 "--outcome", "backtrack", "--to", "s1", "--title", "벽")
        r = self.gil("step", "greenhouse/c001", "--kind", "hypothesis", "--to", "s1", "--title", "가설 B")
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
        self.gil("step", "greenhouse/c001", "--kind", "hypothesis", "--title", "가설 A")
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
        self.gil("step", f"gh/{cycle}", "--kind", "hypothesis", "--title", "H")
        self.gil("step", f"gh/{cycle}", "--kind", "verify", "--title", "V")
        self.gil("step", f"gh/{cycle}", "--kind", "pending", "--title", "승인 요청")

    def test_step_after_pending_rejected(self):
        self._to_pending()
        r = self.gil("step", "gh/c001", "--kind", "analyze", "--outcome", "success", "--title", "자율승인")
        self.assertNotEqual(r.returncode, 0, "pending 뒤 analyze 는 거부돼야 한다")
        self.assertIn("pending", r.stderr + r.stdout)

    def test_approve_makes_live_leaf(self):
        self._to_pending()
        r = self.gil("approve", "gh/c001", "--title", "승인")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Outcome"), "success")
        self.assertEqual(self.trailer("HEAD", "Gil-Approval"), "approved")
        # 승인 후 close 가능(산 잎).
        self.assertEqual(self.gil("close", "gh/c001", "--verdict", "supported").returncode, 0)

    def test_reject_makes_dead_leaf(self):
        self._to_pending()
        r = self.gil("reject", "gh/c001", "--to", "s1", "--title", "기각")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trailer("HEAD", "Gil-Outcome"), "backtrack")
        self.assertEqual(self.trailer("HEAD", "Gil-Approval"), "rejected")

    def test_approve_without_pending_rejected(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "gh", "--purpose", "P")
        self.gil("open", "gh/c001", "--author", "clew", "--purpose", "Q")
        r = self.gil("approve", "gh/c001")
        self.assertNotEqual(r.returncode, 0, "pending 없는데 approve 는 거부")


class TestLiveTip(GilFixture):
    """handoff 팁 선정: 다중 브랜치에서 죽은 잎을 팁으로 잡지 않는다 (2026-07-24)."""

    def test_tip_skips_dead_leaf(self):
        self.gil("init", "--name", "clew")
        self.gil("chain", "gh", "--purpose", "P")
        self.gil("open", "gh/c001", "--author", "clew", "--purpose", "Q")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--title", "가설A")
        self.gil("step", "gh/c001", "--kind", "analyze", "--outcome", "backtrack", "--to", "s1", "--title", "벽")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--to", "s1", "--title", "가설B")
        out = self.gil("handoff").stdout
        # 팁은 죽은 잎(s3 backtrack)이 아니라 산 형제 가지(s4 hypothesis).
        self.assertIn("팁: s4 [hypothesis]", out)
        self.assertNotIn("팁: s3", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
