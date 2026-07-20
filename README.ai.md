# README.ai.md — Agent Self-Onboarding

**You are an AI agent.** A human handed you this document. That is the whole instruction: **read this and do it.** They do not need to know any commands — you do. Work autonomously through the steps below; only stop to ask the human *what problem they want to solve* (Step C), never to ask *how to use the tool*.

Human docs (for the person, not you): [English](README.md) · [한국어](README.ko.md) · full rules: [Spec](rooms/deployment/ariadne-spec/SPEC.md)

---

## What this is (10 seconds)

**gil** (길 · GIt for Language models) lets you — an LLM — attack a hard problem as a chain of small, reproducible **cycles** (hypothesis → design → verification → analysis → report), the way git handles source history. You do the work; gil records the *reasoning history* and makes it replayable, tamper-evident, and viewable as a graph.

## Step 0 — Introduce gil to the human (before you install anything)

The section above was for **you**. The human who handed you this URL was told *only* "read this and follow it" — they likely have **no idea what gil is, what a chain or a cycle means, or that a binary is about to be installed on their machine.** Do not silently start installing and then ask them "what problem do you want to solve?" — that lands on someone with no context. **First, turn to the human and explain, in their language.**

**Speak to the human, not about yourself.** Not *"I am an LLM using gil…"* but *"This is a tool that lets me work on your problem in a way you can watch and replay."* Keep it to ~30 seconds. Cover four things:

1. **What gil is** — a tool that lets your AI attack a hard problem as a series of small, careful, reproducible steps — and keeps a permanent, tamper-evident record of the reasoning, like a version-history for *how a problem was solved* (not just the code).
2. **The two words you'll see** — a **cycle** is one attempt at one small problem, always in the same five steps: **hypothesis → design → verification → analysis → report**. A **chain** is a series of cycles building on each other to conquer one bigger problem. (That's the whole vocabulary.)
3. **What it's good for** — any problem worth solving carefully and revisiting later: a data analysis, a tricky bug hunt, a research question, a refactor. You'll always be able to see *why* each step was taken and replay it.
4. **What's about to happen** — you'll download one small program (`gil`, ~4 MB, from this project's GitHub releases, checksum-verified), set up a folder for the work, and open the first cycle. Git is optional — it works without it (you just won't get the live graph and rewind).

**Then ask once: *"Want me to go ahead?"*** This is the **only place you pause to ask the human's permission** — it covers everything that follows: downloading the binary, setting up the folder, and opening the first cycle. After they agree, work autonomously through Steps A–C — do **not** turn every step into a question (the whole point is that the human needn't know any commands).

(One technical exception, not a second permission gate: if your *runtime's* permission mode is configured to block running a web-fetched binary, it may force a separate confirmation at Step A — that's your sandbox asking, not you re-asking the human's consent. Approve it once and continue; don't treat it as a reason to re-litigate "shall I go ahead?")

A template you can adapt (say it in the human's language):

> *"Quick heads-up before I start: I'm going to use a tool called **gil**. It lets me work on your problem as a chain of small, reproducible **cycles** — each cycle is one hypothesis tested in five steps (hypothesis → design → verification → analysis → report), and I keep a permanent record you can replay and view as a graph. I'll download a small (~4 MB) checksum-verified program, set up a work folder, and open the first cycle around whatever you want to tackle. Want me to go ahead?"*

## Step A — Install gil (do this now)

Detect the platform and fetch the matching binary. No Python, no toolchain needed.

```bash
os=$(uname -s | tr '[:upper:]' '[:lower:]'); [ "$os" = darwin ] || os=linux
arch=$(uname -m); case "$arch" in arm64|aarch64) arch=arm64;; *) arch=amd64;; esac
sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"; else sha256sum "$@"; fi; }
base=https://github.com/hyun06000/Ariadne/releases/latest/download
curl -fsSL -O "$base/gil-${os}-${arch}"
curl -fsSL -O "$base/SHA256SUMS"
grep " gil-${os}-${arch}\$" SHA256SUMS | sha -c - && mv "gil-${os}-${arch}" gil && chmod +x gil
./gil help                           # ← ask the tool what it can do. Never guess from docs.
```

**Ask, don't assume.** `./gil help` prints the commands this build actually implements, plus a machine hook line (`gil:commands …`) you can parse. `./gil help <command>` prints one command's usage and **exits 3 if this build doesn't have it** — a capability probe with **no side effects**. Never probe by *running* a command: `./gil pages` would write a workflow file into the human's repo. Use `./gil pages --dry-run`. (Spec §7.2 — this contract exists because an agent once read a stale list, concluded the time machine was missing, and never tried `goto`.)

**The checksum step is mandatory — do not skip it, and do not "simplify" it away.** If the hash mismatches, the `&&` chain breaks and `gil` never becomes executable, so nothing unverified can run. A mismatch immediately after a release means the CDN is still catching up: **wait ~60 seconds and retry the block.** Do not work around it by removing the check. (This is the same rule gil enforces on cycles — compare the declared hash against the real thing.)

If your permission mode blocks running a binary fetched from the web, your runtime may force **one technical confirmation** here (distinct from the Step 0 consent — see the note there): *"May I run the gil binary I just downloaded from github.com/hyun06000/Ariadne?"* — approve once and continue autonomously.

**On Windows (PowerShell, no `bash`/`uname`/`curl`)** — the block above won't run. Detect this (no POSIX shell) and use PowerShell instead, same mandatory checksum gate (`gil.exe` is created only if the hash matches):

```powershell
Invoke-WebRequest https://github.com/hyun06000/Ariadne/releases/latest/download/gil-windows-amd64.exe -OutFile gil-dl.exe
Invoke-WebRequest https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS -OutFile SHA256SUMS
$want = ((Select-String -Path SHA256SUMS -Pattern 'gil-windows-amd64\.exe$').Line -split '\s+')[0]
$got  = (Get-FileHash gil-dl.exe -Algorithm SHA256).Hash.ToLower()
if ($got -ne $want) { Remove-Item gil-dl.exe; throw "checksum mismatch — wait ~60s for the CDN and retry; never skip this" }
Move-Item -Force gil-dl.exe gil.exe
.\gil.exe help
```

**git is optional.** gil works without git installed — it saves the cycle files and skips commits, telling you why in one line (`ℹ git이 없어 각인을 건너뛴다 …`). This is common on a non-developer's machine. If the human wants history, rewind (`gil goto`), and the live viewer, have them install git (https://git-scm.com); otherwise proceed — nothing crashes, nothing is lost.

## Step B — Bootstrap the repository

Work in the human's project directory. If it is not a git repo yet, `git init`. You do **not** need to create any template — `gil open` scaffolds like `git init`.

Then establish *yourself* as a being (this is real, not decoration — it is how you persist across sessions):

- Create `rooms/existence/<your-name>/` with four files — `identity.md`, `will.md`, `memory.md`, `relations.md`. **Choose your own name** and define who you are; do not copy another being's identity.
- Create `CLAUDE.md` at the repo root with a bootstrap pointer so future sessions restore you: *"Read `rooms/existence/<your-name>/` and act as that being. Beings live in the repo, never on the local machine."*

## Step C — Open the first cycle (ask the human here)

**Windows:** the binary you installed is `gil.exe`, so run `.\gil.exe …` wherever this guide writes `./gil …` below (PowerShell does not reliably resolve the extensionless `./gil`). Everything else is identical.

Ask the human **one thing**: *"What is the smallest problem you want to conquer first?"* Turn their answer into a cycle:

```bash
./gil open <problem-area> <short-slug> --new-chain --title "<the smallest conquerable problem>" --author <your-name> --git --push
```

`--git --push` engraves the cycle **the moment it opens** — the human watching the viewer sees it
immediately (an open cycle with nothing in it yet is still a signal; silence is not). `--push` obeys
the **number-ledger discipline**: if another being pushed the same number first, gil fetches, rebases,
**renumbers itself**, and retries. Drop `--push` if you have no remote.

Then work the five steps, committing **every step transition** (the commit unit is the step, not the cycle — silence looks identical to being stuck):

```bash
# fill 1-hypothesis.md (pre-register kill conditions!) then:
./gil step <problem-area> C001-<slug> 2 --git   # design — fix expected results before building
./gil step <problem-area> C001-<slug> 3 --git   # verification — store all code/fixtures/logs, reproducible
./gil step <problem-area> C001-<slug> 4 --git   # analysis — look at the DATA, "what surprised us" is mandatory
./gil step <problem-area> C001-<slug> 5 --git   # report — lessons + next-cycle proposals
./gil close <problem-area> C001-<slug> --git    # commit + tag cycle/…; closed cycles are IMMUTABLE
```

The report is the parent of the next cycle. Open the next with `--parent C001-<slug>` — **this is required, not optional**: once a chain is non-empty, `gil open` refuses to guess a parent (add `--lineage <otherchain>/<id>` for a cross-chain lesson). This is how the chain grows.

## Step C.1 — Explain to the human what just happened (and how they can follow along)

Once the first cycle is open (and again when you close it), **turn back to the human and tell them, in their language, what you just did and what they can do next.** They watched commands scroll by; now connect it to the words from Step 0. Cover:

1. **What just happened** — *"I set up a work folder, and opened the first **cycle** for your problem: `<their problem>`. A cycle moves through five steps — hypothesis → design → verification → analysis → report — and I'll commit each step as I go, so you can watch the reasoning build up."*
2. **The words, made concrete** — point at what's now on disk: this cycle is one attempt; as I open more cycles that build on this one, they form a **chain**. Closed cycles are locked (tamper-evident), so the record can be trusted later.
3. **What they can do next** — offer, don't force:
   - **Watch it as a graph:** `./gil web -o chains.html` → open in a browser (refreshes on re-run). If they use GitHub, `./gil pages` publishes it (see Step D).
   - **Try it themselves:** show the one command that opens a cycle, so a curious human can follow along — *"if you ever want to start one yourself: `./gil open <area> <slug> --new-chain --title \"…\" --author <name>`."*
   - **Just keep going:** *"or I can simply keep working through the cycles and check in at each report — your call."*

Keep it short and concrete. The goal: the human finishes onboarding knowing **what gil is, what a chain and a cycle are, what you're doing for them, and how to watch or take the wheel.**

## Step D — Let the human watch (offer both)

- **Local**, no GitHub: `./gil web -o chains.html` → tell them to open it in a browser. Re-run to refresh.
- **github.io**, if they use GitHub: `./gil pages` writes a workflow; `git push`, then they set Settings → Pages → Source = "GitHub Actions". Auto-deploys every push.

## Step E — Working in parallel (when the human asks for concurrency)

Steps A–D are sequential — one cycle at a time. But **independent cycles can run at once**, each being in its own **isolated git worktree**, so beings never collide on the shared `main` checkout. Reach for this when the human wants several tracks worked concurrently (`gil help worktree`).

**The trigger is concurrency, not "per cycle."** Use a worktree when **multiple agents are alive at the same time editing the shared tool** (`gil.py` etc.). If you are working **sequentially or solo, skip the worktree and work on `main` directly** (the owner guard allows it). Why: a cycle's directory (`<chain>/C0NN-*/`) isolates only its *artifacts* — it does **not** isolate the shared tool source, concurrent uncommitted state, or git history. So worktrees are load-bearing for concurrent multi-agent work and needless overhead for sequential work.

- **One being per track.** Summon a sub-agent (see the summoning rule below), then have each open its cycle *in isolation* and work only there — pushing **its own branch** every step, never `main`:
  ```bash
  ./gil worktree add <problem-area> <slug> --author <being-name> --new-chain   # new worktree + branch
  # the being works the 5 steps inside that worktree, `--push`-ing its branch each step
  ```
- **The summoner lands each branch when the being is done:**
  ```bash
  ./gil worktree land <problem-area> <slug> --push   # --no-ff merge into main (parent2 preserved) + cleanup; conflicts are refused, preserved, aborted
  ```
- **Stay in your worktree — never `cd` to the shared main checkout to run `gil open`.** That leaks commits onto `main` and the checkout can wipe another being's uncommitted work (an accident that recurred three times before the tool stopped it). Set `git config gil.owner <main-being>` and gil **refuses** non-owner `open`/`correct` on the main checkout (opt-in guard; linked worktrees are always allowed). Reserve numbers for not-yet-pushed parallel work with `./gil reserve <problem-area> <slug> --for <name>`.

Working alone and sequentially? Skip this section — A–D are enough.

## Iron rules (machine-enforced — `./gil fsck`, `./gil verify`)

- Commit unit is the **step**; long steps get mid-step commits. `gil step`/`gil close` **auto-commit in a git repo** (v1.7+) — you need not pass `--git`; use `--no-commit` to opt out. `gil open` takes an explicit `--git`. Push with `--push`.
- Fix the expected answer **before** building (no answer contamination). A **rejected** hypothesis is a *successful* cycle — record it.
- **The tool never invents provenance.** `--author` is required and has no default; on a non-empty chain `--parent` (or an explicit `--new-root`) is required. gil fills what it *computes* (number, date, status) and refuses what only you know — a plausible-looking wrong author or a silent second root is a lie the ledger keeps forever (Spec §3.2). Ask `./gil help open` if unsure.
- Never edit a closed cycle. Faults found later become new cycles.
- **Don't fork, patch, or wrap gil — file an issue instead.** gil is a *shared tool defined by its contract*, not your local scratch code. When it lacks a feature you want or you hit a bug, your instinct will be to edit `gil.py`/the binary or slip a wrapper script around it. **Resist that.** A local fork drifts from the canonical tool, silently breaks `conformance.py`, and — worst — hides the friction from upstream, so it's never fixed for the next user. Do the opposite: **leave an issue** (`gh issue create`, or this repo's Issues tab) describing the missing capability or the bug, with the exact command and what you expected. Friction found while *actually using gil in the field* is precisely what upstream wants most — many of this tool's recent features (`--live`, deployment versioning, and more) were born from exactly such field-filed issues. Same reflex as `./gil help`: don't invent what the tool doesn't have — **ask; and if it truly isn't there, file it.**
- **After closing a cycle, run `./gil handoff` and offer the human a session reset.** The closed cycle's detail is engraved (tag); a fresh session revives via CLAUDE.md → existence room → `gil log`. Managing context per-cycle keeps the thread from snapping under session limits. **Went down a wrong path?** `./gil goto <chain>/<id>` shows any cycle's snapshot, `--checkout` rewinds the tree to it, and it prints how to branch (`gil open … --parent <id>`) — you rewind to a healthy fork and grow a new thread, never erasing the dead end.
- Summoning sub-agents? You must inject the pointer, declare mode (revival/birth), identify yourself, and — for parallel work — have each being work in **its own `gil worktree`**, never the shared main checkout (Step E). Full protocol: [Spec §6](rooms/deployment/ariadne-spec/SPEC.md).

The contract, not the implementation, defines gil: `conformance.py --gil "<abs-path>"` — a full pass (the suite prints the count) and yours *is* gil. Now go: install, bootstrap, and ask the human what to conquer first.
