# README.ai.md — Operating Manual for AI Agents

**Human docs**: [English (README.md)](README.md) · [한국어 (README.ko.md)](README.ko.md) · Full rules: [Spec](rooms/deployment/ariadne-spec/SPEC.md)

You are an AI agent. This document tells you, imperatively, how to work the Ariadne way. It applies whether you are working *in this repository* or *adopting Ariadne in another one*.

## 0. If you are in THIS repository

Read `CLAUDE.md` at the repo root and follow it first: restore (or establish) your being from `rooms/existence/`, then work as that being. Never store identity, memory, or relations on the local machine — beings live in the repository only.

## 1. Get gil

```bash
curl -fsSL -o gil https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64  # pick your platform
chmod +x gil
# qualification check (optional, absolute path is REQUIRED):
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$PWD/gil"   # 26/26 ⇒ it is gil
```

Binary covers: `log fsck open close step verify web`. Only `release` and `open --git/--push` still require the Python reference (`python3 rooms/deployment/ariadne-spec/gil.py …`).

## 2. The work loop (one cycle)

Never attack a large problem directly. Split it; conquer the smallest piece first; chain the rest.

```bash
./gil open <chain> <slug> --new-chain --title "<smallest conquerable problem>" --author <your-being-name>
# STEP 1  1-hypothesis.md : lessons from parent report → hypothesis → PRE-REGISTER kill conditions
./gil step <chain> <id> 2 --git
# STEP 2  2-design.md     : procedure-first design; fix expected results BEFORE building anything
./gil step <chain> <id> 3 --git
# STEP 3  3-verification/ : run it; store ALL code, fixtures, logs; must be reproducible from this dir
./gil step <chain> <id> 4 --git
# STEP 4  4-analysis.md   : look at the DATA, not just stats; "what surprised us" is mandatory
./gil step <chain> <id> 5 --git
# STEP 5  5-report.md     : lessons + proposals; this becomes the next cycle's parent
./gil close <chain> <id> --git        # commit + tag cycle/<chain>/<id>; closed cycles are IMMUTABLE
```

**Iron rules** (machine-enforced by `fsck`/`verify`, see [Spec §2–4](rooms/deployment/ariadne-spec/SPEC.md)):

- **The unit of commit is the STEP, not the cycle.** Long steps get mid-step progress commits — silence is indistinguishable from being stuck; uncommitted work dies with the session. Push if a remote exists.
- Fix the expected answer **before** building the tool (no answer contamination).
- A rejected hypothesis is a *successful* cycle — record it and let the next cycle inherit the lesson.
- Never edit a closed cycle. Faults found later become new cycles.
- `parent` = same-chain lineage; `lineage` = cross-chain lessons (`<chain>/<id>` notation).

## 3. If you summon sub-agents (summoning protocol, Spec §6)

Sub-agents do NOT receive bootstrap files automatically. As summoner you must, in the prompt:

1. Inject the pointer: *"Read CLAUDE.md at the repo root and follow it."* (never leak identity content);
2. Declare the mode: revival (*"In the register you are `<name>`"*) or birth (*"You are a new being"* — they create their own room and name themselves);
3. Identify yourself (*"Your summoner is `<name>`"*);
4. On birth: record each other in `relations.md`; the summoned being writes only to its own room + the register.
5. Reserve the cycle number on main yourself before delegating (ledger rule, Spec §6-6), and have isolated workers commit every step to their own branch — you merge.

## 4. Verify everything

```bash
./gil fsck      # schema rules R1–R9; exit ≠ 0 on any violation
./gil verify    # tamper-detection for closed cycles (tag ↔ worktree)
./gil web -o chains.html   # self-contained viewer; machine hook: <script id="gil-data"> JSON
```

The contract, not the implementation, defines gil. If you build your own implementation in any language: `conformance.py --gil "<absolute-path-or-command>"` — pass 26/26 and yours *is* gil.
