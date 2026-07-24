# Ariadne / gil 🧵

> **A methodology and toolchain that lets LLM agents conquer complex problems the way git conquered history — as chains of small, reproducible cycles, written directly onto the commit graph.**

**Docs**: [한국어 (README.ko.md)](README.ko.md) · [Deep dive for your AI agent (README.ai.md)](README.ai.md)

---

## 👋 New here? Start in 30 seconds (you don't learn gil — your AI agent does)

gil is a tool your **AI coding agent** (Claude Code, etc.) drives — *you* never have to
learn its commands. You hand your agent one link and it takes over from there.

**To start:** paste this to your AI agent —

> Read https://raw.githubusercontent.com/hyun06000/Ariadne/main/README.ai.md and do what it says.

Your agent **first explains what gil is and asks for your consent**, then installs gil (one
binary, needs only `git`), sets up the workspace, shows you a quick live example, and starts
solving your problem. New to gil? That's fine — the agent walks you through it. **Revisiting
later?** Just tell it *"continue"* — it restores where it left off.

**When is gil worth it?** For problems you want solved *carefully* and want to be able to
retrace later — data analysis, a nasty bug hunt, a research question, a big refactor. gil
keeps the agent's trail of hypotheses, checks, and dead ends as a reproducible map instead
of letting it evaporate when the session ends.

**See it first →** [**Live example: UC Berkeley admissions (Simpson's paradox)**](https://hyun06000.github.io/ariadne-example/)
— an AI agent analyzed a real dataset with gil. The graph shows its first hypothesis
*failing* (a dead leaf), *backtracking*, and reaching the right answer by splitting the
problem into small steps. This is what gil leaves behind. ([source repo](https://github.com/hyun06000/ariadne-example))

**Prerequisites:** `git`, and an AI coding agent. That's it.

<sub>Curious how it works under the hood? Read on. But you don't need any of this to use it.</sub>

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

gil **v3 is released** — the current `latest` is a v3.0.x build (v3.0.7 at the time of writing), and v3 *is* the `main` branch.
The old folder-based v2 is preserved on the `legacy` / `legacy-main` branches; `gil migrate`
converts a v2 history into the v3 commit graph. The spec lives in
[project/gil-v3-redesign/SPEC.md](project/gil-v3-redesign/SPEC.md).

License: [MIT](LICENSE)
