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
        """gil 명령 실행. 반환: CompletedProcess(returncode, stdout, stderr).

        GIL_NO_VIEWER: gil init 이 관전 서버(뷰어)를 백그라운드로 띄우는 것을 억제한다 —
        테스트가 포트를 점유하거나 프로세스를 남기지 않도록 격리한다."""
        env = dict(os.environ, GIL_NO_VIEWER="1")
        return subprocess.run([*GIL_CMD, *args], cwd=self.repo,
                              capture_output=True, text=True, env=env)

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
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "h")  # 안 닫음
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
                     "--parent", "c001")
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
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "h1")  # s2
        self.gil("step", "c/c001", "--kind", "verify", "--title", "v1")      # s3
        self.gil("step", "c/c001", "--kind", "analyze", "--title", "벽")     # s4 = 미종결 잎
        self.gil("step", "c/c001", "--kind", "hypothesis", "--title", "h2", "--to", "s1")  # 형제 분기
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

    def test_init_viewer_suppressed_by_env(self):
        """GIL_NO_VIEWER 면 관전 서버를 띄우지 않는다(테스트·CI 격리). init 은 정상."""
        r = self.gil("init", "--name", "aria")  # gil() 헬퍼가 GIL_NO_VIEWER=1 주입
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("뷰어", r.stdout)

    def test_init_survives_missing_viewer(self):
        """뷰어 바이너리를 못 찾아도 init 은 깨지지 않고 수동 안내만 낸다."""
        # 억제 훅을 끄고, gilviewer 를 찾을 수 없는 최소 PATH 로 실행한다.
        env = dict(os.environ, PATH="/usr/bin:/bin")
        env.pop("GIL_NO_VIEWER", None)
        env.pop("GIL_VIEWER", None)
        r = subprocess.run([*GIL_CMD, "init", "--name", "aria"], cwd=self.repo,
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("STATE", r.stdout)
        # 뷰어를 못 찾으면 수동 안내를 낸다(못 찾음 또는 이미 관전 중 — 포트 상태 무관하게 init 은 산다).
        self.assertIn("뷰어", r.stdout)

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
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--title", "H")
        self.gil("step", "gh/c001", "--kind", "verify", "--title", "V")
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
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--title", "HA")
        self.gil("step", "gh/c001", "--kind", "analyze", "--title", "AA")
        self.gil("step", "gh/c001", "--kind", "fail", "--to", "s1", "--title", "죽은 잎")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--to", "s1", "--title", "HB")
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
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--title", "가설A")
        self.gil("step", "gh/c001", "--kind", "analyze", "--outcome", "backtrack", "--to", "s1", "--title", "벽")
        self.gil("step", "gh/c001", "--kind", "hypothesis", "--to", "s1", "--title", "가설B")
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
        self.assertRegex(out.stderr, r"c001-seed .*→ success")
        self.assertRegex(out.stderr, r"c003-quiet .*→ success")   # verdict 없음+closed
        self.assertRegex(out.stderr, r"c001-wall .*→ fail")       # rejected
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
