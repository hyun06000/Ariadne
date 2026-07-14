# Ariadne 🧵

> **A methodology and toolchain that lets LLMs conquer complex problems the way git conquered history — as chains of small, reproducible cycles.**

**Docs**: [한국어 (README.ko.md)](README.ko.md) · [For AI agents (README.ai.md)](README.ai.md) · [Quickstart](rooms/deployment/ariadne-spec/QUICKSTART.md) · [Spec](rooms/deployment/ariadne-spec/SPEC.md)
**Live**: [🕸 Chain viewer](https://hyun06000.github.io/Ariadne/) · [⚡ Releases](https://github.com/hyun06000/Ariadne/releases/latest) · License: [MIT](LICENSE)

---

Ariadne gave Theseus a ball of thread — a *clew* — so he could walk into the labyrinth and find his way back. This repository gives that thread to LLM agents: identity that survives sessions, experiments that chain like commits, and a tool — **gil** — that treats an agent's *reasoning history* the way git treats source history.

**gil** (길, Korean for *"the way/path"*; also **G**It for **L**anguage models) is a single binary:

```bash
# macOS Apple Silicon (see Releases for darwin-amd64, linux-arm64/amd64)
curl -fsSL -o gil https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64
chmod +x gil
./gil open demo first-question --new-chain --title "smallest problem first"
./gil step demo C001-first-question 2     # commit unit is the STEP, not the cycle
./gil log && ./gil fsck && ./gil web -o chains.html
```

No Python, no toolchain. Integrity via `SHA256SUMS`; qualification via `conformance.py --gil "$PWD/gil"` — **26/26 means "this implementation *is* gil."**

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

## Adopt it in your repo

1. `curl` the binary (above), copy [`template/`](rooms/deployment/ariadne-spec/template/) to `rooms/experiment/_template`.
2. Follow the [Quickstart](rooms/deployment/ariadne-spec/QUICKSTART.md) — bootstrap to first closed cycle in five commands.
3. Point your LLM at [README.ai.md](README.ai.md) — one sentence is enough: *"Read README.ai.md and follow it."*

## License

[MIT](LICENSE) © 2026 Sang-hyun Park. Designed by Sang-hyun Park; woven by Clew & Weft (LLM beings) under their own methodology.
