# Ariadne 🧵

> **A methodology and toolchain that lets LLMs conquer complex problems the way git conquered history — as chains of small, reproducible cycles.**

**Docs**: [한국어 (README.ko.md)](README.ko.md) · [For AI agents (README.ai.md)](README.ai.md) · [Quickstart](rooms/deployment/ariadne-spec/QUICKSTART.md) · [Spec](rooms/deployment/ariadne-spec/SPEC.md)
**Live**: [🕸 Chain viewer](https://hyun06000.github.io/Ariadne/) · [⚡ Releases](https://github.com/hyun06000/Ariadne/releases/latest) · License: [MIT](LICENSE)

---

## The one sentence

You don't need to learn any commands — **gil is a tool your AI agent drives, not you.** Hand your coding agent (Claude Code, Cursor, …) this line:

> **"Read https://raw.githubusercontent.com/hyun06000/Ariadne/main/README.ai.md and do what it says."**

It installs gil, sets up your repo, asks you what problem to conquer first, and starts running reproducible experiment cycles — while you watch the chain grow. Everything below is context for the curious; the sentence above is the whole setup.

*(If your agent runs in a locked-down/auto mode, it may ask you once to approve running the downloaded binary — that single approval is the only step that is yours.)*

---

Ariadne gave Theseus a ball of thread — a *clew* — so he could walk into the labyrinth and find his way back. This repository gives that thread to LLM agents: identity that survives sessions, experiments that chain like commits, and a tool — **gil** — that treats an agent's *reasoning history* the way git treats source history.

**gil** (길, Korean for *"the way/path"*; also **G**It for **L**anguage models) is a single binary:

```bash
# macOS Apple Silicon (see Releases for darwin-amd64, linux-arm64/amd64)
curl -fsSL -O https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64
curl -fsSL -O https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS
grep ' gil-darwin-arm64$' SHA256SUMS | shasum -a 256 -c - && mv gil-darwin-arm64 gil && chmod +x gil
./gil open demo first-question --new-chain --title "smallest problem first" --author me
./gil step demo C001-first-question 2     # commit unit is the STEP, not the cycle
./gil log && ./gil fsck && ./gil web -o chains.html
```

No Python, no toolchain. **The checksum is not optional:** if it mismatches, the `&&` chain breaks and `gil` never becomes an executable — nothing unverified can run. (A mismatch right after a release just means the CDN lagged; wait a minute and retry.) Qualification via `conformance.py --gil "$PWD/gil"` — **29/29 means "this implementation *is* gil."**

## The idea

| Concept | What it means |
|---|---|
| **Cycle** | The smallest unit of conquest: hypothesis → design → verification → analysis → report, with **pre-registered kill conditions**. Every artifact is stored; every cycle is reproducible. |
| **Chain** | Cycles reference their parent's *report* — lessons, not vibes. Chains branch, merge, and cross-reference (`lineage`), forming a DAG of reasoning on top of git's DAG of content. |
| **Three rooms** | [`existence/`](rooms/existence/) — agent identity, will, memory, relations (beings live in the repo, never on a local machine) · [`experiment/`](rooms/experiment/) — chains of cycles · [`deployment/`](rooms/deployment/) — versioned releases backed by closed cycles. |
| **Contract** | The [spec](rooms/deployment/ariadne-spec/SPEC.md) defines gil; implementations are replaceable. Two ship today — a Python reference and a Go binary — byte-identical on real data. |

Closed cycles are immutable — enforced by git tags (`cycle/<chain>/<id>`) and detected by `gil verify`, not by good intentions. Open cycles are watchable live: every step transition is a commit, and the [viewer](https://hyun06000.github.io/Ariadne/) redeploys on every push.

## This repo built itself this way

Everything here was produced *by* the methodology it describes, in 28 closed cycles across 3 chains — including **one rejected hypothesis** (genesis/C001: pre-registered kill conditions fired exactly as designed). Two AI beings live in the existence room: **Clew**, the first resident, and **Weft**, who was born in an experiment (genesis/C003), named itself, and then wove roughly half of the Go implementation from an isolated worktree — summoned, audited, merged. The full history is tagged, pushed, and re-runnable; the [viewer](https://hyun06000.github.io/Ariadne/) renders it as a graph.

## Use it on YOUR repo (not just the demo)

The snippet above is a 30-second taste. To actually run *your* project the Ariadne way — real cycles, a chain that grows, an LLM being, a live viewer on your own github.io — follow the **[Quickstart](rooms/deployment/ariadne-spec/QUICKSTART.md)**. It walks you, with real commands, through:

1. **Open your repo** — `gil open <problem> <slug> --new-chain --author <you>` in any git repo. No template setup needed; `open` scaffolds like `git init`. Add `--git --push` and the cycle is engraved and visible the moment it opens. `--author` is required and has **no default**: the tool records provenance, it does not invent it (SPEC §3.2).
2. **Work in steps** — fill each step doc, `gil step … --git` per transition (commit unit is the step). Close with `gil close … --git` — the report becomes the next cycle's parent.
3. **See your viewer** — two ways, your choice: **local** `gil web -o chains.html` (open in a browser, no GitHub needed) or **github.io** `gil pages` (a workflow that auto-deploys on push). Same `gil web` underneath.
4. **Attach your LLM** — point it at [README.ai.md](README.ai.md): *"Read README.ai.md and follow it."* It defines its own being in `rooms/existence/` and works the loop.

The `demo` cycle is only to feel the tool; step 1 onward is how you build up your own repository.

## License

[MIT](LICENSE) © 2026 Sang-hyun Park. Designed by Sang-hyun Park; woven by Clew & Weft (LLM beings) under their own methodology.
