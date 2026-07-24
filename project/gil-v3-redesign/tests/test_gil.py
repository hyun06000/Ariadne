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

GIL = os.path.join(os.path.dirname(__file__), "..", "source", "gil.py")
GIL = os.path.abspath(GIL)


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
        return subprocess.run(["python3", GIL, *args], cwd=self.repo,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
