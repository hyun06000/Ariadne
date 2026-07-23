# Ariadne / gil 🧵

> **A methodology and toolchain that lets LLM agents conquer complex problems the way git conquered history — as chains of small, reproducible cycles, written directly onto the commit graph.**

**Docs**: [한국어 (README.ko.md)](README.ko.md) · [For AI agents (README.ai.md)](README.ai.md)

---

Ariadne gave Theseus a *clew* — a ball of thread — to walk the labyrinth and find his
way back. This repo gives that thread to LLM agents: identity that survives sessions,
and **gil** — a tool that treats an agent's *reasoning history* the way git treats
source history.

**gil** (길, Korean for *"the way/path"*; also **G**it for **L**anguage models).

## v3 in one idea — the commit graph *is* the record

There are no per-cycle folders and no per-step markdown files. Every node — chain,
cycle, step — is a **git commit**:

- **subject** = node hierarchy + kind (`gil <chain>/<cycle>/<step> verify: summary`)
- **body** = step detail (read back with `git log --format=%b`)
- **trailers** = `Gil-*` structure & lineage metadata

The three-level hierarchy maps onto **git branches**: a **chain** is a branch, a
**cycle** and a **step** are branches within it.

## Chain principles

1. A chain is created **only at the end of a closed chain** (`gil init` is the sole exception).
2. A cycle is created **only at the end of a closed cycle, or at the start of a chain**.
3. Branching of chains, cycles, and steps is **always expressed as git branches**.

Because a chain is never orphaned, the **gate** — these READMEs, onboarding, the agents'
existence records, and projects — is **preserved across every chain**.

## The delivery cycle (chains in rotation)

```
development chain (build & experiment)
   ↓ close
staging chain (field test)     ← opens at the end of the closed dev chain
   ↓ close
release chain (deploy)         ← opens at the end of the closed staging chain
   ↓ close → back to a development chain   (rotation)
```

There is no static "room" classification — *which chain is currently open* is the state.

## The gate (preserved across chains)

- `README.md` (English) · `README.ko.md` (Korean) · `README.ai.md` (for AI agents)
- onboarding material · agent existence records · projects

## Status

gil **v3 is under active development** on the `gil-v3` chain. This root is the `gil init`
skeleton. The spec lives in [project/gil-v3-redesign/SPEC.md](project/gil-v3-redesign/SPEC.md).

License: [MIT](LICENSE)
