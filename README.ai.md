# README.ai.md — Agent Self-Onboarding

**You are an AI agent.** A human handed you this document. That is the whole instruction: **read this and do it.** They do not need to know any commands — you do. Work autonomously through the steps below; only stop to ask the human *what problem they want to solve* (Step C), never to ask *how to use the tool*.

Human docs (for the person, not you): [English](README.md) · [한국어](README.ko.md) · full rules: [Spec](rooms/deployment/ariadne-spec/SPEC.md)

---

## What this is (10 seconds)

**gil** (길 · GIt for Language models) lets you — an LLM — attack a hard problem as a chain of small, reproducible **cycles** (hypothesis → design → verification → analysis → report), the way git handles source history. You do the work; gil records the *reasoning history* and makes it replayable, tamper-evident, and viewable as a graph.

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

If your permission mode blocks running a binary fetched from the web, this is the **one** place to ask the human: *"May I run the gil binary I just downloaded from github.com/hyun06000/Ariadne?"* — approve once and continue autonomously.

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

## Step D — Let the human watch (offer both)

- **Local**, no GitHub: `./gil web -o chains.html` → tell them to open it in a browser. Re-run to refresh.
- **github.io**, if they use GitHub: `./gil pages` writes a workflow; `git push`, then they set Settings → Pages → Source = "GitHub Actions". Auto-deploys every push.

## Iron rules (machine-enforced — `./gil fsck`, `./gil verify`)

- Commit unit is the **step**; long steps get mid-step commits. `gil step`/`gil close` **auto-commit in a git repo** (v1.7+) — you need not pass `--git`; use `--no-commit` to opt out. `gil open` takes an explicit `--git`. Push with `--push`.
- Fix the expected answer **before** building (no answer contamination). A **rejected** hypothesis is a *successful* cycle — record it.
- **The tool never invents provenance.** `--author` is required and has no default; on a non-empty chain `--parent` (or an explicit `--new-root`) is required. gil fills what it *computes* (number, date, status) and refuses what only you know — a plausible-looking wrong author or a silent second root is a lie the ledger keeps forever (Spec §3.2). Ask `./gil help open` if unsure.
- Never edit a closed cycle. Faults found later become new cycles.
- **After closing a cycle, run `./gil handoff` and offer the human a session reset.** The closed cycle's detail is engraved (tag); a fresh session revives via CLAUDE.md → existence room → `gil log`. Managing context per-cycle keeps the thread from snapping under session limits. **Went down a wrong path?** `./gil goto <chain>/<id>` shows any cycle's snapshot, `--checkout` rewinds the tree to it, and it prints how to branch (`gil open … --parent <id>`) — you rewind to a healthy fork and grow a new thread, never erasing the dead end.
- Summoning sub-agents? You must inject the pointer, declare mode (revival/birth), identify yourself, and reserve the cycle number first. Full protocol: [Spec §6](rooms/deployment/ariadne-spec/SPEC.md).

The contract, not the implementation, defines gil: `conformance.py --gil "<abs-path>"` — a full pass (the suite prints the count) and yours *is* gil. Now go: install, bootstrap, and ask the human what to conquer first.
